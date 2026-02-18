import asyncio

import disnake
from disnake.ext import commands, tasks

from slashbot import markov
from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.clock import calculate_seconds_until
from slashbot.logger import logger
from slashbot.settings import BotSettings


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

    @tasks.loop(seconds=1)
    async def markov_chain_update_loop(self) -> None:
        """Get the bot to update the chain every 6 hours."""
        if not BotSettings.markov.enable_markov_training:
            return
        if not markov.MARKOV_MODEL:
            return
        sleep_time = calculate_seconds_until(-1, 3, 0, 1)
        self.log_info(
            "Waiting %d seconds/%d minutes/%.1f hours till markov chain update",
            sleep_time,
            sleep_time // 60,
            sleep_time / 3600,
        )
        await asyncio.sleep(sleep_time)

        await markov.update_markov_chain_for_model(
            None,
            markov.MARKOV_MODEL,
            list(self.markov_training_sample.values()),
            BotSettings.markov.current_chain_location,
        )
        self.markov_training_sample.clear()


def setup(bot: CustomInteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.markov.enabled:
        logger.log_warning("%s has been disabled in the configuration file", Markov.__cog_name__)
        return
    bot.add_cog(Markov(bot))
