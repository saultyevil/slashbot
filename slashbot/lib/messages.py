"""Module for general purpose message handling."""

import logging

from slashbot.lib.config import BotConfig
from slashbot.lib.custom_types import ApplicationCommandInteraction, Message
from slashbot.lib.util import split_text_into_chunks
from slashbot.lib.vision import Image, download_and_encode_image

LOGGER = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))
MAX_MESSAGE_LENGTH = BotConfig.get_config("MAX_CHARS")


async def send_message_to_channel(
    message: str, obj: Message | ApplicationCommandInteraction, *, dont_tag_user: bool = False
) -> None:
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


async def get_attached_images_from_message(message: Message) -> list[Image]:
    """Retrieve the URLs for images attached or embedded in a Discord message.

    Parameters
    ----------
    message : Message
        The Discord message object to extract image URLs from.

    Returns
    -------
    List[Image]
        A list of `Image` dataclasses containing the URL, base64-encoded image
        data and the MIME type of the image.

    """
    # DeepSeek doesn't support vision as of current implementation 28/01/2025
    if BotConfig.get_config("AI_CHAT_CHAT_MODEL") in ["deepseek-chat", "deepseek-reasoner", "o3-mini"]:
        LOGGER.debug("Vision not supported in current model %s", BotConfig.get_config("AI_CHAT_CHAT_MODEL"))
        return []

    image_urls = []  # Start off with empty list, which makes it clearer we will always returns a list
    image_urls += [attachment.url for attachment in message.attachments if attachment.content_type.startswith("image/")]
    image_urls += [embed.image.proxy_url for embed in message.embeds if embed.image]
    image_urls += [embed.thumbnail.proxy_url for embed in message.embeds if embed.thumbnail]

    result = []
    for url in image_urls:
        try:
            result.append(download_and_encode_image(url))
        except Exception:
            LOGGER.exception("Failed to download image from %s", url)
    return result
