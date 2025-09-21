"""Commands for sending videos, and scheduled videos."""

import datetime
import random
from zoneinfo import ZoneInfo

import disnake

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.settings import BotSettings


class Videos(CustomCog):
    """Send short clips to the channel."""

    @slash_command_with_cooldown(name="admin_abuse", description="admin abuse!!! you're the worst admin ever!!!")
    async def admin_abuse(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a clip of someone shouting admin abuse.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        await inter.response.defer()
        await inter.edit_original_message(
            file=disnake.File("data/videos/admin_abuse.mp4"),
        )

    @slash_command_with_cooldown(name="goodbye", description="goodbye")
    async def goodbye(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a clip of Marko saying goodbye.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        await inter.response.defer()
        await inter.edit_original_message(file=disnake.File("data/videos/goodbye.mp4"))

    @slash_command_with_cooldown(name="good_morning", description="good morning people")
    async def good_morning(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a video of Marko saying good morning people.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        await inter.response.defer()
        time = datetime.datetime.now(ZoneInfo("Europe/London"))
        if time.hour >= 12:  # noqa: PLR2004
            lee_videos = [
                "data/videos/good_morning_afternoon_1.mp4",
                "data/videos/good_morning_afternoon_2.mp4",
                "data/videos/good_morning_afternoon_3.mp4",
            ]
        else:
            lee_videos = [
                "data/videos/good_morning_vlog.mp4",
                "data/videos/good_morning_still_is.mp4",
            ]

        # this is some hack to make the Marko video just as likely lol
        video_choices = (1 * len(lee_videos) * ["data/videos/good_morning_people.mp4"]) + lee_videos
        video = random.choice(video_choices)

        await inter.edit_original_message(file=disnake.File(video))

    @slash_command_with_cooldown(name="haha", description="haha very funny")
    async def laugh(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a clip of Marko laughing.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        await inter.response.defer()
        await inter.edit_original_message(file=disnake.File("data/videos/marko_laugh.mp4"))


def setup(bot: CustomInteractionBot) -> None:
    """Set up the cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.enabled.videos:
        return
    bot.add_cog(Videos(bot))
