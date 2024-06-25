"""Admin commands for Slashbot."""

import logging
import os
import sys
from pathlib import Path

import disnake
import git
from disnake.ext import commands

from bot import __version__
from bot.custom_cog import SlashbotCog
from slashbot.admin import get_logfile_tail, update_local_repository
from slashbot.config import App

COOLDOWN_USER = commands.BucketType.user
logger = logging.getLogger(App.get_config("LOGGER_NAME"))


def convert_level_to_int(choice: str) -> int:
    """Convert a text choice for logging level into the respective integer.

    Parameters
    ----------
    choice : str
        The choice string.

    Returns
    -------
    int
        The integer for the choice.

    """
    choice = choice.lower()

    if choice == "debug":
        return logging.DEBUG
    if choice == "info":
        return logging.INFO

    return logging.WARNING


class AdminTools(SlashbotCog):
    """Admin commands and tools for Slashbot.

    The purpose of this cog is to manage Slashbot remotely, or to check that
    things are working as intended.
    """

    @commands.cooldown(
        App.get_config("COOLDOWN_RATE"),
        App.get_config("COOLDOWN_STANDARD"),
        COOLDOWN_USER,
    )
    @commands.slash_command(name="version")
    async def print_bot_version(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Print the current version number of the bot."""
        await inter.response.send_message(f"Current version: {__version__}", ephemeral=True)

    @commands.cooldown(
        App.get_config("COOLDOWN_RATE"),
        App.get_config("COOLDOWN_STANDARD"),
        COOLDOWN_USER,
    )
    @commands.slash_command(name="logfile")
    async def print_logfile_tail(
        self,
        inter: disnake.ApplicationCommandInteraction,
        num_lines: int = commands.Param(
            default=10,
            description="The number of lines to include in the tail of the log file.",
            max_value=50,
            min_value=1,
        ),
    ) -> None:
        """Print the tail of the logfile.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        num_lines: int
            The number of lines to print.

        """
        await inter.response.defer(ephemeral=True)
        tail = await get_logfile_tail(Path(App.get_config("LOGFILE_NAME")), num_lines)
        await inter.edit_original_message(f"```{''.join(tail[::-1])}```")

    @commands.slash_command()
    async def restart_bot(
        self,
        inter: disnake.ApplicationCommandInteraction,
        disable_markov: str = commands.Param(
            choices=["Yes", "No"],
            default=False,
            description="Disable Markov sentence generation for faster load times",
            converter=lambda _, arg: arg == "Yes",
        ),
    ) -> None:
        """Restart the bot.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        disable_markov : str / bool
            A bool to indicate if we should disable cached markov sentences. The
            input is a string of "Yes" or "No" which is converted into a bool.

        """
        if inter.author.id != App.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        arguments = ["run.py"]
        if disable_markov:
            arguments.append("--disable-auto-markov")
        logger.info("Restarting with new process with arguments %s", arguments)

        if inter.response.type == disnake.InteractionResponseType.deferred_channel_message:
            await inter.edit_original_message("Restarting the bot...")
        else:
            await inter.response.send_message("Restarting the bot...", ephemeral=True)

        os.execv(sys.executable, ["python", *arguments])  # noqa: S606

    @commands.slash_command(name="update_bot")
    async def update_and_restart(
        self,
        inter: disnake.ApplicationCommandInteraction,
        branch: str = commands.Param(
            default="main",
            description="The branch to update to",
        ),
        disable_markov: str = commands.Param(
            choices=["Yes", "No"],
            default=False,
            description="Disable Markov sentence generation for faster load times",
            converter=lambda _, arg: arg == "Yes",
        ),
    ) -> None:
        """Update and restart the bot.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        branch : str
            The name of the git branch to use
        disable_markov : str / bool
            A bool to indicate if we should disable cached markov sentences. The
            input is a string of "Yes" or "No" which is converted into a bool.

        """
        if inter.author.id != App.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True,
            )
            return

        await inter.response.defer(ephemeral=True)
        try:
            update_local_repository(branch)
        except git.exc.GitCommandError:
            logger.exception("Failed to update repository")
            await inter.edit_original_message("Failed to update local repository", ephemeral=True)
            return
        await self.restart_bot(
            inter,
            disable_markov,
        )


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(AdminTools(bot))
