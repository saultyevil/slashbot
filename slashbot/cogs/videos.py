#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for sending videos, and scheduled videos."""

import datetime
import logging
import random
from types import coroutine

import disnake
from disnake.ext import commands

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.markov import MARKOV_MODEL, generate_sentences_for_seed_words

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


class Videos(SlashbotCog):
    """Send short clips to the channel."""

    def __init__(self, bot: commands.InteractionBot):
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        """
        super().__init__()
        self.bot = bot

        self.markov_sentences = (
            generate_sentences_for_seed_words(
                MARKOV_MODEL,
                [
                    "admin",
                    "admin abuse",
                ],
                1,  # these only happen once in a while, so dont need a big bank of them
            )
            if self.bot.markov_gen_on
            else {"admin": [], "admin abuse": []}
        )

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="admin_abuse", description="admin abuse!!! you're the worst admin ever!!!")
    async def admin_abuse(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a clip of someone shouting admin abuse.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        seed = random.choice(["admin", "admin abuse"])
        return await inter.edit_original_message(
            content=f"{self.get_generated_sentence(seed)}", file=disnake.File("data/videos/admin_abuse.mp4")
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="goodbye", description="goodbye")
    async def goodbye(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a clip of Marko saying goodbye.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        return await inter.edit_original_message(file=disnake.File("data/videos/goodbye.mp4"))

    @commands.cooldown(1, App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="good_morning", description="good morning people")
    async def good_morning(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a video of Marko saying good morning people.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        time = datetime.datetime.now()
        if time.hour >= 12:
            lee_videos = [
                "data/videos/good_morning_afternoon_1.mp4",
                "data/videos/good_morning_afternoon_2.mp4",
                "data/videos/good_morning_afternoon_3.mp4",
            ]
        else:
            lee_videos = [
                "data/videos/good_morning_vlog.mp4",
                "data/videos/good_morning_still_is.mp4",
            ]

        video_choices = (1 * len(lee_videos) * ["data/videos/good_morning_people.mp4"]) + lee_videos
        video = random.choice(video_choices)

        return await inter.edit_original_message(file=disnake.File(video))

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="haha", description="haha very funny")
    async def laugh(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a clip of Marko laughing.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        await inter.response.defer()
        return await inter.edit_original_message(file=disnake.File("data/videos/marko_laugh.mp4"))
