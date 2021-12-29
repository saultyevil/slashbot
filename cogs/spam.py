#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Commands for sending spam to the chat."""

import asyncio
import atexit
import calendar
import datetime
import json
import pickle
import random
import shutil
import string
import xml

import cowsay
import disnake
import pyfiglet
import requests
import rule34 as r34
import tweepy
from disnake.ext import commands, tasks

import config
from markovify import markovify

cd_user = commands.BucketType.user


class Spam(commands.Cog):
    """A collection of commands to spam the chat with."""

    def __init__(self, bot, markov, badwords, godwords, attempts=10):
        self.bot = bot
        self.markov = markov
        self.badwords = badwords
        self.godwords = godwords
        self.attempts = attempts
        self.messages = {}
        self.rule34 = r34.Rule34()
        with open("data/users.json", "r") as fp:
            self.userdata = json.load(fp)
        atexit.unregister(self.rule34._exitHandler)
        self.monday_morning.start()
        self.wednesday_morning.start()
        self.friday_morning.start()
        self.friday_evening.start()
        self.sunday_morning.start()
        # twitter client
        self.twitter = tweepy.Client(config.twitter_bearer)

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, ctx):
        """Reset the cooldown for some users and servers."""
        if ctx.guild.id != config.id_server_adult_children:
            return ctx.application_command.reset_cooldown(ctx)

        if ctx.author.id in config.no_cooldown_users:
            return ctx.application_command.reset_cooldown(ctx)

    # Slash commands -----------------------------------------------------------

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="badword", description="send a naughty word", guild_ids=config.slash_servers)
    async def badword(self, ctx):
        """Send a badword to the chat."""
        badword = random.choice(self.badwords)

        no_user_badword = True
        for user_id, items in self.userdata.items():
            if badword == items.get("badword", None):
                no_user_badword = False
                user = ctx.guild.get_member(int(user_id))
                await ctx.response.send_message(f"Here's one for ya, {user.mention} pal ... {badword}!")

        if no_user_badword:
            await ctx.response.send_message(f"{badword.capitalize()}.")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="chat",
        description="artificial intelligence",
        guild_ids=config.slash_servers,
    )
    async def chat(self, ctx, words=""):
        """Generate a message from the Markov sentence model.
        TODO: this might want to be deferred, as can be too long with a large state size

        Parameters
        ----------
        words: str
            A seed word (or words) to generate a message from.
        """
        await ctx.response.send_message(self.generate_sentence(words, mentions=False))

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(
        name="cowsay",
        description="what the cow say",
        guild_ids=config.slash_servers,
    )
    async def cow(self, ctx, text, cow=commands.Param(default="cow", autocomplete=list(cowsay.char_names))):
        """Generate a cow saying the given text.

        Parameters
        ----------
        text: str
            The text to say.
        """
        text = text.replace("```", "")
        cow = cowsay.get_output_string("cow", text)

        await ctx.response.send_message(f"```{cow}```")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="danny", description="get the latest danny dyer tweet", guild_ids=config.slash_servers)
    async def danny(self, ctx):
        """Send the latest Danny Dyer tweet to the chat."""
        user = self.twitter.get_user(username="MrDDyer")[0]
        tweets = self.twitter.get_users_tweets(user.id, max_results=100, exclude="retweets")[0]
        tweet = random.choice(tweets)

        danny_pics = [
            "https://m.media-amazon.com/images/M/MV5BMTUyMzYxNTEwNV5BMl5BanBnXkFtZTYwNzQxOTEz._V1_UY317_CR6,0,214,317_AL_.jpg",
            "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/Danny_Dyer_at_Upton_Park%2C_02_Oct_2010.jpg"
            "/480px-Danny_Dyer_at_Upton_Park%2C_02_Oct_2010.jpg",
            "https://www.thesun.co.uk/wp-content/uploads/2021/01/c9df3413-00fd-4c0d-9b65-715cdba59ad0.jpg",
            "https://i2-prod.mylondon.news/incoming/article20765554.ece/ALTERNATES/s615/3_JS230006785.jpg",
            "https://www.irishnews.com/picturesarchive/irishnews/irishnews/2019/09/10/084044159-557339d9-0c46-40c1-b2f9-4ce7eee211cc.jpg",
            "https://thebigissue581.wpengine.com/wp-content/uploads/2018/11/DYER02.jpg"
        ]

        embed = disnake.Embed(title=f"{tweet.text}", color=disnake.Color.default())
        embed.set_thumbnail(url=random.choice(danny_pics))
        embed.set_footer(text=f"{self.generate_sentence('danny')}")

        await ctx.response.send_message(embed=embed)

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="figlet", description="encode text to a figlet", guild_ids=config.slash_servers)
    async def figlet(self, ctx, text):
        """Send a figlet to the chat.

        Parameters
        ----------
        text: str
            The text to encode into a figlet.
        """
        text = text.replace("```", "")
        figlet = pyfiglet.Figlet(font="standard").renderText(text)

        await ctx.response.send_message(f"```{figlet}```")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="learn", description="force update the markov chain", guild_ids=config.slash_servers)
    async def learn(self, ctx):
        """Update the Markov chain model."""
        if len(self.messages) == 0:
            if ctx:
                return await ctx.edit_original_message(f"No messages to learn from.")
            else:
                return

        if ctx:
            await ctx.response.defer()
        else:
            print("Updating markov chain...")

        messages = self.clean_up_messages()
        if len(messages) == 0:
            if ctx:
                return await ctx.edit_original_message(f"No messages to learn from.")
            else:
                return

        shutil.copy2("data/chain.pickle", "data/chain.pickle.bak")
        try:
            new_model = markovify.NewlineText(messages)
        except KeyError:
            await ctx.response.send_message("Something bad happened when trying to update the Markov chain.")

        combined = markovify.combine([self.markov.chain, new_model.chain])
        with open("data/chain.pickle", "wb") as fp:
            pickle.dump(combined, fp)
        if ctx:
            with open("data/chain.pickle", "rb") as fp:
                self.markov.chain = pickle.load(fp)

        self.messages.clear()

        if ctx:
            await ctx.edit_original_message(content=f"Markov chain updated with {len(messages)} new messages.")
        else:
            print(f"Markov chain updated with {len(messages)} new messages.")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="oracle", description="a message from god", guild_ids=config.slash_servers)
    async def oracle(self, ctx):
        """Send a Terry Davis inspired "God message" to the chat."""
        words = random.sample(self.godwords, random.randint(7, 15))
        await ctx.response.send_message(f"{' '.join(words)}")

    @commands.cooldown(config.cooldown_rate, config.cooldown_standard, cd_user)
    @commands.slash_command(name="rule34", description="search for a naughty image", guild_ids=config.slash_servers)
    async def rule34(self, ctx, query):
        """Search rule34.xxx for a naughty image.

        Parameters
        ----------
        query: str
            The properly formatted query to search for.
        """
        search = query.replace(" ", "+")
        results = await self.rule34.getImages(search, fuzzy=False, randomPID=True)
        if results is None:
            await ctx.send(f"No results found for `{search}`.")
            return

        choices = [result for result in results if result.has_comments]
        if len(choices) == 0:
            choices = results

        image = random.choice(choices)

        comment, commentor, when = self.rule34_comments(image.id)
        message = f"|| {image.file_url} ||"
        if comment:
            await ctx.send(f"{message}\n>>> \"{comment}\"\n*{commentor}*")
        else:
            await ctx.send(f"{message}\n>>> *Too cursed for comments*")

    @commands.cooldown(1, config.cooldown_standard, cd_user)
    @commands.slash_command(name="spit", description="i spit in your direction", guild_ids=config.slash_servers)
    async def spit(self, ctx):
        """Send the GIF of the girl spitting."""
        await ctx.response.defer()
        await ctx.edit_original_message(file=disnake.File("data/spit.gif"))

    # Listeners ---------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_to_messages(self, message):
        """Record messages for the Markov chain to learn.

        Parameters
        ----------
        message: disnake.Message
            The message to record.
        """
        self.messages[str(message.id)] = message.content

    @commands.Cog.listener("on_raw_message_delete")
    async def remove_delete_messages(self, payload):
        """Remove a deleted message from self.messages.

        Parameters
        ----------
        payload:
            The payload containing the message.
        """
        message = payload.cached_message
        if message is None: return
        self.messages.pop(str(message.id), None)
        await self.bot.wait_until_ready()

    # Utility functions --------------------------------------------------------

    @staticmethod
    def add_time(time, days, hour, minute, second):
        """Add a week to a datetime object.

        Parameters
        ----------
        time: datetime.datetime
            The datetime to calculate from.
        days: float
            The number of additional days to sleep for
        hour: int
            The scheduled hour
        minute: int
            The scheduled minute
        second: int
            The scheduled second
        """
        next_date = time + datetime.timedelta(days=days)
        when = datetime.datetime(year=next_date.year,
                                 month=next_date.month,
                                 day=next_date.day,
                                 hour=hour,
                                 minute=minute,
                                 second=second)
        next_date = when - time

        return next_date.days * 86400 + next_date.seconds

    def clean_up_messages(self):
        """Clean up the recorded messages for the Markov chain to learn.

        Returns
        -------
        learnable: list
            A list of phrases to learn.
        """
        learnable = []

        for phrase in self.messages.values():
            if len(phrase) == 0:
                continue
            elif phrase.startswith(string.punctuation):
                continue
            elif "@" in phrase:
                continue

            learnable.append(phrase)

        return learnable

    def generate_sentence(self, seedword=None, mentions=False):
        """Generate a "safe" message from the markov chain model.

        Parameters
        ----------
        seed: str
            The seed to use to generate a sentence.
        mentions: bool
            Enable the markov chain to generate a message with mentions.
        """
        for _ in range(self.attempts):
            if seedword:
                try:
                    if len(seedword.split()) > 1:
                        sentence = self.markov.make_sentence_with_start(seedword)
                    else:
                        sentence = self.markov.make_sentence_that_contains(seedword)
                except (IndexError, KeyError, markovify.text.ParamError):
                    sentence = self.markov.make_sentence()
            else:
                sentence = self.markov.make_sentence()

            # No matter what, don't allow @here and @everyone mentions, but
            # allow user mentions, if mentions == True

            if "@here" not in sentence and "@everyone" not in sentence:
                if mentions: break
                else:
                    if "@" not in sentence: break

        if not sentence:
            sentence = self.markov.make_sentence()

        return sentence.strip()[:1024]

    @staticmethod
    def rule34_comments(id=None):
        """Get a random comment from a rule34.xxx post.

        Parameters
        ----------
        id: int
            The post ID number.

        Returns
        -------
        comment: str
            The comment.
        commentor: str
            The name of the commenter.
        date: str
            A string of when the comment was created
        """
        if id:
            response = requests.get("https://rule34.xxx//index.php?page=dapi&s=comment&q=index",
                                    params={"post_id": f"{id}"})
        else:
            response = requests.get("https://rule34.xxx//index.php?page=dapi&s=comment&q=index", )
        if response.status_code != 200:
            return None, None, None

        try:
            tree = xml.etree.ElementTree.fromstring(response.content)
        except xml.etree.ElementTree.ParseError:
            return None, None, None

        comments = [(elem.get("body"), elem.get("creator"), elem.get("created_at")) for elem in tree.iter("comment")]
        if len(comments) == 0:
            return None, None, None

        comment, who, when = random.choice(comments)
        dt = datetime.datetime.strptime(when, "%Y-%m-%d %H:%M")
        when = dt.strftime("%d %B, %Y")

        return comment, who, when

    # Scheduled tasks ----------------------------------------------------------

    @tasks.loop(hours=config.hours_in_week)
    async def monday_morning(self):
        """Send a message on Monday morning."""
        server = self.bot.get_guild(config.id_server_adult_children)
        channel = server.get_channel(config.id_channel_idiots)
        await channel.send(self.generate_sentence("monday").replace("monday", "**monday**"),
                           file=disnake.File("data/videos/monday.mp4"))

    @tasks.loop(hours=config.hours_in_week)
    async def wednesday_morning(self):
        """Send a message on Wednesday morning."""
        server = self.bot.get_guild(config.id_server_adult_children)
        channel = server.get_channel(config.id_channel_idiots)
        await channel.send(self.generate_sentence("wednesday").replace("wednesday", "**wednesday**"),
                           file=disnake.File("data/videos/wednesday.mp4"))

    @tasks.loop(hours=config.hours_in_week)
    async def friday_evening(self):
        """Send a message on Friday evening."""
        server = self.bot.get_guild(config.id_server_adult_children)
        channel = server.get_channel(config.id_channel_idiots)
        await channel.send(self.generate_sentence("weekend").replace("weekend", "**weekend**"),
                           file=disnake.File("data/videos/weekend.mp4"))

    @tasks.loop(hours=config.hours_in_week)
    async def friday_morning(self):
        """Send a message on Friday morning."""
        server = self.bot.get_guild(config.id_server_adult_children)
        channel = server.get_channel(config.id_channel_idiots)
        await channel.send(self.generate_sentence("friday").replace("friday", "**friday**"),
                           file=disnake.File("data/videos/friday.mp4"))

    @tasks.loop(hours=config.hours_in_week)
    async def sunday_morning(self):
        """Send a message on Sunday morning."""
        server = self.bot.get_guild(config.id_server_adult_children)
        channel = server.get_channel(config.id_channel_idiots)
        await channel.send(self.generate_sentence("sunday").replace("sunday", "**sunday**"),
                           file=disnake.File("data/videos/sunday.mp4"))

    @tasks.loop(hours=12)
    async def update_markov_chains(self):
        """Get the bot to update the chain every 12 hours."""
        await self.learn(None)

    # Sleep tasks --------------------------------------------------------------

    def calc_sleep_time(self, day, hour, minute):
        """Calculate the time to sleep until the next specified week day.

        Parameters
        ----------
        day: int
            The day of the week to wake up, i.e. calender.MONDAY
        hour: int
            The hour to wake up.
        minute: int
            The minute to wake up.

        Returns
        -------
        sleep: int
            The time to sleep in seconds.
        """

        now = datetime.datetime.now()
        next_date = now + datetime.timedelta(days=(day - now.weekday()) % 7)
        when = datetime.datetime(year=next_date.year,
                                 month=next_date.month,
                                 day=next_date.day,
                                 hour=hour,
                                 minute=minute,
                                 second=0)
        next_date = when - now
        sleep = next_date.days * 86400 + next_date.seconds
        if sleep < 0:
            sleep = self.add_time(when, 7, hour, minute, 0)

        return sleep

    @monday_morning.before_loop
    async def sleep_monday_morning(self):
        """Sleep until Monday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.MONDAY, 8, 30))
        await self.bot.wait_until_ready()

    @wednesday_morning.before_loop
    async def sleep_wednesday_morning(self):
        """Sleep until Wednesday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.WEDNESDAY, 8, 30))
        await self.bot.wait_until_ready()

    @friday_evening.before_loop
    async def sleep_friday_evening(self):
        """Sleep until Monday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.FRIDAY, 17, 0))
        await self.bot.wait_until_ready()

    @friday_morning.before_loop
    async def sleep_friday_morning(self):
        """Sleep until Friday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.FRIDAY, 8, 30))
        await self.bot.wait_until_ready()

    @sunday_morning.before_loop
    async def sleep_sunday_morning(self):
        """Sleep until Monday morning."""
        await asyncio.sleep(self.calc_sleep_time(calendar.SUNDAY, 10, 0))
        await self.bot.wait_until_ready()
