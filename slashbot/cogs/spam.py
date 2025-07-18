"""Commands designed to spam the chat with various things."""

import asyncio
import atexit
import random

import aiofiles
import defusedxml
import defusedxml.ElementTree
import disnake
import requests
import rule34 as r34
from disnake.ext import commands, tasks

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.clock import calculate_seconds_until
from slashbot.core import markov
from slashbot.settings import BotSettings

EMPTY_STRING = ""


class Spam(CustomCog):  # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """A collection of commands to spam the chat with."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        bot: CustomInteractionBot,
        attempts: int = 10,
    ) -> None:
        """Initialize the cog.

        Parameters
        ----------
        bot: CustomInteractionBot
            The bot object.
        attempts: int
            The number of attempts to generate a markov sentence.

        """
        super().__init__(bot)

        self.attempts = attempts
        self.markov_training_sample = {}
        self.rule34_api = r34.Rule34()

        # if we don't unregister this, the bot is weird on close down
        atexit.unregister(self.rule34_api._exitHandler)  # noqa: SLF001

    # Slash commands -----------------------------------------------------------

    @slash_command_with_cooldown(name="bad_word", description="send a naughty word")
    async def bad_word(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a bad word to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        async with aiofiles.open(BotSettings.file_locations.bad_words, encoding="utf-8") as file_in:
            bad_words = await file_in.readlines()
        bad_word = random.choice(bad_words).strip()
        await inter.response.send_message(f"{bad_word.capitalize()}.")

    @slash_command_with_cooldown(name="evil_wii", description="evil wii")
    async def evil_wii(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send the Evil Wii, a cursed image.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to respond to.

        """
        message = random.choice(
            ["evil wii", "evil wii?", "have you seen this?", "||evil wii||", "||evil|| ||wii||"],
        )
        file = disnake.File("data/images/evil_wii.png")
        file.filename = f"SPOILER_{file.filename}"

        await inter.response.send_message(content=message, file=file)

    @slash_command_with_cooldown(name="oracle", description="a message from god")
    async def oracle(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a Terry Davis inspired "God message" to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        async with aiofiles.open(BotSettings.file_locations.god_words, encoding="utf-8") as file_in:
            oracle_words = await file_in.readlines()

        await inter.response.send_message(
            f"{' '.join([word.strip() for word in random.sample(oracle_words, random.randint(5, 25))])}",
        )

    @slash_command_with_cooldown(name="rule34", description="search for a naughty image")
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
        image = random.choice(choices)

        comment, user = self.get_comments_for_rule34_post(image.id)
        comment = "*Too cursed for comments*" if not comment else f'"{comment}"'
        user = " " if not user else f" -- *{user}*"
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
        if not BotSettings.markov.enable_markov_training:
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
        if not BotSettings.markov.enable_markov_training:
            return

        message = payload.cached_message

        # if the message isn't cached, for some reason, we can fetch the channel
        # and the message from the channel
        if message is None:
            channel = await self.bot.fetch_channel(int(payload.channel_id))
            if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                self.log_error("Trying to remove message in non-text channel %d", payload.channel_id)
                return
            try:
                message = await channel.fetch_message(int(payload.message_id))
            except disnake.NotFound:
                self.log_error("Unable to fetch message %d from channel %d", payload.message_id, payload.channel_id)
                return

        self.markov_training_sample.pop(message.id, None)

    # Utility functions --------------------------------------------------------

    def get_comments_for_rule34_post(self, post_id: int | str) -> tuple[str | None, str | None]:
        """Get a random comment from a rule34.xxx post.

        Parameters
        ----------
        post_id: int | str
            The post ID number.

        Returns
        -------
        comment: str
            The comment.

        """
        try:
            request_url = f"https://api.rule34.xxx/index.php?page=dapi&s=comment&q=index&post_id={post_id}"
            self.log_debug("Rule34 API request to %s", request_url)
            response = requests.get(request_url, timeout=5)
            response.raise_for_status()
        except requests.exceptions.Timeout:
            self.log_exception("Request to Rule34 API timed out")
            raise
        except requests.exceptions.RequestException as exc:
            status = getattr(exc.response, "status_code", "unknown")
            self.log_exception("Rule34 API returned %d: unable to get comments for post", status)
            raise

        # the response from the rule34 api is XML, so we have to try and parse that
        try:
            parsed_comment_xml = defusedxml.ElementTree.fromstring(response.content)
        except defusedxml.ElementTree.ParseError:
            self.log_exception("Unable to parse Rule34 comment API return from string into XML %s", response.content)
            raise

        post_comments = [
            (element.get("body"), element.get("creator")) for element in parsed_comment_xml.iter("comment")
        ]
        if not post_comments:
            self.log_error("Unable to find any comments in parsed XML comments %s", response.content)
            return EMPTY_STRING, EMPTY_STRING

        return random.choice(post_comments)

    # Scheduled tasks ----------------------------------------------------------

    @tasks.loop(seconds=1)
    async def markov_chain_update_loop(self) -> None:
        """Get the bot to update the chain every 6 hours."""
        if not BotSettings.markov.enable_markov_training:
            return
        if not markov.MARKOV_MODEL:
            return
        sleep_time = calculate_seconds_until(-1, 3, 0, 1)
        self.log_info(
            "Waiting %d seconds/%d minutes/%.1f hours till markov chain update",
            sleep_time,
            sleep_time // 60,
            sleep_time / 3600,
        )
        await asyncio.sleep(sleep_time)

        await markov.update_markov_chain_for_model(
            None,
            markov.MARKOV_MODEL,
            list(self.markov_training_sample.values()),
            BotSettings.markov.current_chain_location,
        )
        self.markov_training_sample.clear()


def setup(bot: CustomInteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Spam(bot))
