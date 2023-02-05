#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for remembering user info."""

import json
import logging
from types import coroutine

import disnake
from disnake.ext import commands

from slashbot.config import App
from slashbot.cog import CustomCog

logger = logging.getLogger(App.config("LOGGER_NAME"))
cd_user = commands.BucketType.user
remember_options = [
    "location",
    "country",
    "badword",
]


class Users(CustomCog):
    """Cog for commands used to save user data."""

    def __init__(self, bot: commands.InteractionBot) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        """
        self.bot = bot
        self.user_data = App.config("USER_INFO_FILE_STREAM")

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="set_info", description="set info to remember about you")
    async def set_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        thing: str = commands.Param(description="The type of thing to be remembered.", choices=remember_options),
        value: str = commands.Param(
            description="What to remember.",
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

        value = value.lower() if isinstance(value, str) else value

        try:
            self.user_data[str(inter.author.id)][thing] = value
        except KeyError:
            self.user_data[str(inter.author.id)] = {thing: value}

        logger.info("%s has set %s to %s", inter.author.name, thing, value)

        with open(App.config("USERS_FILE"), "w", encoding="utf-8") as file_in:
            json.dump(self.user_data, file_in)

        return await inter.edit_original_message(content=f"{thing.capitalize()} has been set to {value}.")
