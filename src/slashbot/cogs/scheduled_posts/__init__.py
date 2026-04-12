"""Scheduled posts cog."""

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.cogs.scheduled_posts.cog import ScheduledPosts
from slashbot.settings import BotSettings


def setup(bot: CustomInteractionBot) -> None:
    """Set up the cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.scheduled_posts.enabled:
        bot.log_warning("%s has been disabled in the configuration file", ScheduledPosts.__cog_name__)
        return
    bot.add_cog(ScheduledPosts(bot))
