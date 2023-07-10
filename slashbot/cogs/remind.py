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
from sqlalchemy.orm import Session, sessionmaker

from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import Reminder as ReminderDB
from slashbot.db import connect_to_database_engine
from slashbot.markov import MARKOV_MODEL, generate_sentences_for_seed_words

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


def get_reminders_for_user(inter: disnake.ApplicationCommandInteraction, _: str) -> List[str]:
    """Get the reminders for a user.

    TODO, bit of a performance issue here as whenever the user inputs another
          character, this function will re-run and query the database again
          which involves creating a session and running a list comprehension

    Parameters
    ----------
    inter : disnake.ApplicationCommandInteraction
        _description_
    _ : str
        _description_

    Returns
    -------
    str
        _description_
    """
    with Session(connect_to_database_engine()) as session:
        reminders = session.query(ReminderDB).filter(ReminderDB.user_id == inter.author.id)

    return [reminder.reminder for reminder in reminders]


async def close_session(session: Session):
    """Close a database session.

    Parameters
    ----------
    session : Session
        The session to close.
    """
    session.close()


class Reminders(SlashbotCog):
    """Commands to set up reminders."""

    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.timezone = datetime.datetime.utcnow().astimezone().tzinfo

        self.check_reminders.start()  # pylint: disable=no-member

        self.session = sessionmaker(connect_to_database_engine())()

        self.markov_sentences = (
            generate_sentences_for_seed_words(
                MARKOV_MODEL,
                ["reminder"],
                App.config("PREGEN_MARKOV_SENTENCES_AMOUNT"),
            )
            if self.bot.markov_gen_on
            else {"reminder": []}
        )

        self.bot.add_function_to_cleanup(None, close_session, (self.session,))

    # Private methods ----------------------------------------------------------

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
        # now = datetime.datetime.now(tz=self.timezone)
        now = datetime.datetime.now(tz=datetime.UTC)
        reminders = self.session.query(ReminderDB)
        if reminders.count() == 0:
            return

        for reminder in reminders:
            date = reminder.date.replace(tzinfo=datetime.UTC)

            if date <= now:
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
                        if user_id == str(reminder.user_id):
                            continue
                        user = await self.bot.fetch_user(int(user_id))
                        if user and user.mention not in message:
                            message += f" {user.mention}"

                self.session.delete(reminder)
                self.session.commit()
                await channel.send(message, embed=embed)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_reminder", description="set a reminder for later")
    async def set_reminder(  # pylint: disable=too-many-arguments too-many-return-statements
        self,
        inter: disnake.ApplicationCommandInteraction,
        when: str = commands.Param(description="When you want to be reminded, UTC timezones are preferred."),
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
                "That is too long of a reminder. 1024 characters is the max.",
                ephemeral=True,
            )

        # now we need to figure out the time for when the reminder is supposed
        # to happen
        now = datetime.datetime.now(tz=self.timezone)

        # settings makes BST -> British Summer Time instead of Bangladesh, but
        # it does some odd things. If you do something like 21:30 UTC+6, it will
        # convert that date to the bot's local timezone. For an input of 21:30
        # UTC+6 when the bot's timezone is UTC+1, future = 16:30 UTC + 1
        future = dateparser.parse(when, settings={"TIMEZONE": "Europe/London"})

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

        # this is a bit of a hack, because the tagged users is a CSV string....
        tagged_users, reminder = await self.__replace_mentions_in_sentence(reminder)

        self.session.add(
            ReminderDB(
                user_id=inter.author.id,
                channel=inter.channel.id,
                date=future.astimezone(datetime.UTC),
                reminder=reminder,
                tagged_users=tagged_users if tagged_users else None,
            )
        )
        self.session.commit()

        return await inter.response.send_message(f"Reminder set for {date_string}.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="forget_reminder", description="forget a reminder")
    async def forget_reminder(
        self,
        inter: disnake.ApplicationCommandInteraction,
        reminder: str = commands.Param(
            autocomplete=get_reminders_for_user, description="The reminder you want to forget."
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
        reminder = self.session.query(ReminderDB).filter(ReminderDB.reminder == reminder).first()
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
        reminders = [
            (reminder.id, reminder.date.strftime(r"%H:%M %d %B %Y (UTC)"), reminder.reminder) for reminder in reminders
        ]

        table = PrettyTable()
        table.align = "r"
        table.field_names = ["ID", "When", "What"]
        table._max_width = {"ID": 3, "When": 25, "What": 75}  # pylint: disable=protected-access
        table.add_rows(reminders)
        message = f"You have {len(reminders)} reminders set.\n```"
        message += table.get_string(sortby="ID") + "```"
        message += f"Current UTC time: {datetime.datetime.utcnow().strftime(r'%H:%M %d %B %Y')}"

        return await inter.response.send_message(message, ephemeral=True)
