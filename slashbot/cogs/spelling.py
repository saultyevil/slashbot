#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This cog contains commands and tasks to bully people."""

# TODO: command to add words to dictionary

import asyncio
import datetime
import logging
import re
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
        self.incorrect_spellings = defaultdict(lambda: {"word_count": 0, "unknown_words": []})
        self.spellchecker = SpellChecker(case_sensitive=False)
        self.spelling_summary.start()  # pylint: disable=no-member

    @staticmethod
    def _cleanup_message(text: str) -> str:
        """Remove certain parts of a string, so spell checking is cleaner.

        Parameters
        ----------
        text : str
            The string to clean up.

        Returns
        -------
        str
            The cleaned up string.
        """
        # remove discord mentions
        clean_text = re.sub(r"@(\w+|\d+)", "", text.lower())
        # remove code wrappings, so we don't get any code
        clean_text = re.sub(r"`[^`]+`", "", clean_text)
        clean_text = re.sub(r"```[^`]+```", "", clean_text, flags=re.DOTALL)
        # remove numbers and non-word characters
        clean_text = re.sub(r"[0-9]+|\W+|<[^>]+>", " ", clean_text)

        return clean_text

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
        if not message.guild or message.author.bot:
            return
        guild_key = str(message.guild.id)
        if guild_key not in App.get_config("SPELLCHECK_SERVERS"):
            return
        if message.author.id not in App.get_config("SPELLCHECK_SERVERS")[guild_key]:
            return

        words = self._cleanup_message(message.content)
        unknown_words = self.spellchecker.unknown(words.split())
        key = f"{message.author.display_name}+{message.channel.id}"

        self.incorrect_spellings[key]["word_count"] += len(words.split())
        self.incorrect_spellings[key]["unknown_words"] += unknown_words

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

        for key, value in self.incorrect_spellings.items():
            mistakes = sorted(set(value["unknown_words"]))  # remove duplicates with a set
            if len(mistakes) == 0:  # this shouldn't happen
                continue
            word_count = int(value["word_count"])
            percent_wrong = float(len(mistakes)) / float(word_count) * 100.0

            user_name, channel_id = key.split("+")
            channel = await self.bot.fetch_channel(channel_id)
            corrections = [
                correction if (correction := self.spellchecker.correction(mistake)) is not None else "unknown"
                for mistake in mistakes
            ]
            actual_mistakes = [
                f"{correction} ({mistake})"
                for mistake, correction in zip(mistakes, corrections)
                if re.sub(r"[0-9]+|\W+|<[^>]+>", " ", correction) != mistake
            ]

            await channel.send(
                f"**{user_name.capitalize()}** made {len(actual_mistakes)} spelling mistakes, which is "
                + f"{percent_wrong:.1f}% of the words they sent. They spelt the following words incorrectly:  "
                + ", ".join(actual_mistakes),
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
