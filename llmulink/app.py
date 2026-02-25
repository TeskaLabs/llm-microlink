import logging

import asab.api
import asab.library
import asab.web.rest

from .llm import LLMRouterService, LLMWebHandler
from .tool import ToolService, ToolWebHandler
from .sandbox import SandboxService

#

L = logging.getLogger(__name__)

#

asab.Config.add_defaults({
	"web": {
		"listen": "8920",
	},
	"library": {
		"providers": "file://./library",
	},
	"tools": {
		"default": ["ping"],
	},
	"sandbox": {
		"path": "./sandboxes",
	},
})


class LLMMicrolinkApplication(asab.Application):

	def __init__(self):
		super().__init__()

		self.ASABApiService = asab.api.ApiService(self)

		# Initialize WebService
		self.add_module(asab.web.Module)
		self.WebService = self.get_service("asab.WebService")
		self.WebContainer = asab.web.WebContainer(self.WebService, "web")
		self.WebContainer.WebApp.middlewares.append(asab.web.rest.JsonExceptionMiddleware)
		self.ASABApiService.initialize_web(self.WebContainer)

		# Initialize ZooKeeper
		self.ZooKeeperService = None
		self.ZkContainer = None
		if 'zookeeper' in asab.Config.sections():
			# Zookeeper is optional
			self.add_module(asab.zookeeper.Module)
			self.ZooKeeperService = self.get_service("asab.ZooKeeperService")
			self.ZkContainer = asab.zookeeper.ZooKeeperContainer(self.ZooKeeperService, 'zookeeper')
			self.ASABApiService.initialize_zookeeper(self.ZkContainer)

		# Initialize the Tenant service
		self.TenantService = asab.web.tenant.TenantService(self)

		# Initialize LibraryService
		self.LibraryService = asab.library.LibraryService(self, "LibraryService")

		# Initialize SandboxService
		self.SandboxService = SandboxService(self)

		# Initialize ToolService
		self.ToolService = ToolService(self)
		self.ToolWebHandler = ToolWebHandler(self)

		# Initialize LLMConversationRouterService
		self.LLMRouterService = LLMRouterService(self)
		self.LLMWebHandler = LLMWebHandler(self)
