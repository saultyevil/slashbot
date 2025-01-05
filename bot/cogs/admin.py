import asyncio
import logging
import random
from pathlib import Path

import disnake
import git
from disnake.ext import commands

from bot import __version__
from bot.custom_bot import SlashbotInterationBot
from bot.custom_cog import SlashbotCog
from bot.custom_command import slash_command_with_cooldown
from bot.types import ApplicationCommandInteraction
from slashbot.admin import get_logfile_tail, restart_bot, update_local_repository
from slashbot.config import Bot

COOLDOWN_USER = commands.BucketType.user
COOLDOWN_STANDARD = Bot.get_config("COOLDOWN_STANDARD")
COOLDOWN_RATE = Bot.get_config("COOLDOWN_RATE")


class AdminTools(SlashbotCog):
    """Admin commands and tools for Slashbot.

    The purpose of this cog is to manage Slashbot remotely, or to check that
    things are working as intended.
    """

    logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))

    def __init__(self, bot: SlashbotInterationBot) -> None:
        """Intialise the cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The bot the cog will be added to.

        """
        super().__init__(bot)
        self.my_messages = []
        self.invite_task = None

    async def delayed_invite_task(self, member: disnake.Member, delay_minutes: float) -> None:
        """Send an invite to a member after a delay.

        Parameters
        ----------
        member : disnake.Member
            The member to invite.
        delay_minutes : float
            The number of minutes to wait before sending the invite.

        """
        if self.invite_task:
            AdminTools.logger.error("Delayed invite already running")
            return
        try:
            await asyncio.sleep(delay_minutes * 60)
            invite = await member.guild.text_channels[0].create_invite(max_uses=1)
            user = await self.bot.get_user(member.id)
            await user.send(invite.url)
        except asyncio.CancelledError:
            AdminTools.logger.info("Delayed invite for %s cancelled", member.name)
        finally:
            self.invite_task = None

    @commands.Cog.listener("on_member_remove")
    async def unban_user_adam(self, member: disnake.Member) -> None:
        """Unban and re-invite Adam, if removed by Meghun.

        Parameters
        ----------
        member : disnake.Member
            The member which has been removed

        """
        if member.id != Bot.get_config("ID_USER_ADAM"):
            return
        guild = member.guild
        if guild.id != Bot.get_config("ID_SERVER_ADULT_CHILDREN"):
            return
        async for entry in guild.audit_logs(action=disnake.AuditLogAction.ban):
            if entry.target.id == member.id and entry.user.id == Bot.get_config("ID_USER_MEGHUN"):
                await member.unban()
                random_minutes = random.randrange(3, 600)
                AdminTools.logger.info("Adam has been unbanned and will be re-invited in %d minutes", random_minutes)
                self.invite_task = asyncio.create_task(self.delayed_invite_task(member, random_minutes))
                return

    @commands.Cog.listener("on_member_join")
    async def cancel_delayed_invite_task(self, member: disnake.Member) -> None:
        """Cancel the delayed invite for Adam.

        Parameters
        ----------
        member : disnake.Member
            The member which has joined.

        """
        if not self.invite_task or member.id != Bot.get_config("ID_USER_ADAM"):
            return
        guild = member.guild
        if guild.id != Bot.get_config("ID_SERVER_ADULT_CHILDREN"):
            return

        self.invite_task.cancel()
        self.invite_task = None

    @commands.Cog.listener("on_message")
    async def self_listener(self, message: disnake.Message) -> None:
        """Listen to bot messages.

        Parameters
        ----------
        message : disnake.Message
            The message to process.

        """
        if message.author.id == self.bot.user.id or self.bot.user in message.mentions:
            self.my_messages.append(message)

    @slash_command_with_cooldown(
        name="remove_bot_messages",
        description="Remove all of the bot's messages since the last restart.",
        dm_permission=False,
    )
    async def remove_bot_messages(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clean up the bot responses.

        This will delete all of the bot's responses in the chat, since its
        last restart.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interation object representing the user's command interaction.

        """
        if len(self.my_messages) == 0:
            await inter.response.send_message("There is nothing to remove.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        for i in range(0, len(self.my_messages), 100):
            messages_to_delete = list(self.my_messages[i : i + 100])
            await inter.channel.delete_messages(messages_to_delete)
        self.my_messages.clear()
        await inter.delete_original_message()
        await inter.channel.send(
            f"{inter.user.display_name} requested to remove my responses :frowning2:",
            delete_after=10,
        )

    @slash_command_with_cooldown(name="version")
    async def print_bot_version(self, inter: ApplicationCommandInteraction) -> None:
        """Print the current version number of the bot."""
        await inter.response.send_message(f"Current version: {__version__}", ephemeral=True)

    @slash_command_with_cooldown(name="logfile")
    async def print_logfile_tail(
        self,
        inter: ApplicationCommandInteraction,
        num_lines: int = commands.Param(
            default=10,
            description="The number of lines to include in the tail of the log file.",
            max_value=50,
            min_value=1,
        ),
    ) -> None:
        """Print the tail of the logfile.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The interaction to respond to.
        num_lines: int
            The number of lines to print.

        """
        await inter.response.defer(ephemeral=True)
        tail = await get_logfile_tail(Path(Bot.get_config("LOGFILE_NAME")), num_lines)
        await inter.edit_original_message(f"```{tail}```")

    @slash_command_with_cooldown()
    async def restart_bot(
        self,
        inter: ApplicationCommandInteraction,
        disable_markov: str = commands.Param(
            choices=["Yes", "No"],
            default=False,
            description="Disable Markov sentence generation for faster load times",
            converter=lambda _, arg: arg == "Yes",
        ),
    ) -> None:
        """Restart the bot.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The slash command interaction.
        disable_markov : str / bool
            A bool to indicate if we should disable cached markov sentences. The
            input is a string of "Yes" or "No" which is converted into a bool.

        """
        if inter.author.id != Bot.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        arguments = ["run.py"]
        if disable_markov:
            arguments.append("--disable-auto-markov")

        if inter.response.type == disnake.InteractionResponseType.deferred_channel_message:
            await inter.edit_original_message("Restarting the bot...")
        else:
            await inter.response.send_message("Restarting the bot...", ephemeral=True)

        restart_bot(arguments)

    @slash_command_with_cooldown(name="update_bot")
    async def update_and_restart(
        self,
        inter: ApplicationCommandInteraction,
        branch: str = commands.Param(
            default="main",
            description="The branch to update to",
        ),
        disable_markov: str = commands.Param(
            choices=["Yes", "No"],
            default=False,
            description="Disable Markov sentence generation for faster load times",
            converter=lambda _, arg: arg == "Yes",
        ),
    ) -> None:
        """Update and restart the bot.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The slash command interaction.
        branch : str
            The name of the git branch to use
        disable_markov : str / bool
            A bool to indicate if we should disable cached markov sentences. The
            input is a string of "Yes" or "No" which is converted into a bool.

        """
        if inter.author.id != Bot.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            update_local_repository(branch)
        except git.exc.GitCommandError:
            AdminTools.logger.exception("Failed to update repository")
            await inter.edit_original_message("Failed to update local repository")
            return
        await self.restart_bot(inter, disable_markov)


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(AdminTools(bot))
