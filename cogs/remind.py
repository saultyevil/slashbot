
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import disnake
import config
import datetime
from disnake.ext import commands, tasks
import time


cd_user = commands.BucketType.user
time_units = ["minutes", "hours", "days", "weeks", "months"]
whofor = ["channel", "user"]


class Reminder(commands.Cog):
    """Commands to set up reminders.
    """

    def __init__(self, bot, generate_sentence):
        self.bot = bot
        self.generate_sentence = generate_sentence
        self.reminders = {}
        self.load_reminders()
        self.time_units = {"minute" : 60, "hour" : 3600, "day" : 86400, "week": 604800, "month": 2592000}
        self.check_reminders.start()

    # Commands -----------------------------------------------------------------

    @commands.cooldown(1, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="remind",
        description="set a reminder",
        guild_ids=config.slash_servers
    )
    async def reminder(
        self, ctx, amount:float=commands.Param(), time_unit=commands.Param(autocomplete=time_units),
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
            return await ctx.response.send_message("You can't set a reminder for 0 units or less.")

        if len(what) > 1024:
            return await ctx.response.send_message("That is too long of a reminder. 1024 characters is the max.")

        tagged_users, what = self.replace_mentions(what)
        user_id = ctx.author.id
        server_id = ctx.guild.id
        channel_id = ctx.channel.id

        seconds = amount * self.time_units[time_unit[:-1]]
        future = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        self.reminders[int(time.time())] = {
            "user": user_id,
            "whofor": whofor,
            "server": server_id,
            "channel": channel_id,
            "tag": tagged_users,
            "when": future.isoformat(),
            "what": what,
            "amount": amount,
            "time_unit": time_unit
        }
        self.save_reminders()

        await ctx.response.send_message(f"Reminder set for {amount} {time_unit}.")

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

                self.reminders.pop(id)
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
        users = []
        sentence = sentence.split()
        for n, split in enumerate(sentence):
            if split.startswith("<@!"):
                user_id = int(split[3:].rstrip(">"))
                user = self.bot.get_user(user_id)
                users.append(user_id)
                sentence[n] = user.name

        sentence = " ".join(sentence)

        return users, sentence

    def save_reminders(self):
        """Dump the reminders to a file.
        """
        with open("data/reminders.json", "w") as fp:
            json.dump(self.reminders, fp)
