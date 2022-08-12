#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import datetime
import disnake
from disnake.ext import commands

import config

cd_user = commands.BucketType.user


class Content(commands.cog):
    """Demand and provide content, and track leech balance."""

    def __init__(self, bot):
        self.bot = bot
        with open("data/content_bank.json", "r") as fp:
            self.bank = json.load(fp)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user, guild_ids=config.slash_servers)
    @commands.slash_command(name="balance", description="Check how many leech coins you have")
    async def balance(self, ctx):
        """Check your leech coin balance.
        """

        user_id = int(ctx.author.id)

        try:
            balance = self.bank[user_id]
        except KeyError:
            balance = self.create_bank_account(user_id)

        if balance > 0:
            message = f"You have {balance} Leech coins to spend."
        elif balance == 0:
            message = "You Leech coin bank is empty!"
        else:
            message = f"You filthy little Leech, you owe the Leech bank {balance} coins!"

        await ctx.response.send_message(message, ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="demand", description="Demand content, filthy leech", guild_ids=config.slash_servers)
    async def demand(self, ctx):
        """Demand that there be content, filthy little leech.

        Parameters
        ----------
        who: str
            The name of the user who should provide content.
        """
        await self.remove_leech_coin(int(ctx.author.id))
        await ctx.response.send_message(f"{ctx.author.name}, the leech, has requested content")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user, guild_ids=config.slash_servers)
    @commands.slash_command(name="provide", description="Provide content like a good boy")
    async def provide(self, ctx):
        """Provide content from the goodness of your heart, or heed the call for
        content.
        """
        await self.add_leech_coin(int(ctx.author.id))
        await ctx.response.send_message(f"{ctx.author.name} will be providing content")

    # Functions ----------------------------------------------------------------

    async def add_leech_coin(self, user_id):
        """Add a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        self.bank[user_id] = self.bank[user_id] + 1

    async def create_bank_account(self, user_id):
        """Add a user to the bank JSON.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        self.bank[user_id] = 0
        return self.bank[user_id]

    async def remove_leech_coin(self, user_id):
        """Remove a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        self.bank[user_id] = self.bank[user_id] + 1

    async def _save_bank(self):
        """Save changes to the bank to file.
        """
        with open("data/bank.json", "w") as fp:
            json.dump(self.bank, fp)
