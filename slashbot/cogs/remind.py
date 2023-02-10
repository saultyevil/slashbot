#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for setting, viewing and removing reminders."""

import datetime
import logging
import re
from types import coroutine
from typing import List
from typing import Union

import disnake
from dateutil import parser
from disnake.ext import commands, tasks
from prettytable import PrettyTable
from sqlalchemy.orm import sessionmaker

from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.db import Reminder as ReminderDB
from slashbot.db import connect_to_database_engine
from slashbot.markov import MARKOV_MODEL
from slashbot.markov import generate_sentences_for_seed_words

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user
TIME_UNITS = {
    "Time stamp": 1,
    "Seconds": 1,
    "Minutes": 60,
    "Hours": 3600,
}


class ReminderCommands(CustomCog):
    """Commands to set up reminders."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.check_reminders.start()  # pylint: disable=no-member

        self.session = sessionmaker(connect_to_database_engine())()

        self.markov_sentences = generate_sentences_for_seed_words(
            MARKOV_MODEL,
            ["reminder"],
            App.config("PREGEN_MARKOV_SENTENCES_AMOUNT"),
        )

        self.bot.add_to_cleanup(None, self.__close_session, (None))

    # Private methods ----------------------------------------------------------

    async def __close_session(self) -> None:
        """Close the session."""
        self.session.close()

    async def __replace_mentions_in_sentence(self, sentence: str) -> Union[List[str], str]:
        """Replace mentions from a post with the user name.

        Parameters
        ----------
        sentence: str
            The sentence to remove mentions from.

        Returns
        -------
        user_ids: List[str]
            A list of user ids in the sentence.
        sentence: str
            The sentence with mentions removed.
        """
        user_ids = re.findall(r"\<@!(.*?)\>", sentence)
        mention_pattern = "@!"
        if not user_ids:
            user_ids = re.findall(r"\<@(.*?)\>", sentence)
            mention_pattern = "@"

        for user_id in user_ids:
            user = await self.bot.fetch_user(user_id)
            sentence = sentence.replace(f"<{mention_pattern}{user_id}>", f"@{user.name}")

        return ",".join(user_ids), sentence

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=1)
    async def check_reminders(self) -> None:
        """Check if any reminders need to be sent wherever needed."""
        now = datetime.datetime.now()
        reminders = self.session.query(ReminderDB)
        if reminders.count() == 0:
            return

        for reminder in reminders:
            if reminder.date <= now:
                user = await self.bot.fetch_user(reminder.user_id)
                if not user:
                    continue

                embed = disnake.Embed(title=reminder.reminder, color=disnake.Color.default())
                embed.set_footer(text=f"{self.get_generated_sentence('reminder')}")
                embed.set_thumbnail(url=user.avatar.url)

                channel = await self.bot.fetch_channel(reminder.channel)
                message = f"{user.mention}"

                if reminder.tagged_users:
                    for user_id in reminder.tagged_users.split(","):
                        user = await self.bot.fetch_user(int(user_id))
                        if user:
                            message += f" {user.mention}"

                self.session.delete(reminder)
                self.session.commit()
                await channel.send(message, embed=embed)

    # Commands -----------------------------------------------------------------

    # @commands.cooldown(1, App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="set_reminder", description="set a reminder for later")
    async def set_reminder(  # pylint: disable=too-many-arguments too-many-return-statements
        self,
        inter: disnake.ApplicationCommandInteraction,
        time_unit: str = commands.Param(
            description="The time-frame to set for your reminder.",
            choices=list(TIME_UNITS.keys()),
        ),
        when: str = commands.Param(
            description='When you want to be reminded, remember the timezone if you\'ve chosen "time stamp".'
        ),
        reminder: str = commands.Param(description="What you want to be reminded about."),
    ) -> coroutine:
        """Set a reminder.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        time_unit: str
            The unit of time to wait before the reminder.
        when: float
            The amount of time to wait before the reminder.
        reminder: str
            The reminder to set.
        where: str
            Where to be reminded, either "here", "dm" or "both".
        """
        if len(reminder) > 1024:
            return await inter.response.send_message(
                "That is too long of a reminder. 1024 characters is the max.",
                ephemeral=True,
            )

        if time_unit != "Time stamp":
            try:
                when = float(when)
            except ValueError:
                return await inter.response.send_message("That is not a valid number.", ephemeral=True)
            if when <= 0:
                return await inter.response.send_message(
                    f"You can't set a reminder for 0 {time_unit} or less.",
                    ephemeral=True,
                )

        now = datetime.datetime.now()

        if time_unit == "Time stamp":
            try:
                future = parser.parse(when)
            except parser.ParserError:
                return await inter.response.send_message("That is not a valid timestamp.", ephemeral=True)
        else:
            seconds = when * TIME_UNITS[time_unit]
            future = now + datetime.timedelta(seconds=seconds)

        if future < now:
            return await inter.response.send_message("You can't set a reminder in the past.", ephemeral=True)

        tagged_users, reminder = await self.__replace_mentions_in_sentence(reminder)

        self.session.add(
            ReminderDB(
                user_id=inter.author.id,
                channel=inter.channel.id,
                date=future,
                reminder=reminder,
                tagged_users=tagged_users if tagged_users else None,
            )
        )
        self.session.commit()

        if time_unit == "Time stamp":
            return await inter.response.send_message(f"Reminder set for {when}.", ephemeral=True)
        return await inter.response.send_message(f"Reminder set for {when} {time_unit}.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="forget_reminder", description="forget a reminder")
    async def forget_reminder(
        self,
        inter: disnake.ApplicationCommandInteraction,
        reminder_id: str = commands.Param(
            description="The ID of the reminder you want to forget. Use /show_reminders to see your reminders."
        ),
    ) -> coroutine:
        """Clear a reminder or all of a user's reminders.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        m_id: str
            The id of the reminder to remove.
        """
        reminder = self.session.query(ReminderDB).filter(ReminderDB.id == reminder_id).first()
        if not reminder:
            return await inter.response.send_message("There is no reminder with that ID.", ephemeral=True)
        if reminder.user_id != inter.author.id:
            return await inter.response.send_message("This isn't your reminder to remove.", ephemeral=True)
        self.session.delete(reminder)
        self.session.commit()

        return await inter.response.send_message("Reminder removed.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_reminders", description="view your reminders")
    async def show_reminders(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Show the reminders set for a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        reminders = self.session.query(ReminderDB).filter(ReminderDB.user_id == inter.author.id)
        if reminders.count() == 0:
            return await inter.response.send_message("You don't have any reminders.", ephemeral=True)
        reminders = [(reminder.id, reminder.date, reminder.reminder) for reminder in reminders]

        table = PrettyTable()
        table.align = "r"
        table.field_names = ["ID", "When", "What"]
        table._max_width = {"ID": 10, "When": 10, "What": 50}  # pylint: disable=protected-access
        table.add_rows(reminders)
        message = f"You have {len(reminders)} reminders set.\n```"
        message += table.get_string(sortby="ID") + "```"

        return await inter.response.send_message(message, ephemeral=True)
