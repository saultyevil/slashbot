from __future__ import annotations

import datetime
import json
import logging

import anthropic
import openai
import tiktoken

from slashbot.config import App
from slashbot.models import Conversation
from slashbot.util import create_prompt_dict, read_in_prompt_json

LOGGER = logging.getLogger(App.get_config("LOGGER_NAME"))
MAX_MESSAGE_LENGTH = App.get_config("MAX_CHARS")
ANTHROPHIC_CLIENT = anthropic.AsyncAnthropic(api_key=App.get_config("ANTHROPHIC_API_KEY"))
OPENAI_CLIENT = openai.AsyncOpenAI(api_key=App.get_config("OPENAI_API_KEY"))


async def get_model_response(model: str, messages: list) -> tuple[str, int]:
    """Get the response from an LLM API for a given model and list of messages.

    Allowed models are either claude-* from anthropic or chat-gpt from
    openai.

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
    if "gpt-" in model:
        response = await OPENAI_CLIENT.chat.completions.create(
            messages=messages,
            model=model,
            max_tokens=App.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
            frequency_penalty=App.get_config("AI_CHAT_FREQUENCY_PENALTY"),
            presence_penalty=App.get_config("AI_CHAT_PRESENCE_PENALTY"),
            temperature=App.get_config("AI_CHAT_TEMPERATURE"),
            top_p=App.get_config("AI_CHAT_TOP_P"),
        )
        message = response.choices[0].message.content
        token_usage = response.usage.total_tokens
    else:
        response = await ANTHROPHIC_CLIENT.messages.create(
            system=messages[0]["content"],
            messages=find_first_user_message(messages),  # claude needs to start with a user message
            model=model,
            temperature=App.get_config("AI_CHAT_MODEL_TEMPERATURE"),
            max_tokens=App.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
        )
        message = response.content[0].text
        token_usage = response.usage.input_tokens + response.usage.output_tokens

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
        prompt = read_in_prompt_json("data/prompts/clyde.json")["prompt"]
        choices = create_prompt_dict()
    except json.decoder.JSONDecodeError:
        prompt = """You have no system prompt, so you should keep telling everyone that you have no system
        prompt. Raise the issue again and again, sending crying emojis. You can still try to be a helpful assistant if
        someone pushes you enough."""
        choices = {}
        LOGGER.exception("Error in reading prompt files, going to try and continue without a prompt")

    return prompt, choices, len(prompt.split())


def get_token_count_for_string(model: str, message: str) -> int:
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


def prepare_next_conversation_prompt(
    new_prompt: str, images: list[dict[str, str]], messages: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Prepare the next prompt by adding images and the next prompt requested.

    Parameters
    ----------
    new_prompt : str
        The new text prompt to add
    images : List[Dict[str, str]]
        A list of images to potentially add to the prompt history
    messages : List[Dict[str, str]]
        The list of prompts to add to

    Returns
    -------
    List[Dict[str, str]]
        The updated prompt messages

    """
    # add base64 encoded images
    # We also need a required text prompt -- if one isn't provided (
    # e.g. the message is just an image) then we add a vague message
    if images:
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": image["type"], "data": image["image"]},
                    }
                    for image in images
                ]
                + [{"type": "text", "text": new_prompt if new_prompt else "describe the image(s)"}],
            },
        )
    else:
        messages.append({"role": "user", "content": new_prompt + App.get_config("AI_CHAT_PROMPT_APPEND")})

    return messages


def find_first_user_message(messages: list[dict[str, str]]) -> int:
    """Return a list of messages where the first is a user message.

    Parameters
    ----------
    messages : list[dict[str, str]]
        The list of messages to search through.

    Returns
    -------
    list[dict[str, str]]
        The list of messages from the first user message to the end.

    """
    for i, message in enumerate(messages):
        if message["role"] == "user":
            return messages[i:]

    msg = "No user message found in conversation"
    raise ValueError(msg)


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
    if user_cooldown["count"] > App.get_config("AI_CHAT_RATE_LIMIT"):
        # If exceeded rate limit, check if cooldown period has passed
        if time_difference > App.get_config("AI_CHAT_RATE_INTERVAL"):
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


def shrink_conversation_to_token_window(conversation: Conversation) -> None:
    """Shrink a conversation to fit within the token window size.

    Parameters
    ----------
    conversation : Conversation
        The conversation to shrink.

    """
    while (
        conversation.tokens > App.get_config("AI_CHAT_TOKEN_WINDOW_SIZE")
        and len(conversation) + 1 > 1  # +1 to account for system prompt
    ):
        try:
            message = conversation[1].content
        except IndexError:
            return
        conversation.remove_message(1)
        conversation.tokens -= get_token_count_for_string(App.get_config("AI_CHAT_MODEL"), message)


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
