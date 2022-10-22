#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for sending spam/important messages to the chat."""

import atexit
import datetime
import json
import logging
import pickle
import random
import re
import shutil
import string
from types import coroutine
from typing import List, Union
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

logger = logging.getLogger(config.LOGGER_NAME)
cd_user = commands.BucketType.user


class Spam(commands.Cog):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """A collection of commands to spam the chat with."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: commands.InteractionBot,
        markov_gen: markovify.Text,
        bad_words: List[str],
        god_words: List[str],
        attempts: int = 10,
    ) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        markov_gen: makovify.Text
            A markovify.Text object for generating sentences.
        bad_words: List[str]
            A list of bad words.
        god_words: List[str]
            A list of god words.
        attempts: int
            The number of attempts to generate a markov sentence.
        """

        self.bot = bot
        self.markov = markov_gen
        self.bad_words = bad_words
        self.god_words = god_words
        self.attempts = attempts
        self.messages = {}
        self.rule34_api = r34.Rule34()
        self.twitter_api = tweepy.Client(config.TWITTER_BEARER_KEY)
        self.update_markov_chains.start()  # pylint: disable=no-member

        with open(config.USERS_FILE, "r", encoding="utf-8") as file_in:
            self.user_data = json.load(file_in)

        def on_modify(_):
            with open(config.USERS_FILE, "r", encoding="utf-8") as file_in:
                self.user_data = json.load(file_in)
            logger.info("Reloaded user data")

        observer = Observer()
        event_handler = PatternMatchingEventHandler(["*"], None, False, True)
        event_handler.on_modified = on_modify
        observer.schedule(event_handler, config.USERS_FILE, False)
        observer.start()

        # if we don't unregister this, the bot is weird on close down
        atexit.unregister(self.rule34_api._exitHandler)

    # Before command invoke ----------------------------------------------------

    async def cog_before_slash_command_invoke(
        self, inter: disnake.ApplicationCommandInteraction
    ) -> disnake.ApplicationCommandInteraction:
        """Reset the cooldown for some users and servers.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        if inter.guild and inter.guild.id != config.ID_SERVER_ADULT_CHILDREN:
            return inter.application_command.reset_cooldown(inter)

        if inter.author.id in config.NO_COOL_DOWN_USERS:
            return inter.application_command.reset_cooldown(inter)

    # Slash commands -----------------------------------------------------------

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="bad_word", description="send a naughty word")
    async def bad_word(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a bad word to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        bad_word = random.choice(self.bad_words)

        # at this point, check first if a user has set this bad word as their
        # bad word

        no_user_bad_word = True
        for user_id, items in self.user_data.items():
            if bad_word == items.get("badword", None):
                no_user_bad_word = False
                user = inter.guild.get_member(int(user_id))
                return await inter.response.send_message(f"Here's one for ya, {user.mention} pal ... {bad_word}!")

        if no_user_bad_word:
            return await inter.response.send_message(f"{bad_word.capitalize()}.")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(
        name="chat",
        description="artificial intelligence, powered by markov chain sentence generation",
    )
    async def chat(
        self,
        inter: disnake.ApplicationCommandInteraction,
        words: str = commands.Param(
            default="",
            description="A seed word, or words, for sentence generation. Multiple word sentence generation is limited.",
        ),
    ):
        """Generate a message from the Markov sentence model.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        words: str
            A seed word (or words) to generate a message from.
        """
        await inter.response.defer()
        return await inter.edit_original_message(content=self.generate_sentence(words, mentions=False))

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="clap", description="send a clapped out message")
    async def clap(
        self,
        inter: disnake.ApplicationCommandInteraction,
        text: str = commands.Param(description="The sentence to turn into a clapped out message."),
    ) -> coroutine:
        """Replace spaces in a message with claps.

        Parameters
        ---------
        text: str
            The text to replace spaces with claps.
        """
        return await inter.response.send_message(":clap:" + ":clap:".join(text.split()) + ":clap:")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="update_clap", description="force update the markov chain for /chat")
    async def update_markov_chain(self, inter: disnake.ApplicationCommandInteraction) -> Union[coroutine, None]:
        """Update the Markov chain model.

        If there is no inter, e.g. not called from a command, then this function
        behaves a bit differently -- mostly that it does not respond to any
        interactions.

        The markov chain is updated at the end. The chain is updated by
        combining a newly generated chain with the current chain.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        if len(self.messages) == 0:
            if inter:
                return await inter.edit_original_message(content="No messages to learn from.")
            return None

        if inter:
            await inter.response.defer(ephemeral=True)

        messages = self.clean_up_messages()
        if len(messages) == 0:
            if inter:
                return await inter.edit_original_message(content="No messages to learn from.")
            return None

        shutil.copy2("data/chain.pickle", "data/chain.pickle.bak")  # incase something goes wrong when updating
        try:
            new_model = markovify.NewlineText(messages)
        except KeyError:  # I can't remember what causes this... but it can happen when indexing new words
            return await inter.response.send_message("Something bad happened when trying to update the Markov chain.")

        combined = markovify.combine([self.markov.chain, new_model.chain])
        self.messages.clear()
        self.markov.chain = combined

        with open("data/chain.pickle", "wb") as file_in:
            pickle.dump(combined, file_in)

        if inter:
            await inter.edit_original_message(content=f"Markov chain updated with {len(messages)} new messages.")

        logger.info("Markov chain updated with %i new messages.", len(messages))

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="oracle", description="a message from god")
    async def oracle(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a Terry Davis inspired "God message" to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        words = random.sample(self.god_words, random.randint(7, 15))
        return await inter.response.send_message(f"{' '.join(words)}")

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="rule34", description="search for a naughty image")
    async def rule34(
        self,
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(
            description="The search query as you would on rule34.xxx, e.g. furry+donald_trump or ada_wong."
        ),
    ):
        """Search rule34.xxx for a naughty image.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        query: str
            The properly formatted query to search for.
        """
        await inter.response.defer()

        search = query.replace(" ", "+")
        results = await self.rule34_api.getImages(search, fuzzy=False, randomPID=True)
        if results is None:
            return await inter.edit_original_message(f"No results found for `{search}`.")

        choices = [result for result in results if result.has_comments]
        if len(choices) == 0:
            choices = results

        image = random.choice(choices)

        comment, user_name_comment, _ = self.rule34_comments(image.id)
        if not comment:
            comment = "*Too cursed for comments*"
        message = f"|| {image.file_url} ||"

        return await inter.edit_original_message(content=f'{message}\n>>> "{comment}"\n*{user_name_comment}*')

    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_STANDARD, cd_user)
    @commands.slash_command(name="twitter", description="get a random tweet from a user")
    async def twitter(
        self,
        inter: disnake.ApplicationCommandInteraction,
        username: str = commands.Param(description="The @ of the user to get a tweet for."),
    ) -> coroutine:
        """Get a random tweet from a user.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        username: str
            The user to get a random tweet for.
        """
        username = username.lstrip("@")
        user = self.twitter_api.get_user(username=username, user_fields="profile_image_url,url")[0]
        if not user:
            return await inter.response.send_message(f"There is no @{username}.", ephemeral=True)

        tweets = self.twitter_api.get_users_tweets(user.id, max_results=100, exclude="retweets")[0]
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

        return await inter.response.send_message(embed=embed)

    # Listeners ---------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_to_messages(self, message: str) -> None:
        """Record messages for the Markov chain to learn.

        Parameters
        ----------
        message: disnake.Message
            The message to record.
        """
        self.messages[str(message.id)] = message.content

        # Replace twitter video links with fx/vx twitter links
        # Check if someone has opted out. If not set, default to False
        fx_enabled = self.user_data.get(str(message.author.id), {}).get("fxtwitter", False)

        if fx_enabled and "https://twitter.com/" in message.content:
            new_url, old_url = self.convert_twitter_video_links(message.content)
            # i.e. if twitter.com was changed to vxtwitter -- removed embed to
            # avoid upsetting Gareth
            if new_url != old_url:
                try:
                    await message.edit(suppress=True)
                except disnake.errors.Forbidden:  # If we fail, then don't send the message
                    logger.error("Unable to suppress embed for %s", message.author)
                    return

                await message.channel.send(new_url)

    @commands.Cog.listener("on_raw_message_delete")
    async def remove_delete_messages(self, payload: disnake.RawMessageDeleteEvent) -> None:
        """Remove a deleted message from self.messages.

        Parameters
        ----------
        payload: disnake.RawMessageDeleteEvent
            The payload containing the message.
        """
        message = payload.cached_message
        if message is None:
            return
        self.messages.pop(str(message.id), None)
        await self.bot.wait_until_ready()

    # Utility functions --------------------------------------------------------

    def clean_up_messages(self) -> List[str]:
        """Clean up the recorded messages for the Markov chain to learn.

        Returns
        -------
        learnable: list
            A list of phrases to learn.
        """
        learnable_sentences = []

        for sentence in self.messages.values():
            if len(sentence) == 0:  # empty strings
                continue
            if sentence.startswith(string.punctuation):  # ignore commands, which usually start with punctuation
                continue
            if "@" in sentence:  # don't want to learn how to mention :)
                continue

            learnable_sentences.append(sentence)

        return learnable_sentences

    def convert_twitter_video_links(self, tweet_url_from_message: str) -> Union[str, str]:
        """Checks if a tweet has a video, and prepends the URL with vx -- to
        embed a video -- and removes the previous message if it was just a
        message containing a tweet URL.

        Parameters
        ----------
        message: str
            The message containing the URL

        Returns
        -------
        new_url: str
            The new URL, with vxtwitter instead.
        tweet_url_from_message: str
            The original URL.
        """

        new_url = tweet_url_from_message = re.search(r"(?P<url>https?://[^\s]+)", tweet_url_from_message).group("url")
        tweet_id = int(
            re.sub(r"\?.*$", "", tweet_url_from_message.rsplit("/", 1)[-1])
        )  # gets the tweet ID as a int from the passed url
        tweet = self.twitter_api.get_tweet(id=tweet_id, media_fields="type", expansions="attachments.media_keys")

        try:
            media_type = tweet[1]["media"][0].type
        except (IndexError, KeyError):
            return tweet_url_from_message, tweet_url_from_message

        if media_type in ["video", "gif"]:
            new_url = new_url.replace("twitter", "vxtwitter")

        return new_url, tweet_url_from_message

    def generate_sentence(self, seed_word: str = None, mentions=False) -> str:  # pylint: disable=too-many-branches
        """Generate a "safe" message from the markov chain model.

        Parameters
        ----------
        seed_word: str
            The seed to use to generate a sentence.
        mentions: bool
            Enable the markov chain to generate a message with mentions.

        Returns
        -------
        sentence: str
            The generated sentence.
        """
        for _ in range(self.attempts):
            if seed_word:
                try:
                    if len(seed_word.split()) > 1:
                        sentence = self.markov.make_sentence_with_start(seed_word)
                    else:
                        sentence = self.markov.make_sentence_that_contains(seed_word)
                except (IndexError, KeyError, markovify.text.ParamError):
                    sentence = self.markov.make_sentence()

                # need a fallback here, in case the chain is too sparse
                if not sentence:
                    sentence = seed_word
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
    def rule34_comments(post_id: Union[int, str] = None) -> Union[str, str, str]:
        """Get a random comment from a rule34.xxx post.

        Parameters
        ----------
        id: int
            The post ID number.

        Returns
        -------
        comment: str
            The comment.
        who: str
            The name of the commenter.
        when: str
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
        d_time = datetime.datetime.strptime(when, "%Y-%m-%d %H:%M")
        when = d_time.strftime("%d %B, %Y")

        return comment, who, when

    # Scheduled tasks ----------------------------------------------------------

    @tasks.loop(hours=4)
    async def update_markov_chains(self):
        """Get the bot to update the chain every 4 hours."""
        await self.update_markov_chain(None)
