#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Modified InteractionBot class.
"""

import logging
from collections.abc import Iterable
from typing import Any

from disnake.ext import commands

from slashbot.config import App

logger = logging.getLogger(App.config("LOGGER_NAME"))


class ModifiedInteractionBot(commands.InteractionBot):
    """Bot is a modified version of disnake.ext.commands.InteractionBot which
    includes a function to add additional clean up functions when the bot
    is exited, e.g. with ctrl+c.
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the class."""
        super().__init__(**kwargs)
        self.cleanup_functions = []
        self.times_connected = 0

    def add_to_cleanup(self, message: str | None, function: callable, args: Iterable[Any]) -> None:
        """Add a function to the cleanup list.

        Parameters
        ----------
        message: str
            A message to print when running the function
        function: callable
            The function to add to the clean up routine.
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
