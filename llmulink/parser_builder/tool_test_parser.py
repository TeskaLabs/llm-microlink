import os
import logging
import asyncio

from ..tool.tool import FunctionCallTool

L = logging.getLogger(__name__)


async def execute(function_call, cmd, cwd):
	process = await asyncio.create_subprocess_exec(
		*cmd,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
		cwd=cwd,
	)
	
	return_code = 0
	pending = set([
		asyncio.create_task(process.stdout.readline(), name="stdout"),
		asyncio.create_task(process.stderr.readline(), name="stderr"),
		asyncio.create_task(process.wait(), name="return_code"),
	])
	while len(pending) > 0:
		done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
		for task in done:
			match task.get_name():
				
				case "stdout" | "stderr":
					data = task.result()
					if len(data) > 0:
						function_call.content += data.decode("utf-8", errors="replace")
						yield "progress"

						if task.get_name() == "stdout":
							pending.add(asyncio.create_task(process.stdout.readline(), name="stdout"))
						else:
							pending.add(asyncio.create_task(process.stderr.readline(), name="stderr"))

				case "return_code":
					return_code = task.result()

	if return_code != 0:
		function_call.content += "\nExecution of the test (parser) failed with return code: " + str(return_code)	
		function_call.error = True


async def fuction_call_test_parser(conversation, function_call) -> None:
	assert conversation.sandbox is not None, "Sandbox is not initialized"

	for log_file in sorted(os.listdir(os.path.join(conversation.sandbox.path, "log"))):
		if not log_file.endswith(".log"):
			continue

		yield "testing"
		cmd = ["chroot", conversation.sandbox.path, "/parser/parse", "log/" + log_file, "./ECS.yaml"]
		async for result in execute(function_call, cmd, conversation.sandbox.path):
			yield result
		
		function_call.content += f"\nTest `{log_file}` completed.\n---\n"


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
