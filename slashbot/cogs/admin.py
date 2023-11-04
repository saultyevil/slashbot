#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This cog contains admin commands for Slashbot."""

import logging
import os
import re
import sys
from pathlib import Path
from types import coroutine

import disnake
import git
import requests
from disnake.ext import commands

from slashbot import __version__, markov
from slashbot.config import App
from slashbot.custom_cog import SlashbotCog

COOLDOWN_USER = commands.BucketType.user
logger = logging.getLogger(App.config("LOGGER_NAME"))

AVAILABLE_CHAINS = (
    # "chain-0.pickle",
    "chain-1.pickle",
    "chain-2.pickle",
    "chain-3.pickle",
    "chain-4.pickle",
)


class Admin(SlashbotCog):
    """Admin commands and tools for Slashbot.

    The most useful command is to look at the logfile, or to restart the bot
    when changes have been made.
    """

    def __init__(
        self,
        bot: commands.InteractionBot,
    ):
        super().__init__()
        self.bot = bot
        self.logfile_path = Path(App.config("LOGFILE_NAME"))

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="version", description="Print the current version number of the bot")
    async def print_version(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Print the current version number of the bot."""
        await inter.response.send_message(f"Current version: {__version__}", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
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
        file: str
            The name of the file to look at
        num_lines: int
            The number of lines to print.
        """
        await inter.response.defer(ephemeral=True)

        if file == "slashbot":
            file_name = self.logfile_path
        else:
            file_name = self.logfile_path.with_name("disnake.log")

        with open(file_name, "r", encoding="utf-8") as file_in:
            log_lines = file_in.readlines()

        # iterate backwards over log_lines, until either n_lines is reached or
        # the character limit is reached

        tail = []
        num_chars = 0

        for i in range(1, num_lines + 1):
            try:
                num_chars += len(log_lines[-i])
            except IndexError:
                break

            if num_chars > App.config("MAX_CHARS"):
                break
            tail.append(log_lines[-i])

        return await inter.edit_original_message(f"```{''.join(tail[::-1])}```")

    @commands.slash_command(name="ip", description="get the external ip address for the bot")
    async def print_ip_address(self, inter: disnake.ApplicationCommandInteraction):
        """Get the external IP of the bot."""
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)

        try:
            ip_addr = requests.get("https://api.ipify.org", timeout=5).content.decode("utf-8")
            await inter.response.send_message(f"```{ip_addr}```", ephemeral=True)
        except requests.exceptions.Timeout:
            await inter.response.send_message("The IP request timed out.", ephemeral=True)

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
            choices=["0", "1", "2", "3", "4"], default=0, description="Set the state size of the markov model"
        ),
    ):
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
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)

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

        os.execv(sys.executable, ["python"] + arguments)

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
            choices=["0", "1", "2", "3", "4"], default=0, description="Set the state size of the markov model"
        ),
    ):
        """Update and restart the bot with a new process.

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
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)

        await inter.response.defer(ephemeral=True)

        repo = git.Repo(".", search_parent_directories=True)

        if repo.active_branch != branch:
            try:
                branch = repo.branches[branch]
                branch.checkout()
                logger.info("Switched to branch %s", branch)
            except git.exc.GitCommandError as exc:
                logger.exception("Failed to switch branch during update: %s", exc)
                return await inter.response.send_message(f"Failed to checkout {branch} during update", ephemeral=True)

        repo.remotes.origin.pull()

        await self.restart_bot(
            inter,
            disable_markov,
            state_size,
        )

    @commands.slash_command(name="set_markov_chain", description="Set a new Markov chain")
    async def set_markov_chain(
        self,
        inter: disnake.ApplicationCommandInteraction,
        chain_name: str = commands.Param(choices=AVAILABLE_CHAINS, description="The name of the Markov chain to use."),
    ):
        """Switch the current Markov chain.

        Parameters
        ----------
        chain_name : str, optional
            The name of the chain to use.
        """
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)

        await inter.response.send_message(f"Loading chain: {chain_name}", ephemeral=True)

        state_size = int(re.findall(r"\d+", chain_name)[0])
        markov.MARKOV_MODEL = markov.load_markov_model(f"data/chains/{chain_name}", state_size)

        await inter.followup.send(f"{chain_name} has successfully loaded.", ephemeral=True)


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(Admin(bot))
