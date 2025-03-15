"""Custom Cog class."""

import logging

import disnake
from disnake.ext import commands, tasks

from slashbot.lib import markov
from slashbot.lib.config import BotConfig
from slashbot.lib.custom_bot import CustomInteractionBot

logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))


class CustomCog(commands.Cog):
    """A custom cog class which modifies cooldown behaviour."""

    logger = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Intialise the cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The bot the cog will be added to.

        """
        super().__init__()
        self.bot = bot
        self.markov_seed_words = None
        self._markov_sentences = {}

    # --------------------------------------------------------------------------

    def _get_random_sentence(self, seed_word: str | None, amount: int) -> str | list[str]:
        if self.bot.use_markov_cache:
            sentence_cache = self._markov_sentences.get(seed_word, [])
            if amount > len(sentence_cache):
                sentences = markov.generate_text_from_markov_chain(
                    markov.MARKOV_MODEL or markov.MARKOV_BANK, seed_word, amount
                )
            else:
                sentences = []
                for _ in range(amount):
                    sentences.append(sentence_cache.pop(0))
        else:
            sentences = markov.generate_text_from_markov_chain(
                markov.MARKOV_MODEL or markov.MARKOV_BANK, seed_word, amount
            )

        return sentences

    def _populate_markov_cache(self, *, seed_words: list[str] | None = None) -> None:
        for seed_word in seed_words or self.markov_seed_words:
            current_amount = len(self._markov_sentences.get(seed_word, []))
            self._markov_sentences[seed_word] = self.get_random_sentence(
                seed_word, amount=BotConfig.get_config("PREGEN_MARKOV_SENTENCES_AMOUNT") - current_amount
            )
        CustomCog.logger.info(
            "<%s>Generated markov sentences for seed words: %s", self.__cog_name__, self.markov_seed_words
        )

    # --------------------------------------------------------------------------

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
        if inter.guild and inter.guild.id not in BotConfig.get_config("NO_COOLDOWN_SERVERS"):
            inter.application_command.reset_cooldown(inter)
        # Users which don't have a cooldown
        if inter.author.id in BotConfig.get_config("NO_COOLDOWN_USERS"):
            inter.application_command.reset_cooldown(inter)

    async def cog_load(self) -> None:
        """Async cog load method.

        This initialises:
            - Pre-generated markov sentences, if enabled
        """
        if self.bot.use_markov_cache and self.markov_seed_words:
            CustomCog.logger.info(
                "<%s>Generating markov sentence cache",
                self.__cog_name__,
            )
            self._populate_markov_cache()
            self.check_markov_cache_size.start()

    # --------------------------------------------------------------------------

    def get_random_sentence(
        self,
        seed_word: str | None = None,
        amount: int = 1,
    ) -> str | list[str]:
        """Generate a sentence using a markov chain.

        Parameters
        ----------
        seed_word : str, optional
            The seed word to use.
        amount : int, optional
            The number of sentences to generate, by default 1.

        Returns
        -------
        str
            The generated sentence.

        """
        if amount < 1:
            msg = "Requested number of sentences must be > 1"
            raise ValueError(msg)
        return self._get_random_sentence(seed_word, amount)

    @tasks.loop(seconds=10)
    async def check_markov_cache_size(self) -> None:
        """Populate the markov cache if a seed word is below the threshold."""
        if not self.bot.use_markov_cache:
            return
        for seed_word in self.markov_seed_words:
            if len(self._markov_sentences[seed_word]) < BotConfig.get_config("PREGEN_REGENERATE_LIMIT"):
                self._populate_markov_cache(seed_words=[seed_word])
