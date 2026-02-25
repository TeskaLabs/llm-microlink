import os
import json
import logging
import asyncio
import shutil

from ..tool.tool import FunctionCallTool

L = logging.getLogger(__name__)

GO_PARSER_DIR = os.path.join(os.path.dirname(__file__), "go")

async def execute(cmd, cwd, function_call):
	try:
		# Create subprocess for ping command
		# -c 4: send 4 packets
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

		yield f"return_code: {return_code}"

	except FileNotFoundError:
		L.warning("go compiler not found on this system")
		function_call.content = "A command 'go compiler' was not found on this system"
		function_call.error = True
		
	except Exception as e:
		L.exception("Exception occurred while executing go compiler", struct_data={"error": str(e)})
		function_call.content = "Exception occurred while executing command 'go compiler'"
		function_call.error = True


async def fuction_call_compile_parser(conversation, function_call) -> None:
	yield "validating"

	try:
		arguments = json.loads(function_call.arguments)
	except Exception as e:
		L.exception("Exception occurred while parsing arguments: '{}'".format(function_call.arguments), struct_data={"error": str(e)})
		function_call.content = "Exception occurred while parsing arguments."
		function_call.error = True
		return

	code = arguments.get("code")
	if not code:
		function_call.content = "Parameter 'code' is required"
		function_call.error = True
		return

	assert conversation.sandbox is not None, "Sandbox is not initialized"
	trgdir = os.path.join(conversation.sandbox.path, "parser")
	try:
		shutil.copytree(GO_PARSER_DIR, trgdir, dirs_exist_ok=True)

		parser_path = os.path.join(trgdir, "parse.go")
		with open(parser_path, "w") as f:
			f.write(code)

	except Exception as e:
		L.exception("Exception occurred while writing parser code", struct_data={"error": str(e)})
		function_call.content = "Exception occurred while writing parser code"
		function_call.error = True
		return

	yield "tidying"

	cmd = ["go", "mod", "tidy"]
	async for result in execute(cmd, trgdir, function_call):
		if result.startswith("return_code:"):
			return_code = int(result.split(":")[1])
			if return_code != 0:
				function_call.content += "\nTidying failed with return code: " + str(return_code)
				function_call.error = True
				return
		yield result

	yield "compiling"

	cmd = ["go", "build", "-o", "parse", "."]
	async for result in execute(cmd, trgdir, function_call):
		if result.startswith("return_code:"):
			return_code = int(result.split(":")[1])
			if return_code != 0:
				function_call.content += "\nCompilation failed with return code: " + str(return_code)
				function_call.error = True
				return
			else:
				function_call.content += "\nCompilation successful."
		yield result



compile_parser_tool = FunctionCallTool(
		name = "compile_parser",
		title = "Compile a parser in Go language",
		description = """This tool compiles the parser written in Go.
The tool will return the result of the compilation, stdout and stderr of the Go compiler.

The Go code is a single file that defines Parse function as follows:
```
package main

func Parse(log []byte) map[string]interface{} {
	output := map[string]interface{}{}
	// Implement the parser here
	return output
}
```

The main function will be provided by the tool call itself, don't implement it.
		""",
		parameters = {
			"type": "object",
			"properties": {
				"code": {
					"type": "string",
					"description": "The Go code of the parser"
				},
			},
			"required": [
				"code"
			]
		},
		function_call = fuction_call_compile_parser,
		# init_call = init_call_compile_parser,
	)
