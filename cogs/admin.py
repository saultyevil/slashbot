#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import logging

from disnake.ext import commands

import config

cd_user = commands.BucketType.user
logger = logging.getLogger("slashbot")


class Admin(commands.Cog):  # pylint: disable=too-many-instance-attributes
    """Admin tools for the bot."""

    def __init__(self, bot, log_path):
        """Initialize the class."""
        self.bot = bot
        self.log_path = Path(log_path)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="logtail", description="tail the log file")
    @commands.default_member_permissions(administrator=True)
    async def tail_log(self, inter, n_lines=10):
        """Print the tail of the log file.
        TODO: this needs optimizing, e.g.:
              https://stackoverflow.com/questions/136168/get-last-n-lines-of-a-file-similar-to-tail
        """
        with open(self.log_path, "r", encoding="utf-8") as file_in:
            lines = file_in.readlines()

        tail = lines[-n_lines:]

        await inter.response.send_message(tail)
