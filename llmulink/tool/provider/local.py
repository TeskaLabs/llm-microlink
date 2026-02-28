import logging

from .provider_abc import ToolProviderABC
from .function_call.ping import ping_tool
from ..tool import FunctionCallTool

#

L = logging.getLogger(__name__)

#

class LocalToolProvider(ToolProviderABC):
		

	async def locate_tool(self, tool_name) -> FunctionCallTool:
		match tool_name:

			case "ping":
				return ping_tool

			case "busybox":
				from ...sandbox.tool_busybox import busybox_tool
				return busybox_tool

			case "compile_parser":
				from ...parser_builder.tool_compile_parser import compile_parser_tool
				return compile_parser_tool

			case "edit_parser":
				from ...parser_builder.tool_edit_parser import edit_parser_tool
				return edit_parser_tool

			case "test_parser":
				from ...parser_builder.tool_test_parser import test_parser_tool
				return test_parser_tool

			case _:
				return None
