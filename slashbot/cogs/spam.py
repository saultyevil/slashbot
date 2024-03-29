#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for sending spam/important messages to the chat."""

import atexit
import datetime
import logging
import random
import time
import xml
from collections import defaultdict
from types import coroutine
from typing import Any, Union

import disnake
import requests
import rule34 as r34
from disnake.ext import commands, tasks

from slashbot import markov
from slashbot.config import App
from slashbot.custom_cog import SlashbotCog
from slashbot.db import get_users
from slashbot.markov import update_markov_chain_for_model

logger = logging.getLogger(App.get_config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user


class Spam(SlashbotCog):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """A collection of commands to spam the chat with."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: commands.InteractionBot,
        attempts: int = 10,
    ) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: commands.InteractionBot
            The bot object.
        attempts: int
            The number of attempts to generate a markov sentence.
        """
        super().__init__(bot)

        self.attempts = attempts
        self.markov_training_sample = {}
        self.rule34_api = r34.Rule34()

        self.user_cooldown = defaultdict(lambda: {"time": 0.0, "count": 0})  # tracks last unix time someone used it
        self.cooldown_duration = App.get_config("COOLDOWN_STANDARD")
        self.cooldown_rate = App.get_config("COOLDOWN_RATE")

        self.markov_chain_update_loop.start()  # pylint: disable=no-member

        # if we don't unregister this, the bot is weird on close down
        atexit.unregister(self.rule34_api._exitHandler)

        # this forces a markov chain update when the bot exits, e.g. ctrl+c
        # self.bot.add_function_to_cleanup(
        #     None,
        #     update_markov_chain_for_model,
        #     (
        #         None,
        #         markov.MARKOV_MODEL,
        #         self.markov_training_sample.values(),
        #         App.config("CURRENT_MARKOV_CHAIN"),
        #     ),
        # )

    # Slash commands -----------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="bad_word", description="send a naughty word")
    async def bad_word(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a bad word to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        with open(App.get_config("BAD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
            bad_words = file_in.readlines()

        bad_word = random.choice(bad_words).strip()

        users_to_mention = [
            inter.guild.get_member(user_id).mention
            for user_id, user_settings in get_users().items()
            if user_settings["bad_word"] == bad_word
        ]

        if users_to_mention:
            await inter.response.send_message(f"Here's one for ya, {', '.join(users_to_mention)} ... {bad_word}!")
        else:
            await inter.response.send_message(f"{bad_word.capitalize()}.")

    @commands.slash_command(
        name="evil_wii",
        description="evil wii",
    )
    async def evil_wii(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send the Evil Wii

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to respond to.
        """
        message = random.choice(["evil wii", "evil wii?", "have you seen this?", "||evil wii||", "||evil|| ||wii||"])

        file = disnake.File("data/images/evil_wii.png")
        file.filename = f"SPOILER_{file.filename}"

        await inter.response.send_message(content=message, file=file)

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="update_markov_chain", description="force update the markov chain for /sentence")
    @commands.default_member_permissions(administrator=True)
    async def update_markov_chain(self, inter: disnake.ApplicationCommandInteraction):
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
        if not App.get_config("ENABLE_MARKOV_TRAINING"):
            await inter.response.send_message("Updating the Markov Chain has been disabled.")
        else:
            await inter.response.defer(ephemeral=True)

        await update_markov_chain_for_model(
            inter,
            markov.MARKOV_MODEL,
            list(self.markov_training_sample.values()),
            App.get_config("CURRENT_MARKOV_CHAIN"),
        )
        self.markov_training_sample.clear()

        await inter.edit_original_message("Markov chain has been updated.")

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="oracle", description="a message from god")
    async def oracle(self, inter: disnake.ApplicationCommandInteraction):
        """Send a Terry Davis inspired "God message" to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        """
        with open(App.get_config("GOD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
            oracle_words = file_in.readlines()

        await inter.response.send_message(
            f"{' '.join([word.strip() for word in random.sample(oracle_words, random.randint(5, 25))])}"
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="rule34", description="search for a naughty image")
    async def rule34(
        self,
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(
            description="The search query as you would on rule34.xxx, e.g. furry+donald_trump or ada_wong."
        ),
    ):
        """Get an image from rule34 and a random comment.

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
        if not results:
            return await inter.edit_original_message(f"No results found for `{search}`.")

        choices = [result for result in results if result.has_comments]
        if len(choices) == 0:
            choices = results

        image = random.choice(choices)

        comment, user_name_comment, _ = self.get_comments_for_rule34_post(image.id)
        if not comment:
            comment = "*Too cursed for comments*"
        message = f"|| {image.file_url} ||"

        return await inter.edit_original_message(content=f'{message}\n>>> "{comment}"\n*{user_name_comment}*')

    # Listeners ---------------------------------------------------------------

    # @commands.Cog.listener("on_message")
    # async def respond_to_same(self, message: disnake.Message) -> None:
    #     """Respond "same" to a user who says same.

    #     Parameters
    #     ----------
    #     message : disnake.Message
    #         The message to check for "same".
    #     """
    #     if message.author.bot:
    #         return

    #     if self.check_user_on_cooldown(message.author.id):
    #         return

    #     self.user_cooldown[message.author.id]["time"] = time.time()
    #     self.user_cooldown[message.author.id]["count"] += 1

    #     content = message.clean_content.strip().lower()

    #     if content in ["same", "man", "sad", "fr?"]:
    #         await message.channel.send(f"{message.content}")

    @commands.Cog.listener("on_message")
    async def add_message_to_markov_training_sample(self, message: disnake.Message) -> None:
        """Record messages for the Markov chain to learn.

        Parameters
        ----------
        message: disnake.Message
            The message to record.
        """
        if not App.get_config("ENABLE_MARKOV_TRAINING"):
            return
        if message.author.bot:
            return
        self.markov_training_sample[message.id] = message.clean_content

    @commands.Cog.listener("on_raw_message_delete")
    async def remove_message_from_markov_training_sample(self, payload: disnake.RawMessageDeleteEvent) -> None:
        """Remove a deleted message from the Markov training sentences.

        Parameters
        ----------
        payload: disnake.RawMessageDeleteEvent
            The payload containing the message.
        """
        if not App.get_config("ENABLE_MARKOV_TRAINING"):
            return

        message = payload.cached_message

        # if the message isn't cached, for some reason, we can fetch the channel
        # and the message from the channel
        if message is None:
            channel = await self.bot.fetch_channel(int(payload.channel_id))
            try:
                message = await channel.fetch_message(int(payload.message_id))
            except disnake.NotFound:
                logger.error("Unable to fetch message %d", payload.message_id)
                return

        self.markov_training_sample.pop(message.id, None)

    # Utility functions --------------------------------------------------------

    def check_user_on_cooldown(self, user_id: str | int) -> bool:
        """Check if a user is on cooldown, due to hitting the rate limit.

        Parameters
        ----------
        user_id : str | int
            The ID of the user.

        Returns
        -------
        bool
            Returns True if user on cooldown.
        """
        if self.user_cooldown[user_id]["count"] > self.cooldown_rate:
            if time.time() - self.user_cooldown[user_id]["time"] < self.cooldown_duration:
                return True
            self.user_cooldown[user_id]["count"] = 0
            return False

        return False

    @staticmethod
    def get_comments_for_rule34_post(post_id: Union[int, str] = None) -> tuple[None, None, None] | tuple[Any, Any, str]:
        """Get a random comment from a rule34.xxx post.

        Parameters
        ----------
        post_id: int
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
                f"https://api.rule34.xxx/index.php?page=dapi&s=comment&q=index&post_id={post_id}",
                timeout=5,
            )
        else:
            response = requests.get("https://api.rule34.xxx//index.php?page=dapi&s=comment&q=index", timeout=5)

        if response.status_code != 200:
            logger.error("rule34 comment api returned error code %d", response.status_code)
            return None, None, None

        # the response from the rule34 api is XML, so we have to try and parse
        # that
        try:
            tree = xml.etree.ElementTree.fromstring(response.content)
        except xml.etree.ElementTree.ParseError:
            logger.error("failed to parse rule34 comment api")
            return None, None, None

        post_comments = [
            (elem.get("body"), elem.get("creator"), elem.get("created_at")) for elem in tree.iter("comment")
        ]

        if not post_comments:
            logger.error("failed to find comments in parsed rule34 comment api")
            return None, None, None

        comment, who, when = random.choice(post_comments)
        # the original date format isn't very readable
        when = datetime.datetime.strptime(when, "%Y-%m-%d %H:%M").strftime("%d %B, %Y")

        return comment, who, when

    # Scheduled tasks ----------------------------------------------------------

    @tasks.loop(hours=6)
    async def markov_chain_update_loop(self):
        """Get the bot to update the chain every 6 hours."""
        if not App.get_config("ENABLE_MARKOV_TRAINING"):
            return
        await update_markov_chain_for_model(
            None,
            markov.MARKOV_MODEL,
            list(self.markov_training_sample.values()),
            App.get_config("CURRENT_MARKOV_CHAIN"),
        )
        self.markov_training_sample.clear()


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(Spam(bot))
