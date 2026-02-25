import uuid
import typing
import datetime

import pydantic

from ..tool import FunctionCallTool


def _utc_now() -> datetime.datetime:
	"""Factory function for current UTC time."""
	return datetime.datetime.now(datetime.timezone.utc)


class AssistentReasoning(pydantic.BaseModel):
	"""Reasoning block from the LLM response."""
	content: str
	status: typing.Literal['in_progress', 'completed']
	index: int = None  # LLMChatProviderV1Messages is using this index to identify the content block
	key: str = pydantic.Field(default_factory=lambda: "reasoning-{}".format(str(uuid.uuid4())))
	type: typing.Literal['reasoning'] = 'reasoning'
	created_at: datetime.datetime = pydantic.Field(default_factory=_utc_now)

	def to_dict(self) -> dict:
		return {
			"key": self.key,
			"type": "reasoning",
			"created_at": self.created_at.isoformat(),
			"content": self.content,
			"status": self.status,
		}


class AssistentMessage(pydantic.BaseModel):
	"""Message block from the LLM response."""
	content: str
	status: typing.Literal['in_progress', 'completed']
	role: str
	index: int = None  # LLMChatProviderV1Messages is using this index to identify the content block
	key: str = pydantic.Field(default_factory=lambda: "message-{}".format(str(uuid.uuid4())))
	type: typing.Literal['message'] = 'message'
	created_at: datetime.datetime = pydantic.Field(default_factory=_utc_now)

	def to_dict(self) -> dict:
		return {
			"key": self.key,
			"type": "message",
			"created_at": self.created_at.isoformat(),
			"status": self.status,
			"role": self.role,
			"content": self.content,
		}


class UserMessage(pydantic.BaseModel):
	"""User message (item) in a conversation."""
	role: str
	content: str
	model: str
	key: str = pydantic.Field(default_factory=lambda: "user-message-{}".format(str(uuid.uuid4())))
	type: typing.Literal['message'] = 'message'
	created_at: datetime.datetime = pydantic.Field(default_factory=_utc_now)

	def to_dict(self) -> dict:
		return {
			"key": self.key,
			"type": "message",
			"created_at": self.created_at.isoformat(),
			"role": self.role,
			"content": self.content,
			"model": self.model,
		}


class FunctionCall(pydantic.BaseModel):
	"""Function call block from the LLM response."""
	call_id: str
	name: str
	arguments: str
	status: typing.Literal['in_progress', 'completed', 'executing', 'finished']
	content: str = ''
	error: bool = False
	index: int = None  # LLMChatProviderV1ChatCompletition and LLMChatProviderV1Messages are using this index to identify the tool call
	key: str = pydantic.Field(default_factory=lambda: "fc-{}".format(str(uuid.uuid4())))
	type: typing.Literal['function_call'] = 'function_call'
	created_at: datetime.datetime = pydantic.Field(default_factory=_utc_now)

	def to_dict(self) -> dict:
		return {
			"type": "function_call",
			"key": self.key,
			"created_at": self.created_at.isoformat(),
			"status": self.status,
			"name": self.name,
			"arguments": self.arguments,
			"content": self.content,
			"error": self.error,
		}


class ChatToolResult(pydantic.BaseModel):
	"""Result of a tool/function execution."""
	call_id: str
	type: typing.Literal['function_call_output'] = 'function_call_output'
	created_at: datetime.datetime = pydantic.Field(default_factory=_utc_now)


class Exchange(pydantic.BaseModel):
	"""An exchange between the user and the LLM."""
	items: list[UserMessage|AssistentReasoning|AssistentMessage|FunctionCall] = pydantic.Field(default_factory=list)
	completed: bool = False

	def get_last_item(self, item_type: typing.Literal['message', 'reasoning', 'function_call'], status: typing.Literal['in_progress', 'completed'] = None) -> UserMessage|AssistentReasoning|FunctionCall:
		for item in reversed(self.items):
			if item.type == item_type:
				if status is not None and item.status != status:
					continue
				return item
		return None

	def get_last_assistant_message(self, status: typing.Literal['in_progress', 'completed'] = 'in_progress') -> UserMessage|AssistentMessage:
		for item in reversed(self.items):
			if isinstance(item, AssistentMessage) and item.status == status:
				return item
		return None


class Conversation(pydantic.BaseModel):
	"""A complete conversation."""
	conversation_id: str
	instructions: list[str] = pydantic.Field(default_factory=list)
	
	tools: dict[str, FunctionCallTool] = pydantic.Field(default_factory=dict) # name -> tool
	tool_initialized: set[str] = pydantic.Field(default_factory=set)

	created_at: datetime.datetime = pydantic.Field(default_factory=_utc_now)

	exchanges: list[Exchange] = pydantic.Field(default_factory=list)

	monitors: set[typing.Callable] = pydantic.Field(default_factory=set)
		
	tasks: list[typing.Callable] = pydantic.Field(default_factory=list)
	loop_break: bool = True  # If true, then a LLMService will break an agentic loop and wait for the next user message

	sandbox: object = None


	def get_model(self) -> str | None:
		'''
		Get the model from the most recent item in the conversation.
		'''
		for exchange in reversed(self.exchanges):
			for item in reversed(exchange.items):
				if isinstance(item, UserMessage):
					return item.model
		return None
