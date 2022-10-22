#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for requesting and providing content, as well as tracking leech
coins."""

import datetime
import json
import logging
from pathlib import Path
from types import coroutine
from typing import Union

import disnake
from disnake.ext import commands, tasks
from disnake.utils import get
from prettytable import PrettyTable

import config

cd_user = commands.BucketType.user
CHECK_FREQUENCY_SECONDS = 60

logger = logging.getLogger(config.LOGGER_NAME)


async def convert_yes_to_false(_: disnake.ApplicationCommandInteraction, choice: str) -> bool:
    """Swap Yes to False, so, e.g., if share == yes, then ephemeral=False.

    Parameters
    ----------
    _: disnake.ApplicationCommandInteraction
        The slash command interaction. Unused.
    choice: str
        The choice of yes or not.
    """
    if choice.lower() == "Yes":
        return False
    return True


class Content(commands.Cog):  # pylint: disable=too-many-instance-attributes
    """Demand and provide content, and track leech balance.

    Parameters
    ----------
    bot: commands.InteractionBot
        The bot object.
    generate_sentence: callable
        A function which generates sentences given a seed word.
    starting_balance: int
        The balance members start with upon account creation.
    role_name: str
        The name of the role to assign users to.
    stale_minutes: int
        The frequency to check for stale requests to remove.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: commands.InteractionBot,
        generate_sentence: callable,
        starting_balance: int = 5,
        role_name: str = "Content Leeches",
        stale_minutes: int = 30,
    ):
        self.bot = bot
        self.generate_sentence = generate_sentence
        self.starting_balance = starting_balance
        self.role_name = role_name
        self.stale_minutes = stale_minutes
        self.bank_file = Path(config.BANK_FILE)
        self.bank = config.BANK_FILE_STREAM
        self.requests = []
        self.providers = []

        self.remove_stale_requests.start()  # pylint: disable=no-member

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
    @commands.slash_command(
        name="leave_leech",
        description="Leave the leech notification squad",
    )
    async def leave_leech(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Leave the leech notification squad.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        await self.leave_leech_role(inter.guild, inter.author)
        return await inter.response.send_message(
            f"You have left the {self.role_name} notification squad.", ephemeral=True
        )

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="leech_balance",
        description="Check how many leech coins you have",
    )
    async def balance(
        self,
        inter: disnake.ApplicationCommandInteraction,
        share: str = commands.Param(
            description="Whether to share your balance with the chat or not.",
            default="No",
            choices=["Yes", "No"],
            converter=convert_yes_to_false,
        ),
    ) -> coroutine:
        """Check your leech coin balance.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        share: str
            If yes, ephemeral=False and the message will be printed to chat.
        """
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

        return await inter.response.send_message(embed=embed, ephemeral=share)

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="need_content", description="Demand content, filthy leech", dm_permission=False)
    async def need_content(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Demand that there be content, filthy little leech.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
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
            logger.info("%s has been added to the list of requests", inter.author.name)

        if len(self.requests) > 1:
            requesters = (
                ", ".join(map(lambda r: r["who"].name, self.requests[:-1]))
                + f" and {self.requests[-1]['who'].name} *need*"
            )
        else:
            requesters = f"{self.requests[0]['who'].name} *needs*"

        return await inter.response.send_message(f"{mention} {requesters} content.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="leech_squad", description="Join the leech notification squad", dm_permission=False)
    async def leech_squad(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Join the leech notification squad.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        await self.get_or_create_leech_role(inter.guild)
        return await inter.response.send_message(
            f"You've joined the {self.role_name} notification squad.", ephemeral=True
        )

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="content_creator", description="Provide content like a good boy", dm_permission=False)
    async def content_creator(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Provide content from the goodness of your heart, or heed the call
        for content.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
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
            logger.info("%s has been added to the list of providers", inter.author.name)

        if len(self.providers) > 1:
            providers = (
                ", ".join(map(lambda r: r["who"].name, self.providers[:-1])) + f" and {self.providers[-1]['who'].name}"
            )
        else:
            providers = f"{self.providers[0]['who'].name}"

        return await inter.response.send_message(f"{mention} {providers} will be providing content.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="leech_score",
        description="Leech coin leaderboard",
    )
    async def leech_score(
        self,
        inter: disnake.ApplicationCommandInteraction,
        share: str = commands.Param(
            description="Whether to share your balance with the chat or not.",
            default="No",
            choices=["Yes", "No"],
            converter=convert_yes_to_false,
        ),
    ) -> coroutine:
        """Show the balance for all users.

                Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
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

        return await inter.response.send_message(f"```{table.get_string(sortby='Name')}```", ephemeral=share)

    # Events -------------------------------------------------------------------

    @commands.Cog.listener("on_voice_state_update")
    async def check_if_user_started_streaming(  # pylint: disable=too-many-locals
        self, member: disnake.Member, before: disnake.VoiceState, after: disnake.VoiceState
    ) -> None:
        """Check if a user starts streaming after a request.

        Parameters
        ----------
        member: disnake.Member
            The member which changed voice state.
        before: disnake.VoiceState
            The voice state before update.
        after: disnake.VoiceState
            The voice state afterwards.
        """
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
            logger.info("%s started streaming when someone requested", member.name)
            # then remove all stale requests
            n_removed = 0
            for idx, request in enumerate(self.requests):
                user_id = str(request["who"].id)
                when = datetime.datetime.fromisoformat(request["when"])
                if when < now:
                    await self.remove_leech_coin(user_id)
                    logger.info("removing %s from list", request["who"])
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
                    logger.info("%s is streaming when they said they would provide", this_member.name)

        if len(self.requests) > 0:
            logger.debug("requests: %s", self.requests)
        if len(self.providers) > 0:
            logger.debug("providers: %s", self.providers)

    # Role generation ----------------------------------------------------------

    async def get_or_create_leech_role(self, guild: disnake.Guild) -> disnake.Role:
        """Create a leech role if it doesn't already exist, and add user to it.

        Parameters
        ----------
        guild: disnake.Guild
            The guild
        user: disnake.User
            The user

        Returns
        -------
        leech_role: disnake.Role
            The leech Role for the guild.
        """
        leech_role = get(guild.roles, name=self.role_name)

        if not leech_role:
            try:
                leech_role = await guild.create_role(name=self.role_name, mentionable=True)
            except Exception as exception:  # pylint: disable=broad-except
                logger.info("Can't create role: %s", exception)
                return None

        return leech_role

    async def join_leech_role(self, guild: disnake.Guild, user: disnake.User) -> coroutine:
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

        return await user.add_roles(leech_role)

    async def leave_leech_role(self, guild: disnake.Guild, user: disnake.User) -> coroutine:
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

        return await user.remove_roles(leech_role)

    # Functions ----------------------------------------------------------------

    async def prepare_for_leech_command(self, guild: disnake.Guild, user: disnake.User) -> Union[str, disnake.Role]:
        """Check a bank account exists and assign to role.

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
        leech_role: disnake.Role
            The Role object for the guild.
        """
        await self.check_or_create_account(str(user.id))
        leech_role = await self.get_or_create_leech_role(guild)

        return str(user.id), leech_role

    async def add_leech_coin(self, user_id: int, to_add: int = 1) -> None:
        """Add a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        to_add: int
            The number of coins to add.
        """
        user = await self.bot.fetch_user(user_id)

        await self.check_or_create_account(user_id)
        self.bank[user_id] = self.bank[user_id] + to_add
        await self.update_account_status(user_id, user.name)
        await self.save_bank()

        logger.info("Added %i coins to %s. New balance: %i", to_add, user.name, self.bank[user_id])

    async def create_bank_account(self, user_id: int) -> dict:
        """Add a user to the bank JSON.

        Parameters
        ----------
        user_id: int
            The ID of the user.

        Returns
        -------
        account: dict
            The account for the user.
        """
        user = await self.bot.fetch_user(user_id)
        account = {"user_id": user_id, "name": user.name, "balance": self.starting_balance, "status": "Newfag"}

        logger.info("Created bank account for %s user_id %d %s", user.name, user_id, type(user_id))
        self.bank[user_id] = account
        await self.save_bank()

        return account

    async def update_account_status(self, user_id: int, user_name: str) -> None:
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

        logger.info("%s status changed from %s to %s", user_name, self.bank[user_id], new_status)
        self.bank[user_id]["status"] = new_status

    async def remove_leech_coin(self, user_id: int) -> None:
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

        logger.info("Removed coin from %s. New balance: %s", user.name, self.bank[user_id])

    async def save_bank(self) -> None:
        """Save changes to the bank to file."""
        with open(self.bank_file, "w", encoding="utf-8") as fp:
            json.dump(self.bank, fp)

    async def check_or_create_account(self, user_id: int) -> None:
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
    async def remove_stale_requests(self) -> None:
        """Check periodically for stale requests."""
        if len(self.requests) == 0:
            return

        now = datetime.datetime.now()

        # Remove requests that are older than the threshold

        for idx, request in enumerate(self.requests):
            when_stale = datetime.datetime.fromisoformat(request["stale_after"])
            if when_stale < now:
                logger.info("removing %s from content requesters", request["who"])
                self.requests.pop(idx)

        # Then do same for providers. Done separately because they can be
        # different length lists

        for idx, provider in enumerate(self.providers):
            when_stale = datetime.datetime.fromisoformat(provider["stale_after"])
            if when_stale < now:
                logger.info("removing %s from content providers", provider["who"])
                self.providers.pop(idx)
