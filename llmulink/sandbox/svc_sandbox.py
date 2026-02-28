import os
import logging
import asyncio
import tempfile

import asab

from ..llm.datamodel import Conversation
from .sandbox import Sandbox

#

L = logging.getLogger(__name__)

#


class SandboxService(asab.Service):

	def __init__(self, app, service_name="SandboxService"):
		super().__init__(app, service_name)

		self.SandboxPath = asab.Config["sandbox"]["path"]
		os.makedirs(self.SandboxPath, exist_ok=True)

		self.Sandboxes = {}


	async def init_sandbox(self, conversation: Conversation):
		if conversation.sandbox is not None:
			assert conversation.sandbox.Path is not None, "Sandbox path is not set"
			return

		path = tempfile.mkdtemp(dir=self.SandboxPath, prefix="sandbox-")
		sandbox_name = path.rsplit('/', 1)[-1]

		docker_cmd = [
			"/usr/bin/docker", "run", "--rm",
			"-i",
			"--name", sandbox_name,
			"--user", "1000000:1000000",
			"-v", path+":/sandbox",
			"alpine:latest",
			"/bin/cat", "-",
		]

		process = await asyncio.create_subprocess_exec(
			*docker_cmd,
			stdin=asyncio.subprocess.PIPE,
		)

		sandbox = Sandbox(name=sandbox_name, path=path, docker_process=process)
		self.Sandboxes[sandbox_name] = sandbox
		conversation.sandbox = sandbox
