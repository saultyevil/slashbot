
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
    "unix": 1,
    "time stamp": 1,
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
    "weeks": 604800,
    "months": 2592000,
    "years": 31536000
}
whofor = ["channel", "user"]


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
        self, ctx, amount:float=commands.Param(), time_unit=commands.Param(autocomplete=list(time_units.keys())),
        what=commands.Param(), whofor=commands.Param(autocomplete=whofor)
    ):
        """Set a reminder.

        Parameters
        ----------
        amount: float
            The amount of time to wait before the reminder.
        time_unit: str
            The unit of time to wait before the reminder.
        what: str
            The reminder to set.
        who: str
            Who to remind, either "user" or "channel".
        """
        if amount <= 0:
            return await ctx.response.send_message("You can't set a reminder for 0 units or less.", ephemeral=True)

        if len(what) > 1024:
            return await ctx.response.send_message(
                "That is too long of a reminder. 1024 characters is the max.", ephemeral=True
            )

        tagged_users, what = self.replace_mentions(what)
        user_id = ctx.author.id
        server_id = ctx.guild.id
        channel_id = ctx.channel.id

        now = datetime.datetime.now()

        if time_unit == "unix":
            try:
                unix = datetime.datetime.fromtimestamp(amount)
            except TypeError:
                return await ctx.response.send_message("That is not a valid unix timestamp.", ephemeral=True)
            future = unix
        elif time_unit == "time stamp":
            try:
                future = parser.parse(amount)
            except parser.ParserError:
                return await ctx.response.send_message("That is not a valid timestamp.", ephemeral=True)
        else:
            seconds = amount * time_units[time_unit]
            future = now + datetime.timedelta(seconds=seconds)

        future = future.isoformat()
        if future < now.isoformat():
            return await ctx.response.send_message("You can't set a reminder in the past.", ephemeral=True)

        key = f"{int(time.time())}{user_id}"  # the id for the reminder is the current unix time plus the user id
        self.reminders[key] = {
            "user": user_id,
            "whofor": whofor,
            "server": server_id,
            "channel": channel_id,
            "tag": tagged_users,
            "when": future,
            "what": what,
            "amount": amount,
            "time_unit": time_unit
        }
        self.save_reminders()

        await ctx.response.send_message(f"Reminder set for {amount} {time_unit}.")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="forget",
        description="clear your reminders",
        guild_ids=config.slash_servers
    )
    async def clear(self, ctx, id):
        """Clear a reminder or all of a user's reminders.

        Parameters
        ----------
        reminder: int
            The id of the reminder to remove.
        """
        if id not in self.reminders:
            return await ctx.response.send_message("That reminder doesn't exist.", ephemeral=True)

        if self.reminders[id]["user"] != ctx.author.id:
            return await ctx.response.send_message("You can't remove someone else's reminder.", ephemeral=True)

        removed = self.reminders.pop(id, None)
        self.save_reminders()

        await ctx.response.send_message(f"Reminder for {removed['what']} removed.")

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

        await ctx.author.send_message(message + "```")

    # Tasks --------------------------------------------------------------------

    @tasks.loop(seconds=5.0)
    async def check_reminders(self):
        """Check if any reminders need to be sent.
        """
        for id, reminder in list(self.reminders.items()):

            when = datetime.datetime.fromisoformat(reminder["when"])
            if when <= datetime.datetime.now():
                user = self.bot.get_user(reminder["user"])
                if user is None: continue # why does this happen?
                embed = disnake.Embed(title=reminder["what"], color=disnake.Color.default())
                # embed.add_field(name="Added", value=f"{reminder['amount']} {reminder['time_unit']} ago", inline=False)
                embed.set_footer(text=f"{self.generate_sentence('reminder')}")
                embed.set_thumbnail(url=user.avatar.url)

                if reminder["whofor"] == "user":
                    await user.send(embed=embed)
                else:
                    channel = self.bot.get_channel(reminder["channel"])
                    message = f"{user.mention}"
                    if user.id != config.id_user_adam:
                        for user_id in reminder["tag"]:
                            user = self.bot.get_user(user_id)
                            message += f" {user.mention}"
                    await channel.send(message, embed=embed)

                self.reminders.pop(id, None)
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
        for id in user_ids:
            id = self.bot.get_user(int(id))
            sentence = sentence.replace(f"<!@{id.id}>", id.name)

        return user_ids, sentence

    def save_reminders(self):
        """Dump the reminders to a file.
        """
        with open("data/reminders.json", "w") as fp:
            json.dump(self.reminders, fp)
