import asyncio
import logging

import asab

L = logging.getLogger(__name__)

class Sandbox(object):
	"""A sandbox for a conversation."""

	def __init__(self, name: str, path: str, docker_process: asyncio.subprocess.Process):
		self.Name = name
		self.Path = path
		self.DockerProcess = docker_process


	async def execute(self, conversation, cmd, *, stdin=None):
		L.log(asab.LOG_NOTICE, "Executing command in sandbox", struct_data={"sandbox": self.Name, "cmd": ' '.join(cmd)[:128]})

		docker_cmd = [
			"/usr/bin/docker", "exec", 
			"--interactive",
			self.Name,
			*cmd
		]

		process = await asyncio.create_subprocess_exec(
			*docker_cmd,
			stdin=asyncio.subprocess.PIPE if stdin is not None else None,
			stdout=asyncio.subprocess.PIPE,
			stderr=asyncio.subprocess.PIPE,
		)
		
		if stdin is not None:
			process.stdin.write(stdin.encode("utf-8"))
			process.stdin.close()

		terminate_at = asyncio.get_event_loop().time() + 120.0

		return_code = None
		pending = set([
			asyncio.create_task(process.stdout.readline(), name="stdout"),
			asyncio.create_task(process.stderr.readline(), name="stderr"),
			asyncio.create_task(process.wait(), name="return_code"),
		])
		while len(pending) > 0:
			done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=10.0)

			if asyncio.get_event_loop().time() > terminate_at:
				L.warning("Sandbox execution timed out, terminating process")
				terminate_at += 120.0
				process.terminate()
				yield "timeout"

			for task in done:
				task_name = task.get_name()
				match task_name:

					case "stdout" | "stderr":
						data = task.result()
						if len(data) > 0:
							yield task_name, data.decode("utf-8", errors="replace")

							if task_name == "stdout":
								pending.add(asyncio.create_task(process.stdout.readline(), name="stdout"))
							else:
								pending.add(asyncio.create_task(process.stderr.readline(), name="stderr"))
					
					case "return_code":
						return_code = task.result()

		assert return_code is not None, "Return code is not set"

		# Ensure the return code is yielded as a last
		yield "return_code", return_code
