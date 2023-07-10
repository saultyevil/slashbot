#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Various utility functions used through slashbot."""

import json
import logging
import pathlib
import re
from typing import Any

import disnake

from slashbot.config import App

logger = logging.getLogger(App.config("LOGGER_NAME"))


async def send_cooldown_message(
    channel: disnake.TextChannel | disnake.DMChannel, author: disnake.User | disnake.Member
) -> None:
    """Respond to a user on cooldown.

    Historically, this used to do a lot more.

    Parameters
    ----------
    channel
        The channel to send the message to
    author
        The user to respond to
    """
    await channel.send(f"Stop abusing me {author.mention}!")


def split_text_into_chunks(text: str, chunk_length: int) -> list:
    """
    Split text into smaller chunks of a set length while preserving sentences.

    Parameters
    ----------
    text : str
        The input text to be split into chunks.
    chunk_length : int, optional
        The maximum length of each chunk. Default is 1648.

    Returns
    -------
    list
        A list of strings where each string represents a chunk of the text.
    """
    chunks = []
    current_chunk = ""

    while len(text) > 0:
        # Find the nearest sentence end within the chunk length
        end_index = min(len(text), chunk_length)
        while end_index > 0 and text[end_index - 1] not in (".", "!", "?"):
            end_index -= 1

        # If no sentence end found, break at chunk length
        if end_index == 0:
            end_index = chunk_length

        current_chunk += text[:end_index]
        text = text[end_index:]

        if len(text) == 0 or len(current_chunk) + len(text) > chunk_length:
            chunks.append(current_chunk)
            current_chunk = ""

    return chunks


def convert_string_to_lower(_inter: disnake.ApplicationCommandInteraction, variable: Any) -> Any:
    """Slash command convertor to transform a string into all lower case.

    Parameters
    ----------
    _inter : disnake.ApplicationCommandInteraction
        The slash command interaction. Currently unused.
    variable : Any
        The possible string to convert into lower case.

    Returns
    -------
    Any :
        If a string was passed, the lower version of the string is returned.
        Otherwise the original variable is returned.
    """
    return variable.lower() if isinstance(variable, str) else variable


def convert_yes_no_to_bool(_inter: disnake.ApplicationCommandInteraction, choice: str) -> bool:
    """_summary_

    Parameters
    ----------
    _inter : disnake.ApplicationCommandInteraction
        The slash command interaction. Currently unused.
    choice : str
        The yes/no string to convert into a bool.

    Returns
    -------
    bool
        True or False depending on yes or no.
    """
    return True if choice.lower() == "yes" else False


def remove_emojis_from_string(string: str) -> str:
    """Remove emojis from a string.

    Parameters
    ----------
    string : str
        _description_

    Returns
    -------
    str
        _description_
    """
    emoj = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U00002500-\U00002BEF"  # chinese char
        "\U00002702-\U000027B0"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001f926-\U0001f937"
        "\U00010000-\U0010ffff"
        "\u2640-\u2642"
        "\u2600-\u2B55"
        "\u200d"
        "\u23cf"
        "\u23e9"
        "\u231a"
        "\ufe0f"  # dingbats
        "\u3030"
        "]+",
        re.UNICODE,
    )
    return re.sub(emoj, "", string)


def convert_radial_to_cardinal_direction(degrees: float) -> str:
    """Convert a degrees value to a cardinal direction.

    Parameters
    ----------
    degrees: float
        The degrees direction.

    Returns
    -------
    The cardinal direction as a string.
    """
    directions = [
        "N",
        "NNE",
        "NE",
        "ENE",
        "E",
        "ESE",
        "SE",
        "SSE",
        "S",
        "SSW",
        "SW",
        "WSW",
        "W",
        "WNW",
        "NW",
        "NNW",
    ]

    return directions[round(degrees / (360.0 / len(directions))) % len(directions)]


def read_in_prompt_json(filepath: str | pathlib.Path) -> dict:
    """Read in a prompt and check for keys."""
    required_keys = (
        "name",
        "prompt",
    )

    with open(filepath, "r", encoding="utf-8") as prompt_in:
        prompt = json.load(prompt_in)
        if not all(key in prompt for key in required_keys):
            raise OSError(f"{filepath} is missing either 'name' or 'prompt' key")

    return prompt


def create_prompt_dict() -> dict:
    """Creates a dict of prompt_name: prompt."""
    return {
        prompt_dict["name"]: prompt_dict["prompt"]
        for prompt_dict in [
            read_in_prompt_json(file)
            for file in pathlib.Path("data/prompts").glob("*.json")
            if not file.name.startswith("_")  # prompts which start with _ are hidden prompts
        ]
    }
