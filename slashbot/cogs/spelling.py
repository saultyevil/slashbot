"""Cog for bullying people about their spelling mistakes."""

import asyncio
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import aiofiles
import disnake
from disnake.ext import commands, tasks
from spellchecker import SpellChecker

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.clock import calculate_seconds_until
from slashbot.settings import BotSettings


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


@dataclass
class Spellings:
    """Dataclass for storing the incorrect spellings of a user."""

    total: int
    incorrect: list[str]


class Spelling(CustomCog):
    """A cog for bullying people.

    The purpose of this cog is to bully Pip for his poor spelling.
    """

    MAX_EMBEDS_AT_ONCE = 5

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot : CustomInteractionBot
            The bot to pass to the cog.

        """
        super().__init__(bot)
        self.incorrect_spellings = defaultdict(lambda: defaultdict(lambda: Spellings(0, [])))
        self.spellchecker = SpellChecker(case_sensitive=False)
        self.custom_words = self.get_custom_words()

    @slash_command_with_cooldown(
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

    @slash_command_with_cooldown(
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
            with Path(BotSettings.cogs.spellcheck.custom_dictionary).open(encoding="utf-8") as file_in:
                return list({line.strip() for line in file_in})
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
        # remove mentions
        clean_text = re.sub(r"@(\w+|\d+)", "", text.lower())
        # remove URLs
        clean_text = re.sub(r"https?://\S+|www\.\S+", "", clean_text)
        # remove code wrappings, so we don't get any code
        clean_text = re.sub(r"`[^`]+`", "", clean_text)
        clean_text = re.sub(r"```[^`]+```", "", clean_text, flags=re.DOTALL)
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
        if message.author.id not in BotSettings.cogs.spellcheck.servers[guild_key]["users"]:
            return

        cleaned_content = self.cleanup_message(message.content)
        unknown_words = self.spellchecker.unknown(cleaned_content.split())
        unknown_words = list(filter(lambda w: w not in self.custom_words, unknown_words))
        self.incorrect_spellings[guild_key][message.author.id].total += len(message.content.split())
        self.incorrect_spellings[guild_key][message.author.id].incorrect.extend(unknown_words)

    @tasks.loop(seconds=5)
    async def spelling_summary(self) -> None:
        """Print the misspellings of the day.

        The summary will be in a single message. This will run everyday at 5pm.
        """
        if not BotSettings.cogs.spellcheck.enabled:
            return

        sleep_time = calculate_seconds_until(weekday=-1, hour=17, minute=0, frequency_days=1)
        await self.bot.wait_until_ready()

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
                mistakes = sorted(set(user_data.incorrect))
                if len(mistakes) == 0:
                    continue
                word_count = int(user_data.total)  # let's be safe, I guess.
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
                embed.set_thumbnail(url=user.display_avatar.url)

                embeds.append(embed)

            if len(embeds) == 0:
                continue

            channel = await self.bot.fetch_channel(BotSettings.cogs.spellcheck.servers[str(guild_id)]["post_channel"])
            if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                self.log_warning(
                    "Spelling summary has invalid channel %s for guild %s",
                    channel,
                    guild_id,
                )
                continue

            if len(embeds) < self.MAX_EMBEDS_AT_ONCE:
                await channel.send(embeds=embeds)
            else:
                for embed in embeds:
                    await channel.send(embed=embed)

        self.incorrect_spellings.clear()


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Spelling(bot))
