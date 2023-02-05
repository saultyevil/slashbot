#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Slashbot is another discord bot using slash commands. The sole purpose of
this bot is to sometimes annoy Gareth with its useful information.
"""

import logging
import time

import disnake
from disnake.ext import commands

import slashbot.cogs.admin
import slashbot.cogs.ai
import slashbot.cogs.content
import slashbot.cogs.info
import slashbot.cogs.remind
import slashbot.cogs.spam
import slashbot.cogs.users
import slashbot.cogs.videos
import slashbot.cogs.weather

from slashbot.config import App
from slashbot.bot import ModifiedInteractionBot

logger = logging.getLogger(App.config("LOGGER_NAME"))
start = time.time()

# Load in the markov chain and various other bits of data that are passed to
# the cogs

with open(App.config("BAD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
    bad_words = file_in.readlines()[0].split()

with open(App.config("GOD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
    god_words = file_in.read().splitlines()

# Set up the bot and cogs --------------------------------------------------

# Create bot and the various different cogs -- cogs are declared like this
# because I cheat a little and pass spam.generate_sentence to other cogs.
# Ideally I should just write generate_sentence into some global module and
# import it in the cogs instead


bot = ModifiedInteractionBot(intents=disnake.Intents.default())

for cog in [
    slashbot.cogs.spam.Spam(bot, bad_words, god_words),
    slashbot.cogs.info.Info(bot, bad_words, god_words),
    slashbot.cogs.remind.Reminder(bot),
    slashbot.cogs.content.Content(bot),
    slashbot.cogs.weather.Weather(bot),
    slashbot.cogs.videos.Videos(bot, bad_words),
    slashbot.cogs.users.Users(bot),
    slashbot.cogs.admin.Admin(bot, App.config("LOGFILE_NAME")),
    slashbot.cogs.ai.AI(bot),
]:
    bot.add_cog(cog)

# bot.add_to_cleanup(None, update_markov_chain_for_model, [None])

# Bot events ---------------------------------------------------------------


@bot.event
async def on_ready() -> None:
    """Information to print on bot launch."""
    logger.info("Logged in as %s in the current servers:", bot.user)

    for n_server, server in enumerate(bot.guilds):
        logger.info("\t%d). %s (%d)", n_server, server.name, server.id)

    logger.info("Started in %.2f seconds", time.time() - start)


@bot.event
async def on_slash_command_error(inter: disnake.ApplicationCommandInteraction, error: Exception) -> None:
    """Handle different types of errors.

    Parameters
    ----------
    error: Exception
        The error that occurred.
    """
    logger.error("%s for %s failed with error:", inter.application_command.name, inter.author.name)
    logger.error("%s", error)

    if isinstance(error, commands.errors.CommandOnCooldown):
        return await inter.response.send_message("This command is on cool down for you.", ephemeral=True)


# This finally runs the bot

bot.run(App.config("BOT_TOKEN"))
