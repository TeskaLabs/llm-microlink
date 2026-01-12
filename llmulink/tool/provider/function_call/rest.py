import json
import typing
import logging

import pydantic
import aiohttp
import jsonata

import asab.contextvars

from .rest_datamodel import RestRequest, RestResponse


L = logging.getLogger(__name__)


class FunctionCallRest(pydantic.BaseModel):
	"""
	A REST function call configuration loaded from YAML.

	Example YAML:
		function_call:
		  type: rest
		  request:
		    method: GET
		    path: /{{tenant}}/rest/api
	"""
	type: typing.Literal['rest']
	request: RestRequest
	response: dict[int|typing.Literal['_'], RestResponse]

	def model_post_init(self, __context: typing.Any) -> None:
		if self.request.path.startswith('$'):
			self._request_path_expr = jsonata.Jsonata(self.request.path[1:])
		else:
			self._request_path_expr = None

		self._request_headers = JsonataDictCompiler(self.request.headers)
		self._request_query = JsonataDictCompiler(self.request.query)

		if self.request.body is not None and self.request.body.startswith('$'):
			self._request_body_expr = jsonata.Jsonata(self.request.body[1:])
		else:
			self._request_body_expr = None


	async def __call__(self, function_call) -> typing.AsyncGenerator[str, None]:
		yield "validating"
		arguments = json.loads(function_call.arguments)

		jsonata_params = {
			"tenant": asab.contextvars.Tenant.get(),
			"parameters": arguments,
			"arguments": arguments,
		}

		base_url = "http://127.0.0.1:8898"

		headers = self._request_headers.evaluate(jsonata_params)
		query = self._request_query.evaluate(jsonata_params)

		path = self.request.path if self._request_path_expr is None else self._request_path_expr.evaluate(jsonata_params)
		if not path.startswith('/'):
			path = '/' + path

		body = self.request.body if self._request_body_expr is None else self._request_body_expr.evaluate(jsonata_params)
		if isinstance(body, dict):
			body = json.dumps(body)

		L.log(asab.LOG_NOTICE, "Call", struct_data={"base_url": base_url, "path": path, "method": self.request.method})

		async with aiohttp.ClientSession(base_url=base_url, headers=headers) as session:
			async with session.request(self.request.method, url=path, params=query, data=body) as response:
				resp = self.response.get(response.status)
				if resp is None:
					resp = self.response.get('_')

				if resp is None:
					function_call.error = True
					function_call.content = "Tool execution failed with the status code: " + str(response.status)
					return

				if response.content_type == "application/json":
					jsonata_params["response"] = await response.json()
				else:
					jsonata_params["response"] = await response.text()

				if resp._content_expr is not None:
					function_call.content = resp._content_expr.evaluate(jsonata_params)
				else:
					function_call.content = resp.content

				function_call.error = resp.error

		yield "completed"


class JsonataDictCompiler:
	
	def __init__(self, dict: typing.Dict[str, str]):
		self._dict = {
			k: self._compile_expr(v) for k, v in dict.items()
		}

	def _compile_expr(self, expr: str) -> jsonata.Jsonata:
		if expr.startswith('$'):
			return jsonata.Jsonata(expr[1:])
		else:
			return expr

	def evaluate(self, params: dict) -> dict:
		return {
			k:v for k, v in (
				(k, self._evaluate_expr(v, params)) for k, v in self._dict.items()
			) if v is not None
		}

	def _evaluate_expr(self, expr: str, params: dict) -> str:
		if isinstance(expr, str):
			return expr
		if expr is None:
			return None

		v = expr.evaluate(params)
		if isinstance(v, bool):
			return str(v).lower()
		else:
			return v
