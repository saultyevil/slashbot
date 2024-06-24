"""Configure and run the Discord bot.

This script will create a modified InteractionBot class and run it depending on
command line arguments. This script is typically called inside the root
directory of the repository or within the provided docker compose.

Disnake is used as the API client.
"""

import argparse
import logging
import os
import time
import traceback

import disnake
from disnake.ext import commands

from bot.custom_bot import SlashbotInterationBot
from lib import markov
from lib.config import App

# Parse command line arguments, which configure the bot

parser = argparse.ArgumentParser()
parser.add_argument(
    "-d",
    "--development",
    help="Launch the bot in development mode, which enables debug logging, cog reloading and disables automated markov generation",
    action="store_true",
)
parser.add_argument(
    "--disable-auto-markov",
    help="Disable automatic markov sentence generation and revert to on-the-fly generation",
    action="store_false",
)
args = parser.parse_args()

logger = logging.getLogger(App.get_config("LOGGER_NAME"))
logger.info("Initializing Slashbot...")
start = time.time()

if args.development:
    logger.debug("Disabling automatic markov generation for development mode")
    args.disable_auto_markov = False
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

# Load the markov model

markov.MARKOV_MODEL = markov.load_markov_model("data/markov/chain.pickle", 2)

# Set up the bot and cogs ------------------------------------------------------

intents = disnake.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True

bot = SlashbotInterationBot(
    enable_markov_gen=args.disable_auto_markov,
    intents=intents,
    reload=bool(args.development),
)

bot.load_extensions("bot/cogs")

# Define some global bot events


@bot.event
async def on_ready() -> None:
    """Information to print on bot launch."""
    bot.times_connected += 1

    if bot.times_connected == 1:
        logger.info("Logged in as %s in the current servers:", bot.user)

        for n_server, server in enumerate(bot.guilds):
            logger.info("\t%d). %s (%d)", n_server, server.name, server.id)

        logger.info("Started in %.2f seconds", time.time() - start)
    else:
        logger.info("Bot reconnected")


@bot.event
async def on_error(_event, *_args, **_kwargs) -> None:
    """Print exceptions to the logfile."""
    logger.error("%s", traceback.print_exc())


@bot.event
async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception) -> None:
    """Handle different types of errors.

    Parameters
    ----------
    inter : disnake.ApplicationCommandInteraction
        The interaction that failed.
    error: Exception
        The error that occurred.

    """
    stack = traceback.format_exception(type(error), error, error.__traceback__)
    logger.error("The command %s failed with error:\n%s", inter.application_command.name, "".join(stack))

    if isinstance(error, commands.errors.CommandOnCooldown):
        await inter.response.send_message("This command is on cooldown for you.", ephemeral=True)
        return
    if isinstance(error, disnake.NotFound):
        await inter.response.send_message("The Discord API failed for some reason.", ephemeral=True)
        return


# This finally runs the bot

if args.development:
    bot.run(os.getenv("SLASHBOT_DEVELOPMENT_TOKEN"))
else:
    bot.run(os.getenv("SLASHBOT_TOKEN"))
