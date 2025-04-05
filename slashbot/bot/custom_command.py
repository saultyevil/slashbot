import logging
from collections.abc import Callable, Coroutine
from typing import Any

from disnake.ext import commands

from slashbot.settings import BotSettings

COOLDOWN_USER = commands.BucketType.user
COOLDOWN_STANDARD = BotSettings.cooldown.standard
COOLDOWN_RATE = BotSettings.cooldown.rate
LOGGER = logging.getLogger(BotSettings.logging.logger_name)


def slash_command_with_cooldown(
    **kwargs,  # noqa: ANN003
) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], commands.InvokableSlashCommand]:
    """Add a cooldown and slash command functionality to a function.

    Parameters
    ----------
    **kwargs : Any
        Additional keyword arguments to pass to the slash_command decorator.

    Returns
    -------
    Callable[[Callable[..., Coroutine[Any, Any, Any]]], Coroutine[Any, Any, Any]]
        Decorated function.

    """

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> commands.InvokableSlashCommand:
        """Decorate a function with cooldown and slash command functionality.

        Parameters
        ----------
        func : Callable[..., Coroutine[Any, Any, Any]]
            Function to decorate.

        Returns
        -------
        commands.InvokableSlashCommand
            Decorated function.

        """
        func = commands.cooldown(COOLDOWN_RATE, COOLDOWN_STANDARD, COOLDOWN_USER)(func)
        return commands.slash_command(**kwargs)(func)

    return decorator
