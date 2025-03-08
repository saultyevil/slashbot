"""Configure and run the Discord bot.

This script will create a modified InteractionBot class and run it depending on
command line arguments. This script is typically called inside the root
directory of the repository or within the provided docker compose.

Disnake is used as the API client.
"""

import argparse
import datetime
import logging
import os
import time
import traceback

import disnake
from disnake.ext import commands
from slashlib import markov
from slashlib.config import Bot

from slashbot.custom_bot import SlashbotInterationBot

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
    action="store_true",
    dest="enable_auto_markov",
)
args = parser.parse_args()

logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))
logger.info("Initializing Slashbot...")
start = time.time()

if args.development:
    logger.setLevel(logging.DEBUG)
    logger.debug("Disabling automatic markov generation for development mode")
    args.enable_auto_markov = False
else:
    logger.setLevel(logging.INFO)

logger.info("Config file: %s", Bot.get_config("CONFIG_FILE"))

# Set up the bot and cogs ------------------------------------------------------

markov.MARKOV_BANK = markov.load_markov_bank("data/markov/markov-sentences.json")

intents = disnake.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True

bot = SlashbotInterationBot(
    enable_markov_gen=args.enable_auto_markov,
    intents=intents,
    reload=bool(args.development),
)


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
    logger.exception("on_error:")


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
    logger.exception("The command %s failed with error:\n%s", inter.application_command.name, "".join(stack))

    # Delete the original response if it's older than 2.5 seconds and respond
    # to the follow up instead
    time_since_created = datetime.datetime.now(datetime.UTC) - inter.created_at
    if time_since_created > datetime.timedelta(seconds=2.5):
        inter = inter.followup
        try:
            original_message = await inter.original_response()
            await original_message.delete()
        except disnake.HTTPException:
            pass

    if isinstance(error, commands.errors.CommandOnCooldown):
        await inter.response.send_message("This command is on cooldown for you.", ephemeral=True)
    if isinstance(error, disnake.NotFound):
        await inter.response.send_message("Failed to communicate with the Discord API.", ephemeral=True)


bot.load_extensions("slashbot/cogs")

if args.development:
    bot.run(os.getenv("SLASHBOT_DEVELOPMENT_TOKEN"))
else:
    bot.run(os.getenv("SLASHBOT_TOKEN"))
