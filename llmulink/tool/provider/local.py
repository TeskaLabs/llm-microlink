import logging
import typing

from .provider_abc import ToolProviderABC
from .function_call.ping import fuction_call_ping
from ..tool import FunctionCallTool

#

L = logging.getLogger(__name__)

#
class LocalToolProvider(ToolProviderABC):
		

	def get_tools(self) -> list[typing.Any]:	
		tools = [
			FunctionCallTool(
				name = "ping",
				title = "Ping a host",
				description = "Ping a host and return the result",
				parameters = {
					"type": "object",
					"properties": {
						"target": {
							"type": "string",
							"description": "The fully qualified hostname or IP address to ping"
						}
					},
					"required": ["host"]
				},
				function_call = fuction_call_ping
			)
		]
		return tools


	def get_tool(self, function_call):
		for tool in self.get_tools():
			if tool.name == function_call.name:
				return tool
		return None
