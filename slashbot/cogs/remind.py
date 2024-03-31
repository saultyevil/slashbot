#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for setting, viewing and removing reminders."""

import datetime
import logging
import re
from types import coroutine
from typing import List, Union

import dateparser
import disnake
from disnake.ext import commands, tasks
from prettytable import PrettyTable

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import (
    add_reminder,
    get_all_reminders,
    get_all_reminders_for_user,
    remove_reminder,
)
from slashbot.markov import MARKOV_MODEL, generate_sentences_for_seed_words

logger = logging.getLogger(App.get_config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user

SECONDS_IN_DAY = 86400
SECONDS_IN_HOUR = 3600
SECONDS_IN_MINUTE = 60


def get_reminders_autocomplete(inter: disnake.ApplicationCommandInteraction, _: str) -> str:
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
    reminders = get_all_reminders_for_user(inter.author.id)
    return [f"{reminder['date']}: {reminder['reminder']}" for reminder in reminders]


class Reminders(SlashbotCog):
    """Commands to set up reminders."""

    def __init__(self, bot):
        super().__init__(bot)
        self.timezone = datetime.datetime.utcnow().astimezone().tzinfo
        self.check_reminders.start()  # pylint: disable=no-member
        self.markov_sentences = ()

    async def cog_load(self):
        """Initialise the cog.

        Currently this does:
            - create markov sentences
        """
        self.markov_sentences = (
            generate_sentences_for_seed_words(
                MARKOV_MODEL,
                ["reminder"],
                App.get_config("PREGEN_MARKOV_SENTENCES_AMOUNT"),
            )
            if self.bot.markov_gen_on
            else {"reminder": []}
        )
        logger.debug("Generated Markov sentences for %s cog at cog load", self.__cog_name__)

    # Private methods ----------------------------------------------------------

    @staticmethod
    def convert_time_to_datetime(time_format: str, when: str, now: datetime.datetime) -> datetime.datetime:
        """Return a datetime in the future, for a given format and time.

        Parameters
        ----------
        format : str
            The time format chosen.
        when : str
            A string to say when to set the reminder for.
        now : datetime.datetime
            A datetime.datetime object representing now.

        Returns
        -------
        datetime.datetime
            A date time object for the reminder in the future.
        """
        if time_format == "time-string":
            # settings makes BST -> British Summer Time instead of Bangladesh, but
            # it does some odd things. If you do something like 21:30 UTC+6, it will
            # convert that date to the bot's local timezone. For an input of 21:30
            # UTC+6 when the bot's timezone is UTC+1, future = 16:30 UTC + 1
            future = dateparser.parse(when, settings={"TIMEZONE": "Europe/London"})
        else:
            if time_format == "days":
                seconds = when * SECONDS_IN_DAY
            elif time_format == "hours":
                seconds = when * SECONDS_IN_HOUR
            elif time_format == "minutes":
                seconds = when * SECONDS_IN_MINUTE
            else:  # basically default to seconds, I guess
                seconds = when
            future = now + datetime.timedelta(seconds=int(seconds))

        return future

    async def replace_mentions_with_names(self, guild: disnake.Guild, sentence: str) -> Union[List[str], str]:
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
                    name = self.bot.user.name
                else:
                    user = await self.bot.fetch_user(int(mention))
                    name = user.name
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

        mentions_str = " ".join(mentions)
        return mentions_str, modified_sentence

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=1)
    async def check_reminders(self) -> None:
        """Check if any reminders need to be sent wherever needed."""
        reminders = get_all_reminders()
        if len(reminders) == 0:
            return
        now = datetime.datetime.now(tz=datetime.UTC)

        for index, reminder in enumerate(reminders):
            date = datetime.datetime.fromisoformat(reminder["date"]).replace(tzinfo=datetime.UTC)

            if date <= now:
                reminder_user = await self.bot.fetch_user(reminder["user_id"])
                if not reminder_user:
                    continue

                embed = disnake.Embed(title=reminder["reminder"], color=disnake.Color.default())
                embed.set_footer(text=f"{await self.async_get_markov_sentence('reminder')}")
                embed.set_thumbnail(url=reminder_user.avatar.url)

                channel = await self.bot.fetch_channel(reminder["channel"])
                message = f"{reminder_user.mention}"

                if reminder["tagged_users"]:
                    message = f"{reminder['tagged_users']} {message}"

                remove_reminder(index)
                await channel.send(message, embed=embed)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_reminder", description="set a reminder for later")
    async def set_reminder(  # pylint: disable=too-many-arguments too-many-return-statements
        self,
        inter: disnake.ApplicationCommandInteraction,
        time_format: str = commands.Param(
            name="format",
            description="The format for setting reminder times",
            choices=["time-string", "days", "hours", "minutes", "seconds"],
        ),
        when: str = commands.Param(
            description="When you want to be reminded. The current UK time zones is used by default."
        ),
        reminder: str = commands.Param(description="What you want to be reminded about."),
    ) -> coroutine:
        """Set a reminder.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        when: float
            The amount of time to wait before the reminder.
        reminder: str
            The reminder to set.
        """
        if len(reminder) > 1024:
            return await inter.response.send_message(
                "Reminders cannot be longer than 1024 characters.",
                ephemeral=True,
            )

        if time_format != "time-string":
            try:
                when = float(when)
            except ValueError:
                return await inter.response.send_message(
                    f"Can't convert '{when}' into a number",
                    ephemeral=True,
                )

        now = datetime.datetime.now(tz=self.timezone)
        future = self.convert_time_to_datetime(time_format, when, now)

        if not future:
            logger.debug("future is None type for %s", when)
            return await inter.response.send_message(f'Unable to parse "{when}".', ephemeral=True)

        if not future.tzinfo:
            future = future.replace(tzinfo=self.timezone)

        date_string = future.strftime(r"%H:%M UTC%z %d %B %Y")

        if future < now:
            logger.debug("future < now: Parsed time  %s", future)
            logger.debug("future < now: Current time %s", now)
            return await inter.response.send_message(f"{date_string} is in the past.", ephemeral=True)

        tagged_users, reminder = await self.replace_mentions_with_names(inter.guild, reminder)

        add_reminder(
            {
                "user_id": inter.author.id,
                "channel": inter.channel.id,
                "date": future.astimezone(datetime.UTC).isoformat(),
                "reminder": reminder,
                "tagged_users": tagged_users if tagged_users else None,
            }
        )

        return await inter.response.send_message(f"Reminder set for {date_string}.", ephemeral=True)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="forget_reminder", description="forget a reminder")
    async def forget_reminder(
        self,
        inter: disnake.ApplicationCommandInteraction,
        reminder: str = commands.Param(
            autocomplete=get_reminders_autocomplete,
            description="The reminder you want to forget.",
        ),
    ) -> coroutine:
        """Clear a reminder or all of a user's reminders.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        reminder: str
            The reminder to forget
        """
        specific_reminder = list(
            filter(lambda r: f"{r['date']}: {r['reminder']}" == reminder, get_all_reminders_for_user(inter.author.id))
        )
        if not specific_reminder:
            return await inter.response.send_message("This reminder doesn't exist, somehow.", ephemeral=True)

        try:
            specific_reminder = specific_reminder[0]
        except IndexError:
            return await inter.response.send_message("Something went wrong with finding your reminder.", ephemeral=True)

        all_reminders = get_all_reminders()
        index = all_reminders.index(specific_reminder)
        remove_reminder(index)

        return await inter.response.send_message("Reminder removed.", ephemeral=True)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_reminders", description="view your reminders")
    async def show_reminders(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Show the reminders set for a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        reminders = get_all_reminders_for_user(inter.author.id)
        if not reminders:
            return await inter.response.send_message("You don't have any reminders.", ephemeral=True)
        reminders = sorted(
            [
                (datetime.datetime.fromisoformat(reminder["date"]).astimezone(datetime.UTC), reminder["reminder"])
                for reminder in reminders
            ],
            key=lambda entry: entry[0],
        )

        reminders = [(entry[0].strftime(r"%H:%M %d %B %Y (UTC)"), entry[1]) for entry in reminders]

        table = PrettyTable()
        table.align = "r"
        table.field_names = ["When", "What"]
        table._max_width = {"When": 25, "What": 75}  # pylint: disable=protected-access
        table.add_rows(reminders)
        message = f"You have {len(reminders)} reminders set.\n```"
        message += table.get_string() + "```"
        message += f"Current UTC time: {datetime.datetime.utcnow().strftime(r'%H:%M %d %B %Y')}"

        return await inter.response.send_message(message, ephemeral=True)


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(Reminders(bot))
