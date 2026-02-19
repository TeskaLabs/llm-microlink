import re
import uuid
import random
import asyncio
import logging

import asab
import yaml
import jinja2

from .datamodel import Conversation, UserMessage, Exchange, FunctionCall, FunctionCallTool
from .models import get_models

from .provider.v1response import LLMChatProviderV1Response
from .provider.v1messages import LLMChatProviderV1Messages
from .provider.v1chatcompletition import LLMChatProviderV1ChatCompletition

#

L = logging.getLogger(__name__)

#

class LLMRouterService(asab.Service):


	def __init__(self, app, service_name="LLMRouterService"):
		super().__init__(app, service_name)

		self.LibraryService = app.LibraryService

		self.Providers = []
		self.Conversations = dict[str, Conversation]()


	async def initialize(self, app):
		for section in asab.Config.sections():
			if not section.startswith("provider:"):
				continue

			ptype = asab.Config[section].get('type')
			match ptype:
				case 'LLMChatProviderV1Response':
					self.Providers.append(LLMChatProviderV1Response(self, **asab.Config[section]))
				case 'LLMChatProviderV1Messages':
					self.Providers.append(LLMChatProviderV1Messages(self, **asab.Config[section]))
				case 'LLMChatProviderV1ChatCompletition':
					self.Providers.append(LLMChatProviderV1ChatCompletition(self, **asab.Config[section]))
				case 'vllm':
					provider = await self._initialize_vllm(asab.Config[section])
					if provider is not None:
						self.Providers.append(provider)
				case _:
					L.warning("Unknown provider type, skipping", struct_data={"type": ptype})


	async def _initialize_vllm(self, config: dict):
		'''
		vLLM can run a single model.
		We will try to identifty the model and select a proper provider for it.
		'''
		url = config.get('url')
		models = await get_models(url)
		assert len(models) == 1, "vLLM can run a single model"
		model = models[0]
		model_id = model['id']

		match model_id:
			case "arcee-ai/Trinity-Large-Preview-FP8":
				return LLMChatProviderV1ChatCompletition(self, **config)
			case "stepfun-ai/Step-3.5-Flash" | "stepfun-ai/Step-3.5-Flash-FP8":
				return LLMChatProviderV1Response(self, **config)
			case "mistralai/Devstral-2-123B-Instruct-2512":
				return LLMChatProviderV1ChatCompletition(self, **config)
			case "openai/gpt-oss-120b" | "openai/gpt-oss-20b":
				return LLMChatProviderV1Response(self, **config)
			case "MiniMaxAI/MiniMax-M2.5":
				return LLMChatProviderV1ChatCompletition(self, **config)
			case _:
				L.warning("Unknown model, using default LLMChatProviderV1ChatCompletition", struct_data={"model_id": model_id})
				return LLMChatProviderV1ChatCompletition(self, **config)
		

	async def create_conversation(self):
		while True:
			conversation_id = 'conversation-' + uuid.uuid4().hex
			if conversation_id in self.Conversations:
				continue
			break

		L.log(asab.LOG_NOTICE, "New conversation created", struct_data={"conversation_id": conversation_id})

		async with self.LibraryService.open("/AI/Prompts/default.md") as item_io:
			# instructions = yaml.safe_load(item_io.read().decode("utf-8"))
			instructions = item_io.read().decode("utf-8")

		conversation = Conversation(
			conversation_id=conversation_id,
			instructions=[instructions],
			tools=self.App.ToolService.get_tools(),
		)
		self.Conversations[conversation.conversation_id] = conversation
		return conversation


	async def stop_conversation(self, conversation: Conversation) -> None:
		for task in conversation.tasks:
			task.cancel()
		conversation.loop_break = True
		L.log(asab.LOG_NOTICE, "Conversation stopped", struct_data={"conversation_id": conversation.conversation_id})


	def restart_conversation(self, conversation: Conversation, key: str) -> None:
		for i in range(len(conversation.exchanges)):
			if conversation.exchanges[i].items[0].key == key:
				del conversation.exchanges[i:]
				return
		L.warning("Conversation restart failed", struct_data={"conversation_id": conversation.conversation_id, "key": key})
			

	async def update_instructions(self, conversation: Conversation, item: str, params: dict) -> None:
		if item.startswith("/AI/Prompts/"):
			instructions = None
			async with self.LibraryService.open(item) as item_io:
				if item_io is not None:
					instructions = item_io.read().decode("utf-8")

			if instructions is not None:
				conversation.instructions = [jinja2.Template(instructions).render(params)]
			else:
				L.warning("Prompt not found", struct_data={"item": item})

		elif item.startswith("/AI/Skill/"):
			definition = None
			async with self.LibraryService.open(item+"index.yaml") as item_io:
				if item_io is not None:
					definition = yaml.safe_load(item_io.read().decode("utf-8"))
			assert definition is not None, "Index not found"

			conversation.instructions = []
			for instruction in definition['instructions']:
				if instruction.startswith('+'):
					instruction = await self.load_instruction(item, instruction, params)
					if instruction is not None:
						conversation.instructions.append(instruction)
				else:
					conversation.instructions.append(instruction)

			if 'tools' in definition:
				tools = []
				for tool_name, tool_definition in definition['tools'].items():
					tools.append(FunctionCallTool(
						name=tool_name,
						description=tool_definition['description'],
						parameters=tool_definition['parameters'],
						title=tool_definition['title'],
						function_call={}
					))
				conversation.tools = tools

		else:
			L.warning("Unknown item, skipping", struct_data={"item": item})


	async def get_conversation(self, conversation_id, create=False):
		conversation = self.Conversations.get(conversation_id)
		if conversation is None and create:
			conversation = await self.create_conversation(conversation_id)
		return conversation


	async def create_exchange(self, conversation: Conversation, item: UserMessage) -> None:
		new_exchange = Exchange()
		conversation.exchanges.append(new_exchange)

		new_exchange.items.append(item)
		await self.send_update(conversation, {
			"type": "item.appended",
			"item": item.to_dict(),
		})

		await self.schedule_task(conversation, new_exchange, self.task_chat_request)


	async def schedule_task(self, conversation: Conversation, exchange: Exchange, task, *args, **kwargs) -> None:
		t = asyncio.create_task(
			task(conversation, exchange, *args, **kwargs),
			name=f"conversation-{conversation.conversation_id}-task"
		)

		def on_task_done(task):
			conversation.tasks.remove(task)

			if len(conversation.tasks) == 0 and not conversation.loop_break:
				# Initialize a new exchange with LLM
				new_exchange = Exchange()
				conversation.exchanges.append(new_exchange)
				conversation.loop_break = True

				t = asyncio.create_task(
					self.task_chat_request(conversation, new_exchange),
					name=f"conversation-{conversation.conversation_id}-task"
				)
				t.add_done_callback(on_task_done)
				conversation.tasks.append(t)

			asyncio.create_task(self.send_update_tasks(conversation))

		t.add_done_callback(on_task_done)

		conversation.tasks.append(t)
		await self.send_update_tasks(conversation)
		

	async def send_update_tasks(self, conversation: Conversation) -> None:
		await self.send_update(
			conversation,
			{
				"type": "tasks.updated",
				"count": len(conversation.tasks) + (0 if conversation.loop_break else 1),
			}
		)


	async def task_chat_request(self, conversation: Conversation, exchange: Exchange) -> None:
		model_id = conversation.get_model()
		assert model_id is not None, "Model is not set"

		providers = []
		async def collect_models(provider):
			try:
				pmodels = await get_models(provider.URL, provider.prepare_headers())
				for pm in pmodels:
					if pm['id'] == model_id:
						providers.append(provider)
						return
			except Exception as e:
				L.exception("Error collecting models", struct_data={"provider": provider.__class__.__name__})

		async with asyncio.TaskGroup() as tg:
			for provider in self.Providers:
				tg.create_task(collect_models(provider))

		# Find and select a provider for the model
		assert len(providers) > 0, "No provider found for model"
		provider = random.choice(providers)

		async def print_waiting():
			while True:
				await asyncio.sleep(1)
				# TODO: Indicate waiting for a model in the UI
				print("Waiting for a model ...")

		waiting_task = asyncio.create_task(print_waiting())
		try:
			async with provider.Semaphore:
				waiting_task.cancel()
				await provider.chat_request(conversation, exchange)
		finally:
			waiting_task.cancel()
			

	async def get_models(self):
		models = []

		async def collect_models(models, provider):
			try:
				pmodels = await get_models(provider.URL, provider.prepare_headers())
			except Exception as e:
				L.exception("Error collecting models", struct_data={"provider": provider.__class__.__name__})
				return

			if pmodels is not None:
				models.extend(pmodels)

		async with asyncio.TaskGroup() as tg:
			for provider in self.Providers:
				tg.create_task(collect_models(models, provider))

		return models


	async def send_update(self, conversation: Conversation, event: dict):
		async with asyncio.TaskGroup() as tg:
			for monitor in conversation.monitors:
				tg.create_task(monitor(event))


	async def send_full_update(self, conversation: Conversation, monitor):
		items = []
		full_update = {
			"type": "update.full",
			"conversation_id": conversation.conversation_id,
			"created_at": conversation.created_at.isoformat(),
			"items": items,
		}

		for exchange in conversation.exchanges:
			for item in exchange.items:
				match item.__class__:
					case UserMessage:
						items.append(item.to_dict())

		try:
			await monitor(full_update)
		except Exception:
			L.exception("Error sending full update to monitors", struct_data={"conversation_id": conversation.conversation_id})


	async def create_function_call(self, conversation: Conversation, exchange: Exchange, function_call: FunctionCall):
		await self.schedule_task(conversation, exchange, self.task_function_call, function_call)
		

	async def task_function_call(self, conversation: Conversation, exchange: Exchange, function_call: FunctionCall) -> None:
		L.log(asab.LOG_NOTICE, "Calling function ...", struct_data={"name": function_call.name})

		function_call.status = 'executing'
		await self.send_update(conversation, {
			"type": "item.updated",
			"item": function_call.to_dict(),
		})

		try:
			async for _ in self.App.ToolService.execute(function_call):
				await self.send_update(conversation, {
					"type": "item.updated",
					"item": function_call.to_dict(),
				})

		except Exception as e:
			L.exception("Error in function call", struct_data={"name": function_call.name})
			function_call.content = "Generic exception occurred. Try again."
			function_call.error = True

		finally:
			function_call.status = 'finished'
			await self.send_update(conversation, {
				"type": "item.updated",
				"item": function_call.to_dict(),
			})

			# Flag the conversation that is chat requested
			conversation.loop_break = False


	async def load_instruction(self, item: str, instruction: str, params: dict) -> str | None:
		'''
		Load an instruction from a file.
		If the instruction starts with a '+', then it is a sub-instruction.
		'''
		async with self.LibraryService.open(item+instruction[1:]) as item_io:
			if item_io is None:
				return None
			item_content = item_io.read().decode("utf-8")

			lines = []
			for line in item_content.split("\n"):
				if line.startswith('+'):
					instruction = await self.load_instruction(item, line, params)
					if instruction is not None:
						lines.append(instruction)
					else:
						lines.append(line)
				else:
					lines.append(line)

			item_content = jinja2.Template('\n'.join(lines)).render(params)
			return item_content


def normalize_text(text: str) -> str:
	'''
	Normalize the text to be a single line of text.
	All newlines, tabs, and multiple spaces are replaced with a single space.
	Leading and trailing spaces are removed.
	'''
	return re.sub(r'\s+', ' ', text.strip())
