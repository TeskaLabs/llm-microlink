import abc
import uuid
import logging
import typing


L = logging.getLogger(__name__)

class ToolProviderABC(abc.ABC):

	def __init__(self, tool_service):
		self.ToolService = tool_service
		self.Id = str(uuid.uuid4())

	async def initialize(self):
		pass

	@abc.abstractmethod
	def get_tool(self, function_call) -> typing.AsyncGenerator[typing.Any, None]:
		pass
	
	@abc.abstractmethod
	def get_tools(self) -> list[typing.Any]:
		pass
