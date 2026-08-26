"""Commands for getting the weather."""

from slashbot.bot.custom_types import ApplicationCommandInteraction
from slashbot.logger import Logger

LOGGER = Logger(prepend_msg="[Discord errors]")


async def deferred_error_response(
    inter: ApplicationCommandInteraction,
    message: str,
    delay: int = 10,
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
    try:
        await inter.edit_original_message(content=message)
        await inter.delete_original_message(delay=delay)
    except Exception:
        LOGGER.log_exception("Failed to deliver deferred error response")
        raise
    LOGGER.log_debug("Delivered deferred error response")
