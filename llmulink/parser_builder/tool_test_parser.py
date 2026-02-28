import os
import logging

from ..tool.tool import FunctionCallTool

L = logging.getLogger(__name__)


async def fuction_call_test_parser(conversation, function_call) -> None:
	assert conversation.sandbox is not None, "Sandbox is not initialized"

	for log_file in sorted(os.listdir(os.path.join(conversation.sandbox.Path, "log"))):
		if not log_file.endswith(".log"):
			continue

		function_call.content += f"Test of `/sandbox/log/{log_file}`:\n"

		yield "testing"
		return_code = None
		cmd = ["/sandbox/parser/parse", "/sandbox/log/" + log_file, "/sandbox/ECS.yaml"]
		async for r1, r2 in conversation.sandbox.execute(conversation, cmd):
			match r1:
				case "stdout":
					function_call.content += r2
				case "stderr":
					function_call.content += r2
				case "return_code":
					return_code = r2
			yield "progress"

		if return_code != 0:
			function_call.content += "\nTest failed with return code: " + str(return_code)	
		else:
			function_call.content += "\nTest completed successfully."

		function_call.content += "\n---\n"

	yield "completed"


test_parser_tool = FunctionCallTool(
		name = "test_parser",
		title = "Test a parser",
		description = """This tool tests a parser on all available log files.
The tool will return the result of the test, stdout and stderr of the test.
		""",
		parameters = {
			"type": "object",
			"properties": {
			},
			"required": []
		},
		function_call = fuction_call_test_parser,
	)
