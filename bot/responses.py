from bot.types import InteractionReference, Message


async def is_reply_to_slash_command_response(message: Message) -> bool:
    """Check if a message is in response to a slash command.

    Parameters
    ----------
    message : Message
        The message to check.

    Returns
    -------
    bool
        If the message is a reply to a slash command, True is returned.
        Otherwise, False is returned.

    """
    if not message.reference:
        return False

    reference = message.reference
    old_message = (
        reference.cached_message if reference.cached_message else await message.channel.fetch_message(message.id)
    )

    # can't see how this can happen (unless no message intents, but then the
    # chat cog won't work at all) but should take into account just in case
    if not old_message:
        return False

    # if old_message is an interaction response, this will return true
    return isinstance(old_message.interaction, InteractionReference)
