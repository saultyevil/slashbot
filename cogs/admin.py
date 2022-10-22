#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Admin commands for the bot."""

import logging
import os
import sys
from pathlib import Path
import datetime
import json
from types import coroutine

import disnake
import requests
from prettytable import PrettyTable
from disnake.ext import commands
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

import config

cd_user = commands.BucketType.user
logger = logging.getLogger(config.LOGGER_NAME)


class Admin(commands.Cog):
    """Admin tools for the bot."""

    def __init__(self, bot: commands.InteractionBot, log_path: Path):
        """Initialize the class."""
        self.bot = bot
        self.log_path = Path(log_path)

        self.load_reminders()

        def on_modify(_):
            self.load_reminders()
            logger.info("Reloaded reminders")

        observer = Observer()
        event_handler = PatternMatchingEventHandler(["*"], None, False, True)
        event_handler.on_modified = on_modify
        observer.schedule(event_handler, config.REMINDERS_FILE, False)
        observer.start()

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(
        self, inter: disnake.ApplicationCommandInteraction
    ) -> disnake.ApplicationCommandInteraction:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOL_DOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="logfile", description="get the tail of the logfile")
    @commands.default_member_permissions(administrator=True)
    async def log_tail(
        self,
        inter: disnake.ApplicationCommandInteraction,
        num_lines: int = commands.Param(
            default=10,
            description="The number of lines to include in the tail of the log file.",
            max_value=50,
            min_value=1,
        ),
    ):
        """Print the tail of the log file.

        TODO: reading in the file may need optimizing in the future, e.g.:
              https://stackoverflow.com/questions/136168/get-last-n-lines-of-a-file-similar-to-tail

        Parameters
        ----------
        n_lines: int
            The number of lines to print.
        """
        await inter.response.defer(ephemeral=True)

        with open(self.log_path, "r", encoding="utf-8") as file_in:
            log_lines = file_in.readlines()

        # iterate backwards over log_lines, until either n_lines is reached or
        # the character limit is reached

        tail = []
        num_chars = 0

        for i in range(num_lines):
            num_chars += len(log_lines[-i])
            if num_chars > config.MAX_CHARS:
                break
            tail.append(log_lines[-i])

        await inter.edit_original_message(f"```{' '.join(tail)}```")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="ip", description="get the external ip address for the bot")
    @commands.default_member_permissions(administrator=True)
    async def external_ip_address(self, inter: disnake.ApplicationCommandInteraction):
        """Get the external IP of the bot."""
        if inter.author.id != config.ID_USER_SAULTYEVIL:
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)

        ip_addr = requests.get("https://api.ipify.org").content.decode("utf-8")
        await inter.response.send_message(f"```{ip_addr}```", ephemeral=True)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="reboot", description="restart the bot")
    async def reboot(self, inter: disnake.ApplicationCommandInteraction):

        """Restart the bot."""
        if inter.author.id != config.ID_USER_SAULTYEVIL:
            return await inter.response.send_message("You don't have permission to use this command.")

        logger.info("restarting bot with new process")
        await inter.response.send_message("Restarting the bot...", ephemeral=True)

        os.execv(sys.executable, ["python"] + sys.argv)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="show_all_reminders", description="view all the reminders")
    @commands.default_member_permissions(administrator=True)
    async def show_all_reminders(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Show all the reminders.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        reminders = [
            [m_id, datetime.datetime.fromisoformat(item["when"]), item["what"]] for m_id, item in self.reminders.items()
        ]

        if not reminders:
            return await inter.response.send_message("There are no reminders.", ephemeral=True)

        message = f"There are {len(reminders)} reminders set.\n```"
        table = PrettyTable()
        table.align = "r"
        table.field_names = ["ID", "When", "What"]
        table._max_width = {"ID": 10, "When": 10, "What": 50}  # pylint: disable=protected-access
        table.add_rows(reminders)
        message += table.get_string(sortby="ID") + "```"

        return await inter.response.send_message(message[:2000], ephemeral=True)

    # Functions ----------------------------------------------------------------

    def load_reminders(self):
        """Load the reminders from a file."""
        with open(config.REMINDERS_FILE, "r", encoding="utf-8") as file_in:
            self.reminders = json.load(file_in)
