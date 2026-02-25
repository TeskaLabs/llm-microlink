import os
import json
import shutil
import logging
import asyncio

from ...tool import FunctionCallTool


L = logging.getLogger(__name__)

BUSYBOX_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "sandbox", "template_busybox")

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
	cmd = ["chroot", conversation.sandbox.path, "/bin/busybox", "sh", "-c", command]

	try:
		# Create subprocess for executing the command
		process = await asyncio.create_subprocess_exec(
			*cmd,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
			stdin=asyncio.subprocess.PIPE if stdin is not None else None,
		)

		if stdin is not None:
			process.stdin.write(stdin.encode("utf-8"))
			process.stdin.close()
		
		return_code = 0
		pending = set([
			asyncio.create_task(process.stdout.readline(), name="stdout"),
			asyncio.create_task(process.stderr.readline(), name="stderr"),
			asyncio.create_task(process.wait(), name="return_code"),
		])
		while len(pending) > 0:
			done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=60*5)
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
			function_call.content += "\nBusybox command failed with return code: " + str(return_code)	
			function_call.error = True

		function_call.content += "\nTool execution completed successfully."

		yield "completed"

	except FileNotFoundError:
		L.warning("busybox command not found on this system")
		function_call.content = "A command 'busybox' was not found on this system"
		function_call.error = True
		
	except Exception as e:
		L.exception("Exception occurred while executing busybox", struct_data={"error": str(e)})
		function_call.content = "Exception occurred while executing command 'busybox'"
		function_call.error = True


async def init_call_busybox(app, conversation) -> None:
	await app.SandboxService.init_sandbox(conversation)

	shutil.copytree(BUSYBOX_TEMPLATE_DIR, conversation.sandbox.path, dirs_exist_ok=True)

	# Intall busybox in the sandbox
	process = await asyncio.create_subprocess_exec(
		"chroot", conversation.sandbox.path, "/bin/busybox", "--install", "-s", "/bin",
	)
	await process.wait()


busybox_tool = FunctionCallTool(
		name = "busybox",
		title = "Execute a Shell command using busybox",
		description = """Execute a shell command using busybox and return the stdout and stderr of the command.
		The command is executed in a sandboxed environment with busybox installed.
		Use this tool to ie list or read files in the sandbox.
		If the user is reffering to files, use this tool to access them.
		You can provide an optional stdin input to the command.
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
