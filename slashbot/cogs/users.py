"""Commands for remembering user info."""

import disnake
from disnake.ext import commands

from slashbot.convertors import convert_string_to_lower
from slashbot.core.custom_bot import CustomInteractionBot
from slashbot.core.custom_cog import CustomCog
from slashbot.core.custom_command import slash_command_with_cooldown

USER_OPTIONS = [
    disnake.OptionChoice("City", "city"),
    disnake.OptionChoice("Country code", "country_code"),
    disnake.OptionChoice("Bad word", "bad_word"),
]


class Users(CustomCog):
    """Cog for commands used to save user data."""

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(name="set_info", description="Set data to be remembered about you")
    async def set_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        thing: str = commands.Param(description="The thing to be remembered.", choices=USER_OPTIONS),
        value: str = commands.Param(
            description="What to be remembered.",
            converter=convert_string_to_lower,
        ),
    ) -> None:
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
        await self.db.update_user(inter.author.id, thing, value)
        await inter.response.send_message(f"{thing.capitalize()} has been set to '{value}'.", ephemeral=True)

    @slash_command_with_cooldown(name="show_info", description="View data you set to be remembered about you")
    async def query_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        thing: str = commands.Param(description="The thing to query the value of.", choices=USER_OPTIONS),
    ) -> None:
        """Print a user set value to an ephemeral chat.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The disnake interaction.
        thing : str, optional
            The thing to show saved values for.

        """
        user = await self.db.get_user(inter.author.id)

        match thing:
            case "city":
                value = user.city
            case "country_code":
                value = user.country_code
            case "bad_word":
                value = user.bad_word

        await inter.response.send_message(f"{thing.capitalize()} is set to '{value}'.", ephemeral=True)


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Users(bot))
