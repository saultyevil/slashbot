#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Slashbot is another discord bot using slash commands. The sole purpose of
this bot is to sometimes annoy Gareth with its useful information.
"""

import argparse
import logging
import time
import traceback
from typing import Coroutine

import disnake
from disnake.ext import commands

import slashbot.cogs.admin

# import slashbot.cogs.archive
import slashbot.cogs.chat
import slashbot.cogs.image

# import slashbot.cogs.content
import slashbot.cogs.info
import slashbot.cogs.remind
import slashbot.cogs.scheduled_posts
import slashbot.cogs.spam
import slashbot.cogs.users
import slashbot.cogs.videos
import slashbot.cogs.weather
from slashbot import markov
from slashbot.config import App
from slashbot.custom_bot import SlashbotInterationBot
from slashbot.db import migrate_old_json_to_db

parser = argparse.ArgumentParser()
parser.add_argument(
    "--disable-auto-markov",
    help="Disable automatic markov sentence generation and revert to on-the-fly generation",
    action="store_false",
)
parser.add_argument(
    "--state-size",
    default=3,
    help="The state size of the Markov model to use",
    choices=[1, 2, 3, 4],
    type=int,
)
args = parser.parse_args()
App.set("MARKOV_STATE_SIZE", int(args.state_size))

logger = logging.getLogger(App.config("LOGGER_NAME"))
logger.info("Initializing Slashbot...")
start = time.time()

# Set up the bot and cogs --------------------------------------------------

intents = disnake.Intents.default()
intents.message_content = True
intents.messages = True
intents.members = True

bot = SlashbotInterationBot(
    markov_gen_on=args.disable_auto_markov,
    intents=intents,
)

markov.MARKOV_MODEL = markov.load_markov_model(App.config("MARKOV_CHAIN_FILE"))

for cog in [
    slashbot.cogs.admin.Admin(bot, App.config("LOGFILE_NAME")),
    # slashbot.cogs.archive.Archive(bot),
    slashbot.cogs.chat.Chat(bot),
    # slashbot.cogs.content.Content(bot),
    slashbot.cogs.image.ImageGen(bot),
    slashbot.cogs.info.Info(bot),
    slashbot.cogs.remind.Reminders(bot),
    slashbot.cogs.scheduled_posts.ScheduledPosts(bot),
    slashbot.cogs.spam.Spam(bot),
    slashbot.cogs.users.Users(bot),
    slashbot.cogs.videos.Videos(bot),
    slashbot.cogs.weather.Weather(bot),
]:
    bot.add_cog(cog)


# Bot events ---------------------------------------------------------------


@bot.event
async def on_connect() -> None:
    """_summary_

    Returns
    -------
    _type_
        _description_
    """
    await migrate_old_json_to_db(bot)


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

    user = await bot.fetch_user(App.config("ID_BOT"))
    App.set("BOT_USER_OBJECT", user)


@bot.event
async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception) -> Coroutine:
    """Handle different types of errors.

    Parameters
    ----------
    error: Exception
        The error that occurred.
    """
    stack = traceback.format_exception(type(error), error, error.__traceback__)
    logger.error("The command %s failed with error:\n%s", inter.application_command.name, "".join(stack))

    if isinstance(error, commands.errors.CommandOnCooldown):
        return await inter.response.send_message("This command is on cooldown for you.", ephemeral=True)

    if isinstance(error, disnake.NotFound):
        return await inter.response.send_message("The Discord API failed for some reason.", ephemeral=True)


# This finally runs the bot

bot.run(App.config("BOT_TOKEN"))
