"""Commands designed to spam the chat with various things."""

import atexit
import logging
import random
from types import coroutine

import aiofiles
import defusedxml
import defusedxml.ElementTree
import disnake
import requests
import rule34 as r34
from disnake.ext import commands, tasks
from slashlib import markov
from slashlib.config import Bot
from slashlib.db import get_users
from slashlib.markov import MARKOV_MODEL, update_markov_chain_for_model

from slashbot.custom_cog import SlashbotCog

logger = logging.getLogger(Bot.get_config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user
EMPTY_STRING = ""


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

        # If no markov model, don't start the loop.
        if MARKOV_MODEL:
            self.markov_chain_update_loop.start()  # pylint: disable=no-member

        # if we don't unregister this, the bot is weird on close down
        atexit.unregister(self.rule34_api._exitHandler)  # noqa: SLF001

    # Slash commands -----------------------------------------------------------

    @commands.cooldown(Bot.get_config("COOLDOWN_RATE"), Bot.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="bad_word", description="send a naughty word")
    async def bad_word(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Send a bad word to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        async with aiofiles.open(Bot.get_config("BAD_WORDS_FILE"), encoding="utf-8") as file_in:
            bad_words = await file_in.readlines()

        bad_word = random.choice(bad_words).strip()  # noqa: S311
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
        """Send the Evil Wii, a cursed image.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to respond to.

        """
        message = random.choice(  # noqa: S311
            ["evil wii", "evil wii?", "have you seen this?", "||evil wii||", "||evil|| ||wii||"],
        )
        file = disnake.File("data/images/evil_wii.png")
        file.filename = f"SPOILER_{file.filename}"

        await inter.response.send_message(content=message, file=file)

    @commands.cooldown(Bot.get_config("COOLDOWN_RATE"), Bot.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="update_markov_chain", description="force update the markov chain for /sentence")
    @commands.default_member_permissions(administrator=True)
    async def update_markov_chain(self, inter: disnake.ApplicationCommandInteraction) -> None:
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
        if not Bot.get_config("ENABLE_MARKOV_TRAINING"):
            await inter.response.send_message("Updating the Markov Chain has been disabled.")
        else:
            await inter.response.defer(ephemeral=True)

        await update_markov_chain_for_model(
            inter,
            markov.MARKOV_MODEL,
            list(self.markov_training_sample.values()),
            Bot.get_config("CURRENT_MARKOV_CHAIN"),
        )
        self.markov_training_sample.clear()

        await inter.edit_original_message("Markov chain has been updated.")

    @commands.cooldown(Bot.get_config("COOLDOWN_RATE"), Bot.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="oracle", description="a message from god")
    async def oracle(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a Terry Davis inspired "God message" to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        async with aiofiles.open(Bot.get_config("GOD_WORDS_FILE"), encoding="utf-8") as file_in:
            oracle_words = await file_in.readlines()

        await inter.response.send_message(
            f"{' '.join([word.strip() for word in random.sample(oracle_words, random.randint(5, 25))])}",  # noqa: S311
        )

    @commands.cooldown(Bot.get_config("COOLDOWN_RATE"), Bot.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="rule34", description="search for a naughty image")
    async def rule34(
        self,
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(
            description="The search query as you would on rule34.xxx, e.g. furry+donald_trump or ada_wong.",
        ),
    ) -> None:
        """Get an image from rule34 and a random comment.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.
        query: str
            The properly formatted query to search for.

        """
        await inter.response.defer()

        results = await self.rule34_api.getImages(query, fuzzy=False, randomPID=True)
        if not results:
            await inter.edit_original_message(f"No results found for `{query}`.")
            return

        choices = [result for result in results if result.has_comments]
        if len(choices) == 0:
            choices = results
        image = random.choice(choices)  # noqa: S311

        comment, user = self.get_comments_for_rule34_post(image.id)
        comment = "*Too cursed for comments*" if not comment else f'"{comment}"'
        user = " " if not user else f"\n\- *{user}*"  # noqa: W605
        message = f"|| {image.file_url} ||\n>>> {comment}{user}"

        await inter.edit_original_message(content=message)

    # Listeners ---------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def add_message_to_markov_training_sample(self, message: disnake.Message) -> None:
        """Record messages for the Markov chain to learn.

        Parameters
        ----------
        message: disnake.Message
            The message to record.

        """
        if not Bot.get_config("ENABLE_MARKOV_TRAINING"):
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
        if not Bot.get_config("ENABLE_MARKOV_TRAINING"):
            return

        message = payload.cached_message

        # if the message isn't cached, for some reason, we can fetch the channel
        # and the message from the channel
        if message is None:
            channel = await self.bot.fetch_channel(int(payload.channel_id))
            try:
                message = await channel.fetch_message(int(payload.message_id))
            except disnake.NotFound:
                logger.exception("Unable to fetch message %d", payload.message_id)
                return

        self.markov_training_sample.pop(message.id, None)

    # Utility functions --------------------------------------------------------

    @staticmethod
    def get_comments_for_rule34_post(post_id: int | str) -> tuple[str, str]:
        """Get a random comment from a rule34.xxx post.

        Parameters
        ----------
        post_id: int | str
            The post ID number.

        Returns
        -------
        comment: str
            The comment.
        who: str
            The name of the commenter.

        """
        try:
            request_url = f"https://api.rule34.xxx/index.php?page=dapi&s=comment&q=index&post_id={post_id}"
            logger.debug("Rule34 API request to %s", request_url)
            response = requests.get(request_url, timeout=5)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            logger.exception("Request to Rule34 API timed out")
            return EMPTY_STRING, EMPTY_STRING
        except requests.exceptions.RequestException:
            logger.exception("Rule34 API returned %d: unable to get comments for post", response.status_code)
            return EMPTY_STRING, EMPTY_STRING

        # the response from the rule34 api is XML, so we have to try and parse that
        try:
            parsed_comment_xml = defusedxml.ElementTree.fromstring(response.content)
        except defusedxml.ElementTree.ParseError:
            logger.exception("Unable to parse Rule34 comment API return from string into XML")
            logger.debug("%s", response.content)
            return EMPTY_STRING, EMPTY_STRING

        post_comments = [
            (element.get("body"), element.get("creator")) for element in parsed_comment_xml.iter("comment")
        ]
        if not post_comments:
            logger.error("Unable to find any comments in parsed XML comments")
            logger.debug("%s", response.content)
            return EMPTY_STRING, EMPTY_STRING

        return random.choice(post_comments)  # noqa: S311

    # Scheduled tasks ----------------------------------------------------------

    @tasks.loop(hours=6)
    async def markov_chain_update_loop(self) -> None:
        """Get the bot to update the chain every 6 hours."""
        if not Bot.get_config("ENABLE_MARKOV_TRAINING"):
            return
        await update_markov_chain_for_model(
            None,
            markov.MARKOV_MODEL,
            list(self.markov_training_sample.values()),
            Bot.get_config("CURRENT_MARKOV_CHAIN"),
        )
        self.markov_training_sample.clear()


def setup(bot: commands.InteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Spam(bot))
