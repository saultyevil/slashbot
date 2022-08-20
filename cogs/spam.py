#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Commands for sending spam to the chat."""


import atexit
import datetime
import json
import pickle
import random
import re
import shutil
import string
import xml

import disnake
import requests
import rule34 as r34
import tweepy
from disnake.ext import commands, tasks
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

import config
from markovify import markovify

cd_user = commands.BucketType.user


class Spam(commands.Cog):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """A collection of commands to spam the chat with."""

    def __init__(self, bot, markov, badwords, godwords, attempts=10):  # pylint: disable=too-many-arguments
        self.bot = bot
        self.markov = markov
        self.badwords = badwords
        self.godwords = godwords
        self.attempts = attempts
        self.messages = {}
        self.rule34_api = r34.Rule34()
        self.update_markov_chains.start()  # pylint: disable=no-member
        self.twitter = tweepy.Client(config.TWITTER_BEARER_KEY)

        with open(config.USERS_FILES, "r", encoding="utf-8") as fp:
            self.userdata = json.load(fp)

        def on_modify(_):
            with open(config.USERS_FILES, "r", encoding="utf-8") as fp:
                self.userdata = json.load(fp)
            print("Reloaded userdata")

        observer = Observer()
        event_handler = PatternMatchingEventHandler(["*"], None, False, True)
        event_handler.on_modified = on_modify
        observer.schedule(event_handler, config.USERS_FILES, False)
        observer.start()

        # if we don't unregister this, the bot is weird on close down
        # TODO: add this to the bot's shutdown function in bot.py
        atexit.unregister(self.rule34_api._exitHandler)

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(self, inter):
        """Reset the cooldown for some users and servers."""
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOLDOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Slash commands -----------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="badword", description="send a naughty word")
    async def badword(self, inter):
        """Send a badword to the chat."""
        badword = random.choice(self.badwords)

        no_user_badword = True
        for user_id, items in self.userdata.items():
            if badword == items.get("badword", None):
                no_user_badword = False
                user = inter.guild.get_member(int(user_id))
                await inter.response.send_message(f"Here's one for ya, {user.mention} pal ... {badword}!")

        if no_user_badword:
            await inter.response.send_message(f"{badword.capitalize()}.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="chat",
        description="artificial intelligence",
    )
    async def chat(self, inter, words=""):
        """Generate a message from the Markov sentence model.

        Parameters
        ----------
        words: str
            A seed word (or words) to generate a message from.
        """
        await inter.response.defer()
        await inter.edit_original_message(content=self.generate_sentence(words, mentions=False))

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="clap", description="send a clapped out message")
    async def clap(self, inter, text):
        """Replace spaces in a message with claps.

        Parameters
        ---------
        text: str
            The text to replace spaces with claps.
        """
        await inter.response.send_message(":clap:" + ":clap:".join(text.split()) + ":clap:")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="learn", description="force update the markov chain")
    async def learn(self, inter):
        """Update the Markov chain model."""
        if len(self.messages) == 0:
            if inter:
                return await inter.edit_original_message(content="No messages to learn from.")
            else:
                return

        if inter:
            await inter.response.defer(ephemeral=True)

        messages = self.clean_up_messages()
        if len(messages) == 0:
            if inter:
                return await inter.edit_original_message(content="No messages to learn from.")
            return

        shutil.copy2("data/chain.pickle", "data/chain.pickle.bak")
        try:
            new_model = markovify.NewlineText(messages)
        except KeyError:
            await inter.response.send_message("Something bad happened when trying to update the Markov chain.")

        combined = markovify.combine([self.markov.chain, new_model.chain])
        with open("data/chain.pickle", "wb") as fp:
            pickle.dump(combined, fp)
        if inter:
            with open("data/chain.pickle", "rb") as fp:
                self.markov.chain = pickle.load(fp)

        self.messages.clear()

        if inter:
            await inter.edit_original_message(content=f"Markov chain updated with {len(messages)} new messages.")
        else:
            print(f"Markov chain updated with {len(messages)} new messages.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="oracle", description="a message from god")
    async def oracle(self, inter):
        """Send a Terry Davis inspired "God message" to the chat."""
        words = random.sample(self.godwords, random.randint(7, 15))
        await inter.response.send_message(f"{' '.join(words)}")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="rule34", description="search for a naughty image")
    async def rule34(self, inter, query):
        """Search rule34.xxx for a naughty image.

        Parameters
        ----------
        query: str
            The properly formatted query to search for.
        """
        if inter.channel_id == config.ID_CHANNEL_IDIOTS:
            inter.channel_id = config.ID_CHANNEL_SPAM
            inter.channel = self.bot.get_channel(inter.channel_id)

        await inter.response.defer()

        search = query.replace(" ", "+")
        results = await self.rule34_api.getImages(search, fuzzy=False, randomPID=True)
        if results is None:
            await inter.send(f"No results found for `{search}`.")
            return

        choices = [result for result in results if result.has_comments]
        if len(choices) == 0:
            choices = results

        image = random.choice(choices)

        comment, commentor, _ = self.rule34_comments(image.id)
        message = f"|| {image.file_url} ||"
        if comment:
            await inter.edit_original_message(content=f'{message}\n>>> "{comment}"\n*{commentor}*')
        else:
            await inter.edit_original_message(content=f"{message}\n>>> *Too cursed for comments*")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="twatter", description="get a random tweet")
    async def twatter(self, inter, username: str):
        """Get a random tweet from a user.

        Parameters
        ----------
        username: str
            The user to get a random tweet for.
        """
        username = username.lstrip("@")
        user = self.twitter.get_user(username=username, user_fields="profile_image_url,url")[0]
        if not user:
            return await inter.response.send_message(f"There is no @{username}.", ephemeral=True)
        tweets = self.twitter.get_users_tweets(user.id, max_results=100, exclude="retweets")[0]
        if not tweets:
            return await inter.response.send_message(
                f"@{user.username} has no tweets or is a private nonce.", ephemeral=True
            )
        tweet = random.choice(tweets)

        text = tweet.text
        if len(text) > 256:
            text = text[252:] + "..."

        embed = disnake.Embed(title=text, color=disnake.Color.default())
        embed.set_footer(text=f"@{user.username}")
        embed.set_thumbnail(url=user.profile_image_url)

        await inter.response.send_message(embed=embed)

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

        # react a snowflake to adam :-)
        # if message.author.id == config.id_user_adam:
        #    try:
        #        await message.add_reaction("\N{SNOWFLAKE}")
        #    except disnake.errors.Forbidden:
        #        # await message.channel.send(":snowflake:")
        #        pass

        # Replace twitter video links with fx/vx twitter links
        # Check if someone has opted out. If not set, default to False
        fx_enabled = self.userdata.get(str(message.author.id), {}).get("fxtwitter", False)

        if fx_enabled and "https://twitter.com/" in message.content:
            new_url, old_url = self.convert_twitter_video_links(message.content)
            # i.e. if twitter.com was changed to vxtwitter -- removed embed to
            # avoid upsetting Gareth
            if new_url != old_url:
                try:
                    await message.edit(suppress=True)
                except disnake.errors.Forbidden:  # If we fail, then don't send the message
                    return print(f"Unable to suppress embed for {message.author}")

                await message.channel.send(new_url)

    @commands.Cog.listener("on_raw_message_delete")
    async def remove_delete_messages(self, payload):
        """Remove a deleted message from self.messages.

        Parameters
        ----------
        payload:
            The payload containing the message.
        """
        message = payload.cached_message
        if message is None:
            return
        self.messages.pop(str(message.id), None)
        await self.bot.wait_until_ready()

    # Utility functions --------------------------------------------------------

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

    def convert_twitter_video_links(self, tweet_url_from_message):
        """Checks if a tweet has a video, and preprends the URL with fx -- to
        embed a video -- and removes the previous message if it was just a
        message containing a tweet URL.

        Parameters
        ----------
        message: str
            The message containing the URL

        Returns
        -------
        message: str
            The new message to send.
        """

        new_url = tweet_url_from_message = re.search(r"(?P<url>https?://[^\s]+)", tweet_url_from_message).group("url")
        tweet_id = int(
            re.sub(r"\?.*$", "", tweet_url_from_message.rsplit("/", 1)[-1])
        )  # gets the tweet ID as a int from the passed url
        tweet = self.twitter.get_tweet(id=tweet_id, media_fields="type", expansions="attachments.media_keys")

        try:
            media_type = tweet[1]["media"][0].type
        except (IndexError, KeyError):
            return tweet_url_from_message, tweet_url_from_message

        if media_type in ["video", "gif"]:
            new_url = new_url.replace("twitter", "vxtwitter")

        return new_url, tweet_url_from_message

    def generate_sentence(self, seedword=None, mentions=False):  # pylint: disable=too-many-branches
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

                # need a fallback here, in case the chain is too sparse
                if not sentence:
                    sentence = seedword
            else:
                sentence = self.markov.make_sentence()

            # another fallback case, in case the chain is too sparse
            if not sentence:
                sentence = "I have no idea what I'm doing."

            # No matter what, don't allow @here and @everyone mentions, but
            # allow user mentions, if mentions == True

            if "@here" not in sentence and "@everyone" not in sentence:
                if mentions:
                    break
                if "@" not in sentence:
                    break

        if not sentence:
            sentence = self.markov.make_sentence()

        sentence = sentence.strip()
        if len(sentence) > 1024:
            sentence = sentence[:1020] + "..."

        return sentence

    @staticmethod
    def rule34_comments(post_id=None):
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
        if post_id:
            response = requests.get(
                "https://rule34.xxx//index.php?page=dapi&s=comment&q=index",
                params={"post_id": f"{post_id}"},
            )
        else:
            response = requests.get(
                "https://rule34.xxx//index.php?page=dapi&s=comment&q=index",
            )
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

    @tasks.loop(hours=12)
    async def update_markov_chains(self):
        """Get the bot to update the chain every 12 hours."""
        await self.learn(None)
