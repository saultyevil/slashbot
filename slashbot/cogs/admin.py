import asyncio
import datetime
import logging
import os
import random
import shutil
from pathlib import Path

import disnake
import git
from disnake.ext import commands
from git.exc import GitCommandError

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.bot.custom_types import ApplicationCommandInteraction
from slashbot.logger import logger
from slashbot.settings import BotSettings

JERMA_GIFS = list(Path("data/images").glob("jerma*.gif"))


def restart_bot(arguments: list[str]) -> None:
    """Restart the current process with the given arguments.

    Parameters
    ----------
    arguments : list[str]
        Additional arguments to pass to the new process.

    """
    logger = logging.getLogger(BotSettings.logging.logger_name)
    poetry_executable = shutil.which("poetry")
    if poetry_executable is None:
        logger.error("Could not find the poetry executable")
        return
    command = [poetry_executable, "run", *arguments]
    logger.info("Restarting with command %s", command)
    os.execv(command[0], command)  # noqa: S606


def update_local_repository(branch: str) -> None:
    """Update the local git repository to `branch` and pull in changes.

    Parameters
    ----------
    branch : str
        The branch to switch to.

    """
    repo = git.Repo(".", search_parent_directories=True)
    if repo.active_branch != branch:
        target_branch = repo.heads[branch]
        target_branch.checkout()
    repo.remotes.origin.pull()


def ordinal_suffix(n: int) -> str:
    """Return the ordinal suffix for a given number.

    Parameters
    ----------
    n : int
        The number to get the ordinal suffix for.

    Returns
    -------
    str
        The ordinal suffix for the given number.

    """
    if 11 <= (n % 100) <= 13:  # noqa: PLR2004
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


class AdminTools(CustomCog):
    """Admin commands and tools for Slashbot.

    The purpose of this cog is to manage Slashbot remotely, or to check that
    things are working as intended.
    """

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Intialise the cog.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The bot the cog will be added to.

        """
        super().__init__(bot)
        self.my_messages = []
        self.invite_tasks = {}

    async def _find_entry_in_audit_log(
        self,
        guild: disnake.Guild,
        member: disnake.Member,
        filter_user: disnake.Member | disnake.User,
        action: disnake.AuditLogAction,
    ) -> str | None:
        async for entry in guild.audit_logs(action=action, after=member.joined_at, user=filter_user):
            if not entry.target:
                continue
            if entry.target.id == member.id:
                return f'"{entry.reason}"' if entry.reason else "no reason"

        return None

    async def _count_times_in_audit_log_in_30_day_window(
        self, guild: disnake.Guild, member: disnake.Member | disnake.User, action: disnake.AuditLogAction
    ) -> int:
        times_happened = 0
        month_ago = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=30)
        async for entry in guild.audit_logs(action=action, after=month_ago, limit=None):
            if not entry.target:
                continue
            if entry.target.id == member.id:
                times_happened += 1

        return times_happened

    async def _check_audit_log_for_action_and_invite(
        self,
        guild: disnake.Guild,
        member: disnake.Member,
        action_user: disnake.Member | disnake.User,
        action: disnake.AuditLogAction,
    ) -> str | None:
        """Check audit logs for specific actions and send invites.

        Parameters
        ----------
        guild : disnake.Guild
            The guild where the action occurred.
        member : disnake.Member
            The member who was the target of the action.
        action_user: disnake.Member or disnake.User
            The user who initiated the action.
        action : disnake.AuditLogAction
            The action to check in the audit log. Must be ban or kick.

        Returns
        -------
        str
            The reason for "action" happening

        """
        if action not in (disnake.AuditLogAction.ban, disnake.AuditLogAction.kick):
            msg = "action must be ban or kick"
            raise ValueError(msg)
        action_present = "banning" if action == disnake.AuditLogAction.ban else "kicking"
        reason = await self._find_entry_in_audit_log(guild, member, action_user, action)
        if reason:
            num_times = await self._count_times_in_audit_log_in_30_day_window(guild, member, action)
            channel = await self.bot.fetch_channel(BotSettings.discord.channels.idiots)
            if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                msg = "Trying to send a message to a non-text channel"
                raise RuntimeError(msg)
            await channel.send(
                f":warning: looks like {action_user.display_name} needs to zerk off after {action_present} "
                f"{member.display_name} for {reason}!! This is the {num_times}{ordinal_suffix(num_times)} "
                f"time in the past month!! :warning:",
                file=disnake.File(random.choice(JERMA_GIFS)),
            )
            random_minutes = random.uniform(60, 3600) / 60  # 1 minute to 1 hour
            self.invite_tasks[member.id] = asyncio.create_task(
                self.invite_after_delay_task(member, random_minutes, unban_user=action == disnake.AuditLogAction.ban)
            )
            self.log_info("Adam will be re-invited in %f minutes", random_minutes)

        return reason

    async def _invite_user(self, member: disnake.Member) -> None:
        """Send an invite to a member.

        Parameters
        ----------
        member : disnake.Member
            The member to invite.

        """
        invite = await member.guild.text_channels[0].create_invite(max_uses=1)
        user = await self.bot.fetch_user(member.id)
        await user.send(invite.url)

    async def invite_after_delay_task(
        self, member: disnake.Member, delay_minutes: float, *, unban_user: bool = False
    ) -> None:
        """Send an invite to a banned member after a delay.

        Parameters
        ----------
        member : disnake.Member
            The member to invite.
        delay_minutes : float
            The number of minutes to wait before sending the invite.
        unban_user : bool
            Whether to unban the user before inviting them, use False if the
            user has already been unbanned or kicked.

        """
        try:
            await asyncio.sleep(delay_minutes * 60)
            if unban_user:
                try:
                    await member.unban()
                except disnake.NotFound:
                    self.invite_tasks.pop(member.id)
                    return
            await self._invite_user(member)
        except asyncio.CancelledError:
            self.log_info("Invite for %s cancelled by asyncio", member.display_name)
        finally:
            self.invite_tasks.pop(member.id)

    @commands.Cog.listener("on_member_join")
    async def on_member_join(self, member: disnake.Member) -> None:
        """Handle member join events.

        Parameters
        ----------
        member : disnake.Member
            The member who joined the server.

        """
        self.log_info("Member %s has joined guild %s", member, member.guild.name)

    @commands.Cog.listener("on_raw_member_remove")
    async def on_member_remove(self, payload: disnake.RawGuildMemberRemoveEvent) -> None:
        """Handle member removal, including un-banning and un-kicking Adam.

        Parameters
        ----------
        payload : disnake.RawGuildMemberRemoveEvent
            The payload containing information about the member who was removed.

        """
        member = payload.user
        guild = await self.bot.fetch_guild(payload.guild_id)
        self.log_info("Member %s has been removed from guild %s", member, guild.name)
        if not isinstance(member, disnake.Member):
            return
        if member.id != BotSettings.discord.users.adam:
            return
        guild = member.guild
        if guild.id != BotSettings.discord.servers.adult_children:
            return
        filter_user = await self.bot.fetch_user(BotSettings.discord.users.seventytwo)

        # First check if he has been banned
        banned = await self._check_audit_log_for_action_and_invite(
            guild, member, filter_user, disnake.AuditLogAction.ban
        )
        # If he has been banned, then we don't need to check for being kicked.
        if banned:
            return
        # If not banned, check for kicked...
        await self._check_audit_log_for_action_and_invite(
            guild,
            member,
            filter_user,
            disnake.AuditLogAction.kick,
        )

    @commands.Cog.listener("on_member_join")
    async def cancel_delayed_invite_task(self, member: disnake.Member) -> None:
        """Cancel the delayed invite for Adam.

        Parameters
        ----------
        member : disnake.Member
            The member which has joined.

        """
        if member.id != BotSettings.discord.users.adam:
            return
        guild = member.guild
        if guild.id != BotSettings.discord.servers.adult_children:
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
        if isinstance(inter.channel, disnake.PartialMessageable):
            await inter.response.send_message("I can't delete messages in this channel.", ephemeral=True)
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

    @slash_command_with_cooldown(name="last_error")
    async def print_last_error(self, inter: ApplicationCommandInteraction) -> None:
        """Print the last error which occured.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The interaction to respond to.

        """
        await inter.response.defer(ephemeral=True)
        last_error = self.get_last_error()
        await inter.edit_original_message(
            content=f"```{last_error}```" if last_error else "There have been no errors since the last restart.",
        )

    @slash_command_with_cooldown()
    async def restart_bot(
        self,
        inter: ApplicationCommandInteraction,
        on_the_fly_markov: str = commands.Param(
            choices=["Yes", "No"],
            default=False,
            description="Use on-the-fly Markov sentence generation for slower load times but more flexibility",
            converter=lambda _, arg: arg == "Yes",
        ),
    ) -> None:
        """Restart the bot.

        Parameters
        ----------
        inter : ApplicationCommandInteraction
            The slash command interaction.
        on_the_fly_markov: str / bool
            A bool to indicate if we should use on-the-fly markov generation
            or not. The input is a string of "Yes" or "No" which is converted
            into a bool.

        """
        if inter.author.id != BotSettings.discord.users.saultyevil:
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return

        arguments = ["slashbot"]
        if on_the_fly_markov:
            arguments.append("--only-the-fly-markov")

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
        on_the_fly_markov: str = commands.Param(
            choices=["Yes", "No"],
            default=False,
            description="Use on-the-fly Markov sentence generation for slower load times but more flexibility",
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
        on_the_fly_markov: str / bool
            A bool to indicate if we should use on-the-fly markov generation
            or not. The input is a string of "Yes" or "No" which is converted
            into a bool.

        """
        if inter.author.id != BotSettings.discord.users.saultyevil:
            await inter.response.send_message("You don't have permission to use this command.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            update_local_repository(branch)
        except GitCommandError:
            self.log_exception("Failed to update repository")
            await inter.edit_original_message("Failed to update local repository")
            return
        await self.restart_bot(inter, on_the_fly_markov)


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    if not BotSettings.cogs.admin.enabled:
        logger.log_warning("%s has been disabled in the configuration file", AdminTools.__cog_name__)
        return
    bot.add_cog(AdminTools(bot))
