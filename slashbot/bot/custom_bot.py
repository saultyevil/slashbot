"""Modified InteractionBot class."""

from collections.abc import Callable, Iterable
from typing import Any

from disnake.ext.commands import InteractionBot

from slashbot.core import markov
from slashbot.core.database import Database
from slashbot.core.logger import Logger
from slashbot.settings import BotSettings


class CustomInteractionBot(InteractionBot, Logger):
    """InteractionBot class for Slashbot.

    This is a modified version of disnake.ext.commands.InteractionBot.
    """

    def __init__(self, *, enable_markov_cache: bool = False, **kwargs: Any) -> None:
        """Initialise the bot.

        Parameters
        ----------
        enable_markov_cache: bool
            Whether or not to enable automatic Markov sentence generation,
            default is False.
        **kwargs : int
            The keyword arguments to pass to the parent class.

        """
        super().__init__(**kwargs)
        Logger.__init__(self)
        self.cleanup_functions = []
        self.times_connected = 0
        self.db = Database(BotSettings.files.database)
        self.use_markov_cache = enable_markov_cache and markov.MARKOV_MODEL
        if markov.MARKOV_MODEL:
            self.log_info(
                "Automatic Markov sentence generation is %s",
                "enabled" if self.use_markov_cache else "disabled",
            )

    def add_function_to_cleanup(self, message: str | None, function: Callable, args: Iterable[Any]) -> None:
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
                self.log_info("%s", function["message"])

            if function["args"]:
                await function["function"](*function["args"])
            else:
                await function["function"]()

        await super().close()

    async def initialise_database(self) -> None:
        """Initialise the database.

        This will create the database if it does not exist, and create the
        tables if they do not exist.

        """
        if not self.db:
            self.db = Database(BotSettings.files.database)
        await self.db.init()
