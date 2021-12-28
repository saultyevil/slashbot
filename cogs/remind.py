
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import disnake
import config
import datetime
from disnake.ext import commands, tasks
from dateutil import parser
import time
import re


cd_user = commands.BucketType.user
time_units = {
    "time": 1,
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
}
whofor = ["here", "dm", "both"]


class Reminder(commands.Cog):
    """Commands to set up reminders.
    """

    def __init__(self, bot, generate_sentence):
        self.bot = bot
        self.generate_sentence = generate_sentence
        self.reminders = {}
        self.load_reminders()
        self.check_reminders.start()

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, ctx):
        """Reset the cooldown for some users and servers.
        """
        if ctx.guild.id != config.id_server_adult_children:
            return ctx.application_command.reset_cooldown(ctx)

        if ctx.author.id in config.no_cooldown_users:
            return ctx.application_command.reset_cooldown(ctx)

    # Commands -----------------------------------------------------------------

    @commands.cooldown(1, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="remind",
        description="set a reminder",
        guild_ids=config.slash_servers
    )
    async def add(
        self, ctx, when:str=commands.Param(), time_unit=commands.Param(autocomplete=list(time_units.keys())),
        reminder=commands.Param(), where=commands.Param(default="here", autocomplete=whofor)
    ):
        """Set a reminder.

        Parameters
        ----------
        when: float
            The amount of time to wait before the reminder.
        time_unit: str
            The unit of time to wait before the reminder.
        reminder: str
            The reminder to set.
        who: str
            Where to be reminded, either "here", "dm" or "both".
        """
        if len(reminder) > 1024:
            return await ctx.response.send_message(
                "That is too long of a reminder. 1024 characters is the max.", ephemeral=True
            )

        tagged_users, reminder = self.replace_mentions(reminder)
        user_id = ctx.author.id
        server_id = ctx.guild.id
        channel_id = ctx.channel.id

        if time_unit != "time":
            try:
                when = float(when)
            except ValueError:
                return await ctx.response.send_message("That is not a valid number.", ephemeral=True)
            if when <= 0:
                return await ctx.response.send_message(f"You can't set a reminder for 0 {time_unit} or less.", ephemeral=True)

        now = datetime.datetime.now()

        if time_unit == "time":
            try:
                future = parser.parse(when)
            except parser.ParserError:
                return await ctx.response.send_message("That is not a valid timestamp.", ephemeral=True)
        else:
            seconds = when * time_units[time_unit]
            future = now + datetime.timedelta(seconds=seconds)

        future = future.isoformat()

        if future < now.isoformat():
            return await ctx.response.send_message("You can't set a reminder in the past.", ephemeral=True)

        key = f"{int(time.time())}{user_id}"
        self.reminders[key] = {
            "user": user_id,
            "whofor": where,
            "channel": channel_id,
            "tag": tagged_users,
            "when": future,
            "what": reminder,
        }
        self.save_reminders()

        if time_unit == "time":
            await ctx.response.send_message(f"Reminder set for {when}.", ephemeral=True)
        else:
            await ctx.response.send_message(f"Reminder set for {when} {time_unit}.", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="forget",
        description="clear your reminders",
        guild_ids=config.slash_servers
    )
    async def remove(self, ctx, m_id):
        """Clear a reminder or all of a user's reminders.

        Parameters
        ----------
        m_id: str
            The id of the reminder to remove.
        """
        if m_id not in self.reminders:
            return await ctx.response.send_message("That reminder doesn't exist.", ephemeral=True)

        if self.reminders[m_id]["user"] != ctx.author.id:
            return await ctx.response.send_message("You can't remove someone else's reminder.", ephemeral=True)

        removed = self.reminders.pop(m_id, None)
        self.save_reminders()

        await ctx.response.send_message(f"Reminder for {removed['what']} removed.", ephemeral=True)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="planned",
        description="view your reminders",
        guild_ids=config.slash_servers
    )
    async def show(self, ctx):
        """Show the reminders set for a user.
        """
        reminders = [(id, item) for id, item in self.reminders.items() if item["user"] == ctx.author.id]

        if not reminders:
            return await ctx.response.send_message("You don't have any reminders set.", ephemeral=True)

        message = f"You have {len(reminders)} reminders set.\n```"
        for id, reminder in reminders:
            message += f"{id}: {reminder['what']} at {datetime.datetime.fromisoformat(reminder['when'])}\n"

        await ctx.author.send(message + "```")

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=5.0)
    async def check_reminders(self):
        """Check if any reminders need to be sent.
        """
        for m_id, reminder in list(self.reminders.items()):
            when = datetime.datetime.fromisoformat(reminder["when"])

            if when <= datetime.datetime.now():
                user = self.bot.get_user(reminder["user"])
                embed = disnake.Embed(title=reminder["what"], color=disnake.Color.default())
                embed.set_footer(text=f"{self.generate_sentence('reminder')}")
                embed.set_thumbnail(url=user.avatar.url)

                if reminder["whofor"] == "user" or reminder["whofor"] == "both":
                    await user.send(embed=embed)

                if reminder["whofor"] == "here" or reminder["whofor"] == "both":
                    channel = self.bot.get_channel(reminder["channel"])
                    message = f"{user.mention}"

                    if user.id != config.id_user_adam:
                        for user_id in reminder["tag"]:
                            user = self.bot.get_user(int(user_id))
                            if user:
                                message += f" {user.mention}"

                    await channel.send(message, embed=embed)

                self.reminders.pop(m_id, None)
                self.save_reminders()

    # Functions ----------------------------------------------------------------

    def load_reminders(self):
        """Load the reminders from a file.
        """
        with open("data/reminders.json", "r") as fp:
            self.reminders = json.load(fp)

    def replace_mentions(self, sentence):
        """Replace mentions from a post with the user name.
        """
        user_ids = re.findall(r"\<@!(.*?)\>", sentence)

        for u_id in user_ids:
            user = self.bot.get_user(int(u_id))
            sentence = sentence.replace(f"<@!{u_id}>", user.name)

        return user_ids, sentence

    def save_reminders(self):
        """Dump the reminders to a file.
        """
        with open("data/reminders.json", "w") as fp:
            json.dump(self.reminders, fp)
