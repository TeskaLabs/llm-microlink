import pydantic

#

class Sandbox(pydantic.BaseModel):
	"""A sandbox for a conversation."""
	path: str
