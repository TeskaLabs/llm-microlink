import abc
import logging

import asab

from ..datamodel import Conversation, Exchange

L = logging.getLogger("llmulink.llm")

class LLMChatProviderABC(abc.ABC):
	def __init__(self, service, *, url):
		self.LLMChatService = service
		self.URL = url.rstrip('/') + '/'

		L.log(asab.LOG_NOTICE, "Loaded provider", struct_data={"url": self.URL, "type": self.__class__.__name__})

	@abc.abstractmethod
	def prepare_headers(self):
		pass

	@abc.abstractmethod
	async def chat_request(self, conversation: Conversation, exchange: Exchange):
		pass
