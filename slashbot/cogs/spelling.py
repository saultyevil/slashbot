#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This cog contains commands and tasks to bully people."""

# TODO: command to add words to dictionary

import asyncio
import datetime
import logging
import re
from collections import defaultdict
from typing import List

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
        super().__init__(bot)
        self.incorrect_spellings = defaultdict(lambda: {"word_count": 0, "unknown_words": []})
        self.spellchecker = SpellChecker(case_sensitive=False)
        self.spelling_summary.start()  # pylint: disable=no-member
        self.custom_words = self.get_custom_words()

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="add_word_to_dict",
        description="Add a word to the custom dictionary for the spelling summary",
        guild_ids=[int(guild_id) for guild_id in App.get_config("SPELLCHECK_SERVERS").keys()],
    )
    async def add_word_to_dict(
        self,
        inter: disnake.ApplicationCommandInteraction,
        word: str = commands.Param(
            name="word", description="The word to add to the dictionary", min_length=2, max_length=64
        ),
    ):
        """Add a word to the custom dictionary.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        word : str
            The word to add to the dictionary.
        """
        word_lower = word.lower()
        if word_lower in self.custom_words:
            return await inter.response.send_message(f"The word '{word}' is already in the dictionary.", ephemeral=True)
        self.custom_words.append(word_lower)
        with open(App.get_config("SPELLCHECK_CUSTOM_DICTIONARY"), "w", encoding="utf-8") as file_out:
            file_out.write("\n".join(self.custom_words))

        await inter.response.send_message(f"Added '{word_lower}' to dictionary.", ephemeral=True)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="remove_word_from_dict",
        description="Remove a word from the custom dictionary for the spelling summary",
        guild_ids=[int(guild_id) for guild_id in App.get_config("SPELLCHECK_SERVERS").keys()],
    )
    async def remove_word_from_dict(
        self,
        inter: disnake.ApplicationCommandInteraction,
        word: str = commands.Param(
            name="word", description="The word to remove from the dictionary", min_length=2, max_length=64
        ),
    ):
        """Add a word to the custom dictionary.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        word : str
            The word to add to the dictionary.
        """
        word_lower = word.lower()
        if word_lower not in self.custom_words:
            return await inter.response.send_message(f"The word '{word}' is not in the dictionary.", ephemeral=True)
        self.custom_words.remove(word_lower)
        with open(App.get_config("SPELLCHECK_CUSTOM_DICTIONARY"), "w", encoding="utf-8") as file_out:
            file_out.write("\n".join(self.custom_words))

        await inter.response.send_message(f"Removed '{word_lower}' from dictionary.", ephemeral=True)

    @staticmethod
    def get_custom_words() -> List[str]:
        """Get a list of custom dictionary words.

        These are checked in addition to the unknown words in spellchecker.

        Returns
        -------
        List[str]
            The list of words in the custom dictionary.
        """
        try:
            with open(App.get_config("SPELLCHECK_CUSTOM_DICTIONARY"), "r", encoding="utf-8") as file_in:
                return list(set([line.strip() for line in file_in.readlines()]))
        except IOError:
            logger.error("No dictionary found at %s", App.get_config("SPELLCHECK_CUSTOM_DICTIONARY"))
            return []

    @staticmethod
    def cleanup_message(text: str) -> str:
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

        words = self.cleanup_message(message.content)
        unknown_words = self.spellchecker.unknown(words.split())
        unknown_words = list(filter(lambda w: w not in self.custom_words, unknown_words))
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
