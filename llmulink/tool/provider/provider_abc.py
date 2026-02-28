import abc
import uuid
import logging
import typing

from ..tool import FunctionCallTool


L = logging.getLogger(__name__)

class ToolProviderABC(abc.ABC):

	def __init__(self, tool_service):
		self.ToolService = tool_service
		self.Id = str(uuid.uuid4())


	async def initialize(self):
		pass


	@abc.abstractmethod
	async def locate_tool(self, tool_name) -> FunctionCallTool:
		pass
