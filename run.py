#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Slashbot is another discord bot using slash commands. The sole purpose of
this bot is to sometimes annoy Gareth with its useful information.
"""

import logging
import time
from typing import Coroutine

import disnake
from disnake.ext import commands

import slashbot.cogs.admin
import slashbot.cogs.archive
import slashbot.cogs.chat
import slashbot.cogs.content
import slashbot.cogs.info
import slashbot.cogs.remind
import slashbot.cogs.schedule
import slashbot.cogs.spam
import slashbot.cogs.users
import slashbot.cogs.videos
import slashbot.cogs.weather

from slashbot.config import App
from slashbot.custom_bot import ModifiedInteractionBot
from slashbot.db import migrate_old_json_to_db

logger = logging.getLogger(App.config("LOGGER_NAME"))
logger.info("Initializing Slashbot...")
start = time.time()

# Set up the bot and cogs --------------------------------------------------

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True

bot = ModifiedInteractionBot(intents=intents)

for cog in [
    slashbot.cogs.admin.AdminCommands(bot, App.config("LOGFILE_NAME")),
    slashbot.cogs.archive.ArchiveCommands(bot),
    slashbot.cogs.chat.Chat(bot),
    slashbot.cogs.content.ContentCommands(bot),
    slashbot.cogs.info.InfoCommands(bot),
    slashbot.cogs.remind.ReminderCommands(bot),
    slashbot.cogs.schedule.ScheduledPosts(bot),
    slashbot.cogs.spam.SpamCommands(bot),
    slashbot.cogs.users.UserCommands(bot),
    slashbot.cogs.videos.VideoCommands(bot),
    slashbot.cogs.weather.WeatherCommands(bot),
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


@bot.event
async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception) -> Coroutine:
    """Handle different types of errors.

    Parameters
    ----------
    error: Exception
        The error that occurred.
    """
    logger.error("%s for %s failed with error:", inter.application_command.name, inter.author.name)
    logger.error("%s", error)
    print(error)

    if isinstance(error, commands.errors.CommandOnCooldown):
        return await inter.response.send_message("This command is on cooldown for you.", ephemeral=True)

    if isinstance(error, disnake.NotFound):
        return await inter.response.send_message("The Discord API failed for some reason.", ephemeral=True)


# This finally runs the bot

bot.run(App.config("BOT_TOKEN"))
