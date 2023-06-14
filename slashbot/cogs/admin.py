#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Admin commands for the bot."""
import random
import asyncio
import logging
import os
import sys
from pathlib import Path
from types import coroutine

import disnake
import requests
from disnake.ext import commands

from slashbot import __version__
from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.markov import MARKOV_MODEL
from slashbot.markov import generate_sentences_for_seed_words

cd_user = commands.BucketType.user
logger = logging.getLogger(App.config("LOGGER_NAME"))


class AdminCommands(CustomCog):
    """Admin tools for the bot."""

    def __init__(self, bot: commands.InteractionBot, log_path: Path):
        """Initialize the class."""
        super().__init__()
        self.bot = bot
        self.log_path = Path(log_path)

        self.markov_sentences = (
            generate_sentences_for_seed_words(
                MARKOV_MODEL,
                ["unban"],
                1,
            )
            if self.bot.enable_auto_markov_gen
            else {"unban": []}
        )

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="version", description="get the version number of the bot")
    @commands.default_member_permissions(administrator=True)
    async def check_version(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Check the version of the bot in use"""
        await inter.response.send_message(f"Version {__version__}", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="logfile", description="get the tail of the logfile")
    @commands.default_member_permissions(administrator=True)
    async def log_tail(
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

        TODO: reading in the file may need optimizing in the future, e.g.:
              https://stackoverflow.com/questions/136168/get-last-n-lines-of-a-file-similar-to-tail

        Parameters
        ----------
        file: str
            The name of the file to look at
        num_lines: int
            The number of lines to print.
        """
        await inter.response.defer(ephemeral=True)

        if file == "slashbot":
            file_name = self.log_path
        else:
            file_name = self.log_path.with_name("disnake.log")

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

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="ip", description="get the external ip address for the bot")
    @commands.default_member_permissions(administrator=True)
    async def external_ip_address(self, inter: disnake.ApplicationCommandInteraction):
        """Get the external IP of the bot."""
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)

        ip_addr = requests.get("https://api.ipify.org", timeout=5).content.decode("utf-8")
        await inter.response.send_message(f"```{ip_addr}```", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="restart_bot", description="restart the bot")
    @commands.default_member_permissions(administrator=True)
    async def restart_bot(self, inter: disnake.ApplicationCommandInteraction):
        """Restart the bot."""
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)

        logger.info("restarting bot with new process")
        await inter.response.send_message("Restarting the bot...", ephemeral=True)

        os.execv(sys.executable, ["python"] + sys.argv)

    @commands.slash_command(description="unban adam and invite to the server")
    @commands.default_member_permissions(administrator=True)
    async def unban_adam(self, inter: disnake.ApplicationCommandInteraction):
        """Un-ban and re-invite Adam.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The command interaction.
        """
        user = await self.bot.fetch_user(App.config("ID_USER_ADAM"))
        guild = await self.bot.fetch_guild(App.config("ID_SERVER_ADULT_CHILDREN"))
        channel = await self.bot.fetch_channel(App.config("ID_CHANNEL_IDIOTS"))

        if inter.author.guild != guild:
            return await inter.response.send_message(
                "You can only use this in the adult children server.", ephemeral=True
            )

        # If the user isn't banned, fetch_ban raises NotFound
        try:
            _ban = await guild.fetch_ban(user)
        except disnake.NotFound:
            return await inter.response.send_message("The user is not currently banned.", ephemeral=True)

        # Generate a funny little timer between 1 and 24 hours
        delay = random.randint(1, 24) * 3600

        # Let the user know that the process has started
        await inter.response.send_message(
            "The unbanning process has started. This can take anywhere from 1 to 24 hours.", ephemeral=True
        )

        # Start a background task to handle the unbanning and re-invitation
        self.bot.loop.create_task(self.delayed_unban_and_invite(user, guild, channel, delay))

    async def delayed_unban_and_invite(self, user, guild, channel, delay):
        # Wait for the random timer before unbanning
        await asyncio.sleep(delay)

        try:
            await guild.unban(user)
        except disnake.Forbidden:
            return print("Do not have permission to un-ban user.")  # Adjust this to handle the error as desired

        try:
            invite = await channel.create_invite(reason="Invite Adam", max_uses=1, unique=True)
        except disnake.Forbidden:
            return print("Do not have permission to create an invite.")  # Adjust this to handle the error as desired

        await user.send(f"{self.get_generated_sentence('unban')}: {invite}")
