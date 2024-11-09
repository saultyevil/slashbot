"""Custom Cog class."""

import logging

import disnake
from disnake.ext import commands, tasks

from bot.custom_bot import SlashbotInterationBot
from slashbot.config import Bot
from slashbot.markov import (
    MARKOV_MODEL,
    async_generate_list_of_sentences_with_seed_word,
    async_generate_markov_sentence,
    generate_markov_sentence,
)

logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))


class SlashbotCog(commands.Cog):
    """A custom cog class which modifies cooldown behaviour."""

    def __init__(self, bot: SlashbotInterationBot) -> None:
        """Intialise the cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The bot the cog will be added to.

        """
        super().__init__()
        self.bot = bot
        self.premade_markov_sentences = {}
        self.regenerate_markov_sentences.start()

    # Before command invokes ---------------------------------------------------

    async def cog_before_slash_command_invoke(
        self,
        inter: disnake.ApplicationCommandInteraction,
    ) -> disnake.ApplicationCommandInteraction:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        # Servers which don't have a cooldown
        if inter.guild and inter.guild.id not in Bot.get_config("NO_COOLDOWN_SERVERS"):
            inter.application_command.reset_cooldown(inter)
        # Users which don't have a cooldown
        if inter.author.id in Bot.get_config("NO_COOLDOWN_USERS"):
            inter.application_command.reset_cooldown(inter)

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=30)
    async def regenerate_markov_sentences(self) -> None:
        """Re-generate the markov sentences with a given seed word."""
        if not self.bot.markov_gen_enabled or not self.premade_markov_sentences:
            return

        for seed_word, seed_sentences in self.premade_markov_sentences.items():
            if len(seed_sentences) <= Bot.get_config("PREGEN_REGENERATE_LIMIT"):
                self.premade_markov_sentences[seed_word] = await async_generate_list_of_sentences_with_seed_word(
                    MARKOV_MODEL,
                    seed_word,
                    Bot.get_config("PREGEN_MARKOV_SENTENCES_AMOUNT"),
                )

    @regenerate_markov_sentences.before_loop
    async def wait_before_start(self) -> None:
        """Wait until the bot is ready for the task."""
        await self.bot.wait_until_ready()

    # Functions ----------------------------------------------------------------

    def get_markov_sentence(self, seed_word: str) -> str:
        """Retrieve a pre-generated sentence from storage.

        If a sentence for a seed word doesn't exist, then a sentence is created
        on-the-fly instead.

        Parameters
        ----------
        seed_word : str
            The seed word for the sentence.

        Returns
        -------
        str
            The generated sentence.

        """
        if seed_word not in self.premade_markov_sentences:
            if self.bot.markov_gen_enabled:
                logger.error("Seed word '%s' is missing in pre-made markov sentences", seed_word)
            return generate_markov_sentence(MARKOV_MODEL, seed_word)

        try:
            return self.premade_markov_sentences[seed_word].pop()
        except IndexError:
            if self.bot.markov_gen_enabled:
                logger.exception("Unable to get pre-made markov sentence for seed word '%s'", seed_word)
            return generate_markov_sentence(MARKOV_MODEL, seed_word)

    async def async_get_markov_sentence(self, seed_word: str) -> str:
        """Retrieve a pre-generated sentence from storage.

        If a sentence for a seed word doesn't exist, then a sentence is created
        on-the-fly instead.

        Parameters
        ----------
        seed_word : str
            The seed word for the sentence.

        Returns
        -------
        str
            The generated sentence.

        """
        if seed_word not in self.premade_markov_sentences:
            if self.bot.markov_gen_enabled:
                logger.error("Seed word '%s' is missing in pre-made markov sentences", seed_word)
            return await async_generate_markov_sentence(MARKOV_MODEL, seed_word)

        try:
            return self.premade_markov_sentences[seed_word].pop()
        except IndexError:
            if self.bot.markov_gen_enabled:
                logger.exception("Unable to get pre-made markov sentence for seed word '%s'", seed_word)
            return await async_generate_markov_sentence(MARKOV_MODEL, seed_word)
