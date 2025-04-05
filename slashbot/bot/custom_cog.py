"""Custom Cog class."""

from typing import Any

import disnake
from disnake.ext import tasks
from disnake.ext.commands import Cog

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.core import markov
from slashbot.core.database import Database
from slashbot.core.logger import Logger
from slashbot.settings import BotSettings


class CustomCog(Cog, Logger):
    """A custom cog class which modifies cooldown behaviour."""

    def __init__(self, bot: CustomInteractionBot, **kwargs: Any) -> None:
        """Intialise the cog.

        Parameters
        ----------
        bot : CustomInteractionBot
            The bot the cog will be added to.
        **kwargs : dict
            The keyword arguments to pass to the parent class.

        """
        Cog.__init__(**kwargs)
        Logger.__init__(self)
        self.bot = bot
        self.db = Database()
        self.markov_seed_words = []
        self._markov_sentences = {}

    # --------------------------------------------------------------------------

    async def cog_load(self) -> None:
        """Async cog load method.

        This initialises:
            - The database attribute, from the bot/client
            - Pre-generated markov sentences, if enabled
            - Starts all tasks
        """
        await self.bot.wait_until_first_connect()
        self.db = self.bot.db
        if self.bot.use_markov_cache and self.markov_seed_words:
            self.log_info("Generating markov sentence cache")
            self._populate_markov_cache()
            self.check_markov_cache_size.start()
        self._start_all_tasks()

    def _start_all_tasks(self) -> None:
        """Start all tasks in the cog."""
        for attr in dir(self):
            task_candidate = getattr(self, attr)
            if isinstance(task_candidate, tasks.Loop) and not task_candidate.is_running():
                self.log_debug("Starting task: %s", attr)
                task_candidate.start()

    async def cog_before_slash_command_invoke(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        # Servers which don't have a cooldown
        if inter.guild and inter.guild.id not in BotSettings.cooldown.no_cooldown_servers:
            inter.application_command.reset_cooldown(inter)
        # Users which don't have a cooldown
        if inter.author.id in BotSettings.cooldown.no_cooldown_users:
            inter.application_command.reset_cooldown(inter)

    # --------------------------------------------------------------------------

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
        for seed_word in seed_words or self.markov_seed_words or []:
            current_amount = len(self._markov_sentences.get(seed_word, []))
            self._markov_sentences[seed_word] = self.get_random_markov_sentence(
                seed_word, amount=BotSettings.markov.num_pregen_sentences - current_amount
            )
        self.log_info("Generated markov sentences for seed words: %s", self.markov_seed_words)

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
            if len(self._markov_sentences[seed_word]) < BotSettings.markov.pregenerate_limit:
                self._populate_markov_cache(seed_words=[seed_word])
