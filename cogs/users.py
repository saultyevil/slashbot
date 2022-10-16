#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import json
import logging

from disnake.ext import commands
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

import config

logger = logging.getLogger("slashbot")

cd_user = commands.BucketType.user
remember_options = ["location", "country", "badword", "fxtwitter"]


async def autocomplete_remember_choices(inter, _: str):
    """Autocompletion for choices for the remember command.

    Returns
    -------
    choice: Union[str, List[str]]
        The converted choice.
    """
    thing_chosen = inter.filled_options["thing"]
    return ["enable", "disable"] if thing_chosen == "fxtwitter" else ""


async def convert_fxtwitter_to_bool(inter, choice: str) -> str:
    """Convert the fxtwitter option (enable/disable) to a bool.

    Parameters
    ----------
    choice: str
        The choice to convert.

    Returns
    -------
    choice: Union[str, bool]
        The converted choice.
    """
    if inter.filled_options["thing"] == "fxtwitter":
        return choice == "enable"

    return choice


class Users(commands.Cog):
    """Cog for commands used to save user data."""

    def __init__(self, bot):
        self.bot = bot

        with open(config.USERS_FILES, "r", encoding="utf-8") as fp:
            self.userdata = json.load(fp)

        def on_modify(_):
            with open(config.USERS_FILES, "r", encoding="utf-8") as fp:
                self.userdata = json.load(fp)
            logger.info("Reloaded userdata")

        observer = Observer()
        event_handler = PatternMatchingEventHandler(["*"], None, False, True)
        event_handler.on_modified = on_modify
        observer.schedule(event_handler, config.USERS_FILES, False)
        observer.start()

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOLDOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="remember", description="set user data")
    async def remember(
        self,
        inter,
        thing=commands.Param(choices=remember_options),
        value=commands.Param(autocomplete=autocomplete_remember_choices, converter=convert_fxtwitter_to_bool),
    ):
        """Set some user variables for a user.

        Parameters
        ----------
        thing: str
            The thing to set.
        value: str
            The value of the thing to set.
        """
        value = value.lower() if isinstance(value, str) else value

        try:
            self.userdata[str(inter.author.id)][thing] = value
        except KeyError:
            self.userdata[str(inter.author.id)] = {}
            self.userdata[str(inter.author.id)][thing] = value

        logger.info(f"{inter.author.name} has set {thing} to {value}")

        with open(config.USERS_FILES, "w", encoding="utf-8") as fp:
            json.dump(self.userdata, fp)

        await inter.response.send_message(f"{thing.capitalize()} has been set to {value}.", ephemeral=True)
