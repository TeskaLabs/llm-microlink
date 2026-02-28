import logging
import typing

import yaml
import pydantic

from .provider_abc import ToolProviderABC
from ..tool import FunctionCallTool
from .function_call.rest import FunctionCallRest

#

L = logging.getLogger(__name__)

#

class ZookeeperToolProvider(ToolProviderABC):

	def __init__(self, tool_service):
		super().__init__(tool_service)

		self.ToolsBasePath = "/asab/llm/tool"
		self.Cache = {}


	async def locate_tool(self, tool_name) -> FunctionCallTool:
		tool = self.Cache.get(tool_name)
		if tool is not None:
			return tool

		tool_path = f"{self.ToolsBasePath}/{tool_name}"

		tool_data, _ = await self.ToolService.App.ZkContainer.ZooKeeper.get(tool_path)
		if tool_data is None:
			return

		try:
			tool_definition = ToolDefinition.from_yaml(tool_data)
		except pydantic.ValidationError as e:
			L.warning("Invalid tool definition", struct_data={"error": str(e), "tool_path": tool_path})
			return
		except yaml.YAMLError as e:
			L.warning("Error parsing tool YAML", struct_data={"error": str(e), "tool_path": tool_path})
			return
		except Exception as e:
			L.warning("Error loading tool definition", struct_data={"error": str(e), "tool_path": tool_path})
			return

		function_call_type = tool_definition.function_call.get('type')
		function_call = None
		match function_call_type:
			case 'rest':
				function_call = FunctionCallRest(
					**tool_definition.function_call
				)
			case _:
				L.warning("Unknown function call type", struct_data={"function_call_type": function_call_type})
				return

		tool = FunctionCallTool(
			name=tool_definition.name,
			description=tool_definition.description,
			parameters=tool_definition.parameters.model_dump(),
			title=tool_definition.title,
			function_call=function_call,
		)
		self.Cache[tool_name] = tool
		return tool


class ToolDefine(pydantic.BaseModel):
	"""The 'define' block identifying the tool."""
	type: typing.Literal['llm/tool']
	name: str


class ParameterProperty(pydantic.BaseModel):
	"""A single parameter property definition."""
	type: str
	description: str = ''


class ToolParameters(pydantic.BaseModel):
	"""Parameters schema for the tool."""
	type: typing.Literal['object'] = 'object'
	properties: dict[str, ParameterProperty] = pydantic.Field(default_factory=dict)
	required: list[str] = pydantic.Field(default_factory=list)


class ToolDefinition(pydantic.BaseModel):
	"""
	A tool definition loaded from YAML.
	
	Example YAML:
		define:
		  type: llm/tool
		  name: read_note
		
		title: Reading a markdown note
		
		description: >
		  Read and return the full content of a Markdown note.
		
		parameters:
		  type: object
		  properties:
		    path:
		      type: string
		      description: The path to the markdown note.
		  required:
		  - path

		function_call: {...}
	"""
	define: ToolDefine
	description: str
	title: str = None
	function_call: dict
	parameters: ToolParameters = pydantic.Field(default_factory=ToolParameters)


	@classmethod
	def from_yaml(cls, yaml_content: str | bytes) -> 'ToolDefinition':
		"""Load a ToolDefinition from YAML string or bytes."""
		data = yaml.safe_load(yaml_content)
		return cls.model_validate(data)

	@property
	def name(self) -> str:
		"""Shortcut to access the tool name."""
		return self.define.name
