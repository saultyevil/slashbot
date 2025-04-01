"""Cog for bullying people about their spelling mistakes."""

import asyncio
import re
from collections import defaultdict
from pathlib import Path

import aiofiles
import disnake
from disnake.ext import commands, tasks
from spellchecker import SpellChecker

from slashbot.clock import calculate_seconds_until
from slashbot.core.custom_cog import CustomCog
from slashbot.settings import BotSettings

COOLDOWN_USER = commands.BucketType.user
MAX_EMBEDS_AT_ONCE = 5


def join_list_max_chars(words: list[str], max_chars: int) -> str:
    """Join a list of words into a comma-separated list.

    Parameters
    ----------
    words : List[str]
        A list of words to join together
    max_chars : int
        The maximum length the output string can be

    Returns
    -------
    str
        The joined words with "..." at the end if max_chars is hit

    """
    result = ""
    current_length = 0

    for word in words:
        if current_length + len(word) > max_chars - 3:
            if result:
                result += "..."
            break
        result += word + ", "
        current_length += len(word)

    # Remove the trailing ", " if there's anything in the result
    return result.removesuffix(", ")


class Spelling(CustomCog):
    """A cog for bullying people.

    The purpose of this cog is to bully Pip for his poor spelling.
    """

    def __init__(self, bot: commands.InteractionBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot : commands.InteractionBot
            The bot to pass to the cog.

        """
        super().__init__(bot)
        self.incorrect_spellings = defaultdict(
            lambda: defaultdict(
                lambda: {"word_count": 0, "unknown_words": []},
            ),  # incorrect_spellings[guild_id][user_id]
        )
        self.spellchecker = SpellChecker(case_sensitive=False)
        self.spelling_summary.start()  # pylint: disable=no-member
        self.custom_words = self.get_custom_words()

    @commands.cooldown(
        BotSettings.cooldown.rate,
        BotSettings.cooldown.standard,
        COOLDOWN_USER,
    )
    @commands.slash_command(
        name="add_word_to_dict",
        description="Add a word to the custom dictionary for the spelling summary",
        guild_ids=tuple(int(guild_id) for guild_id in BotSettings.cogs.spellcheck.servers),
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
    ) -> None:
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
            await inter.response.send_message(f"The word '{word}' is already in the dictionary.", ephemeral=True)
            return
        self.custom_words.append(word_lower)
        async with aiofiles.open(BotSettings.cogs.spellcheck.custom_dictionary, "w", encoding="utf-8") as file_out:
            await file_out.write("\n".join(self.custom_words))

        await inter.response.send_message(f"Added '{word_lower}' to dictionary.", ephemeral=True)

    @commands.cooldown(
        BotSettings.cooldown.rate,
        BotSettings.cooldown.standard,
        COOLDOWN_USER,
    )
    @commands.slash_command(
        name="remove_word_from_dict",
        description="Remove a word from the custom dictionary for the spelling summary",
        guild_ids=[int(guild_id) for guild_id in BotSettings.cogs.spellcheck.servers],
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
    ) -> None:
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
            await inter.response.send_message(f"The word '{word}' is not in the dictionary.", ephemeral=True)
            return
        self.custom_words.remove(word_lower)
        async with aiofiles.open(BotSettings.cogs.spellcheck.custom_dictionary, "w", encoding="utf-8") as file_out:
            await file_out.write("\n".join(self.custom_words))

        await inter.response.send_message(f"Removed '{word_lower}' from dictionary.", ephemeral=True)

    def get_custom_words(self) -> list[str]:
        """Get a list of custom dictionary words.

        These are checked in addition to the unknown words in spellchecker.

        Returns
        -------
        List[str]
            The list of words in the custom dictionary.

        """
        try:
            with Path.open(BotSettings.cogs.spellcheck.custom_dictionary, encoding="utf-8") as file_in:
                return list({line.strip() for line in file_in.readlines()})
        except OSError:
            self.log_exception("No dictionary found at %s", BotSettings.cogs.spellcheck.custom_dictionary)
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
        # remove slashbot mentions
        clean_text = re.sub(r"@(\w+|\d+)", "", text.lower())
        # remove code wrappings, so we don't get any code
        clean_text = re.sub(r"`[^`]+`", "", clean_text)
        clean_text = re.sub(r"```[^`]+```", "", clean_text, flags=re.DOTALL)
        # remove apostrophes first
        clean_text = re.sub(r"'", "", clean_text)
        # remove numbers and non-word characters (excluding hyphens in words)
        clean_text = re.sub(r"[0-9]+|(?<!\w)-(?!\w)|[^\w\s-]|<[^>]+>", " ", clean_text)
        # replace multiple spaces with a single space
        return re.sub(r"\s+", " ", clean_text)

    @commands.Cog.listener("on_message")
    async def check_for_incorrect_spelling(self, message: disnake.Message) -> None:
        """Check a message for an incorrect spelling.

        At the moment, this will only run in the Bumpaper server.

        Parameters
        ----------
        message : disnake.Message
            The message to check.

        """
        if not BotSettings.cogs.spellcheck.enabled:
            return
        if not message.guild or message.author.bot:
            return
        guild_key = str(message.guild.id)
        if guild_key not in BotSettings.cogs.spellcheck.servers:
            return
        if message.author.id not in BotSettings.cogs.spellcheck.servers[guild_key]["USERS"]:
            return

        cleaned_content = self.cleanup_message(message.content)
        unknown_words = self.spellchecker.unknown(cleaned_content.split())
        unknown_words = list(filter(lambda w: w not in self.custom_words, unknown_words))

        self.incorrect_spellings[guild_key][str(message.author.id)]["word_count"] += len(message.content.split())
        self.incorrect_spellings[guild_key][str(message.author.id)]["unknown_words"] += unknown_words

    @tasks.loop(seconds=5)
    async def spelling_summary(self) -> None:
        """Print the misspellings of the day.

        The summary will be in a single message. This will run everyday at 5pm.
        """
        await self.bot.wait_until_ready()
        if not BotSettings.cogs.spellcheck.enabled:
            return

        sleep_time = calculate_seconds_until(-1, 17, 0, 1)

        self.log_info(
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

            if len(embeds) == 0:
                continue

            channel = await self.bot.fetch_channel(BotSettings.cogs.spellcheck.servers[str(guild_id)]["CHANNEL"])

            if len(embeds) < MAX_EMBEDS_AT_ONCE:
                await channel.send(embeds=embeds)
            else:
                for embed in embeds:
                    await channel.send(embed=embed)

        self.incorrect_spellings.clear()


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Spelling(bot))
