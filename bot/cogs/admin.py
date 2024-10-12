import logging
from pathlib import Path

import disnake
import git
from disnake.ext import commands

from bot import __version__
from bot.custom_cog import SlashbotCog
from bot.custom_command import cooldown_and_slash_command
from bot.types import ApplicationCommandInteraction
from slashbot.admin import get_logfile_tail, restart_bot, update_local_repository
from slashbot.config import App

COOLDOWN_USER = commands.BucketType.user
COOLDOWN_STANDARD = App.get_config("COOLDOWN_STANDARD")
COOLDOWN_RATE = App.get_config("COOLDOWN_RATE")
LOGGER = logging.getLogger(App.get_config("LOGGER_NAME"))


class AdminTools(SlashbotCog):
    """Admin commands and tools for Slashbot.

    The purpose of this cog is to manage Slashbot remotely, or to check that
    things are working as intended.
    """

    @cooldown_and_slash_command(name="version")
    async def print_bot_version(self, inter: ApplicationCommandInteraction) -> None:
        """Print the current version number of the bot."""
        await inter.response.send_message(f"Current version: {__version__}", ephemeral=True)

    @cooldown_and_slash_command(name="logfile")
    async def print_logfile_tail(
        self,
        inter: ApplicationCommandInteraction,
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
        inter : ApplicationCommandInteraction
            The interaction to respond to.
        num_lines: int
            The number of lines to print.

        """
        await inter.response.defer(ephemeral=True)
        tail = await get_logfile_tail(Path(App.get_config("LOGFILE_NAME")), num_lines)
        await inter.edit_original_message(f"```{tail}```")

    @cooldown_and_slash_command()
    async def restart_bot(
        self,
        inter: ApplicationCommandInteraction,
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
        inter : ApplicationCommandInteraction
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

        if inter.response.type == disnake.InteractionResponseType.deferred_channel_message:
            await inter.edit_original_message("Restarting the bot...")
        else:
            await inter.response.send_message("Restarting the bot...", ephemeral=True)

        restart_bot(arguments)

    @cooldown_and_slash_command(name="update_bot")
    async def update_and_restart(
        self,
        inter: ApplicationCommandInteraction,
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
        inter : ApplicationCommandInteraction
            The slash command interaction.
        branch : str
            The name of the git branch to use
        disable_markov : str / bool
            A bool to indicate if we should disable cached markov sentences. The
            input is a string of "Yes" or "No" which is converted into a bool.

        """
        if inter.author.id != App.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            update_local_repository(branch)
        except git.exc.GitCommandError:
            LOGGER.exception("Failed to update repository")
            await inter.edit_original_message("Failed to update local repository")
            return
        await self.restart_bot(inter, disable_markov)


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(AdminTools(bot))
