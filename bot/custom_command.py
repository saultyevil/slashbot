import logging
from collections.abc import Callable, Coroutine
from typing import Any

from disnake.ext import commands

from slashbot.config import App

COOLDOWN_USER = commands.BucketType.user
COOLDOWN_STANDARD = App.get_config("COOLDOWN_STANDARD")
COOLDOWN_RATE = App.get_config("COOLDOWN_RATE")
LOGGER = logging.getLogger(App.get_config("LOGGER_NAME"))


def cooldown_and_slash_command(
    **kwargs,  # noqa: ANN003
) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], Coroutine[Any, Any, Any]]:
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

    def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> Coroutine[Any, Any, Any]:
        """Decorate a function with cooldown and slash command functionality.

        Parameters
        ----------
        func : Callable[..., Coroutine[Any, Any, Any]]
            Function to decorate.

        Returns
        -------
        Coroutine[Any, Any, Any]
            Decorated function.

        """
        func = commands.cooldown(COOLDOWN_RATE, COOLDOWN_STANDARD, COOLDOWN_USER)(func)
        return commands.slash_command(**kwargs)(func)

    return decorator
