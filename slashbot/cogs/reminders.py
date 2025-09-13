"""Commands for setting, viewing and removing reminders."""

import datetime
import re

import dateparser
import disnake
from disnake.ext import commands, tasks
from prettytable import PrettyTable

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.convertors import get_user_reminders
from slashbot.core.database import ReminderSQL, UserSQL


class Reminders(CustomCog):
    """Commands to set up reminders."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot: CustomInteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.my_timezone = datetime.datetime.now(datetime.UTC).astimezone().tzinfo

    # Private methods ----------------------------------------------------------

    @staticmethod
    def convert_user_requested_time_to_datetime(user_input: str) -> datetime.datetime:
        """Return a datetime in the future, for a given format and time.

        Parameters
        ----------
        user_input : str
            A string to say when to set the reminder for.

        Returns
        -------
        datetime.datetime
            A date time object for the reminder in the future.

        """
        # settings makes BST -> British Summer Time instead of Bangladesh, but
        # it does some odd things. If you do something like 21:30 UTC+6, it will
        # convert that date to the bot's local timezone. For an input of 21:30
        # UTC+6 when the bot's timezone is UTC+1, future = 16:30 UTC + 1
        parsed_date = dateparser.parse(user_input, settings={"TIMEZONE": "Europe/London"})
        if not parsed_date:
            msg = f"Unable to parse date {user_input}"
            raise ValueError(msg)
        return parsed_date

    async def replace_mentions_with_display_names(self, guild: disnake.Guild | None, sentence: str) -> tuple[str, str]:
        """Replace mentions from a post with the corresponding name.

        Parameters
        ----------
        guild: disnake.Guild
            The guild the reminder is being set in
        sentence: str
            The sentence to remove mentions from.

        Returns
        -------
        mentions_str: str
            A string containing the original user and role mentions found in
            the sentence.
        modified_sentence: str
            The sentence with user and role mentions replaced by names.

        """
        mentions = []
        modified_sentence = sentence

        # Replace user mentions
        user_mentions = re.findall(r"<@!?(\d+)>", sentence)
        for mention in user_mentions:
            mentions.append(f"<@!{mention}>")
            try:
                if mention.startswith(str(self.bot.user.id)):
                    name = self.bot.user.display_name
                else:
                    user = await self.bot.fetch_user(int(mention))
                    name = user.display_name
            except disnake.errors.HTTPException:
                continue

            modified_sentence = modified_sentence.replace(f"<@!{mention}>", f"@{name}")
            modified_sentence = modified_sentence.replace(f"<@{mention}>", f"@{name}")

        # Replace role mentions in a guild, if we are in one
        if guild:
            role_mentions = re.findall(r"<@&(\d+)>", sentence)
            for mention in role_mentions:
                mentions.append(f"<@&{mention}>")
                role = guild.get_role(int(mention))
                if not role:
                    continue
                try:
                    name = role.name
                except AttributeError:
                    continue
                modified_sentence = modified_sentence.replace(f"<@&{mention}>", f"@{name}")

        mentions_str = ", ".join(mentions)
        return mentions_str, modified_sentence

    # Tasks --------------------------------------------------------------------

    CHECK_PERIOD = 1

    @tasks.loop(seconds=CHECK_PERIOD)
    async def check_reminders(self) -> None:
        """Check if any reminders need to be sent wherever needed."""
        await self.bot.wait_until_first_connect()
        dt_now = datetime.datetime.now(tz=datetime.UTC)
        reminders = await self.db.get_all_reminders()

        if len(reminders) == 0:
            return

        for reminder in reminders:
            # Be careful, reminders are stored as UTC+0, so we don't need to
            # convert the times back to UTC!!!! But we still need to make it
            # timezone aware.
            reminder_date = reminder.date.replace(tzinfo=datetime.UTC)
            if reminder_date >= dt_now and not reminder.notified:
                continue

            try:
                user = await self.bot.fetch_user(reminder.user_id)
            except disnake.NotFound:
                self.log_error("User %s not found when trying to send reminder", reminder.user_id)
                continue

            embed = disnake.Embed(title=reminder.content, color=disnake.Color.default())
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=f"Reminder date: {reminder_date.strftime(r'%d/%m/%Y %H:%H:%S %Z')}")
            message = f"{user.mention}"
            if reminder.tagged_users:
                message = f"{message}, {reminder.tagged_users}"

            try:
                channel = await self.bot.fetch_channel(reminder.channel_id)
            except (disnake.NotFound, disnake.Forbidden):
                self.log_error("Channel %s not found when trying to send reminder", reminder.channel_id)
                continue

            if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                self.log_error("Channel %s is not a text channel when trying to send reminder", channel.id)
                continue

            await channel.send(f"Here's your reminder, {message}", embed=embed)
            await self.db.mark_reminder_as_notified(reminder.id)

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(name="set_reminder", description="Set a reminder for later.")
    async def set_reminder(
        self,
        inter: disnake.ApplicationCommandInteraction,
        when: str = commands.Param(
            description="Timestamp for when you want to be reminded (UK time zone unless otherwise specified)",
        ),
        reminder_content: str = commands.Param(name="reminder", description="Your reminder", max_length=1024),
    ) -> None:
        """Set a reminder.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        when: float
            The time stamp for when to be reminded.
        reminder_content: str
            The reminder to set.

        """
        try:
            reminder_date = self.convert_user_requested_time_to_datetime(when)
        except ValueError:
            await inter.response.send_message(f'Unable to understand timestamp "{when}"', ephemeral=True)
            return
        if not reminder_date:
            await inter.response.send_message(f'Unable to understand timestamp "{when}"', ephemeral=True)
            return
        if not reminder_date.tzinfo:
            reminder_date = reminder_date.replace(tzinfo=self.my_timezone)
        now = datetime.datetime.now(tz=self.my_timezone)
        if reminder_date < now:
            date_string = reminder_date.strftime(r"%H:%M UTC%z %d %B %Y")
            await inter.response.send_message(f"{date_string} is in the past.", ephemeral=True)
            return
        reminder_date = reminder_date.replace(microsecond=0)
        self.log_debug("Reminder date %s in UTC is %s", reminder_date, reminder_date.astimezone(datetime.UTC))

        tagged_users, reminder_content = await self.replace_mentions_with_display_names(inter.guild, reminder_content)

        await self.db.add_reminder(
            ReminderSQL(
                user_id=inter.author.id,
                channel_id=inter.channel.id,
                date=reminder_date.astimezone(datetime.UTC),
                content=reminder_content,
                tagged_users=tagged_users if tagged_users else None,
            )
        )

        response = reminder_date.strftime(r"%d/%m/%Y %H:%M:%S %Z")
        await inter.response.send_message(f"Your reminder has been set for {response}.", ephemeral=True)

    @slash_command_with_cooldown(name="forget_reminder", description="Forget one of your reminders.")
    async def forget_reminder(
        self,
        inter: disnake.ApplicationCommandInteraction,
        reminder: str = commands.Param(
            autocomplete=get_user_reminders,
            description="The reminder you want to forget.",
        ),
    ) -> None:
        """Clear a reminder or all of a user's reminders.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        reminder: str
            The reminder to forget

        """
        reminder_to_remove = list(
            filter(
                lambda r: f"{r.date}: {r.content}" == reminder,
                await self.db.get_users_reminders(inter.author.id),
            ),
        )
        if not reminder_to_remove:
            self.log_error("Failed to find reminder (%s) in auto-completion field", reminder)
            await inter.response.send_message("Something went wrong with finding the reminder.", ephemeral=True)
            return
        try:
            reminder_to_remove = reminder_to_remove[0]
        except IndexError:
            self.log_exception("Failed to index of reminder when trying to delete it from the database")
            await inter.response.send_message("Something went wrong with finding the reminder.", ephemeral=True)
            return
        await self.db.delete_reminder(reminder_to_remove.id)

        await inter.response.send_message("Your reminder has been removed.", ephemeral=True)

    @slash_command_with_cooldown(name="show_reminders", description="View your reminders.")
    async def show_reminders(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Show the reminders set for a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.

        """
        user = await self.db.get_user_by_discord_id(inter.author.id)
        if not user:
            user = await self.db.add_user(
                UserSQL(
                    discord_id=inter.author.id,
                    username=inter.author.name,
                )
            )
        reminders = await self.bot.db.get_users_reminders(inter.author.id)
        if not reminders:
            await inter.response.send_message("You don't have any reminders.", ephemeral=True)
            return
        reminders = sorted(
            [(reminder.date.replace(tzinfo=datetime.UTC), reminder.content) for reminder in reminders],
            key=lambda entry: entry[0],
        )
        reminders = [(entry[0].strftime(r"%H:%M %d %B %Y (UTC)"), entry[1]) for entry in reminders]

        # Create table using PrettyTable, so it looks nicer
        table = PrettyTable()
        table.add_rows(reminders)
        table.align = "r"
        table.field_names = ["When", "Reminder"]
        table._max_width = {"When": 25, "Reminder": 75}  # noqa: SLF001
        message = f"You have {len(reminders)} reminders set.\n```"
        message += table.get_string() + "```"
        message += f"Current UTC time: {datetime.datetime.now(tz=datetime.UTC).strftime(r'%H:%M %d %B %Y')}"

        await inter.response.send_message(message, ephemeral=True)


def setup(bot: CustomInteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Reminders(bot))
