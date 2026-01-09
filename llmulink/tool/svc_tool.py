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

		self.Tools = {}

		self.Providers = [LocalToolProvider(self)]

		if 'zookeeper' in asab.Config.sections():
			from .provider.zookeeper import ZookeeperToolProvider
			self.Providers.append(ZookeeperToolProvider(self))


	def get_tools(self) -> list[FunctionCallTool]:
		return list(self.Tools.values())


	async def execute(self, function_call) -> typing.AsyncGenerator[typing.Any, None]:
		provider = None
		for provider_id, tool_name in self.Tools.keys():
			if tool_name == function_call.name:
				for p in self.Providers:
					if p.Id == provider_id:
						provider = p
						break
				break
		
		if provider is None:
			L.warning("Tool not found", struct_data={"name": function_call.name})
			function_call.content = "Tool not found"
			function_call.error = True
			yield
			return

		async for result in provider.execute(function_call):
			yield result


	async def initialize(self, app):
		async with asyncio.TaskGroup() as tg:
			for provider in self.Providers:
				tg.create_task(provider.initialize())


	def _register(self, provider: ToolProviderABC, tools: list[FunctionCallTool]):
		'''
		Register (update) a list of tools provided by a provider.
		'''
		for tool in tools:
			if (provider.Id,tool.name) in self.Tools:
				continue
			for _, existing_tool_name in self.Tools.keys():
				if existing_tool_name == tool.name:
					L.warning("Tool with the sama name is already registered by other tool provider", struct_data={"provider": provider.Id, "tool": tool.name})
					continue
			self.Tools[(provider.Id,tool.name)] = tool

		# Remove tools that are no longer provided by the provider
		to_remove = []
		tools_names = {t.name for t in tools}
		for provider_id, tool_name in self.Tools.keys():
			if provider_id != provider.Id:
				continue
			if tool_name not in tools_names:
				to_remove.append((provider_id, tool_name))
		for provider_id, tool_name in to_remove:
			del self.Tools[(provider_id, tool_name)]
