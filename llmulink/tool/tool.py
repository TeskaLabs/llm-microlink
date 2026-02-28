import typing
import pydantic

class FunctionCallTool(pydantic.BaseModel):
	"""A tool for the conversation."""
	name: str
	description: str
	parameters: dict
	title: str = None
	function_call: typing.Callable = None
	init_call: typing.Callable = None
