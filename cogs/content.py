#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime
import json
from pathlib import Path
import re

import disnake
from disnake.ext import commands, tasks
from disnake.utils import get
from prettytable import PrettyTable

import config

cd_user = commands.BucketType.user
CHECK_FREQUENCY_SECONDS = 60


async def convert_yes_to_false(_, inp):
    """Swap Yes to False, so, e.g., if share == yes, then ephemeral=False."""
    if inp == "Yes":
        return False
    return True


class Content(commands.Cog):  # pylint: disable=too-many-instance-attributes
    """Demand and provide content, and track leech balance."""

    def __init__(
        self,
        bot,
        generate_sentence,
        starting_balance=5,
        role_name="Content Leeches",
        stale_minutes=30,
    ):
        self.bot = bot
        self.generate_sentence = generate_sentence
        self.starting_balance = starting_balance
        self.role_name = role_name
        self.stale_minutes = stale_minutes
        self.bank_file = Path(config.BANK_FILE)
        with open(self.bank_file, "r", encoding="utf-8") as fp:
            self.bank = json.load(fp)
        self.requests = []
        self.providers = []

        self.remove_stale_requests.start()  # pylint: disable=no-member

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOLDOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="leaveleech",
        description="Leave the leech notification squad",
    )
    async def leaveleech(self, inter):
        """Leave the leech notification squad."""
        await self.leave_leech_role(inter.guild, inter.author)
        await inter.response.send_message(f"You have left the {self.role_name} notification squad.", ephemeral=True)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="balance",
        description="Check how many leech coins you have",
    )
    async def balance(
        self, inter, share=commands.Param(default="No", choices=["Yes", "No"], converter=convert_yes_to_false)
    ):
        """Check your leech coin balance."""
        user_id, _ = await self.prepare_for_leech_command(inter.guild, inter.author)
        balance = self.bank[user_id]["balance"]

        if balance > 0:
            message = "You have Leech coins in your bank account."
        elif balance == 0:
            message = "You're broke, povvo!"
        else:
            message = "You filthy little Leech, you owe the bank!"

        embed = disnake.Embed(
            title=f"{inter.author.name}'s Leech Balance", color=disnake.Color.default(), description=message
        )
        embed.set_footer(text=f"{self.generate_sentence('leech')}")
        embed.set_thumbnail(url="https://www.nicepng.com/png/full/258-2581153_cartoon-leech.png")
        embed.add_field(name="Balance", value=f"{balance} Leech coins")
        embed.add_field(name="Status", value=f"{self.bank[user_id]['status']}")

        await inter.response.send_message(embed=embed, ephemeral=share)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="needcontent",
        description="Demand content, filthy leech",
    )
    async def needcontent(self, inter):
        """Demand that there be content, filthy little leech.

        Parameters
        ----------
        who: str
            The name of the user who should provide content.
        """
        user_id, role = await self.prepare_for_leech_command(inter.guild, inter.author)
        mention = role.mention if role else self.role_name
        current_requesters = [r["who"].id for r in self.requests]

        balance = self.bank[user_id]["balance"]

        if balance <= 0:
            return await inter.response.send_message(
                "You don't have enough Leech coins to ask for content.", ephemeral=True
            )

        # Add request to queue of requests to be answered
        if inter.author.id not in current_requesters:
            now = datetime.datetime.now()
            request = {
                "when": now.isoformat(),
                "stale_after": (now + datetime.timedelta(minutes=self.stale_minutes)).isoformat(),
                "who": inter.author,
            }
            self.requests.append(request)
            print(f"{inter.user.name} has been added to the list of requests")

        if len(self.requests) > 1:
            requesters = (
                ", ".join(map(lambda r: r["who"].name, self.requests[:-1]))
                + f" and {self.requests[-1]['who'].name} *need*"
            )
        else:
            requesters = f"{self.requests[0]['who'].name} *needs*"

        await inter.response.send_message(f"{mention} {requesters} content.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="leechsquad",
        description="Join the leech notification squad",
    )
    async def leechsquad(self, inter):
        """Join the leech notification squad."""
        await self.get_or_create_leech_role(inter.guild)
        await inter.response.send_message(f"You've joined the {self.role_name} notification squad.", ephemeral=True)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="contentcreator",
        description="Provide content like a good boy",
    )
    async def contentcreator(self, inter):
        """Provide content from the goodness of your heart, or heed the call
        for content."""
        _, role = await self.prepare_for_leech_command(inter.guild, inter.author)
        mention = role.mention if role else self.role_name
        current_providers = [p["who"].id for p in self.providers]

        if inter.author.id not in current_providers:
            # same data structure as when requesting for content
            now = datetime.datetime.now()
            request = {
                "when": now.isoformat(),
                "stale_after": (now + datetime.timedelta(minutes=self.stale_minutes)).isoformat(),
                "who": inter.author,
            }
            self.providers.append(request)
            print(f"{inter.author.name} has been added to the list of providers")

        if len(self.providers) > 1:
            providers = (
                ", ".join(map(lambda r: r["who"].name, self.providers[:-1])) + f" and {self.providers[-1]['who'].name}"
            )
        else:
            providers = f"{self.providers[0]['who'].name}"

        await inter.response.send_message(f"{mention} {providers} will be providing content.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="leechscore",
        description="Leech coin leaderboard",
    )
    async def leechscore(
        self, inter, share=commands.Param(default="No", choices=["Yes", "No"], converter=convert_yes_to_false)
    ):
        """Show the balance for all users."""
        _, _ = await self.prepare_for_leech_command(inter.guild, inter.author)
        if not self.bank:
            await inter.response.send_message("There are no accounts.", ephemeral=True)

        # Use list comprehension to get a list of name, balance and status for
        # each account
        rows = [[account["name"], account["balance"], account["status"]] for account in self.bank.values()]

        # PrettyTable to create a nicely formatted table
        table = PrettyTable()
        table.align = "r"
        table.field_names = ["Name", "Balance", "Status"]
        table.add_rows(rows)

        await inter.response.send_message(f"```{table.get_string(sortby='Name')}```", ephemeral=share)

    # Events -------------------------------------------------------------------

    @commands.Cog.listener("on_voice_state_update")
    async def check_if_user_started_streaming(self, member, before, after):
        """Check if a user starts streaming after a request."""
        now = datetime.datetime.now()
        started_streaming = before.self_stream is False and after.self_stream is True

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
                user_id = str(request["who"].id)
                when = datetime.datetime.fromisoformat(request["when"])
                if when < now:
                    await self.remove_leech_coin(user_id)
                    print(f"removing {request['who']} from list")
                    self.requests.pop(idx)
                    n_removed += 1

            # give them some number of leech coins, depending on number of requests
            return await self.add_leech_coin(str(member.id), n_removed)

        # If no requests, but the person is a provider then check if someone
        # is providing on the voice channel
        if self.providers:
            for this_member in channel.members:
                is_member_streaming = this_member.voice.self_stream
                is_member_provider = this_member in self.providers

                if is_member_provider and is_member_streaming:
                    self.providers.remove(this_member.id)
                    await self.add_leech_coin(str(this_member.id))
                    print(f"{this_member.name} is streaming when they said they would provide")

        print("reqests: ", self.requests)
        print("providers: ", self.providers)

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
            except Exception as exception:  # pylint: disable=broad-except
                print("Can't create role: ", exception)
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
        await self.check_or_create_account(str(user.id))
        leech_role = await self.get_or_create_leech_role(guild)

        return str(user.id), leech_role

    async def add_leech_coin(self, user_id, to_add=1):
        """Add a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        user = await self.bot.fetch_user(user_id)

        await self.check_or_create_account(user_id)
        self.bank[user_id] = self.bank[user_id] + to_add
        await self.update_account_status(user_id, user.name)
        await self.save_bank()

        print(f"Added {to_add} coins to {user.name}. New balance:", self.bank[user_id])

    async def create_bank_account(self, user_id):
        """Add a user to the bank JSON.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        user = await self.bot.fetch_user(user_id)
        account = {"user_id": user_id, "name": user.name, "balance": self.starting_balance, "status": "Newfag"}

        print("Created bank account for", user.name, "user_id", user_id, type(user_id))
        self.bank[user_id] = account
        await self.save_bank()

        return account

    async def update_account_status(self, user_id, user_name):
        """Update the account status depending on balance.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        user_name: str
            The name of the user.
        """
        balance = self.bank[user_id]["balance"]
        new_status = self.bank[user_id]["status"]

        if balance > 0:
            new_status = "Valued content provider"
        else:
            new_status = "Despicable leech"

        print(f"{user_name} status changed from {self.bank[user_id]['status']} to {new_status}")
        self.bank[user_id]["status"] = new_status

    async def remove_leech_coin(self, user_id):
        """Remove a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        """
        user = await self.bot.fetch_user(user_id)

        await self.check_or_create_account(user_id)
        self.bank[user_id] = self.bank[user_id] - 1
        await self.update_account_status(user_id, user.name)
        await self.save_bank()

        print(f"Removed coin from {user.name}. New balance:", self.bank[user_id])

    async def save_bank(self):
        """Save changes to the bank to file."""
        with open(self.bank_file, "w", encoding="utf-8") as fp:
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

        # Remove requests that are older than the threshold

        for idx, request in enumerate(self.requests):
            when_stale = datetime.datetime.fromisoformat(request["stale_after"])
            if when_stale < now:
                print(f"removing {request['who']} from content requesters")
                self.requests.pop(idx)

        # Then do same for providers. Done separately because they can be
        # different length lists

        for idx, provider in enumerate(self.providers):
            when_stale = datetime.datetime.fromisoformat(provider["stale_after"])
            if when_stale < now:
                print(f"removing {provider['who']} from content providers")
                self.providers.pop(idx)
