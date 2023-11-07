#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This cog contains commands and tasks to bully people."""

import asyncio
import datetime
import logging
from collections import defaultdict

import disnake
from disnake.ext import commands, tasks
from spellchecker import SpellChecker

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog

COOLDOWN_USER = commands.BucketType.user
logger = logging.getLogger(App.get_config("LOGGER_NAME"))


class Spelling(SlashbotCog):
    """A cog for bullying people.

    The purpose of this cog is to bully Pip for his poor spelling.
    """

    def __init__(self, bot: commands.InteractionBot):
        super().__init__()
        self.bot = bot
        self.incorrect_spellings = defaultdict(list)
        self.spellchecker = SpellChecker()
        self.spelling_summary.start()  # pylint: disable=no-member

    @commands.Cog.listener("on_message")
    async def check_for_incorrect_spelling(self, message: disnake.Message):
        """Check a message for an incorrect spelling.

        At the moment, this will only run in the Bumpaper server.

        Parameters
        ----------
        message : disnake.Message
            The message to check.
        """
        if not App.get_config("SPELLCHECK_ENABLED"):
            return
        if not message.guild:
            return
        if message.author.id == self.bot.user.id:
            return
        if message.guild.id not in App.get_config("SPELLCHECK_SERVERS"):
            return

        self.incorrect_spellings[f"{message.author.display_name}+{message.channel.id}"] += self.spellchecker.unknown(
            message.clean_content.split(),
        )

    @tasks.loop(seconds=5)
    async def spelling_summary(self):
        """Print the misspellings of the day.

        The summary will be in a single message. This will run everyday at 5pm.
        """
        await self.bot.wait_until_ready()
        if not App.get_config("SPELLCHECK_ENABLED"):
            return

        now = datetime.datetime.now()
        target_time = datetime.time(hour=17, minute=0, second=0)
        target_datetime = datetime.datetime.combine(now, target_time)
        if now >= target_datetime:
            target_datetime += datetime.timedelta(days=1)
        time_to_target = target_datetime - now
        sleep_time = time_to_target.total_seconds()

        logger.info(
            "Waiting %d seconds/%d minutes/%.1f hours till spelling summary",
            sleep_time,
            sleep_time // 60,
            sleep_time / 3600,
        )
        await asyncio.sleep(sleep_time)

        for key, values in self.incorrect_spellings.items():
            mistakes = sorted(set(values))  # remove duplicates with a set
            if len(mistakes) == 0:  # this shouldn't happen
                continue

            user_name, channel_id = key.split("+")
            channel = await self.bot.fetch_channel(channel_id)
            corrections = [
                correction if (correction := self.spellchecker.correction(mistake)) is not None else "unknown"
                for mistake in mistakes
            ]
            message = [
                f"- {mistake.capitalize()} -> {correction.capitalize()}\n"
                for mistake, correction in zip(mistakes, corrections)
            ]
            await channel.send(
                f"{user_name} made spelling mistakes today:\n" + "".join(message),
            )

        self.incorrect_spellings.clear()


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(Spelling(bot))
