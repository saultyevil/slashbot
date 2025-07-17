"""Commands for getting the weather."""

from slashbot.bot.custom_types import ApplicationCommandInteraction


async def deferred_error_message(
    inter: ApplicationCommandInteraction,
    message: str,
    delay: int = 30,
) -> None:
    """Send and delete an error message for a delayed response.

    Parameters
    ----------
    inter : ApplicationCommandInteraction
        The deferred interaction.
    message : str
        An error message to send to chat.
    delay : int, optional
        The delay (in seconds) before the error message is deleted, by
        default 30

    """
    await inter.edit_original_message(content=message)
    await inter.delete_original_message(delay=delay)
