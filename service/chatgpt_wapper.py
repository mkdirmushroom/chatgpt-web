import random
import time

import openai  # for OpenAI API calls
import traceback
import json
import asyncio
from loguru import logger
from backoff import on_exception, expo
import concurrent.futures

base = {"role": "system", "content": "You are a helpful assistant."}

async def process(prompt, options, memory_count, top_p, message_store, model="gpt-3.5-turbo"):
		if not prompt:
				logger.error("Prompt is empty.")
				yield "[Failed to recognize input because Prompt is empty, please try again or check server error logs.]"

		try:
				chat = {"role": "user", "content": prompt}

				if options:
						parent_message_id = options.get("parentMessageId")
						messages = message_store.get_from_key(parent_message_id)
						if messages:
								messages.append(chat)
						else:
								messages = [base, chat]
				else:
						parent_message_id = None
						messages = [base, chat]

				messages = [messages[0]] + messages[-memory_count:]

				params = dict(
						stream=True, messages=messages, model=model, top_p=top_p
				)
				if parent_message_id:
						params["request_id"] = parent_message_id

				res = await _create_async(params)

				result_messages = []
				text = ""
				role = ""
				for openai_object in res:
						openai_object_dict = openai_object.to_dict_recursive()
						if not role:
								role = openai_object_dict["choices"][0]["delta"].get("role", "")

						text_delta = openai_object_dict["choices"][0]["delta"].get("content", "")
						text += text_delta

						message = json.dumps(dict(
								role=role,
								id=openai_object_dict["id"],
								parentMessageId=parent_message_id,
								text=text,
								delta=text_delta,
								detail=dict(
										id=openai_object_dict["id"],
										object=openai_object_dict["object"],
										created=openai_object_dict["created"],
										model=openai_object_dict["model"],
										choices=openai_object_dict["choices"]
								)
						))
						result_messages.append(message)

				yield "\n".join(result_messages)
		except:
				err = traceback.format_exc()
				logger.error(err)
				yield "Something went wrong. Please check the server logs."

		try:
				# save to cache
				chat = {"role": role, "content": text}
				messages.append(chat)

				openai_object_dict = json.loads(result_messages[-1])
				parent_message_id = openai_object_dict["id"]
				message_store.set(parent_message_id, messages)
		except:
				err = traceback.format_exc()
				logger.error(err)


@on_exception(expo, openai.error.RateLimitError)
def _create(params):
		return openai.ChatCompletion.create(**params)


async def _create_async(params):
		with concurrent.futures.ThreadPoolExecutor() as executor:
				result = await asyncio.get_event_loop().run_in_executor(
						executor, _create, params
				)
		return result
