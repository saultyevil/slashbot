"""Custom Cog class."""

import asyncio
from collections import deque
from typing import Any

import disnake
from disnake.ext import tasks
from disnake.ext.commands import Cog

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.database import DatabaseSQL, DeclarativeBase, UserSQL
from slashbot.logger import Logger
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
        super().__init__(**kwargs)
        Logger.__init__(self)
        self.bot = bot
        self.db = DatabaseSQL(BotSettings.files.database, DeclarativeBase)
        self.markov_seed_words = []
        self._markov_sentences: dict[str, deque[str]] = {}
        self._markov_refill_task: asyncio.Task | None = None

    # --------------------------------------------------------------------------

    async def cog_load(self) -> None:
        """Async cog load method.

        This initialises:
            - The database attribute, from the bot/client
            - Pre-generated markov sentences, if enabled
            - Starts all tasks
        """
        self.log_debug("Loading cog")
        try:
            await self.bot.wait_until_ready()
            self.db = self.bot.db or self.db
            await self.db.init()
            if self.bot.use_markov_cache and self.markov_seed_words:
                self.log_info("Generating markov sentence cache")
                await self._populate_markov_cache()
            self._start_all_tasks()
        except Exception:
            self.log_exception("Failed while loading cog")
            raise
        self.log_info("Loaded cog: %s", self.__cog_name__)

    def _start_all_tasks(self) -> None:
        """Start all tasks in the cog."""
        for attr in dir(self):
            task_candidate = getattr(self, attr)
            if isinstance(task_candidate, tasks.Loop):
                self.log_debug("Starting task: %s", attr)
                try:
                    task_candidate.start()
                except Exception:
                    self.log_exception("Failed to start task: %s", attr)
                    raise

    async def cog_before_slash_command_invoke(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        self.log_debug(
            "Command invoked: command=%s user=%s guild=%s channel=%s",
            inter.application_command.name,
            inter.author.id,
            inter.guild.id if inter.guild else None,
            inter.channel.id if inter.channel else None,
        )
        # Servers which don't have a cooldown
        if inter.guild and inter.guild.id not in BotSettings.cooldown.no_cooldown_servers:
            inter.application_command.reset_cooldown(inter)
        # Users which don't have a cooldown
        if inter.author.id in BotSettings.cooldown.no_cooldown_users:
            inter.application_command.reset_cooldown(inter)

    # --------------------------------------------------------------------------

    def _get_random_markov_sentence(self, seed_word: str | None, amount: int) -> str | list[str]:
        """Get a random markov generated sentence.

        If the markov cache is enabled and the seed word is cached, sentences
        are taken from the cache without any computation, and a refill is
        scheduled in the background. Anything the cache cannot supply is
        generated immediately.

        Parameters
        ----------
        seed_word : str
            The seed word to use.
        amount : int
            The number of sentences to generate.

        Returns
        -------
        str | list[str]
            The generated sentence, or sentences if more than one was asked for.

        """
        sentences = []
        cache = self._markov_sentences.get(seed_word) if self.bot.use_markov_cache and seed_word else None

        if cache is not None:
            sentences = [cache.popleft() for _ in range(min(amount, len(cache)))]
            if len(cache) < BotSettings.markov.pregenerate_limit:
                self._request_markov_cache_refill()

        if len(sentences) < amount:
            sentences.extend(self._generate_markov_sentences(seed_word, amount - len(sentences)))

        return sentences[0] if amount == 1 else sentences

    def _generate_markov_sentences(self, seed_word: str | None, amount: int) -> list[str]:
        """Generate sentences using the bot's Markov generator."""
        if self.bot.markov_generator is None:
            return ["Markov generation is not available."] * amount
        return self.bot.markov_generator.generate_response(amount, seed_word)

    async def _populate_markov_cache(self) -> None:
        """Top up the cache for every seed word, generating off the event loop."""
        for seed_word in self.markov_seed_words:
            cache = self._markov_sentences.setdefault(seed_word, deque())
            missing = BotSettings.markov.num_pregen_sentences - len(cache)
            if missing > 0:
                cache.extend(await asyncio.to_thread(self._generate_markov_sentences, seed_word, missing))
        self.log_debug("Markov sentence cache populated for seed words: %s", self.markov_seed_words)

    def _request_markov_cache_refill(self) -> None:
        """Start a background refill of the cache, if one is not already running."""
        if self._markov_refill_task and not self._markov_refill_task.done():
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._markov_refill_task = loop.create_task(self._refill_markov_cache())

    async def _refill_markov_cache(self) -> None:
        """Refill the cache, logging rather than raising any failure."""
        try:
            await self._populate_markov_cache()
        except Exception:
            self.log_exception("Failed to refill the markov sentence cache")

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

    async def get_user_db_from_inter(self, inter: disnake.ApplicationCommandInteraction) -> UserSQL:
        """Get the associated user in the database from an interaction.

        If the user does not exist, then a new row will be populated in the
        database.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The disnake interact for the user.

        Returns
        -------
        User
            The user associated with the interaction.

        """
        user = await self.db.get_user("discord_id", inter.author.id)
        if not user:
            user = await self.db.upsert_row(
                UserSQL(
                    discord_id=inter.author.id,
                    username=inter.author.name,
                )
            )
        return user
