#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Custom Cog class for slashbot."""

import disnake
from disnake.ext import commands

from config import App


class CustomCog(commands.Cog):
    """A custom cog class which modifies cooldown behavior."""

    async def cog_before_slash_command_invoke(
        self, inter: disnake.ApplicationCommandInteraction
    ) -> disnake.ApplicationCommandInteraction:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        if inter.guild and inter.guild.id != App.config("ID_SERVER_ADULT_CHILDREN"):
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in App.config("NO_COOL_DOWN_USERS"):
            return inter.application_command.reset_cooldown(inter)
