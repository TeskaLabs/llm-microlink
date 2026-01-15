import typing

import jsonata
import pydantic

class RestRequest(pydantic.BaseModel):
	"""The request configuration for a REST function call."""
	method: str # typing.Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
	path: str
	headers: typing.Dict[str, str] = {}
	query: typing.Dict[str, str] = {}
	body: str | None = None


class RestResponse(pydantic.BaseModel):
	"""The response configuration for a REST function call."""
	content: str = ''
	error: bool = False

	def model_post_init(self, __context: typing.Any) -> None:
		if self.content.startswith('$'):
			self._content_expr = jsonata.Jsonata(self.content[1:])
		else:
			self._content_expr = None