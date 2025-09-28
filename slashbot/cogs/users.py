"""Commands for remembering user info."""

import disnake
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.convertors import convert_string_to_lower
from slashbot.logger import logger
from slashbot.settings import BotSettings

USER_OPTIONS = [
    disnake.OptionChoice("City", "city"),
    disnake.OptionChoice("Country code", "country_code"),
    disnake.OptionChoice("Bad word", "bad_word"),
    disnake.OptionChoice("Letterboxd Username", "letterboxd_username"),
]


class UserInfo(CustomCog):
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
        user = await self.get_user_db_from_inter(inter)
        await self.db.update_user("discord_id", user.discord_id, thing, value)
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
        user = await self.get_user_db_from_inter(inter)
        if thing not in user.__table__.columns:
            msg = f"{thing} is not a valid attribute for a user"
            self.log_error("%s", msg)
            await inter.response.send_message(msg, ephemeral=True)
            return
        value = getattr(user, thing)
        await inter.response.send_message(f"{thing.capitalize()} is set to '{value}'.", ephemeral=True)

    @slash_command_with_cooldown(name="forget_info", description="Forget some data remembered about you")
    async def forget_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        thing: str = commands.Param(description="The thing to forget the value of.", choices=USER_OPTIONS),
    ) -> None:
        """Forget a user set value.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The disnake interaction.
        thing : str, optional
            The thing to forget the set value for.

        """
        user = await self.get_user_db_from_inter(inter)
        if thing not in user.__table__.columns:
            msg = f"{thing} is not a valid attribute for a user"
            self.log_error("%s", msg)
            await inter.response.send_message(msg, ephemeral=True)
            return
        await self.db.update_user("discord_id", inter.author.id, thing, None)
        await inter.response.send_message(f"{thing.capitalize()} has been forgotten.", ephemeral=True)


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.users.enabled:
        logger.log_warning("%s has been disabled in the configuration file", UserInfo.__cog_name__)
        return
    bot.add_cog(UserInfo(bot))
