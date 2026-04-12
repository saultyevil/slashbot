import disnake
from slashbot.settings import BotSettings

MAX_MESSAGE_LENGTH = BotSettings.discord.max_chars


async def is_reply_to_slash_command_response(message: disnake.Message) -> bool:
    """Check if a message is a reply to a slash command response.

    Parameters
    ----------
    message : disnake.Message
        The message to inspect for a slash command reference.

    Returns
    -------
    bool
        ``True`` if the message is a reply to a slash command interaction
        response, ``False`` otherwise.

    Notes
    -----
    Returns ``False`` early if the message has no reference, if the referenced
    message cannot be found, or if it carries no interaction metadata.
    """
    if not message.reference:
        return False

    reference = message.reference
    old_message = (
        reference.cached_message if reference.cached_message else await message.channel.fetch_message(message.id)
    )
    if not old_message or not old_message.interaction_metadata:
        return False
    return old_message.interaction_metadata.type == disnake.InteractionType.application_command


def split_text_into_chunks(text: str, chunk_length: int) -> list[str]:
    """Split a string into chunks no longer than ``chunk_length``, preserving sentences.

    The function attempts to break at sentence-ending punctuation (``'.'``,
    ``'!'``, ``'?'``). If no such boundary is found within the allowed length,
    it breaks at exactly ``chunk_length``.

    Parameters
    ----------
    text : str
        The input text to split.
    chunk_length : int
        Maximum character length of each chunk.

    Returns
    -------
    list of str
        Ordered list of text chunks, each at most ``chunk_length`` characters.
    """
    chunks = []
    current_chunk = ""
    while len(text) > 0:
        end_index = min(len(text), chunk_length)
        while end_index > 0 and text[end_index - 1] not in (".", "!", "?"):
            end_index -= 1
        if end_index == 0:
            end_index = chunk_length
        current_chunk += text[:end_index]
        text = text[end_index:]
        if len(text) == 0 or len(current_chunk) + len(text) > chunk_length:
            chunks.append(current_chunk)
            current_chunk = ""
    return chunks


async def send_message_to_channel(
    message: str,
    obj: disnake.Message | disnake.ApplicationCommandInteraction,
    *,
    dont_tag_user: bool = False,
) -> list[disnake.Message]:
    """Send a message to the channel associated with a Discord object.

    If ``message`` exceeds ``MAX_MESSAGE_LENGTH``, it is split into chunks via
    :func:`split_text_into_chunks` and sent as multiple consecutive messages.
    The author mention is prepended to the first chunk only.

    Parameters
    ----------
    message : str
        The text content to send.
    obj : disnake.Message or disnake.ApplicationCommandInteraction
        The Discord object whose channel and author are used as the send
        target and mention source respectively.
    dont_tag_user : bool, optional
        When ``True``, the author mention is omitted from all messages.
        Defaults to ``False``.

    Returns
    -------
    list of disnake.Message
        All message objects sent to the channel, in order.
    """
    sent_messages = []
    if len(message) > MAX_MESSAGE_LENGTH:
        for i, chunk in enumerate(split_text_into_chunks(message, MAX_MESSAGE_LENGTH)):
            mention = obj.author.mention if not dont_tag_user else ""
            sent = await obj.channel.send(f"{mention if i == 0 else ''} {chunk}")
            sent_messages.append(sent)
    else:
        mention = obj.author.mention if not dont_tag_user else ""
        sent = await obj.channel.send(f"{mention} {message}")
        sent_messages.append(sent)
    return sent_messages
