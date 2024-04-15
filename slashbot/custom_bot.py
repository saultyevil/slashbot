#!/usr/bin/env python3

"""Modified InteractionBot class."""

import logging
from collections.abc import Iterable
from typing import Any

from disnake.ext import commands

from slashbot.config import App

logger = logging.getLogger(App.get_config("LOGGER_NAME"))


class SlashbotInterationBot(commands.InteractionBot):
    """ "SlashbotInterationBot is a modified version of
    disnake.ext.commands.InteractionBot which includes a function to add
    additional clean up functions when the bot is exited, e.g. with ctrl+c.
    """

    def __init__(self, markov_gen_on: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self.cleanup_functions = []
        self.times_connected = 0
        self.markov_gen_on = markov_gen_on

        if self.markov_gen_on:
            logger.info("Automatic Markov sentence generation is enabled")
        else:
            logger.info("Automatic Markov sentence generation is disabled")

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
