"""Commands for setting, viewing and removing reminders."""

import datetime
import re

import dateparser
import disnake
from disnake.ext import commands, tasks
from prettytable import PrettyTable

from bot.custom_bot import SlashbotInterationBot
from bot.custom_cog import SlashbotCog
from bot.custom_command import slash_command_with_cooldown
from slashbot.db import (
    add_reminder,
    get_all_reminders,
    get_all_reminders_for_user,
    remove_reminder,
)


def forget_reminders_autocompleter(inter: disnake.ApplicationCommandInteraction, _: str) -> list[str]:
    """Interface to get reminders for /forget_reminder autocomplete.

    Parameters
    ----------
    inter : disnake.ApplicationCommandInteraction
        The interaction this is ued with.
    _ : str
        The user input, which is unused.

    Returns
    -------
    List[str]
        A list of reminders

    """
    return [f"{reminder['date']}: {reminder['reminder']}" for reminder in get_all_reminders_for_user(inter.author.id)]


class Reminders(SlashbotCog):
    """Commands to set up reminders."""

    def __init__(self, bot: SlashbotInterationBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.

        """
        super().__init__(bot)
        self.my_timezone = datetime.datetime.now(datetime.UTC).astimezone().tzinfo
        self.check_reminders.start()

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
        return dateparser.parse(user_input, settings={"TIMEZONE": "Europe/London"})

    async def replace_mentions_with_display_names(self, guild: disnake.Guild, sentence: str) -> list[str] | str:
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

        # Replace role mentions
        role_mentions = re.findall(r"<@&(\d+)>", sentence)
        for mention in role_mentions:
            mentions.append(f"<@&{mention}>")
            try:
                role = guild.get_role(int(mention))
                name = role.name
            except AttributeError:
                continue

            modified_sentence = modified_sentence.replace(f"<@&{mention}>", f"@{name}")

        mentions_str = ", ".join(mentions)
        return mentions_str, modified_sentence

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=1)
    async def check_reminders(self) -> None:
        """Check if any reminders need to be sent wherever needed."""
        reminders = get_all_reminders()
        if len(reminders) == 0:
            return
        now = datetime.datetime.now(tz=datetime.UTC)

        for reminder in reminders:
            date = datetime.datetime.fromisoformat(reminder["date"]).replace(tzinfo=datetime.UTC)

            if date <= now:
                remove_reminder(reminder)
                owner = await self.bot.fetch_user(reminder["user_id"])
                embed = disnake.Embed(title=reminder["reminder"], color=disnake.Color.default())
                embed.set_thumbnail(url=owner.avatar.url)
                message = f"{owner.mention}"
                if reminder["tagged_users"]:
                    message = f"{message}, {reminder['tagged_users']}"

                channel = await self.bot.fetch_channel(reminder["channel"])
                await channel.send(f"Here's your reminder {message}", embed=embed)

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(name="remind_me", description="Set a reminder for later.")
    async def set_reminder(
        self,
        inter: disnake.ApplicationCommandInteraction,
        when: str = commands.Param(
            description="Timestamp for when you want to be reminded (UK time zone unless otherwise specified)",
        ),
        reminder: str = commands.Param(description="Your reminder", max_length=1024),
    ) -> None:
        """Set a reminder.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        when: float
            The time stamp for when to be reminded.
        reminder: str
            The reminder to set.

        """
        future_time = self.convert_user_requested_time_to_datetime(when)
        if not future_time:
            await inter.response.send_message(f'Unable to understand timestamp "{when}"', ephemeral=True)
            return
        if not future_time.tzinfo:
            future_time = future_time.replace(tzinfo=self.my_timezone)
        now = datetime.datetime.now(tz=self.my_timezone)
        if future_time < now:
            date_string = future_time.strftime(r"%H:%M UTC%z %d %B %Y")
            await inter.response.send_message(f"{date_string} is in the past.", ephemeral=True)
            return

        tagged_users, reminder = await self.replace_mentions_with_display_names(inter.guild, reminder)
        add_reminder(
            {
                "user_id": inter.author.id,
                "channel": inter.channel.id,
                "date": future_time.astimezone(datetime.UTC).isoformat(),
                "reminder": reminder,
                "tagged_users": tagged_users if tagged_users else None,
            },
        )

        await inter.response.send_message(f"Your reminder has been set for {when}.", ephemeral=True)

    @slash_command_with_cooldown(name="forget_reminder", description="Forget one of your reminders.")
    async def forget_reminder(
        self,
        inter: disnake.ApplicationCommandInteraction,
        reminder: str = commands.Param(
            autocomplete=forget_reminders_autocompleter,
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
            filter(lambda r: f"{r['date']}: {r['reminder']}" == reminder, get_all_reminders_for_user(inter.author.id)),
        )
        if not reminder_to_remove:
            Reminders.logger.error("Failed to find reminder (%s) in auto-completion field", reminder)
            await inter.response.send_message("Something went wrong with finding the reminder.", ephemeral=True)
            return
        try:
            reminder_to_remove = reminder_to_remove[0]
        except IndexError:
            Reminders.logger.exception("Failed to index of reminder when trying to delete it from the database")
            await inter.response.send_message("Something went wrong with finding the reminder.", ephemeral=True)
            return
        remove_reminder(reminder_to_remove)

        await inter.response.send_message("Your reminder has been removed.", ephemeral=True)

    @slash_command_with_cooldown(name="my_reminders", description="View your reminders.")
    async def show_reminders(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Show the reminders set for a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.

        """
        reminders = get_all_reminders_for_user(inter.author.id)
        if not reminders:
            await inter.response.send_message("You don't have any reminders.", ephemeral=True)
            return
        reminders = sorted(
            [
                (datetime.datetime.fromisoformat(reminder["date"]).astimezone(datetime.UTC), reminder["reminder"])
                for reminder in reminders
            ],
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


def setup(bot: commands.InteractionBot) -> None:
    """Set up cogs in this module.

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Reminders(bot))
