import asyncio
import datetime
import random
import re
from typing import TYPE_CHECKING, cast

import disnake
from disnake.ext import commands, tasks

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.markov import MarkovGeneratorType, MarkovTextGenerator
from slashbot.settings import BotSettings

if TYPE_CHECKING:
    from slashbot.cogs.message_archive.cog import MessageArchive

# Naive times are interpreted as UTC by disnake, so use the local timezone
UPDATE_TIME = datetime.time(
    BotSettings.cogs.markov.update_hour,
    BotSettings.cogs.markov.update_minute,
    tzinfo=datetime.datetime.now(datetime.UTC).astimezone().tzinfo,
)

SEED_WORD_PATTERN = re.compile(r"^\?(?=\S*[^\W_])(\S+)")


def can_train(generator: MarkovTextGenerator | None) -> bool:
    """Check whether a generator has a chain which can be trained."""
    return generator is not None and generator.type == MarkovGeneratorType.ON_THE_FLY


class Markov(CustomCog):
    """Cog associated with Markov sentence generation and training."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: CustomInteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.markov_training_sample = {}
        self.markov_generator = bot.markov_generator

    def generate_sentences(self, seed_word: str | None = None, amount: int = 1) -> list[str]:
        """Generate sentences from the Markov chain.

        Parameters
        ----------
        seed_word: str | None
            An optional seed word to include in the sentences.
        amount: int
            The number of sentences to generate.

        Returns
        -------
        list[str]
            The generated sentences, or an empty list if no chain is loaded.

        """
        if self.markov_generator is None:
            return []
        return self.markov_generator.generate_response(amount, seed_word)

    # Listeners ---------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def add_message_to_markov_training_sample(self, message: disnake.Message) -> None:
        """Record messages for the Markov chain to learn.

        Parameters
        ----------
        message: disnake.Message
            The message to record.

        """
        if not BotSettings.markov.enable_markov_training:
            return
        if message.author.bot:
            return
        self.markov_training_sample[message.id] = message.clean_content

    @commands.Cog.listener("on_message")
    async def respond_to_seed_word_message(self, message: disnake.Message) -> None:
        """Respond to messages of the form "?word" with a sentence using that word.

        Parameters
        ----------
        message: disnake.Message
            The message to check.

        """
        if message.author.bot:
            return
        match = SEED_WORD_PATTERN.match(message.content.strip())
        if not match or self.markov_generator is None:
            return
        async with message.channel.typing():
            sentences = await asyncio.to_thread(self.generate_sentences, match.group(1), 1)
            if sentences:
                await message.channel.send(sentences[0])

    @commands.Cog.listener("on_message")
    async def respond_randomly(self, message: disnake.Message) -> None:
        """Very rarely respond to a message with a random Markov sentence.

        Parameters
        ----------
        message: disnake.Message
            The message to possibly respond to.

        """
        if message.author.bot:
            return
        # messages starting with ? are handled by the seed word listener
        if message.content.lstrip().startswith("?") or self.markov_generator is None:
            return
        if random.random() >= BotSettings.cogs.markov.random_response_chance:  # noqa: S311
            return
        async with message.channel.typing():
            sentences = await asyncio.to_thread(self.generate_sentences, None, 1)
            if sentences:
                await message.channel.send(sentences[0])

    @commands.Cog.listener("on_raw_message_delete")
    async def remove_message_from_markov_training_sample(self, payload: disnake.RawMessageDeleteEvent) -> None:
        """Remove a deleted message from the Markov training sentences.

        Parameters
        ----------
        payload: disnake.RawMessageDeleteEvent
            The payload containing the message.

        """
        if not BotSettings.markov.enable_markov_training:
            return

        message = payload.cached_message

        # if the message isn't cached, for some reason, we can fetch the channel
        # and the message from the channel
        if message is None:
            channel = await self.bot.fetch_channel(int(payload.channel_id))
            if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                self.log_error("Trying to remove message in non-text channel %d", payload.channel_id)
                return
            try:
                message = await channel.fetch_message(int(payload.message_id))
            except disnake.NotFound:
                self.log_error("Unable to fetch message %d from channel %d", payload.message_id, payload.channel_id)
                return

        self.markov_training_sample.pop(message.id, None)

    # Commands ----------------------------------------------------------------

    @slash_command_with_cooldown(name="markov", description="Generate a sentence using the Markov chain")
    async def markov_sentence(
        self,
        inter: disnake.ApplicationCommandInteraction,
        seed_word: str | None = commands.Param(
            default=None,
            name="seed_word",
            description="An optional single word for the sentence to contain",
            max_length=64,
        ),
    ) -> None:
        """Generate a Markov sentence, optionally containing a seed word.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        seed_word : str | None
            An optional seed word, which must be a single word.

        """
        seed_word = seed_word.strip() if seed_word else None
        if seed_word and len(seed_word.split()) > 1:
            await inter.response.send_message("The seed word must be a single word.", ephemeral=True)
            return

        if self.markov_generator is None:
            await inter.response.send_message("The Markov chain is not available.", ephemeral=True)
            return

        await inter.response.defer()
        sentences = await asyncio.to_thread(self.generate_sentences, seed_word, 1)
        await inter.edit_original_message(content=sentences[0])

    @tasks.loop(time=UPDATE_TIME)
    async def markov_chain_update_loop(self) -> None:
        """Update the regular chain and rebuild the grouped chain daily."""
        if not BotSettings.markov.enable_markov_training or not can_train(self.markov_generator):
            return

        archive = cast("MessageArchive | None", self.bot.get_cog("MessageArchive"))
        sample = self.markov_training_sample.copy()
        sentences = list(sample.values())
        self.log_info("Updating Markov chain with %d training samples", len(sentences))
        try:
            if archive is None:
                updated = await asyncio.to_thread(self.markov_generator.update_chain, sentences)
            else:
                messages = await archive.store.messages()
                updated = await asyncio.to_thread(self.markov_generator.rebuild_chain, messages)
        except Exception:
            self.log_exception("Failed to update the Markov chain")
        else:
            if archive is None or updated:
                for message_id, content in sample.items():
                    if self.markov_training_sample.get(message_id) == content:
                        self.markov_training_sample.pop(message_id)
            self.log_info("Markov chain update complete with %d sentences", updated)

        if archive is not None:
            try:
                grouped = await archive.store.grouped_messages()
                count = await asyncio.to_thread(self.markov_generator.rebuild_grouped_chain, grouped)
            except Exception:  # noqa: BLE001
                self.log_exception("Failed to rebuild the grouped Markov chain")
            else:
                self.log_info("Grouped Markov chain update complete with %d messages", count)

    @markov_chain_update_loop.before_loop
    async def markov_chain_update_loop_before(self) -> None:
        """Wait for the bot to be ready before the first scheduled run."""
        await self.bot.wait_until_ready()

    @markov_chain_update_loop.error
    async def markov_chain_update_loop_error(self, exception: BaseException) -> None:
        """Log an unexpected Markov worker failure."""
        self.log_error("Markov chain worker stopped unexpectedly: %s", exception)
