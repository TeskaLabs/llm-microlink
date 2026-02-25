import typing
import asyncio
import logging

import asab

from .tool import FunctionCallTool
from .provider.provider_abc import ToolProviderABC
from .provider.local import LocalToolProvider

#

L = logging.getLogger(__name__)

#

class ToolService(asab.Service):


	def __init__(self, app, service_name="ToolService"):
		super().__init__(app, service_name)

		self.Providers = [LocalToolProvider(self)]

		if 'zookeeper' in asab.Config.sections():
			from .provider.zookeeper import ZookeeperToolProvider
			self.Providers.append(ZookeeperToolProvider(self))


	async def locate_tool(self, name) -> FunctionCallTool:
		for provider in self.Providers:
			tool = await provider.locate_tool(name)
			if tool is not None:
				return tool
		return None


	async def ensure_init(self, conversation):
		uninitialized_tools = set(conversation.tools.keys()) - conversation.tool_initialized
		for tool_name in uninitialized_tools:
			tool = conversation.tools[tool_name]
			if tool.init_call is not None:
				await tool.init_call(self.App, conversation)
			conversation.tool_initialized.add(tool_name)


	async def execute(self, conversation, function_call) -> typing.AsyncGenerator[typing.Any, None]:
		tool = conversation.tools.get(function_call.name)		
		if tool is None:
			function_call.content = "Tool not found"
			function_call.error = True
			function_call.status = 'completed'
			yield
			return

		try:
			async for result in tool.function_call(conversation,function_call):
				yield result
			function_call.status = 'completed'
		except Exception:
			L.exception("Error executing tool", struct_data={"name": function_call.name})
			if len(function_call.content) > 0:
				function_call.content += "\n\n"
			function_call.content += "Tool failed."
			function_call.error = True
			function_call.status = 'completed'
			yield


	async def initialize(self, app):
		async with asyncio.TaskGroup() as tg:
			for provider in self.Providers:
				tg.create_task(provider.initialize())
