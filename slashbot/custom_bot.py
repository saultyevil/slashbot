"""Modified InteractionBot class."""

import logging
from collections.abc import Iterable
from typing import Any

from disnake.ext import commands
from slashlib.config import Bot
from slashlib.markov import MARKOV_MODEL

logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))


class SlashbotInterationBot(commands.InteractionBot):
    """InteractionBot class for Slashbot.

    This is a modified version of disnake.ext.commands.InteractionBot.
    """

    def __init__(self, *, enable_markov_gen: bool = False, **kwargs: int) -> None:
        """Initialise the bot.

        Parameters
        ----------
        enable_markov_gen : bool
            Whether or not to enable automatic Markov sentence generation,
            default is False.
        **kwargs : int
            The keyword arguments to pass to the parent class.

        """
        super().__init__(**kwargs)
        self.cleanup_functions = []
        self.times_connected = 0
        self.markov_gen_enabled = enable_markov_gen and MARKOV_MODEL
        logger.info(
            "Automatic Markov sentence generation is %s",
            "enabled" if self.markov_gen_enabled else "disabled",
        )

    def add_function_to_cleanup(self, message: str | None, function: callable, args: Iterable[Any]) -> None:
        """Add a function to the cleanup list.

        Parameters
        ----------
        message: str
            A message to print when running the function
        function: callable
            The function to add to the cleanup routine.
        args: iterable | None
            The arguments to pass to the function.

        """
        self.cleanup_functions.append({"message": message, "function": function, "args": args})

    async def close(self) -> None:
        """Clean up things on close."""
        for function in self.cleanup_functions:
            if function["message"]:
                logger.info("%s", function["message"])

            if function["args"]:
                await function["function"](*function["args"])
            else:
                await function["function"]()

        await super().close()
