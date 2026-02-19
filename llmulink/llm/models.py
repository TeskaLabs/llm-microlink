import logging

import aiohttp

L = logging.getLogger(__name__)

async def get_models(url, headers = None):
	'''
	Get the list of models from the LLM chat provider.
	Implements /v1/models call that works with vLLM, tensorrm-llm, OpenAI and Anthropic API and possibly other LLM chat providers.
	'''

	async with aiohttp.ClientSession(headers=headers) as session:
		try:
			async with session.get(url + "v1/models") as response:
				if response.status != 200:
					if response.status == 401 and response.content_type == "application/json":
						resp = await response.json()
						L.warning("Unauthorized access to LLM chat provider", struct_data={"url": url, "response": resp})
						return None
					L.warning("Error getting models", struct_data={"status": response.status, "text": await response.text()})
					return None

				resp = await response.json()
				models = resp['data']
				if url.startswith('https://api.openai.com/'):
					# Filter only GPT models from OpenAI API
					# They offer more models but they are not directly usable for chat.
					models = filter(lambda model: model['owned_by'] == 'openai', models)
				return models

		except aiohttp.ClientError as e:
			L.warning("Error communicating with LLM: {} {}".format(e.__class__.__name__, e), struct_data={"url": url})
			return None

	return []


async def measure_tokens_vllm(chat_service, session, url, data, conversation):
	async with session.post(url + "tokenize", json=data, timeout=60*10) as response:
		if response.status == 200:
			token_count = await response.json()
			await chat_service.send_update(conversation, {
				"type": "chat.tokens",
				"token_count": token_count.get('count'),
				"token_max": token_count.get('max_model_len'),
			})
