#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from dis import dis
import json
import datetime
import disnake
from disnake.utils import get
from disnake.ext import commands, tasks
from pathlib import Path

import config


cd_user = commands.BucketType.user

STARTING_BALANCE = 3
ROLE_NAME = "Content Leeches"
STALE_MINUTES = 30
CHECK_FREQUENCY_SECONDS = 60


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
        self.current_requests = []
        self.current_providers = []

        self.check_for_stale_requests.start()

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="abandon", description="Leave the leech notification squad", guild_ids=config.slash_servers)
    async def abandon(self, ctx):
        """Leave the leech notification squad.
        """
        await self._leave_leech_role(ctx.guild, ctx.author)
        await ctx.response.send_message("You have left the leech notification squad.", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="balance", description="Check how many leech coins you have", guild_ids=config.slash_servers)
    async def balance(self, ctx):
        """Check your leech coin balance.
        """
        print(self.bank)

        user_id = ctx.author.id
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
    @commands.slash_command(name="content", description="Demand content, filthy leech", guild_ids=config.slash_servers)
    async def content(self, ctx):
        """Demand that there be content, filthy little leech.

        Parameters
        ----------
        who: str
            The name of the user who should provide content.
        """
        user_id, role = await self._prepare_for_leech_command(ctx.guild, ctx.author)
        mention = role.mention if role else ROLE_NAME
        balance = self.bank[user_id]

        if balance <= 0:
            return await ctx.response.send_message(
                f"{mention} your fellow leech, {ctx.author.name}, wants content BUT IS TOO POOR TO REQUEST IT. They "
                f"have a balance of {balance} Leech coins."
            )

        # Add request to queue of requests to be answered
        now = datetime.datetime.now()
        request = {
            "when": now.isoformat(),
            "stale_after": (now + datetime.timedelta(minutes=STALE_MINUTES)).isoformat(),
            "who": user_id
        }
        self.current_requests.append(request)


        await ctx.response.send_message(f"{mention} your fellow leech, {ctx.author.name}, is requesting content")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="notifsquad", description="Join the leech notification squad", guild_ids=config.slash_servers)
    async def notifsquad(self, ctx):
        """Join the leech notification squad.
        """
        await self._get_or_create_leech_role(ctx.guild)
        await ctx.response.send_message("You have joined the leech notification squad.", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="provide", description="Provide content like a good boy", guild_ids=config.slash_servers)
    async def provide(self, ctx):
        """Provide content from the goodness of your heart, or heed the call for
        content.
        """
        user_id, role = await self._prepare_for_leech_command(ctx.guild, ctx.author)
        self.current_providers.append(user_id)
        print(self.current_providers)

        mention = role.mention if role else ROLE_NAME
        await ctx.response.send_message(f"ALART {mention}, {ctx.author.name} will be providing content")

    # Events -------------------------------------------------------------------

    @commands.Cog.listener("on_voice_state_update")
    async def check_if_user_started_streaming(self, member, before, after):
        """Check if a user starts streaming after a request
        """
        now = datetime.datetime.now()
        num_requests = len(self.current_requests)
        started_streaming = before.self_stream == False and after.self_stream == True

        channel = after.channel
        if not channel: return
        users_in_channel = len(channel.members) - 1
        if users_in_channel == 0: return

        # If there are requests, and this member just started streaming
        if num_requests and started_streaming:
            # then remove all stale requests
            n_removed = 0
            for idx, request in enumerate(self.current_requests):
                user_id = int(request["who"])
                when = datetime.datetime.fromisoformat(request["when"])
                if when < now:
                    await self.remove_leech_coin(user_id)
                    self.current_requests.pop(idx)
                    n_removed += 1

            # give them some number of leech coins, depending on number of requests
            await self.add_leech_coin(member.id, n_removed)
            return

        # If no requests, but the person is a provider then check if someone
        # is providing on the voice channel
        for member in channel.members:
            is_member_streaming = member.voice.self_stream
            is_member_provider = member.id in self.current_providers

            if is_member_provider and is_member_streaming:
                await self.add_leech_coin(member.id)
                self.current_providers.remove(member.id)

    # Role generation ----------------------------------------------------------

    async def _get_or_create_leech_role(self, guild):
        """Create a leech role if it doesn't already exist, and add user to it.

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user
        """
        leech_role = get(guild.roles, name=ROLE_NAME)

        if not leech_role:
            try:
                leech_role = await guild.create_role(name=ROLE_NAME, mentionable=True)
            except Exception as e:
                print("Can't create role: ", e)
                return None

        return leech_role

    async def _join_leech_role(self, guild, user):
        """Add user to leech squad.

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user
        """
        leech_role = get(guild.roles, name=ROLE_NAME)

        if not leech_role:
            return

        await user.add_roles(leech_role)

    async def _leave_leech_role(self, guild, user):
        """Remove user from leech squad.

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user
        """
        leech_role = get(guild.roles, name=ROLE_NAME)

        if not leech_role:
            return

        await user.remove_roles(leech_role)

    # Functions ----------------------------------------------------------------

    async def _prepare_for_leech_command(self, guild, user):
        """Check a bank account exists and assigbn to role

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user

        Returns
        -------
        user.id: int
            The id of the user.
        """
        await self._check_for_account(user.id)
        leech_role = await self._get_or_create_leech_role(guild)

        return user.id, leech_role

    async def add_leech_coin(self, user_id, to_add=1):
        """Add a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        await self._check_for_account(user_id)
        self.bank[user_id] = self.bank[user_id] + to_add
        print(f"adding coin to {user_id}, balance is {self.bank[user_id]}")
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
        await self._check_for_account(user_id)
        self.bank[user_id] = self.bank[user_id] - 1
        print(f"removing coin from {user_id}, balance is {self.bank[user_id]}")
        await self._save_bank()

    async def _save_bank(self):
        """Save changes to the bank to file.
        """
        with open(self.bank_file, "w") as fp:
            json.dump(self.bank, fp)
        print("banked saved", self.bank)

    async def _check_for_account(self, user_id):
        """Check a bank account exists for a user.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        if user_id not in self.accounts:
            await self.create_bank_account(user_id)

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=CHECK_FREQUENCY_SECONDS)
    async def check_for_stale_requests(self):
        """Check periodically for stale requests.
        """
        if len(self.current_requests) == 0:
            return

        now = datetime.datetime.now()
        for idx, request in enumerate(self.current_requests):
            when_stale = datetime.datetime.fromisoformat(request["stale_after"])
            if when_stale < now:
                self.current_requests.pop(idx)
