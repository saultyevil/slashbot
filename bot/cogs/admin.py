"""Admin commands for Slashbot."""

import datetime
import logging
import os
import re
import sys
from pathlib import Path
from types import coroutine

import aiofiles
import aiohttp
import disnake
import git
from disnake.ext import commands
from prettytable import PrettyTable

from bot import __version__
from bot.custom_cog import SlashbotCog
from lib import markov
from lib.config import App
from lib.db import get_all_reminders

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

    The most useful command is to look at the logfile, or to restart the bot
    when changes have been made.
    """

    def __init__(
        self,
        bot: commands.InteractionBot,
    ) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot : commands.InteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.logfile_path = Path(App.get_config("LOGFILE_NAME"))

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="version", description="Print the current version number of the bot")
    async def print_version(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Print the current version number of the bot."""
        await inter.response.send_message(f"Current version: {__version__}", ephemeral=True)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="logfile", description="get the tail of the logfile")
    async def print_logfile(
        self,
        inter: disnake.ApplicationCommandInteraction,
        file: str = commands.Param(
            default="slashbot",
            description="The log file to tail, slashbot or disnake.",
            choices=["slashbot", "disnake"],
        ),
        num_lines: int = commands.Param(
            default=10,
            description="The number of lines to include in the tail of the log file.",
            max_value=50,
            min_value=1,
        ),
    ) -> coroutine:
        """Print the tail of the log file.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        file: str
            The name of the file to look at
        num_lines: int
            The number of lines to print.

        """
        await inter.response.defer(ephemeral=True)

        file_name = self.logfile_path if file == "slashbot" else self.logfile_path.with_name("disnake.log")
        async with aiofiles.open(file_name, encoding="utf-8") as file_in:
            log_file = await file_in.read()

        log_lines = log_file.splitlines()

        # iterate backwards over log_lines, until either n_lines is reached or
        # the character limit is reached

        tail = []
        num_chars = 0

        for i in range(1, num_lines + 1):
            try:
                num_chars += len(log_lines[-i])
            except IndexError:
                break

            if num_chars > App.get_config("MAX_CHARS"):
                break
            tail.append(log_lines[-i])

        await inter.edit_original_message(f"```{''.join(tail[::-1])}```")

    @commands.slash_command(name="ip", description="get the external ip address for the bot")
    async def print_ip_address(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Get the external IP of the bot."""
        if inter.author.id != App.get_config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
        try:
            async with (
                aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=4)) as session,
                session.get("https://api.ipify.org") as resp,
            ):
                ip_addr = await resp.text()
            await inter.response.send_message(f"{ip_addr}", ephemeral=True)
        except (TimeoutError, aiohttp.ClientError):
            await inter.response.send_message("The IP request failed.", ephemeral=True)
            await session.close()

    @commands.slash_command(name="restart_bot", description="restart the bot")
    async def restart_bot(
        self,
        inter: disnake.ApplicationCommandInteraction,
        disable_markov: str = commands.Param(
            choices=["Yes", "No"],
            default=False,
            description="Disable Markov sentence generation for faster load times",
            converter=lambda _, arg: arg == "Yes",
        ),
        state_size: int = commands.Param(
            choices=["0", "1", "2", "3", "4"],
            default=0,
            description="Set the state size of the markov model",
        ),
    ) -> None:
        """Restart the bot with a new process.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        disable_markov : str / bool
            A bool to indicate if we should disable cached markov sentences. The
            input is a string of "Yes" or "No" which is converted into a bool.
        state_size : int
            The state size of the Markov Chain to load.

        """
        if inter.author.id != App.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        arguments = ["run.py"]
        if disable_markov:
            arguments.append("--disable-auto-markov")
        if state_size:
            arguments.append(f"--state-size={state_size}")
        logger.info("Restarting with new process with arguments %s", arguments)

        if inter.response.type == disnake.InteractionResponseType.deferred_channel_message:
            await inter.edit_original_message("Restarting the bot...")
        else:
            await inter.response.send_message("Restarting the bot...", ephemeral=True)

        os.execv(sys.executable, ["python", *arguments])

    @commands.slash_command(name="update_bot", description="Update and restart the bot")
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
        state_size: int = commands.Param(
            choices=["0", "1", "2", "3", "4"],
            default=0,
            description="Set the state size of the markov model",
        ),
    ) -> None:
        """Update and restart the bot with a new process.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        branch : str
            The name of the git branch to use
        disable_markov : str / bool
            A bool to indicate if we should disable cached markov sentences. The
            input is a string of "Yes" or "No" which is converted into a bool.
        state_size : int
            The state size of the Markov Chain to load.

        """
        if inter.author.id != App.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True,
            )
            return

        await inter.response.defer(ephemeral=True)

        repo = git.Repo(".", search_parent_directories=True)

        if repo.active_branch != branch:
            try:
                branch = repo.branches[branch]
                branch.checkout()
                logger.info("Switched to branch %s", branch)
            except git.exc.GitCommandError as exc:
                logger.exception("Failed to switch branch")
                await inter.edit_original_message(
                    content=f"Failed to checkout {branch}  due to {exc}",
                )
                return

        try:
            repo.remotes.origin.pull()
        except git.exc.GitCommandError as exc:
            logger.exception("Failed to pull changes")
            await inter.edit_original_message(
                content=f"Failed to pull updated changes due to {exc}",
            )
            return

        await self.restart_bot(
            inter,
            disable_markov,
            state_size,
        )

    @commands.slash_command(name="set_logging_level", description="Set the verbosity level for /logfile")
    async def set_logging_level(
        self,
        inter: disnake.ApplicationCommandInteraction,
        level: int = commands.Param(
            choices=["Debug", "Info", "Error"],
            converter=convert_level_to_int,
            description="What to show in the log output",
        ),
    ) -> None:
        """Set the logging level for the logfile.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The command interaction.
        level : int, optional
            The logging level to set.

        """
        logger.setLevel(level)
        await inter.response.send_message(f"Logging level set to {level.lower()}")

    @commands.slash_command(name="set_markov_chain", description="Set a new Markov chain")
    async def set_markov_chain(
        self,
        inter: disnake.ApplicationCommandInteraction,
        chain_name: str = commands.Param(
            choices=sorted([str(p) for p in Path("data/chains").glob("*.pickle")]),
            description="The name of the Markov chain to use.",
        ),
    ) -> None:
        """Switch the current Markov chain.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The command interaction.
        chain_name : str, optional
            The name of the chain to use.

        """
        if inter.author.id != App.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        await inter.response.send_message(f"Loading chain: {chain_name}", ephemeral=True)
        state_size = int(re.findall(r"\d+", chain_name)[0])
        markov.MARKOV_MODEL = markov.load_markov_model(f"data/chains/{chain_name}", state_size)

        await inter.followup.send(f"{chain_name} has successfully loaded.", ephemeral=True)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_all_reminders", description="view all of the reminders")
    async def show_all_reminders(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Show the reminders set for a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.

        """
        reminders = get_all_reminders()
        if not reminders:
            return await inter.response.send_message("You don't have any reminders.", ephemeral=True)
        reminders = sorted(
            [
                (datetime.datetime.fromisoformat(reminder["date"]).astimezone(datetime.UTC), reminder["reminder"])
                for reminder in reminders
            ],
            key=lambda entry: entry[0],
        )

        reminders = [(entry[0].strftime(r"%H:%M %d %B %Y (UTC)"), entry[1]) for entry in reminders]

        table = PrettyTable()
        table.align = "r"
        table.field_names = ["When", "What"]
        table._max_width = {"When": 25, "What": 75}  # pylint: disable=protected-access
        table.add_rows(reminders)
        message = f"You have {len(reminders)} reminders set.\n```"
        message += table.get_string() + "```"
        message += f"Current UTC time: {datetime.datetime.now(tz=datetime.UTC).strftime(r'%H:%M %d %B %Y')}"

        return await inter.response.send_message(message, ephemeral=True)


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(AdminTools(bot))
