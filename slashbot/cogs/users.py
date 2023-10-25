#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for remembering user info."""

import logging
import re
from types import coroutine

import disnake
from disnake.ext import commands
from sqlalchemy.orm import Session

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import (
    BadWord,
    connect_to_database_engine,
    get_twitter_opt_in,
    get_user,
)
from slashbot.error import deferred_error_message
from slashbot.util import convert_string_to_lower

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user
USER_OPTIONS = [
    "City",
    "Country code",
    "Bad word",
    "Twitter URL",
]


def press(inter: disnake.ApplicationCommandInteraction, _: str):
    """Auto complete options for set_info.

    This is currently set up only for the "Twitter URL" option.
    """
    if inter.filled_options["thing"] == "Twitter URL":
        return "Press to continue..."


class Users(SlashbotCog):
    """Cog for commands used to save user data."""

    def __init__(self, bot: commands.InteractionBot) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        """
        super().__init__()
        self.bot = bot
        self.opt_in_twitter_users = get_twitter_opt_in()

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_info", description="set info to remember about you")
    async def set_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        thing: str = commands.Param(description="The thing to be remembered.", choices=USER_OPTIONS),
        value: str = commands.Param(
            description="What to be remembered.", autocomplete=press, converter=convert_string_to_lower
        ),
    ) -> coroutine:
        """Set some user variables for a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        thing: str
            The thing to set.
        value: str
            The value of the thing to set.
        """
        await inter.response.defer(ephemeral=True)

        with Session(connect_to_database_engine()) as session:
            user = get_user(session, inter.author.id, inter.author.name)

            if not isinstance(value, str):
                logger.error(
                    "Disnake somehow passed something which isn't a str for value: %s (%s)", value, type(value)
                )
                return inter.edit_original_message(content="An error has occured with Disnake :-(")

            value = value.lower()

            match thing:
                case "City":
                    user.city = value.capitalize()
                case "Country code":
                    if len(value) != 2:
                        return inter.edit_original_message(
                            content=f"{value} is not a valid country code, which should be 2 characters e.g. GB, US."
                        )
                    # value = "gb" if value == "uk" else value  # convert uk to gb, else value
                    user.country_code = value.upper()
                case "Bad word":
                    word = session.query(BadWord).filter(BadWord.word == value).first()
                    if not word:
                        return inter.edit_original_message(
                            content=f"There is no bad word {value} in the bad word database."
                        )
                    user.bad_word = value  # TODO, this should be an ID to a bad word instead
                case "Twitter URL":
                    user.twitter_url_opt_in = not user.twitter_url_opt_in
                    if user.twitter_url_opt_in:
                        return inter.edit_original_message("You have opted in to change your Twitter URLs.")
                    else:
                        return inter.edit_original_message("You have opted out to change your Twitter URLs.")
                case _:
                    logger.error("Disnake somehow allowed an unknown choice %s", thing)
                    return inter.edit_original_message(content="An error has occurred with Disnake :-(")

            session.commit()

        return await inter.edit_original_message(content=f"{thing.capitalize()} has been set to '{value}'.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_info", description="view info you set to remember")
    async def query_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        thing: str = commands.Param(description="The thing to query the value of.", choices=USER_OPTIONS),
    ) -> coroutine:
        """_summary_

        Parameters
        ----------
        inter : _type_
            _description_
        thing : str, optional
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        await inter.response.defer(ephemeral=True)

        with Session(connect_to_database_engine()) as session:
            user = get_user(session, inter.author.id, inter.author.name)

            match thing:
                case "City":
                    value = user.city
                case "Country code":
                    value = user.country_code
                case "Bad word":
                    value = user.bad_word
                case _:
                    logger.error("Disnake somehow allowed an unknown choice %s", thing)
                    return deferred_error_message(inter, "An error has occurred with Disnake :-(")

        return await inter.edit_original_message(content=f"{thing.capitalize()} is set to '{value}'.")

    @commands.Cog.listener("on_message")
    async def change_to_fxtwitter(self, message: disnake.Message):
        """Send a new message containing an fxtwitter link.

        Parameters
        ----------
        message : disnake.Message
            A message potentially containing a twitter link.
        """
        url_pattern = r"https?://(?:www\.)?twitter\.com/([a-zA-Z0-9_]+)"
        matches = re.finditer(url_pattern, message.content)

        if not matches or message.author not in self.opt_in_twitter_users:
            return

        await message.edit(suppress_embeds=True)
        for match in matches:
            await message.channel.send(f"{match.string.replace('twitter', 'fxtwitter')}")
        await message.channel.send("*(You can opt in or out of this with /set_info)*")
