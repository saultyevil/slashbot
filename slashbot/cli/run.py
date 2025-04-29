"""Configure and run the Discord bot.

This script will create a modified InteractionBot class and run it depending on
command line arguments. This script is typically called inside the root
directory of the repository or within the provided docker compose.

Disnake is used as the API client.
"""

import argparse
import asyncio
import datetime
import logging
import time
import traceback
from collections.abc import Callable
from typing import Any

import disnake
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.core import markov
from slashbot.settings import BotSettings
from slashbot.core.logger import setup_logging

LAUNCH_TIME = time.time()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments for the bot.

    Returns
    -------
    argparse.Namespace
        The parsed command line arguments.

    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug",
        help="Launch the bot in development mode, which enables debug logging, cog reloading and disables automated markov generation",
        action="store_true",
    )
    parser.add_argument(
        "--on-the-fly-markov",
        help="Use on-the-fly markov sentence generation instead of pre-generated markov sentences",
        default=False,
        action="store_true",
        dest="on_the_fly_markov",
    )
    parser.add_argument(
        "--enable-markov-cache",
        help="Enable markov sentence pre-generation to cache sentences for certain seed words",
        action="store_true",
        dest="enable_markov_cache",
        default=False,
    )
    return parser.parse_args()


def create_on_ready(bot: CustomInteractionBot) -> Callable:
    """Closure for the on_ready event.

    Parameters
    ----------
    bot : SlashbotInterationBot
        The bot.

    """

    async def on_ready() -> None:
        bot.times_connected += 1

        if bot.times_connected == 1:
            bot.log_info("Logged in as %s in the current servers:", bot.user)
            for n_server, server in enumerate(bot.guilds):
                bot.log_info("\t%d). %s (%d)", n_server, server.name, server.id)
            bot.log_info("Started in %.2f seconds", time.time() - LAUNCH_TIME)
        else:
            bot.log_info("Bot reconnected")

    return on_ready


def create_on_error(bot: CustomInteractionBot) -> Callable:
    """Closure for on_error event.

    Parameters
    ----------
    bot : SlashbotInterationBot
        The bot.

    """

    async def on_error(_event: Any, *_args: Any, **_kwargs: Any) -> None:
        bot.log_exception("on_error:")

    return on_error


def create_on_slash_command_error(bot: CustomInteractionBot) -> Callable:
    """Closure for on_slash_command_error event.

    Parameters
    ----------
    bot : SlashbotInterationBot
        The bot.

    """

    async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception) -> None:
        stack = traceback.format_exception(type(error), error, error.__traceback__)
        bot.log_exception("The command %s failed with error:\n%s", inter.application_command.name, "".join(stack))

        # Delete the original response if it's older than 2.5 seconds and respond
        # to the follow up instead
        time_since_created = datetime.datetime.now(datetime.UTC) - inter.created_at
        if time_since_created > datetime.timedelta(seconds=2.5):
            respond_to = inter.followup.send
        else:
            respond_to = inter.response.send_message

        if isinstance(error, commands.errors.CommandOnCooldown):
            await respond_to("This command is on cooldown for you.", ephemeral=True)
        if isinstance(error, disnake.NotFound):
            await respond_to("Failed to communicate with the Discord API.", ephemeral=True)

    return on_slash_command_error


def initialise_bot(args: argparse.Namespace) -> CustomInteractionBot:
    """Initialise the bot instance.

    Parameters
    ----------
    args : argparse.Namespace
        The command line arguments.

    Returns
    -------
    CustomInteractionBot
        The initialised bot instance.

    """
    intents = disnake.Intents.default()
    intents.message_content = True
    intents.messages = True
    intents.members = True

    bot = CustomInteractionBot(
        enable_markov_cache=args.enable_markov_cache,
        intents=intents,
        reload=bool(args.debug),
    )

    if args.debug:
        bot.set_log_level(logging.DEBUG)

    bot.log_info("Initializing... %s", args)
    bot.log_info("Config file: %s", BotSettings.config_file)

    if args.on_the_fly_markov:
        markov.MARKOV_MODEL = markov.load_markov_model("data/markov/chain.pickle")
    else:
        markov.MARKOV_BANK = markov.load_markov_bank("data/markov/markov-sentences.json")

    bot.load_extensions("slashbot/cogs")
    bot.add_listener(create_on_ready(bot))
    bot.add_listener(create_on_error(bot))
    bot.add_listener(create_on_slash_command_error(bot))

    event_loop = asyncio.get_event_loop()
    event_loop.run_until_complete(bot.initialise_database())

    for cog in bot.cogs.values():
        if args.debug:
            cog.set_log_level(logging.DEBUG)  # type: ignore  # noqa: PGH003

    return bot


def main() -> int:
    """Run Slashbot."""
    setup_logging()
    args = parse_args()
    bot = initialise_bot(args)

    try:
        if args.debug:
            bot.run(BotSettings.keys.development_token)
        else:
            bot.run(BotSettings.keys.run_token)
    except TypeError:
        bot.log_error("No Discord token provided.")
        return 1

    return 0


if __name__ == "__main__":
    main()
