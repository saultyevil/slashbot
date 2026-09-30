import asyncio
import re
from collections import defaultdict
from pathlib import Path

import disnake
from disnake.ext import commands, tasks
from spellchecker import SpellChecker

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.clock import calculate_seconds_until
from slashbot.cogs.spelling.dictionary import add_word, load_words, remove_word, save_words
from slashbot.cogs.spelling.processing import UserSpellCheck, cleanup_message, get_incorrect_words, join_list_into_csv
from slashbot.settings import BotSettings

SPELLING_GUILDS = [int(guild_id) for guild_id in BotSettings.cogs.spelling.servers]


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
        self.incorrect_spellings = defaultdict(lambda: defaultdict(lambda: UserSpellCheck(0, [])))
        self.spellchecker = SpellChecker(case_sensitive=False)
        self.custom_words = self.get_custom_words()

    def get_custom_words(self) -> list[str]:
        """Get a list of custom dictionary words.

        These are checked in addition to the unknown words in spellchecker.

        Returns
        -------
        List[str]
            The list of words in the custom dictionary.

        """
        try:
            return load_words(Path(BotSettings.cogs.spelling.custom_dictionary))
        except OSError:
            self.log_exception("No dictionary found at %s", BotSettings.cogs.spelling.custom_dictionary)
            return []

    def _get_checked_words(self, message: disnake.Message) -> list[str]:
        """Get the words from a message that should be spell-checked.

        Parameters
        ----------
        message : disnake.Message
            The message whose content should be processed.

        Returns
        -------
        list[str]
            The normalized words to check.

        """
        return cleanup_message(message.content).split()

    def _is_tracked_message(self, message: disnake.Message) -> bool:
        """Return whether a message belongs to a configured spelling-check user.

        Parameters
        ----------
        message : disnake.Message
            The message to check against the spelling configuration.

        Returns
        -------
        bool
            Whether spelling checks are enabled for the message author and guild.

        """
        if not BotSettings.cogs.spelling.enabled or not message.guild or message.author.bot:
            return False
        guild_settings = BotSettings.cogs.spelling.servers.get(str(message.guild.id))
        return guild_settings is not None and message.author.id in guild_settings["users"]

    def _record_spellings(self, guild_id: str, user_id: int, words: list[str]) -> None:
        """Record checked words and their incorrect spellings for a user.

        Parameters
        ----------
        guild_id : str
            The ID of the guild containing the message.
        user_id : int
            The ID of the user who sent the message.
        words : list[str]
            The normalized words to record.

        """
        user_data = self.incorrect_spellings[guild_id][user_id]
        user_data.total += len(words)
        user_data.incorrect.extend(get_incorrect_words(words, self.spellchecker, self.custom_words))

    async def _create_user_summary(self, user_id: int, user_data: UserSpellCheck) -> disnake.Embed | None:
        """Create a spelling summary embed for a user with recorded mistakes.

        Parameters
        ----------
        user_id : int
            The ID of the user being summarized.
        user_data : UserSpellCheck
            The user's recorded word counts and incorrect spellings.

        Returns
        -------
        disnake.Embed or None
            The summary embed, or ``None`` when the user has no mistakes.

        """
        mistakes = sorted(set(user_data.incorrect))
        if not mistakes:
            return None

        word_count = user_data.total
        percent_wrong = len(user_data.incorrect) / word_count * 100.0
        corrections = [self.spellchecker.correction(mistake) or "" for mistake in mistakes]
        actual_mistakes = [
            f"{correction} [{mistake}]"
            for mistake, correction in zip(mistakes, corrections, strict=False)
            if re.sub(r"[0-9]+|\W+|<[^>]+>", " ", correction) != mistake
        ]

        user = await self.bot.fetch_user(user_id)
        embed = disnake.Embed(
            title=f"{user.display_name.capitalize()}'s spelling summary",
            description=join_list_into_csv(actual_mistakes, 1950),
        )
        embed.add_field(name="Total words", value=f"{word_count}", inline=True)
        embed.add_field(name="Mistakes", value=f"{len(mistakes)}", inline=True)
        embed.add_field(name="Percent wrong", value=f"{percent_wrong:.1f}%", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url)
        return embed

    async def _create_guild_summaries(self, user_spellings: dict[int, UserSpellCheck]) -> list[disnake.Embed]:
        """Create summaries for all users with mistakes in a guild.

        Parameters
        ----------
        user_spellings : dict[int, UserSpellCheck]
            The recorded spelling data keyed by user ID.

        Returns
        -------
        list[disnake.Embed]
            The summary embeds for users with at least one mistake.

        """
        embeds = []
        for user_id, user_data in user_spellings.items():
            if embed := await self._create_user_summary(user_id, user_data):
                embeds.append(embed)
        return embeds

    async def _send_summaries(self, guild_id: str, embeds: list[disnake.Embed]) -> None:
        """Send a guild's summaries to its configured channel.

        Parameters
        ----------
        guild_id : str
            The ID of the guild whose configured channel should receive the summaries.
        embeds : list[disnake.Embed]
            The summary embeds to send.

        """
        if not embeds:
            return

        channel = await self.bot.fetch_channel(BotSettings.cogs.spelling.servers[guild_id]["post_channel"])
        if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
            self.log_warning("Spelling summary has invalid channel %s for guild %s", channel, guild_id)
            return

        if len(embeds) < self.MAX_EMBEDS_AT_ONCE:
            await channel.send(embeds=embeds)
            return
        for embed in embeds:
            await channel.send(embed=embed)

    @commands.Cog.listener("on_message")
    async def check_for_incorrect_spelling(self, message: disnake.Message) -> None:
        """Check a message for an incorrect spelling.

        At the moment, this will only run in the Bumpaper server.

        Parameters
        ----------
        message : disnake.Message
            The message to check.

        """
        if not self._is_tracked_message(message):
            return

        if message.guild is None:
            return
        guild_key = str(message.guild.id)
        self._record_spellings(guild_key, message.author.id, self._get_checked_words(message))

    @tasks.loop(seconds=5)
    async def spelling_summary(self) -> None:
        """Print the misspellings of the day.

        The summary will be in a single message. This will run everyday at 5pm.
        """
        if not BotSettings.cogs.spelling.enabled:
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

        for guild_id, user_spellings in self.incorrect_spellings.items():
            embeds = await self._create_guild_summaries(user_spellings)
            await self._send_summaries(str(guild_id), embeds)

        self.incorrect_spellings.clear()

    @slash_command_with_cooldown(
        name="add_word_to_dict",
        description="Add a word to the custom dictionary for the spelling summary",
        guild_ids=SPELLING_GUILDS,
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
        word_lower = add_word(self.custom_words, word)
        if word_lower is None:
            await inter.response.send_message(f"The word '{word}' is already in the dictionary.", ephemeral=True)
            return
        save_words(Path(BotSettings.cogs.spelling.custom_dictionary), self.custom_words)

        await inter.response.send_message(f"Added '{word_lower}' to dictionary.", ephemeral=True)
        self.log_info("Added spelling dictionary word: user=%s word_length=%d", inter.author.id, len(word_lower))

    @slash_command_with_cooldown(
        name="remove_word_from_dict",
        description="Remove a word from the custom dictionary for the spelling summary",
        guild_ids=SPELLING_GUILDS,
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
        word_lower = remove_word(self.custom_words, word)
        if word_lower is None:
            await inter.response.send_message(f"The word '{word}' is not in the dictionary.", ephemeral=True)
            return
        save_words(Path(BotSettings.cogs.spelling.custom_dictionary), self.custom_words)

        await inter.response.send_message(f"Removed '{word_lower}' from dictionary.", ephemeral=True)
        self.log_info("Removed spelling dictionary word: user=%s word_length=%d", inter.author.id, len(word_lower))
