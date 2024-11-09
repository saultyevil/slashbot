from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING

import openai
import tiktoken

from slashbot.config import Bot
from slashbot.util import create_prompt_dict, read_in_prompt_json

if TYPE_CHECKING:
    from slashbot.models import Conversation

LOGGER = logging.getLogger(Bot.get_config("LOGGER_NAME"))
MAX_MESSAGE_LENGTH = Bot.get_config("MAX_CHARS")
OPENAI_CLIENT = openai.AsyncOpenAI(api_key=Bot.get_config("OPENAI_API_KEY"))


async def genete_text_from_llm(model: str, messages: list) -> tuple[str, int]:
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
    response = await OPENAI_CLIENT.chat.completions.create(
        messages=messages,
        model=model,
        max_tokens=Bot.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
        frequency_penalty=Bot.get_config("AI_CHAT_FREQUENCY_PENALTY"),
        presence_penalty=Bot.get_config("AI_CHAT_PRESENCE_PENALTY"),
        temperature=Bot.get_config("AI_CHAT_TEMPERATURE"),
        top_p=Bot.get_config("AI_CHAT_TOP_P"),
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

    tokens = get_token_count(Bot.get_config("AI_CHAT_CHAT_MODEL"), prompt)

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
    model = model if model != "gpt-4o-mini" else "gpt-4o"  # hack for tiktoken!!
    if "gpt-" in model:
        return len(tiktoken.encoding_for_model(model).encode(message))

    # fall back to a simple word count
    return len(message.split())


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
    if user_cooldown["count"] > Bot.get_config("AI_CHAT_RATE_LIMIT"):
        # If exceeded rate limit, check if cooldown period has passed
        if time_difference > Bot.get_config("AI_CHAT_RATE_INTERVAL"):
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
