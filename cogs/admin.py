#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path
import logging
import requests

from disnake.ext import commands

import config

cd_user = commands.BucketType.user
logger = logging.getLogger("slashbot")


class Admin(commands.Cog):
    """Admin tools for the bot."""

    def __init__(self, bot, log_path):
        """Initialize the class."""
        self.bot = bot
        self.log_path = Path(log_path)

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOLDOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="logtail", description="tail the log file")
    @commands.default_member_permissions(administrator=True)
    async def logtail(self, inter, n_lines=20):
        """Print the tail of the log file.
        TODO: this needs optimizing, e.g.:
              https://stackoverflow.com/questions/136168/get-last-n-lines-of-a-file-similar-to-tail

        Parameters
        ----------
        n_lines: int
            The number of lines to print.
        """
        await inter.response.defer(ephemeral=True)

        with open(self.log_path, "r", encoding="utf-8") as file_in:
            log_lines = file_in.readlines()

        tail = log_lines[-n_lines:]
        formatted = " ".join(tail)[-:1990]

        await inter.edit_original_message(f"```{formatted}```")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="externip", description="get the external ip address for the bot")
    @commands.default_member_permissions(administrator=True)
    async def externip(self, inter):
        """Get the external IP of the bot."""
        if inter.author.id != config.ID_USER_SAULTYEVIL:
            return await inter.response.send_message("```0.0.0.0```", ephemeral=True)

        ip_addr = requests.get("https://api.ipify.org").content.decode("utf-8")
        await inter.response.send_message(f"```{ip_addr}```", ephemeral=True)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="reboot", description="reboot the bot")
    @commands.default_member_permissions(administrator=True)
    async def reboot(self, inter):
        """Restart the bot."""
        if inter.author.id != config.ID_USER_SAULTYEVIL:
            return await inter.response.send_message("You don't have permission to use this command.")

        logger.info("bot is being restarted")
        await inter.response.send_message("Restarting the bot...", ephemeral=True)
        os.execv(sys.executable, ["python"] + sys.argv)
