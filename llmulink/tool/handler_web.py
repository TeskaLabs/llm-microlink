import uuid
import json
import logging

import asab.web.rest
import aiohttp.web


L = logging.getLogger(__name__)


class ToolWebHandler():

	def __init__(self, app):
		self.ToolService = app.ToolService
		app.WebContainer.WebApp.router.add_put(r"/{tenant}/function_call", self.function_call)


	async def function_call(self, request):
		json_data = await request.json()
		name = json_data.get("name")
		arguments = json_data.get("arguments")

		from ..llm.datamodel import FunctionCall
		function_call = FunctionCall(
			call_id=str(uuid.uuid4()),
			name=name,
			arguments=json.dumps(arguments),
			status='in_progress',
		)

		async for _ in self.ToolService.execute(function_call):
			print("...")
			pass

		return asab.web.rest.json_response(
			request,
			data={
				"result": "OK",
				"data": function_call.to_dict(),
			}
		)
