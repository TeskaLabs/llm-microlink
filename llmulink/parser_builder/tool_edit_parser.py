import os
import json
import logging

from ..tool.tool import FunctionCallTool
from .tool_compile_parser import execute

L = logging.getLogger(__name__)


async def fuction_call_edit_parser(conversation, function_call) -> None:
	"""
	Edit a parser in Go language.
	"""

	yield "validating"

	try:
		arguments = json.loads(function_call.arguments)
	except Exception as e:
		L.exception("Exception occurred while parsing arguments: '{}'".format(function_call.arguments), struct_data={"error": str(e)})
		function_call.content = "Exception occurred while parsing arguments."
		function_call.error = True
		return

	edit = arguments.get("edit")
	if edit is None:
		function_call.content = "Parameter 'edit' is required"
		function_call.error = True
		return

	assert conversation.sandbox is not None, "Sandbox is not initialized"
	trgdir = os.path.join(conversation.sandbox.Path, "parser")


edit_parser_tool = FunctionCallTool(
		name = "edit_parser",
		title = "Edit a parser in Go language",
		description = """Edits the parser source file (`parse.go`) using SEARCH/REPLACE blocks and recompiles it.
Returns the compiler stdout and stderr.

The `edit` parameter contains one or more SEARCH/REPLACE blocks formatted as:

⏪
<exact lines from the current source to match>
⏸️
<replacement lines>
⏩

Rules:
- Each delimiter (⏪ ⏸️ ⏩) must be on its own line.
- The SEARCH section must exactly match the existing source, including whitespace and comments.
- Only the first occurrence of each SEARCH match is replaced.
- Include enough surrounding context in the SEARCH section to ensure a unique match.
- If the SEARCH section does not match any part of the source, the edit will fail with an error.

Example:

⏪
func Parse(log []byte) map[string]interface{} {
	output := map[string]interface{}{}
	return output
}
⏸️
func Parse(log []byte) map[string]interface{} {
	output := map[string]interface{}{}
	output["message"] = string(log)
	return output
}
⏩""",
		parameters = {
			"type": "object",
			"properties": {
				"edit": {
					"type": "string",
					"description": "SEARCH/REPLACE blocks, one or more"
				},
			},
			"required": [
				"edit"
			]
		},
		function_call = fuction_call_edit_parser,
		# init_call = init_call_compile_parser,
	)
