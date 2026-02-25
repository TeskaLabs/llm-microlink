import os
import logging
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


	async def init_sandbox(self, conversation: Conversation):
		if conversation.sandbox is not None:
			return

		path = tempfile.mkdtemp(dir=self.SandboxPath)
		conversation.sandbox = Sandbox(path=path)


