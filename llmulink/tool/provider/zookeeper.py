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

		self.Tools = []
		
		tool_service.App.PubSub.subscribe("ZooKeeperContainer.state/CONNECTED!", self.discover)
		tool_service.App.PubSub.subscribe("application.tick/10!", self.discover)


	async def initialize(self):
		await self.discover("initialize")


	def get_tools(self) -> list[typing.Any]:
		return self.Tools


	def get_tool(self, function_call):
		for tool in self.get_tools():
			if tool.name == function_call.name:
				return tool
		return None


	async def discover(self, event_name, zkcontainer = None):
		if zkcontainer is not None and zkcontainer != self.ToolService.App.ZkContainer:
			# Not for me
			return

		zk = self.ToolService.App.ZkContainer.ZooKeeper

		if not zk.Client.connected:
			return

		toolsbasepath = "/asab/llm/tool"

		toolslist =  await zk.get_children(toolsbasepath)
		if toolslist is None:
			return

		tools = []
		for item in toolslist:
			tool = await self._discover_tool(zk, f"{toolsbasepath}/{item}")
			if tool is not None:
				tools.append(tool)

		self.Tools = tools


	async def _discover_tool(self, zk, tool_path):
		tool_data, _ = await zk.get(tool_path)
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

		return FunctionCallTool(
			name=tool_definition.name,
			description=tool_definition.description,
			parameters=tool_definition.parameters.model_dump(),
			title=tool_definition.title,
			function_call=function_call,
		)


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
