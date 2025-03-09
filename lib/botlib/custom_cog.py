"""Custom Cog class."""

import logging

import disnake
from disnake.ext import commands

from botlib.config import BotConfig
from botlib.custom_bot import CustomInteractionBot

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
        if inter.guild and inter.guild.id not in BotConfig.get_config("NO_COOLDOWN_SERVERS"):
            inter.application_command.reset_cooldown(inter)
        # Users which don't have a cooldown
        if inter.author.id in BotConfig.get_config("NO_COOLDOWN_USERS"):
            inter.application_command.reset_cooldown(inter)
