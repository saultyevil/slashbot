"""Module for general purpose message handling."""

from slashbot.bot.custom_types import ApplicationCommandInteraction, Message
from slashbot.logger import Logger
from slashbot.settings import BotSettings

LOGGER = Logger()
MAX_MESSAGE_LENGTH = BotSettings.discord.max_chars


def split_text_into_chunks(text: str, chunk_length: int) -> list:
    """Split text into smaller chunks of a set length while preserving sentences.

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


async def send_message_to_channel(
    message: str, obj: Message | ApplicationCommandInteraction, *, dont_tag_user: bool = False
) -> Message | list[Message]:
    """Send a response to the provided message channel and author.

    Parameters
    ----------
    message : str
        The message to send to chat.
    obj : Message | ApplicationCommandInteraction
        The object (channel or interaction) to respond to.
    dont_tag_user : bool
        Boolean to indicate if a user should be tagged or not. Default is
        False, which would tag the user.

    Returns
    -------
    Message | list[Message]
        The message or messages sent to the chat.

    """
    sent_messages = []
    if len(message) > MAX_MESSAGE_LENGTH:
        response_chunks = split_text_into_chunks(message, MAX_MESSAGE_LENGTH)
        for i, response_chunk in enumerate(response_chunks):
            user_mention = obj.author.mention if not dont_tag_user else ""
            sent_message = await obj.channel.send(f"{user_mention if i == 0 else ''} {response_chunk}")
            sent_messages.append(sent_message)
    else:
        sent_message = await obj.channel.send(f"{obj.author.mention if not dont_tag_user else ''} {message}")
        sent_messages.append(sent_message)

    return sent_messages
