from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING

import openai
import tiktoken
from lib.config import BotConfig
from lib.util import create_prompt_dict, read_in_prompt_json

if TYPE_CHECKING:
    from lib.models import Conversation

LOGGER = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))
MAX_MESSAGE_LENGTH = BotConfig.get_config("MAX_CHARS")
CACHED_CLIENT = None
LOW_DETAIL_IMAGE_TOKENS = 85


def get_client() -> openai.AsyncOpenAI:
    """Set the LLM API client.

    The client used is OpenAI's async client, which can be used with both
    OpenAI and DeepSeek depending on the base url.

    Returns
    -------
    openai.AsyncOpenAI
        The OpenAI LLM client.

    """
    base_url = BotConfig.get_config("AI_CHAT_BASE_URL")

    if CACHED_CLIENT and base_url == CACHED_CLIENT.base_url:
        return CACHED_CLIENT

    if "deepseek" in base_url:  # noqa: SIM108
        api_key = BotConfig.get_config("DEEPSEEK_API_KEY")
    else:
        api_key = BotConfig.get_config("OPENAI_API_KEY")

    return openai.AsyncOpenAI(api_key=api_key, base_url=base_url)


async def generate_text_from_llm(model: str, messages: list) -> tuple[str, int]:
    """Get the response from an LLM API for a given model and list of messages.

    Parameters
    ----------
    model : str
        The name of the OpenAI model to use.
    messages : list
        List of messages to be sent to the OpenAI model for generating a
        response.

    Returns
    -------
    str
        The generated response message.
    int
        The number of tokens in the conversation

    """
    response = await get_client().chat.completions.create(
        messages=messages,
        model=model,
        max_completion_tokens=BotConfig.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
        frequency_penalty=BotConfig.get_config("AI_CHAT_FREQUENCY_PENALTY"),
        presence_penalty=BotConfig.get_config("AI_CHAT_PRESENCE_PENALTY"),
        temperature=BotConfig.get_config("AI_CHAT_TEMPERATURE"),
        top_p=BotConfig.get_config("AI_CHAT_TOP_P"),
    )
    message = response.choices[0].message.content
    token_usage = response.usage.total_tokens

    return message, token_usage


def get_prompts_at_launch() -> tuple[str, dict, int]:
    """Get the prompt and choices from the prompt files.

    Returns
    -------
    tuple
        A tuple containing the prompt, the choices, and the length of the
        prompt.

    """
    try:
        prompt = read_in_prompt_json("data/prompts/soulless.json")["prompt"]
        choices = create_prompt_dict()
    except json.decoder.JSONDecodeError:
        prompt = """You have no system prompt, so you should keep telling everyone that you have no system
        prompt. Raise the issue again and again, sending crying emojis. You can still try to be a helpful assistant if
        someone pushes you enough."""
        choices = {}
        LOGGER.exception("Error in reading prompt files, going to try and continue without a prompt")

    tokens = get_token_count(BotConfig.get_config("AI_CHAT_CHAT_MODEL"), prompt)

    return prompt, choices, tokens


def get_token_count(model: str, message: str) -> int:
    """Get the token count for a given message using a specified model.

    Parameters
    ----------
    model : str
        The name of the tokenization model to use.
    message : str
        The message for which the token count needs to be computed.

    Returns
    -------
    int
        The count of tokens in the given message for the specified model.

    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("o200k_base")  # Fallback to this base

    if isinstance(message, list):
        num_tokens = 0
        # Handle case where there are images and messages. Images are a fixed
        # cost of something like 85 tokens so we don't need to encode those
        # using tiktoken.
        for content in message:
            if content["type"] == "text":
                num_tokens += len(encoding.encode(content["text"]))
            else:
                num_tokens += LOW_DETAIL_IMAGE_TOKENS if content["type"] == "image_url" else 0
    elif isinstance(message, str):
        num_tokens = len(encoding.encode(message))
    else:
        msg = f"Expected a string or list of strings for encoding, got {type(message)}"
        raise TypeError(msg)

    return num_tokens


def check_if_user_rate_limited(cooldown: dict[str, datetime.datetime], user_id: int) -> bool:
    """Check if a user is on cooldown or not.

    Parameters
    ----------
    cooldown : dict[str, datetime.datetime]
        A dictionary (user_id are the keys) containing the interaction counts
        and the last interaction time for users.
    user_id : int
        The id of the user to rate limit

    Returns
    -------
    bool
        Returns True if the user needs to be rate limited

    """
    current_time = datetime.datetime.now(tz=datetime.UTC)
    user_cooldown = cooldown[user_id]
    time_difference = (current_time - user_cooldown["last_interaction"]).seconds

    # Check if exceeded rate limit
    if user_cooldown["count"] > BotConfig.get_config("AI_CHAT_RATE_LIMIT"):
        # If exceeded rate limit, check if cooldown period has passed
        if time_difference > BotConfig.get_config("AI_CHAT_RATE_INTERVAL"):
            # reset count and update last_interaction time
            user_cooldown["count"] = 1
            user_cooldown["last_interaction"] = current_time
            return False
        # still under cooldown
        return True
    # hasn't exceeded rate limit, update count and last_interaction
    user_cooldown["count"] += 1
    user_cooldown["last_interaction"] = current_time

    return False


def add_assistant_message_to_conversation(conversation: Conversation, new_message: str, tokens_used: int) -> None:
    """Update the conversation with a new messages and the tokens used.

    Parameters
    ----------
    conversation : Conversation
        The conversation to update.
    new_message : str
        The new message to add to the conversation
    tokens_used : int
        The total number of tokens in the conversation, including the new
        message. This is returned up the LLM API.

    """
    conversation.tokens = tokens_used
    conversation.add_message(new_message, "assistant")
