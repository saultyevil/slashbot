#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
from dis import dis
from pathlib import Path

import disnake
from disnake.ext import commands, tasks
from disnake.utils import get

import config

cd_user = commands.BucketType.user
CHECK_FREQUENCY_SECONDS = 60


class Content(commands.Cog):
    """Demand and provide content, and track leech balance."""

    def __init__(self, bot, starting_balance=5, role_name="Content Leeches", stale_minutes=30):
        self.bot = bot
        self.starting_balance = starting_balance
        self.role_name = role_name
        self.stale_minutes = stale_minutes

        self.bank_file = Path("data/bank.json")
        with open(self.bank_file, "r") as fp:
            self.bank = json.load(fp)

        self.requests = []
        self.providers = []

        self.remove_stale_requests.start()

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="abandon",
        description="Leave the leech notification squad",
        guild_ids=config.slash_servers,
    )
    async def abandon(self, ctx):
        """Leave the leech notification squad."""
        await self.leave_leech_role(ctx.guild, ctx.author)
        await ctx.response.send_message(f"You have left the {self.role_name} notification squad.", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="balance",
        description="Check how many leech coins you have",
        guild_ids=config.slash_servers,
    )
    async def balance(self, ctx):
        """Check your leech coin balance."""
        print(self.bank)

        user_id = ctx.author.id
        await self.prepare_for_leech_command(ctx.guild, ctx.author)

        try:
            balance = self.bank[user_id]
        except KeyError:
            balance = await self.create_bank_account(user_id)

        if balance > 0:
            message = f"You have {balance} Leech coins in your bank account."
        elif balance == 0:
            message = "You bank account is empty, povvo!"
        else:
            message = f"You filthy little Leech, you owe the bank {abs(balance)} Leech coins!"

        await ctx.response.send_message(message, ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="needcontent",
        description="Demand content, filthy leech",
        guild_ids=config.slash_servers,
    )
    async def needcontent(self, ctx):
        """Demand that there be content, filthy little leech.

        Parameters
        ----------
        who: str
            The name of the user who should provide content.
        """
        user_id, role = await self.prepare_for_leech_command(ctx.guild, ctx.author)
        mention = role.mention if role else self.role_name
        balance = self.bank[user_id]

        if balance <= 0:
            return await ctx.response.send_message(
                "You don't have enough Leech coins to ask for content.", ephemeral=True
            )

        # Add request to queue of requests to be answered
        now = datetime.datetime.now()
        request = {
            "when": now.isoformat(),
            "stale_after": (now + datetime.timedelta(minutes=self.stale_minutes)).isoformat(),
            "who": user_id,
        }
        self.requests.append(request)

        user = await self.bot.fetch_user(user_id)
        print(f"{user.name} has been added to the list of requests")

        await ctx.response.send_message(f"{mention} your fellow leech {ctx.author.name} is requesting content.")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="notifsquad",
        description="Join the leech notification squad",
        guild_ids=config.slash_servers,
    )
    async def notifsquad(self, ctx):
        """Join the leech notification squad."""
        await self.get_or_create_leech_role(ctx.guild)
        await ctx.response.send_message(f"You've joined the {self.role_name} notification squad.", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="provide",
        description="Provide content like a good boy",
        guild_ids=config.slash_servers,
    )
    async def provide(self, ctx):
        """Provide content from the goodness of your heart, or heed the call
        for content."""
        user_id, role = await self.prepare_for_leech_command(ctx.guild, ctx.author)
        self.providers.append(user_id)

        user = await self.bot.fetch_user(user_id)
        print(f"{user.name} has been added to the list of providers")

        mention = role.mention if role else self.role_name
        await ctx.response.send_message(f"{mention}: {ctx.author.name} will be providing content soon.")

    # Events -------------------------------------------------------------------

    @commands.Cog.listener("on_voice_state_update")
    async def check_if_user_started_streaming(self, member, before, after):
        """Check if a user starts streaming after a request."""
        now = datetime.datetime.now()
        started_streaming = before.self_stream == False and after.self_stream == True

        channel = after.channel
        if not channel:
            return
        users_in_channel = len(channel.members) - 1
        if users_in_channel == 0:
            return

        # If there are requests, and this member just started streaming
        if self.requests and started_streaming:
            print(f"{member.name} started streaming when someone requested")
            # then remove all stale requests
            n_removed = 0
            for idx, request in enumerate(self.requests):
                user_id = int(request["who"])
                when = datetime.datetime.fromisoformat(request["when"])
                if when < now:
                    await self.remove_leech_coin(user_id)
                    self.requests.pop(idx)
                    n_removed += 1

            # give them some number of leech coins, depending on number of requests
            return await self.add_leech_coin(member.id, n_removed)

        # If no requests, but the person is a provider then check if someone
        # is providing on the voice channel
        if self.providers:
            for member in channel.members:
                is_member_streaming = member.voice.self_stream
                is_member_provider = member.id in self.providers

                if is_member_provider and is_member_streaming:
                    self.providers.remove(member.id)
                    await self.add_leech_coin(member.id)
                    print(f"{member.name} is streaming when they said they would provide")

    # Role generation ----------------------------------------------------------

    async def get_or_create_leech_role(self, guild):
        """Create a leech role if it doesn't already exist, and add user to it.

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user
        """
        leech_role = get(guild.roles, name=self.role_name)

        if not leech_role:
            try:
                leech_role = await guild.create_role(name=self.role_name, mentionable=True)
            except Exception as e:
                print("Can't create role: ", e)
                return None

        return leech_role

    async def join_leech_role(self, guild, user):
        """Add user to leech squad.

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user
        """
        leech_role = get(guild.roles, name=self.role_name)

        if not leech_role:
            return

        await user.add_roles(leech_role)

    async def leave_leech_role(self, guild, user):
        """Remove user from leech squad.

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user
        """
        leech_role = get(guild.roles, name=self.role_name)

        if not leech_role:
            return

        await user.remove_roles(leech_role)

    # Functions ----------------------------------------------------------------

    async def prepare_for_leech_command(self, guild, user):
        """Check a bank account exists and assigbn to role.

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
        await self.check_or_create_account(user.id)
        leech_role = await self.get_or_create_leech_role(guild)

        return user.id, leech_role

    async def add_leech_coin(self, user_id, to_add=1):
        """Add a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        await self.check_or_create_account(user_id)
        self.bank[user_id] = self.bank[user_id] + to_add
        await self.save_bank()

        user = await self.bot.fetch_user(user_id)
        print(f"Added {to_add} coins to {user.name}. New balance:", self.bank[user_id])

    async def create_bank_account(self, user_id):
        """Add a user to the bank JSON.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        self.bank[user_id] = self.starting_balance
        return self.bank[user_id]

    async def remove_leech_coin(self, user_id):
        """Remove a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        await self.check_or_create_account(user_id)
        self.bank[user_id] = self.bank[user_id] - 1
        await self.save_bank()

        user = await self.bot.fetch_user(user_id)
        print(f"Removed coin from {user.name}. New balance:", self.bank[user_id])

    async def save_bank(self):
        """Save changes to the bank to file."""
        with open(self.bank_file, "w") as fp:
            json.dump(self.bank, fp)

    async def check_or_create_account(self, user_id):
        """Check a bank account exists for a user.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        if user_id not in self.bank:
            await self.create_bank_account(user_id)

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=CHECK_FREQUENCY_SECONDS)
    async def remove_stale_requests(self):
        """Check periodically for stale requests."""
        if len(self.requests) == 0:
            return

        now = datetime.datetime.now()
        for idx, request in enumerate(self.requests):
            when_stale = datetime.datetime.fromisoformat(request["stale_after"])
            if when_stale < now:
                self.requests.pop(idx)
