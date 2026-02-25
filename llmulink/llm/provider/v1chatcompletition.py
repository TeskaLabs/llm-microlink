import json
import asyncio
import logging

import aiohttp

import asab

from ..models import measure_tokens_vllm
from ..datamodel import Conversation, Exchange, AssistentMessage, AssistentReasoning, FunctionCall
from .provider_abc import LLMChatProviderABC


L = logging.getLogger(__name__)


class LLMChatProviderV1ChatCompletition(LLMChatProviderABC):
	'''
	OpenAI API v1 chat completions adapter (old).

	https://platform.openai.com/docs/api-reference/chat/create
	'''

	def __init__(self, service, *, url, **kwargs):
		super().__init__(service, url=url)
		self.APIKey = kwargs.get('api_key', None)
		self.Semaphore = asyncio.Semaphore(2)

	def prepare_headers(self):
		headers = {
			'Content-Type': 'application/json',
		}
		if self.APIKey is not None:
			headers['Authorization'] = f"Bearer {self.APIKey}"
		return headers


	async def chat_request(self, conversation: Conversation, exchange: Exchange) -> None:
		# Add system message if instructions are provided
		messages = [{
			"role": "system",
			"content": "\n".join(conversation.instructions),
		}]

		for exch in conversation.exchanges:
			for item in exch.items:
				match item.__class__.__name__:

					case "UserMessage":
						messages.append({
							"role": "user",
							"content": item.content,
						})

					case "AssistentMessage":
						messages.append({
							"role": "assistant",
							"content": item.content,
						})

					case "AssistentReasoning":
						# Reasoning is not directly supported in chat completions API
						# Skip for now
						pass

					case "FunctionCall":
						# OpenAI chat completions uses tool_calls format
						messages.append({
							"role": "assistant",
							"content": None,
							"tool_calls": [{
								"id": item.call_id,
								"type": "function",
								"function": {
									"name": item.name,
									"arguments": item.arguments,
								},
							}],
						})

						messages.append({
							"role": "tool",
							"tool_call_id": item.call_id,
							"content": item.content,
						})


		model = conversation.get_model()
		assert model is not None

		data = {
			"model": model,
			"messages": messages,
			"stream": True,
			"stream_options": {
				"include_usage": True,
			},
		}

		tools = self._build_tools(conversation)
		if len(tools) > 0:
			data["tools"] = tools

		L.log(asab.LOG_NOTICE, "Sending request to LLM", struct_data={"conversation_id": conversation.conversation_id, "model": model, "provider": self.URL})

		async with aiohttp.ClientSession(headers=self.prepare_headers()) as session:

			# vLLM tokenize endpoint
			await measure_tokens_vllm(self.LLMChatService, session, self.URL, data, conversation)

			async with session.post(self.URL + "v1/chat/completions", json=data, timeout=60*30) as response:
				if response.status != 200:
					text = await response.text()
					L.error(
						"Error when sending request to LLM chat provider",
						struct_data={"status": response.status, "text": text}
					)
					return

				assert response.content_type == "text/event-stream"

				async for line in response.content:
					line = line.decode("utf-8").rstrip('\n\r')

					if line == '':
						continue

					if line.startswith('data: '):
						data_str = line[6:]
						if data_str == '[DONE]':
							# Stream finished, finalize any pending items
							await self._finalize_stream(conversation, exchange)
							break
						try:
							data = json.loads(data_str)
							await self._on_llm_chunk(conversation, exchange, data)
						except json.JSONDecodeError as e:
							L.warning("Invalid JSON in SSE response", struct_data={"line": line, "error": str(e)})


	async def _on_llm_chunk(self, conversation: Conversation, exchange: Exchange, chunk: dict) -> None:
		'''
		Process a streaming chunk from the chat completions API.

		Chunk format:
		{
			"id": "chatcmpl-...",
			"object": "chat.completion.chunk",
			"created": 1234567890,
			"model": "gpt-4",
			"choices": [{
				"index": 0,
				"delta": {
					"role": "assistant",
					"content": "Hello",
					"tool_calls": [...]
				},
				"finish_reason": null | "stop" | "tool_calls"
			}]
		}
		'''
		choices = chunk.get('choices', [])
		if not choices:
			return

		choice = choices[0]
		delta = choice.get('delta', {})

		finish_reason = choice.get('finish_reason')

		if delta.get('role', None) == 'assistant' and delta.get('content', None) == '':
			# This is some kind of initialization message, ignore it
			return

		# Handle text content delta
		content = delta.get('content', None)
		if content is not None:
			await self._ensure_reasoning_completed(conversation, exchange)

			item = exchange.get_last_assistant_message('in_progress')
			if item is None:
				item = AssistentMessage(
					role='assistant',
					content='',
					status='in_progress',
				)
				exchange.items.append(item)
				await self.LLMChatService.send_update(conversation, {
					"type": "item.appended",
					"item": item.to_dict(),
				})
			item.content += content
			await self.LLMChatService.send_update(conversation, {
				"type": "item.delta",
				"key": item.key,
				"delta": content,
			})

		# Handle reasoning delta
		reasoning = delta.get('reasoning', None)
		if reasoning is not None:
			item = exchange.get_last_item('reasoning', status='in_progress')
			if item is None:
				item = AssistentReasoning(
					content='',
					status='in_progress',
				)
				exchange.items.append(item)
				await self.LLMChatService.send_update(conversation, {
					"type": "item.appended",
					"item": item.to_dict(),
				})
			assert isinstance(item, AssistentReasoning)
			assert item.status == 'in_progress'
			item.content += reasoning
			await self.LLMChatService.send_update(conversation, {
				"type": "item.delta",
				"key": item.key,
				"delta": reasoning,
			})

		# Handle tool calls delta
		tool_calls = delta.get('tool_calls', None)
		if tool_calls is not None:
			await self._ensure_reasoning_completed(conversation, exchange)

			for tool_call_delta in tool_calls:
				tool_index = tool_call_delta.get('index')
				assert tool_index is not None
				
				tool_calls_filtered = [*filter(lambda item: isinstance(item, FunctionCall) and item.index == tool_index, exchange.items)]
				if len(tool_calls_filtered) == 0:
					# New tool call
					tool_call_id = tool_call_delta.get('id', '')
					function_info = tool_call_delta.get('function', {})
					function_name = function_info.get('name', '')
					arguments = function_info.get('arguments', '')

					item = FunctionCall(
						call_id=tool_call_id,
						name=function_name,
						arguments=arguments,
						status='in_progress',
						index=tool_index,
					)
					exchange.items.append(item)
					await self.LLMChatService.send_update(conversation, {
						"type": "item.appended",
						"item": item.to_dict(),
					})

				elif len(tool_calls_filtered) == 1:
					# Update existing tool call with more arguments
					item = tool_calls_filtered[0]
					function_info = tool_call_delta.get('function', {})
					if 'arguments' in function_info:
						if finish_reason is None:
							item.arguments += function_info['arguments']
						else:
							# This is from testing of zai-org/GLM-4.7-FP8
							# It seems that the arguments are not streamed, but rather sent all at once in the finish reason message
							item.arguments = function_info['arguments']
						await self.LLMChatService.send_update(conversation, {
							"type": "item.arguments.delta",
							"key": item.key,
							"arguments": function_info['arguments'],
						})

				else:
					raise RuntimeError("Multiple tool calls with the same ID found")

		# Handle finish reason
		if finish_reason is not None:
			await self._ensure_reasoning_completed(conversation, exchange)

			if finish_reason == 'stop':
				# Normal completion
				item = exchange.get_last_assistant_message(status='in_progress')
				if item is not None:
					item.status = 'completed'
					await self.LLMChatService.send_update(conversation, {
						"type": "item.updated",
						"item": item.to_dict(),
					})

			elif finish_reason == 'tool_calls':
				# Tool calls completion - finalize all tool calls
				tool_index = choice.get('index')
				assert tool_index is not None
				
				tool_calls_filtered = [*filter(lambda item: isinstance(item, FunctionCall) and item.index == tool_index, exchange.items)]
				assert len(tool_calls_filtered) == 1
				item = tool_calls_filtered[0]
				item.status = 'completed'
				await self.LLMChatService.send_update(conversation, {
					"type": "item.updated",
					"item": item.to_dict(),
				})
				await self.LLMChatService.create_function_call(conversation, exchange, item)

			else:
				L.warning("Unknown finish reason", struct_data={"finish_reason": finish_reason})


	async def _ensure_reasoning_completed(self, conversation: Conversation, exchange: Exchange) -> None:
		'''
		Ensure that the reasoning item is completed.
		'''
		reasoning = exchange.get_last_item('reasoning', status='in_progress')
		if reasoning is not None:
			reasoning.status = 'completed'
			await self.LLMChatService.send_update(conversation, {
				"type": "item.updated", 
				"item": reasoning.to_dict(),
			})

	async def _finalize_stream(self, conversation: Conversation, exchange: Exchange) -> None:
		'''
		Finalize any pending items when the stream ends.
		'''
		# Finalize assistant message if still in progress
		message = exchange.get_last_assistant_message(status='in_progress')
		if message is not None:
			message.status = 'completed'
			await self.LLMChatService.send_update(conversation, {
				"type": "item.updated",
				"item": message.to_dict(),
			})

		# Finalize any tool calls still in progress
		for item in filter(lambda item: isinstance(item, FunctionCall), exchange.items):
			if item.status != 'in_progress':
				continue
			item.status = 'completed'
			await self.LLMChatService.send_update(conversation, {
				"type": "item.updated",
				"item": item.to_dict(),
			})
			await self.LLMChatService.create_function_call(conversation, exchange, item)


	def _build_tools(self, conversation: Conversation) -> list[dict]:
		'''
		Output format:
			"tools": [
				{
					"type": "function",
					"function": {
						"name": "ping",
						"description": "Invoke a command-line ping tool with provided target host or service, return the textual result of the ping.",
						"parameters": {
							"type": "object",
							"properties": {
								"target": {
									"type": "string",
									"description": "The target host or service to ping"
								}
							},
							"required": ["target"]
						}
					}
				}
			]
		}
		'''
		tools = []
		for tool_name, tool in conversation.tools.items():
			tools.append({
				"type": "function",
				"function": {
					"name": tool_name,
					"description": tool.description,
					"parameters": tool.parameters,
				}
			})
		return tools
