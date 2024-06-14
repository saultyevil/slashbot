#!/usr/bin/env python3

"""This cog contains commands and tasks to bully people."""

import asyncio
import logging
import re
from collections import defaultdict

import disnake
from disnake.ext import commands, tasks
from spellchecker import SpellChecker

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.util import calculate_seconds_until, join_list_max_chars

COOLDOWN_USER = commands.BucketType.user
logger = logging.getLogger(App.get_config("LOGGER_NAME"))


class Spelling(SlashbotCog):
    """A cog for bullying people.

    The purpose of this cog is to bully Pip for his poor spelling.
    """

    def __init__(self, bot: commands.InteractionBot):
        super().__init__(bot)
        self.incorrect_spellings = defaultdict(
            lambda: defaultdict(
                lambda: {"word_count": 0, "unknown_words": []},
            ),  # incorrect_spellings[guild_id][user_id]
        )
        self.spellchecker = SpellChecker(case_sensitive=False)
        self.spelling_summary.start()  # pylint: disable=no-member
        self.custom_words = self.get_custom_words()

        self.markov_sentences = ()

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
            name="word",
            description="The word to add to the dictionary",
            min_length=2,
            max_length=64,
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
            name="word",
            description="The word to remove from the dictionary",
            min_length=2,
            max_length=64,
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
    def get_custom_words() -> list[str]:
        """Get a list of custom dictionary words.

        These are checked in addition to the unknown words in spellchecker.

        Returns
        -------
        List[str]
            The list of words in the custom dictionary.

        """
        try:
            with open(App.get_config("SPELLCHECK_CUSTOM_DICTIONARY"), encoding="utf-8") as file_in:
                return list(set([line.strip() for line in file_in.readlines()]))
        except OSError:
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
        # remove apostrophes first
        clean_text = re.sub(r"'", "", clean_text)
        # remove numbers and non-word characters (excluding hyphens in words)
        clean_text = re.sub(r"[0-9]+|(?<!\w)-(?!\w)|[^\w\s-]|<[^>]+>", " ", clean_text)
        # replace multiple spaces with a single space
        clean_text = re.sub(r"\s+", " ", clean_text)

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
        if message.author.id not in App.get_config("SPELLCHECK_SERVERS")[guild_key]["USERS"]:
            return

        cleaned_content = self.cleanup_message(message.content)
        unknown_words = self.spellchecker.unknown(cleaned_content.split())
        unknown_words = list(filter(lambda w: w not in self.custom_words, unknown_words))

        self.incorrect_spellings[guild_key][str(message.author.id)]["word_count"] += len(message.content.split())
        self.incorrect_spellings[guild_key][str(message.author.id)]["unknown_words"] += unknown_words

    @tasks.loop(seconds=5)
    async def spelling_summary(self):
        """Print the misspellings of the day.

        The summary will be in a single message. This will run everyday at 5pm.
        """
        await self.bot.wait_until_ready()
        if not App.get_config("SPELLCHECK_ENABLED"):
            return

        sleep_time = calculate_seconds_until(-1, 17, 0, 1)

        logger.info(
            "Waiting %d seconds/%d minutes/%.1f hours till spelling summary",
            sleep_time,
            sleep_time // 60,
            sleep_time / 3600,
        )
        await asyncio.sleep(sleep_time)

        # first loop over the guild stuff
        for guild_id, user_spellings in self.incorrect_spellings.items():
            # next we'll loop over each user in that guild
            embeds = []
            for user_id, user_data in user_spellings.items():
                mistakes = sorted(set(user_data["unknown_words"]))
                if len(mistakes) == 0:
                    continue
                word_count = int(user_data["word_count"])  # let's be safe, I guess.
                percent_wrong = float(len(mistakes) / float(word_count)) * 100.0
                corrections = [
                    correction if (correction := self.spellchecker.correction(mistake)) is not None else ""
                    for mistake in mistakes
                ]
                actual_mistakes = [
                    f"{correction} [{mistake}]"
                    for mistake, correction in zip(mistakes, corrections, strict=False)
                    if re.sub(r"[0-9]+|\W+|<[^>]+>", " ", correction) != mistake  # this re.sub removes all punctuation
                ]
                mistake_string = join_list_max_chars(actual_mistakes, 4096)

                user = await self.bot.fetch_user(int(user_id))
                embed = disnake.Embed(
                    title=f"{user.display_name.capitalize()}'s spelling summary",
                    description=mistake_string,
                )
                embed.add_field(name="Total words", value=f"{word_count}", inline=True)
                embed.add_field(name="Mistakes", value=f"{len(mistakes)}", inline=True)
                embed.add_field(name="Percent wrong", value=f"{percent_wrong:.1f}%", inline=True)

                embed.set_thumbnail(url=user.avatar.url)

                embeds.append(embed)

            channel = await self.bot.fetch_channel(App.get_config("SPELLCHECK_SERVERS")[str(guild_id)]["CHANNEL"])
            if len(embeds) < 10:
                await channel.send(embeds=embeds)
            else:
                for embed in embeds:
                    await channel.send(embed=embed)

        self.incorrect_spellings.clear()


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Spelling(bot))
