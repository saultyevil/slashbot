"""Custom Cog class."""

import disnake
from disnake.ext import tasks
from disnake.ext.commands import Cog

from slashbot.lib import markov
from slashbot.lib.config import BotConfig
from slashbot.lib.custom_bot import CustomInteractionBot
from slashbot.lib.logger import Logger


class CustomCog(Cog, Logger):
    """A custom cog class which modifies cooldown behaviour."""

    def __init__(self, bot: CustomInteractionBot, **kwargs) -> None:
        """Intialise the cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The bot the cog will be added to.

        """
        super().__init__(**kwargs)
        Logger.__init__(self)
        self.bot = bot
        self.markov_seed_words = None
        self._markov_sentences = {}

    # --------------------------------------------------------------------------

    def _get_random_markov_sentence(self, seed_word: str | None, amount: int) -> str | list[str]:
        """Get a random markov generated sentence.

        If the markov cache is enabled, the sentence will be taken from the
        cache if there are not in there. If not, the sentence will be generated
        on-the-fly or taken directly from the markov bank.

        Parameters
        ----------
        seed_word : str
            The seed word to use.
        amount : int
            The number of sentences to generate.

        Returns
        -------
        str
            The generated sentence.

        """
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
        """Populate the markov cache for the given seed words.

        If no seed words are provided, the seed words in the class attribute
        will be used.

        Parameters
        ----------
        seed_words : list[str] | None, optional
           The seed words to generate sentences for, by default None

        """
        for seed_word in seed_words or self.markov_seed_words:
            current_amount = len(self._markov_sentences.get(seed_word, []))
            self._markov_sentences[seed_word] = self.get_random_markov_sentence(
                seed_word, amount=BotConfig.get_config("PREGEN_MARKOV_SENTENCES_AMOUNT") - current_amount
            )
        self.log_info("Generated markov sentences for seed words: %s", self.markov_seed_words)

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
            self.log_info("Generating markov sentence cache")
            self._populate_markov_cache()
            self.check_markov_cache_size.start()

    # --------------------------------------------------------------------------

    def get_random_markov_sentence(
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
        return self._get_random_markov_sentence(seed_word, amount)

    @tasks.loop(seconds=10)
    async def check_markov_cache_size(self) -> None:
        """Populate the markov cache if a seed word is below the threshold."""
        if not self.bot.use_markov_cache:
            return
        for seed_word in self.markov_seed_words:
            if len(self._markov_sentences[seed_word]) < BotConfig.get_config("PREGEN_REGENERATE_LIMIT"):
                self._populate_markov_cache(seed_words=[seed_word])
