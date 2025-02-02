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
from slashbot.admin import (
    get_logfile_tail,
    get_modifiable_config_keys,
    restart_bot,
    set_config_value,
    update_local_repository,
)
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
        self.invite_tasks = {}

    async def delayed_invite_task(self, member: disnake.Member, delay_minutes: float) -> None:
        """Send an invite to a member after a delay.

        Parameters
        ----------
        member : disnake.Member
            The member to invite.
        delay_minutes : float
            The number of minutes to wait before sending the invite.

        """
        try:
            await asyncio.sleep(delay_minutes * 60)
            try:
                await member.unban(reason="why not?")
            except disnake.NotFound:
                AdminTools.logger.info("A good samaritan already unbanned %s", member.display_name)
                self.invite_tasks.pop(member.id)
                return
            invite = await member.guild.text_channels[0].create_invite(max_uses=1)
            user = await self.bot.fetch_user(member.id)
            await user.send(invite.url)
        except asyncio.CancelledError:
            AdminTools.logger.info("Delayed invite for %s cancelled", member.display_name)
        finally:
            self.invite_tasks.pop(member.id)

    @commands.Cog.listener("on_member_remove")
    async def unban_user_adam(self, member: disnake.Member) -> None:
        """Unban and re-invite Adam, if removed by Meghun.

        Parameters
        ----------
        member : disnake.Member
            The member which has been removed

        """
        jerma_gifs = (
            "https://media1.tenor.com/m/XcEBpnPquUMAAAAd/jerma-pog.gif",
            "https://media1.tenor.com/m/s5OePfXg13AAAAAd/jerma-eat-burger-whopper.gif",
            "https://media1.tenor.com/m/YOeQ5oo0M_EAAAAd/jerma-jermafood.gif",
            "https://media1.tenor.com/m/Akk1cG-C_a0AAAAd/jerma-jerma985.gif",
            "https://media1.tenor.com/m/1Fn-Lhpkfm8AAAAd/jerma985-i-saw-what-you-deleted.gif",
        )

        if member.id != Bot.get_config("ID_USER_ADAM"):
            return
        guild = member.guild
        if guild.id != Bot.get_config("ID_SERVER_ADULT_CHILDREN"):
            return
        filter_user = await self.bot.fetch_user(Bot.get_config("ID_USER_MEGHUN"))
        async for entry in guild.audit_logs(
            action=disnake.AuditLogAction.ban, after=member.joined_at, user=filter_user
        ):
            if entry.target.id == member.id:
                channel = await self.bot.fetch_channel(Bot.get_config("ID_CHANNEL_IDIOTS"))
                reason = f'"{entry.reason}"' if entry.reason else "no reason"
                await channel.send(
                    f":warning: looks like 72 needs to ZERK off after banning adam again for {reason}!! :warning: {random.choice(jerma_gifs)}",
                )
                random_minutes = random.uniform(5, 240)
                self.invite_tasks[member.id] = asyncio.create_task(self.delayed_invite_task(member, random_minutes))
                AdminTools.logger.info("Adam has been unbanned and will be re-invited in %f minutes", random_minutes)
                return

    @commands.Cog.listener("on_member_join")
    async def cancel_delayed_invite_task(self, member: disnake.Member) -> None:
        """Cancel the delayed invite for Adam.

        Parameters
        ----------
        member : disnake.Member
            The member which has joined.

        """
        if member.id != Bot.get_config("ID_USER_ADAM"):
            return
        guild = member.guild
        if guild.id != Bot.get_config("ID_SERVER_ADULT_CHILDREN"):
            return
        if member.id not in self.invite_tasks:
            return

        self.invite_tasks[member.id].cancel()
        self.invite_tasks.pop(member.id)

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

    @slash_command_with_cooldown(name="set_config_value")
    async def set_config_value(
        self,
        inter: ApplicationCommandInteraction,
        key: str = commands.Param(description="The config setting to update.", choices=get_modifiable_config_keys()),
        new_value: str = commands.Param(description="The new value of the config setting."),
    ) -> None:
        """Change the value of a configuration parameter.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The slash command interaction.
        key : str
            The key of the config setting to update.
        new_value : str
            The new value of the config setting.

        """
        if inter.author.id != Bot.get_config("ID_USER_SAULTYEVIL"):
            await inter.response.send_message("You aren't allowed to use this command.", ephemeral=True)
            return

        old_value = set_config_value(key, new_value)
        await inter.response.send_message(f"Updated {key} from {old_value} to {new_value}", ephemeral=True)


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(AdminTools(bot))
