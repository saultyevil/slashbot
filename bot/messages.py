from bot.types import ApplicationCommandInteraction, Message
from slashbot.config import App
from slashbot.util import get_image_from_url, resize_image, split_text_into_chunks

MAX_MESSAGE_LENGTH = App.get_config("MAX_CHARS")


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
    if len(message) > MAX_MESSAGE_LENGTH:
        response_chunks = split_text_into_chunks(message, MAX_MESSAGE_LENGTH)
        for i, response_chunk in enumerate(response_chunks):
            user_mention = obj.author.mention if not dont_tag_user else ""
            await obj.channel.send(f"{user_mention if i == 0 else ''} {response_chunk}")
    else:
        await obj.channel.send(f"{obj.author.mention if not dont_tag_user else ''} {message}")


async def get_attached_images_from_message(message: Message) -> list[str]:
    """Retrieve the URLs for images attached or embedded in a Discord message.

    Parameters
    ----------
    message : Message
        The Discord message object to extract image URLs from.

    Returns
    -------
    List[str]
        A list of base64-encoded image data strings for the images attached
        or embedded in the message.

    """
    image_urls = [attachment.url for attachment in message.attachments if attachment.content_type.startswith("image/")]
    image_urls += [embed.image.proxy_url for embed in message.embeds if embed.image]
    image_urls += [embed.thumbnail.proxy_url for embed in message.embeds if embed.thumbnail]
    num_found = len(image_urls)

    if num_found == 0:
        return []
    images = await get_image_from_url(image_urls)

    return [{"type": image["type"], "image": resize_image(image["image"], image["type"])} for image in images]