import json
import logging

from ..tool.tool import FunctionCallTool


L = logging.getLogger(__name__)


async def fuction_call_busybox(conversation, function_call) -> None:
	"""
	Execute a shell command using busybox and return the stdout and stderr of the command.
	
	Args:
		command: The shell command to execute
		reply: Async callback to submit JSON chunks to the webui client
	"""
	yield "validating"

	try:
		arguments = json.loads(function_call.arguments)
	except Exception as e:
		L.exception("Exception occurred while parsing arguments: '{}'".format(function_call.arguments), struct_data={"error": str(e)})
		function_call.content = "Exception occurred while parsing arguments."
		function_call.error = True
		return

	command = arguments.get("command")
	if not command:
		function_call.content = "Parameter 'command' is required"
		function_call.error = True
		return

	stdin = arguments.get("stdin")

	yield "executing"
	return_code = None
	async for r1, r2 in conversation.sandbox.execute(conversation, ["sh", "-c", command], stdin=stdin):
		match r1:
			case "stdout":
				function_call.content += r2
			case "stderr":
				function_call.content += r2
			case "return_code":
				return_code = r2
		yield "progress"

	if return_code != 0:
		function_call.content += "\nBusybox command failed with return code: " + str(return_code)	
		function_call.error = True
	else:
		function_call.content += "\nTool execution completed successfully."
	
	yield "completed"


async def init_call_busybox(app, conversation) -> None:
	await app.SandboxService.init_sandbox(conversation)


busybox_tool = FunctionCallTool(
		name = "busybox",
		title = "Execute a Shell command using busybox",
		description = """Execute a shell command using busybox and return the stdout and stderr of the command.
		The command is executed in a sandboxed environment with busybox installed.
		Use this tool to ie list or read files in the sandbox.
		If the user is reffering to files, use this tool to access them.
		You can provide an optional stdin input to the command.
		The persistent directory is /sandbox, you can use it to store files; other directories are not persistent.
		Example:
		```
		{
			"command": "cat > hi.txt",
			"stdin": "Hello, world!"
		}
		```
		""",
		parameters = {
			"type": "object",
			"properties": {
				"command": {
					"type": "string",
					"description": "The shell command to execute"
				},
				"stdin": {
					"type": "string",
					"description": "Optional stdin input to the command"
				}

			},
			"required": ["command"]
		},
		function_call = fuction_call_busybox,
		init_call = init_call_busybox,
	)
