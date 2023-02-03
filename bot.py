#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Slashbot is another discord bot using slash commands. The sole purpose of
this bot is to sometimes annoy Gareth with its useful information.
"""

import logging
import os
import pickle
import time

import disnake
from disnake.ext import commands

import cogs.admin
import cogs.ai
import cogs.content
import cogs.info
import cogs.remind
import cogs.spam
import cogs.users
import cogs.videos
import cogs.weather
from slashbot import markovify
from slashbot.bot import ModifiedInteractionBot
from slashbot.config import App

logger = logging.getLogger(App.config("LOGGER_NAME"))
start = time.time()

# Load in the markov chain and various other bits of data that are passed to
# the cogs

markov_gen = markovify.Text("Jack is a naughty boy.", state_size=4)
if os.path.exists("data/chain.pickle"):
    with open("data/chain.pickle", "rb") as file_in:
        markov_gen.chain = pickle.load(file_in)

with open(App.config("BAD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
    bad_words = file_in.readlines()[0].split()

with open(App.config("GOD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
    god_words = file_in.read().splitlines()

# Set up the bot and cogs --------------------------------------------------

intents = disnake.Intents.default()
intents.members = True  # pylint: disable=assigning-non-slot
intents.messages = True  # pylint: disable=assigning-non-slot
intents.message_content = True  # pylint: disable=assigning-non-slot

# Create bot and the various different cogs -- cogs are declared like this
# because I cheat a little and pass spam.generate_sentence to other cogs.
# Ideally I should just write generate_sentence into some global module and
# import it in the cogs instead

bot = ModifiedInteractionBot(intents=intents)

spam = cogs.spam.Spam(bot, markov_gen, bad_words, god_words)
info = cogs.info.Info(bot, spam.generate_sentence, bad_words, god_words)
reminder = cogs.remind.Reminder(bot, spam.generate_sentence)
content = cogs.content.Content(bot, spam.generate_sentence)
weather = cogs.weather.Weather(bot, spam.generate_sentence)
videos = cogs.videos.Videos(bot, bad_words, spam.generate_sentence)
users = cogs.users.Users(bot)
admin = cogs.admin.Admin(bot, App.config("LOGFILE_NAME"))
ai = cogs.ai.AI(bot)

# Add all the cogs to the bot

bot.add_cog(spam)
bot.add_cog(info)
bot.add_cog(reminder)
bot.add_cog(content)
bot.add_cog(weather)
bot.add_cog(videos)
bot.add_cog(users)
bot.add_cog(admin)
bot.add_cog(ai)

# This part is adding various clean up functions to run when the bot
# closes, e.g. on keyboard interrupt

bot.add_to_cleanup(None, spam.update_markov_chain, [None])  # need to send a None to act as the interaction

# Bot events ---------------------------------------------------------------


@bot.event
async def on_ready():
    """Information to print on bot launch."""
    logger.info("Logged in as %s in the current servers:", bot.user)

    for n_server, server in enumerate(bot.guilds):
        logger.info("\t%d). %s (%d)", n_server, server.name, server.id)

    logger.info("Started in %.2f seconds", time.time() - start)


@bot.event
async def on_slash_command_error(inter, error):
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
