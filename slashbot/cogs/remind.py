#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for setting, viewing and removing reminders."""

import datetime
import json
import logging
import re
from types import coroutine
from typing import List, Union

import disnake
from dateutil import parser
from disnake.ext import commands, tasks
from prettytable import PrettyTable

from slashbot.config import App
from slashbot.cog import CustomCog
from slashbot.markov import generate_sentence

logger = logging.getLogger(App.config("LOGGER_NAME"))
cd_user = commands.BucketType.user
time_units = {
    "time stamp": 1,
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
}
who_for = ("here", "dm", "both")


class Reminder(CustomCog):
    """Commands to set up reminders."""

    def __init__(self, bot):
        self.bot = bot
        self.reminders = App.config("REMINDERS_FILE_STREAM")
        self.check_reminders.start()  # pylint: disable=no-member

    # Commands -----------------------------------------------------------------

    @commands.cooldown(1, App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="set_reminder", description="set a reminder for later")
    async def set_reminder(  # pylint: disable=too-many-arguments too-many-return-statements
        self,
        inter: disnake.ApplicationCommandInteraction,
        time_unit: str = commands.Param(
            description="The time-frame to set for your reminder.",
            choices=list(time_units.keys()),
        ),
        when: str = commands.Param(
            description='When you want to be reminded, remember the timezone if you\'ve chosen "time stamp".'
        ),
        reminder: str = commands.Param(description="What you want to be reminded about."),
        where: str = commands.Param(
            description="Where to be reminded.",
            default="here",
            choices=who_for,
        ),
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

        tagged_users, reminder = self.replace_mentions(reminder)
        user_id = inter.author.id
        channel_id = inter.channel.id

        if time_unit != "time stamp":
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

        if time_unit == "time stamp":
            try:
                future = parser.parse(when)
            except parser.ParserError:
                return await inter.response.send_message("That is not a valid timestamp.", ephemeral=True)
        else:
            seconds = when * time_units[time_unit]
            future = now + datetime.timedelta(seconds=seconds)

        future = future.isoformat()

        if future < now.isoformat():
            return await inter.response.send_message("You can't set a reminder in the past.", ephemeral=True)

        key = len(reminder) + 1
        while str(key) in self.reminders:
            key += 1

        self.reminders[str(key)] = {
            "user": user_id,
            "whofor": where,
            "channel": channel_id,
            "tag": tagged_users,
            "when": future,
            "what": reminder,
        }
        self.save_reminders()

        logger.info("tagged users %s", tagged_users)

        if time_unit == "time stamp":
            return await inter.response.send_message(f"Reminder set for {when}.", ephemeral=True)

        return await inter.response.send_message(f"Reminder set for {when} {time_unit}.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
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
        if reminder_id not in self.reminders:
            return await inter.response.send_message(
                "That reminder doesn't exist, use /show_reminders to see your reminders.", ephemeral=True
            )

        if self.reminders[reminder_id]["user"] != inter.author.id:
            return await inter.response.send_message("You can't remove someone else's reminder.", ephemeral=True)

        removed = self.reminders.pop(reminder_id, None)
        self.save_reminders()

        return await inter.response.send_message(f"Reminder for {removed['what']} removed.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), cd_user)
    @commands.slash_command(name="show_reminders", description="view your reminders")
    async def show_reminders(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Show the reminders set for a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction object for the command.
        """
        reminders = [  # this is one hell of a list comprehension
            [m_id, datetime.datetime.fromisoformat(item["when"]), item["what"]]
            for m_id, item in self.reminders.items()
            if item["user"] == inter.author.id
        ]
        if not reminders:
            return await inter.response.send_message("You don't have any reminders set.", ephemeral=True)

        message = f"You have {len(reminders)} reminders set.\n```"
        table = PrettyTable()
        table.align = "r"
        table.field_names = ["ID", "When", "What"]
        table._max_width = {"ID": 10, "When": 10, "What": 50}  # pylint: disable=protected-access
        table.add_rows(reminders)
        message += table.get_string(sortby="ID") + "```"

        return await inter.response.send_message(message, ephemeral=True)

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=5.0)
    async def check_reminders(self):
        """Check if any reminders need to be sent wherever needed."""
        for reminder_id, reminder in list(self.reminders.items()):
            when = datetime.datetime.fromisoformat(reminder["when"])

            if when <= datetime.datetime.now():
                user = self.bot.get_user(reminder["user"])
                if not user:
                    continue

                embed = disnake.Embed(title=reminder["what"], color=disnake.Color.default())
                embed.set_footer(text=f"{generate_sentence(seed_word='reminder')}")
                embed.set_thumbnail(url=user.avatar.url)

                self.reminders.pop(reminder_id, None)
                self.save_reminders()

                if reminder["whofor"] in ["dm", "both"]:
                    await user.send(embed=embed)

                if reminder["whofor"] in ["here", "both"]:
                    channel = self.bot.get_channel(reminder["channel"])
                    message = f"{user.mention}"

                    for user_id in reminder["tag"]:
                        user = self.bot.get_user(int(user_id))
                        if user:
                            message += f" {user.mention}"

                    await channel.send(message, embed=embed)

    # Functions ----------------------------------------------------------------

    def replace_mentions(self, sentence: str) -> Union[List[str], str]:
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

        logger.info("user_ids found in sentence %s", user_ids)

        for u_id in user_ids:
            user = self.bot.get_user(int(u_id))
            sentence = sentence.replace(f"<{mention_pattern}{u_id}>", f"@{user.name}")

        return user_ids, sentence

    def save_reminders(self):
        """Dump the reminders to a file."""
        with open(App.config("REMINDERS_FILE"), "w", encoding="utf-8") as file_in:
            json.dump(self.reminders, file_in)
