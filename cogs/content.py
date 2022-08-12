#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import datetime
import disnake
from disnake.utils import get
from disnake.ext import commands
from pathlib import Path

import config


cd_user = commands.BucketType.user
STARTING_BALANCE = 3
ROLE_NAME = "Content Leeches"


class Content(commands.Cog):
    """Demand and provide content, and track leech balance."""

    def __init__(self, bot):
        self.bot = bot

        self.bank_file = Path("data/content_bank.json")
        if not self.bank_file.is_file():
            with open(self.bank_file, "w") as fp:
                fp.write("{}")

        with open(self.bank_file, "r") as fp:
            self.bank = json.load(fp)

        self.accounts = tuple(self.bank.keys())

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="balance", description="Check how many leech coins you have", guild_ids=config.slash_servers)
    async def balance(self, ctx):
        """Check your leech coin balance.
        """
        user_id = int(ctx.author.id)
        await self._prepare_for_leech_command(ctx.guild, ctx.author)

        try:
            balance = self.bank[user_id]
        except KeyError:
            balance = await self.create_bank_account(user_id)

        if balance > 0:
            message = f"You have {balance} Leech coins to spend."
        elif balance == 0:
            message = "You Leech coin bank is empty!"
        else:
            message = f"You filthy little Leech, you owe the Leech bank {abs(balance)} coins!"

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
        user_id = int(ctx.author.id)
        await self._prepare_for_leech_command(ctx.guild, ctx.author)

        await self.remove_leech_coin(user_id)
        await ctx.response.send_message(f"{ctx.author.name}, the leech, has requested content")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="provide", description="Provide content like a good boy", guild_ids=config.slash_servers)
    async def provide(self, ctx):
        """Provide content from the goodness of your heart, or heed the call for
        content.
        """
        user_id = int(ctx.author.id)
        await self._prepare_for_leech_command(ctx.guild, ctx.author)

        await self.add_leech_coin(user_id)
        await ctx.response.send_message(f"{ctx.author.name} will be providing content")


    # Role generation ----------------------------------------------------------

    async def create_and_assign_leech_role(self, guild, user):
        """Create a leech role if it doesn't already exist.
        """
        leech_role = get(guild.roles, name=ROLE_NAME)

        if not leech_role:
            try:
                leech_role = await guild.create_role(name=ROLE_NAME, mentionable=True)
            except Exception as e:
                return print("Can't create role: ", e)

        await user.add_roles(leech_role)

    # Functions ----------------------------------------------------------------

    async def _prepare_for_leech_command(self, guild, user):
        """Check a bank account exists and assigbn to role

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user
        """
        await self._check_for_account(int(user.id))
        await self.create_and_assign_leech_role(guild, user)

    async def add_leech_coin(self, user_id):
        """Add a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        self.bank[user_id] = self.bank[user_id] + 1
        await self._save_bank()

    async def create_bank_account(self, user_id):
        """Add a user to the bank JSON.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        self.bank[user_id] = STARTING_BALANCE
        self.accounts = tuple(self.bank.keys())

        return self.bank[user_id]

    async def remove_leech_coin(self, user_id):
        """Remove a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        self.bank[user_id] = self.bank[user_id] - 1
        await self._save_bank()

    async def _save_bank(self):
        """Save changes to the bank to file.
        """
        with open(self.bank_file, "w") as fp:
            json.dump(self.bank, fp)

    async def _check_for_account(self, user_id):
        """Check a bank account exists for a user.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        if user_id not in self.accounts:
            await self.create_bank_account(user_id)
