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


	def get_tools(self) -> list[FunctionCallTool]:
		ret = list()
		for provider in self.Providers:
			try:
				tools = provider.get_tools()
				ret.extend(tools)
			except Exception as e:
				L.exception("Error getting tools from provider", struct_data={"provider": provider.Id})
		return ret


	async def execute(self, function_call) -> typing.AsyncGenerator[typing.Any, None]:
		tool = None
		for provider in self.Providers:
			tool = provider.get_tool(function_call)
			if tool is not None:
				break
		
		if tool is None:
			function_call.content = "Tool not found"
			function_call.error = True
			function_call.status = 'completed'
			yield
			return

		try:
			async for result in tool.function_call(function_call):
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
