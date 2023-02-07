#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for requesting and providing content, as well as tracking leech
coins."""

import datetime
import logging
from types import coroutine

import disnake
from disnake.ext import commands, tasks
from prettytable import PrettyTable
from sqlalchemy.orm import Session

from slashbot.config import App
from slashbot.db import connect_to_database_engine
from slashbot.db import get_bank_account
from slashbot.db import BankAccount
from slashbot.custom_cog import CustomCog
from slashbot.markov import generate_sentence

COOLDOWN_USER = commands.BucketType.user
CHECK_FREQUENCY_SECONDS = 30

logger = logging.getLogger(App.config("LOGGER_NAME"))


class ContentCommands(CustomCog):  # pylint: disable=too-many-instance-attributes
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
        stale_minutes: int = 30,
    ):
        self.bot = bot
        self.stale_minutes = stale_minutes

        self.current_content_requests = []
        self.current_content_providers = []
        self.remove_stale_requests.start()  # pylint: disable=no-member

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
        if self.current_content_requests and started_streaming:
            logger.debug("%s started streaming when someone requested", member.name)
            # then remove all stale requests
            n_removed = 0
            for idx, request in enumerate(self.current_content_requests):
                user_id = str(request["who"].id)
                when = datetime.datetime.fromisoformat(request["when"])
                if when < now:
                    await self.modify_leech_coin_balance(user_id, -1)
                    logger.debug("removing %s from list", request["who"])
                    self.current_content_requests.pop(idx)
                    n_removed += 1

            # give them some number of leech coins, depending on number of requests
            return await self.modify_leech_coin_balance(str(member.id), n_removed)

        # If no requests, but the person is a provider then check if someone
        # is providing on the voice channel
        if self.current_content_providers:
            for this_member in channel.members:
                is_member_streaming = this_member.voice.self_stream
                is_member_provider = this_member in self.current_content_providers

                if is_member_provider and is_member_streaming:
                    self.current_content_providers.remove(this_member.id)
                    await self.modify_leech_coin_balance(this_member.id, 1)
                    logger.debug("%s is streaming when they said they would provide", this_member.name)

        if len(self.current_content_requests) > 0:
            logger.info("requests: %s", self.current_content_requests)
        if len(self.current_content_providers) > 0:
            logger.info("providers: %s", self.current_content_providers)

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=CHECK_FREQUENCY_SECONDS)
    async def remove_stale_requests(self) -> None:
        """Check periodically for stale requests."""
        if len(self.current_content_requests) == 0:
            return

        now = datetime.datetime.now()

        # Remove requests that are older than the threshold

        for idx, request in enumerate(self.current_content_requests):
            when_stale = datetime.datetime.fromisoformat(request["stale_after"])
            if when_stale < now:
                logger.info("removing %s from content requesters", request["who"])
                self.current_content_requests.pop(idx)

        # Then do same for providers. Done separately because they can be
        # different length lists

        for idx, provider in enumerate(self.current_content_providers):
            when_stale = datetime.datetime.fromisoformat(provider["stale_after"])
            if when_stale < now:
                logger.info("removing %s from content providers", provider["who"])
                self.current_content_providers.pop(idx)

    # Functions ----------------------------------------------------------------

    @staticmethod
    def get_account(user_id: int) -> BankAccount:
        """Get a bank account for a given user ID.

        Parameters
        ----------
        user_id : int
            The Discord ID for the user to get the account for.

        Returns
        -------
        BankAccount
            The back account requested.
        """
        with Session(connect_to_database_engine()) as session:
            return get_bank_account(session, user_id)

    @staticmethod
    def modify_leech_coin_balance(user_id: int, modify_amount: int) -> None:
        """Add a leech coin to a user's bank.

        Parameters
        ----------
        user_id: int
            The ID of the user.
        to_add: int
            The number of coins to add.
        """
        with Session(connect_to_database_engine()) as session:
            account = get_bank_account(session, user_id)

            account.balance += modify_amount
            if account.balance <= 0:
                account.status = "Content leech"
            else:
                account.status = "Content consoomer"

            session.commit()

        logger.debug("Modified %d balance by %i coins", user_id, modify_amount)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="content_balance",
        description="Check how many Content coins you have",
    )
    async def balance(
        self,
        inter: disnake.ApplicationCommandInteraction,
    ) -> coroutine:
        """Check your leech coin balance.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        account = self.get_account(inter.author.id)

        if account.balance > 0:
            message = "You are a handsome content provider."
        elif account.balance == 0:
            message = "You are content neutral."
        else:
            message = "You are owe the server content!"

        embed = disnake.Embed(
            title=f"{inter.author.name}'s Content Balance", color=disnake.Color.default(), description=message
        )
        embed.set_footer(text=f"{generate_sentence(seed_word='content')}")
        embed.set_thumbnail(url="https://www.nicepng.com/png/full/258-2581153_cartoon-leech.png")
        embed.add_field(name="Balance", value=f"{account.balance} Content Coins")
        embed.add_field(name="Status", value=f"{account.status}")

        return await inter.response.send_message(embed=embed)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="need_content", description="Demand some content, like a bad boy", dm_permission=False)
    async def request_content(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Demand that there be content, filthy little leech.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        who: str
            The name of the user who should provide content.
        """
        _ = self.get_account(inter.author.id)
        current_requesters = [requests["who"].id for requests in self.current_content_requests]

        # Add request to queue of requests to be answered
        if inter.author.id not in current_requesters:
            now = datetime.datetime.now()
            request = {
                "when": now.isoformat(),
                "stale_after": (now + datetime.timedelta(minutes=self.stale_minutes)).isoformat(),
                "who": inter.author,
            }
            self.current_content_requests.append(request)
            logger.info("%s has been added to the list of requests", inter.author.name)

        if len(self.current_content_requests) > 1:
            requesters = (
                ", ".join(map(lambda r: r["who"].name, self.current_content_requests[:-1]))
                + f" and {self.current_content_requests[-1]['who'].name} *need*"
            )
        else:
            requesters = f"{self.current_content_requests[0]['who'].name} *needs*"

        return await inter.response.send_message(f"{requesters} content.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="provide_content", description="Provide content like a good boy", dm_permission=False)
    async def provide_content(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Provide content from the goodness of your heart, or heed the call
        for content.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        _ = self.get_account(inter.author.id)
        current_providers = [provider["who"].id for provider in self.current_content_providers]

        if inter.author.id not in current_providers:
            # same data structure as when requesting for content
            now = datetime.datetime.now()
            request = {
                "when": now.isoformat(),
                "stale_after": (now + datetime.timedelta(minutes=self.stale_minutes)).isoformat(),
                "who": inter.author,
            }
            self.current_content_providers.append(request)
            logger.info("%s has been added to the list of providers", inter.author.name)

        if len(self.current_content_providers) > 1:
            providers = (
                ", ".join(map(lambda r: r["who"].name, self.current_content_providers[:-1]))
                + f" and {self.current_content_providers[-1]['who'].name}"
            )
        else:
            providers = f"{self.current_content_providers[0]['who'].name}"

        return await inter.response.send_message(f"{providers} will be providing content.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="content_leaderboard",
        description="Content coin leaderboard",
    )
    async def leech_score(
        self,
        inter: disnake.ApplicationCommandInteraction,
        sort_by: str = commands.Param(
            default="User", choices=["User", "Balance"], description="The column to sort the table by."
        ),
    ) -> coroutine:
        """Show the balance for all users.

                Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        _ = self.get_account(inter.author.id)
        with Session(connect_to_database_engine()) as session:
            accounts = session.query(BankAccount)
            if accounts.count() == 0:
                return await inter.response.send_message("There are no accounts.", ephemeral=True)
            leaderboard_rows = [(account.user.user_name, int(account.balance), account.status) for account in accounts]

        # PrettyTable to create a nicely formatted table
        table = PrettyTable()
        table.align = "r"
        table.field_names = ["User", "Balance", "Status"]
        table.add_rows(leaderboard_rows)

        return await inter.response.send_message(f"```{table.get_string(sortby=sort_by)}```")
