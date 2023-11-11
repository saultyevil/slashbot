#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Custom Cog class."""

import logging

import disnake
from disnake.ext import commands, tasks

from slashbot.config import App
from slashbot.markov import (
    MARKOV_MODEL,
    async_generate_list_of_sentences_with_seed_word,
    async_generate_sentence,
)

logger = logging.getLogger(App.get_config("LOGGER_NAME"))


class SlashbotCog(commands.Cog):
    """A custom cog class which modifies cooldown behavior."""

    def __init__(self):
        super().__init__()
        self.markov_sentences = {}
        self.regenerate_markov_sentences.start()  # pylint: disable=no-member

    # Before command invokes ---------------------------------------------------

    async def cog_before_slash_command_invoke(
        self, inter: disnake.ApplicationCommandInteraction
    ) -> disnake.ApplicationCommandInteraction:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        if inter.guild and inter.guild.id not in App.get_config("COOLDOWN_SERVERS"):
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in App.get_config("NO_COOLDOWN_USERS"):
            return inter.application_command.reset_cooldown(inter)

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=30)
    async def regenerate_markov_sentences(self) -> None:
        """Re-generate the markov sentences with a given seed word."""
        if not self.bot.markov_gen_on or not self.markov_sentences:
            return

        for seed_word, seed_sentences in self.markov_sentences.items():
            if len(seed_sentences) <= App.get_config("PREGEN_REGENERATE_LIMIT"):
                # logger.debug("Regenerating sentences for seed word %s", seed_word)
                self.markov_sentences[seed_word] = await async_generate_list_of_sentences_with_seed_word(
                    MARKOV_MODEL, seed_word, App.get_config("PREGEN_MARKOV_SENTENCES_AMOUNT")
                )

    @regenerate_markov_sentences.before_loop
    async def wait_before_start(self) -> None:
        """Wait until the bot is ready for the task."""
        await self.bot.wait_until_ready()

    # Functions ----------------------------------------------------------------

    async def get_markov_sentence(self, seed_word: str) -> str:
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
        if seed_word not in self.markov_sentences:
            if self.bot.markov_gen_on:
                logger.error("No pre-generated markov sentences for seed word %s ", seed_word)
            return await async_generate_sentence(MARKOV_MODEL, seed_word)

        try:
            return self.markov_sentences[seed_word].pop()
        except IndexError:
            if self.bot.markov_gen_on:
                logger.debug("Using generate_sentence instead of pre gen sentences for %s", seed_word)
            return await async_generate_sentence(MARKOV_MODEL, seed_word)
