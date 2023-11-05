#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for remembering user info."""

import logging
import re
from types import coroutine
from typing import List

import disnake
from disnake.ext import commands

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import get_twitter_convert_users, get_user, update_user
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


def press(inter: disnake.ApplicationCommandInteraction, _: str) -> List[str]:
    """Auto complete options for set_info.

    This is currently set up only for the "Twitter URL" option.
    """
    if inter.filled_options["thing"] == "Twitter URL":
        return [
            "Select to continue...",
        ]
    return []


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
        self.opt_in_twitter_users = get_twitter_convert_users()

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

        if not isinstance(value, str):
            logger.error("Disnake somehow passed something which isn't a str for value: %s (%s)", value, type(value))
            return await inter.edit_original_message(content="An error has occured with Disnake :-(")

        value = value.lower()
        user = get_user(inter.author)

        match thing:
            case "City":
                user["city"] = value.capitalize()
            case "Country code":
                if len(value) != 2:
                    return await inter.edit_original_message(
                        content=f"{value} is not a valid country code, which should be 2 characters e.g. GB, US."
                    )
                # value = "gb" if value == "uk" else value  # convert uk to gb, else value
                user["country_code"] = value.upper()
            case "Bad word":
                # TODO: we should check that the bad word exists in the list of bad words
                user["bad_word"] = value
            case "Twitter URL":
                user["convert_twitter_url"] = not user["convert_twitter_url"]
                self.opt_in_twitter_users = get_twitter_convert_users()
                if user["convert_twitter_url"]:
                    return await inter.edit_original_message("You have opted in to change your Twitter URLs.")
                return await inter.edit_original_message("You have opted out to change your Twitter URLs.")
            case _:
                logger.error("Disnake somehow allowed an unknown choice %s", thing)
                return await inter.edit_original_message(content="An error has occurred with Disnake :-(")

        update_user(inter.author.id, user)

        return await inter.edit_original_message(content=f"{thing.capitalize()} has been set to '{value}'.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_info", description="view info you set to remember")
    async def query_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        thing: str = commands.Param(description="The thing to query the value of.", choices=USER_OPTIONS),
    ) -> coroutine:
        """Print a user set value to an ephemeral chat.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The disnake interaction.
        thing : str, optional
            The thing to show saved values for.
        """
        await inter.response.defer(ephemeral=True)

        user = get_user(inter.author)

        match thing:
            case "City":
                value = user["city"]
            case "Country code":
                value = user["country_code"]
            case "Bad word":
                value = user["bad_word"]
            case "Twitter URL":
                if user["convert_twitter_url"]:
                    value = "enabled"
                else:
                    value = "disabled"
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
        url_pattern = r"https://twitter\.com/[^/\s]+/status/\d+"
        matches = list(re.finditer(url_pattern, message.content))

        if not matches or message.author.id not in self.opt_in_twitter_users:
            return

        await message.edit(suppress_embeds=True)
        for match in matches:
            await message.channel.send(f"{match.group(0).replace('twitter', 'fxtwitter')}")
        await message.channel.send("*(You can opt in or out of this with /set_info)*")


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(Users(bot))
