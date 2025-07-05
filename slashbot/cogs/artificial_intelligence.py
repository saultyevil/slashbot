"""Text generation cog for Slashbot."""

import asyncio
import datetime
import logging
import random
from collections import defaultdict
from dataclasses import dataclass
from textwrap import shorten

import disnake
from disnake.ext import commands
from pyinstrument import Profiler

import slashbot.watchers
from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.bot.custom_types import ApplicationCommandInteraction, Message
from slashbot.core import markov
from slashbot.core.ai import AIChat, AIChatSummary, SummaryMessage
from slashbot.core.text_generation import (
    SUPPORTED_MODELS,
    GenerationFailureError,
    TextGenerationInput,
    VisionImage,
    VisionVideo,
    read_in_prompt,
)
from slashbot.messages import send_message_to_channel
from slashbot.responses import is_reply_to_slash_command_response
from slashbot.settings import BotSettings

MAX_MESSAGE_LENGTH = BotSettings.discord.max_chars


@dataclass
class Cooldown:
    """Dataclass for tracking cooldowns for a user."""

    count: int
    last_interaction: datetime.datetime


class ArtificialIntelligence(CustomCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialize the AIChatbot class.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The instance of the SlashbotInterationBot class.

        """
        super().__init__(bot)
        self.chats = {}
        self.channel_histories = {}
        self.user_cooldown_map = defaultdict(lambda: Cooldown(0, datetime.datetime.now(tz=datetime.UTC)))

        self._lock = asyncio.Lock()
        self._profiler = Profiler(async_mode="enabled")
        file_handler = logging.FileHandler("logs/profile.log")
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        self._profiler_logger = logging.getLogger("ProfilerLogger")
        self._profiler_logger.handlers.clear()
        self._profiler_logger.addHandler(file_handler)
        self._profiler_logger.setLevel(logging.INFO)

    def _start_profiler(self) -> None:
        if not BotSettings.cogs.artificial_intelligence.enable_profiling:
            return
        if self._profiler.is_running:
            self._profiler.stop()
            self._profiler.reset()
        self._profiler.start()

    def _stop_profiler(self) -> None:
        if not BotSettings.cogs.artificial_intelligence.enable_profiling:
            return
        if not self._profiler.is_running:
            self.log_error("Attempted to stop the profiler when it's not running -- resetting profiler")
            self._profiler.reset()
            return
        self._profiler.stop()
        profiler_output = self._profiler.output_text()
        self._profiler_logger.info("\n%s", profiler_output)
        self._profiler.reset()

    @staticmethod
    def _get_context_id(obj: Message | ApplicationCommandInteraction) -> int:
        return obj.channel.id

    def _get_ai_summary_for_id(self, obj: int | Message | ApplicationCommandInteraction) -> AIChatSummary:
        context_id = self._get_context_id(obj) if not isinstance(obj, int) else obj
        if context_id in self.channel_histories:
            return self.channel_histories[context_id]

        if isinstance(obj, int):
            msg = "History ID is an int, but a ai conversation has not been found"
            raise ValueError(msg)  # noqa: TRY004

        if isinstance(obj.channel, disnake.TextChannel):
            extra_print = f"{obj.channel.name}"
        elif isinstance(obj.channel, disnake.DMChannel):
            extra_print = f"{obj.channel.recipient}"
        else:
            extra_print = f"{obj.channel.id}"

        self.channel_histories[context_id] = AIChatSummary(
            token_window_size=BotSettings.cogs.artificial_intelligence.token_window_size,
            extra_print=extra_print,
        )
        return self.channel_histories[context_id]

    def _get_ai_chat_for_id(self, obj: int | Message | ApplicationCommandInteraction) -> AIChat:
        context_id = self._get_context_id(obj) if not isinstance(obj, int) else obj
        if context_id in self.chats:
            return self.chats[context_id]
        if isinstance(obj, int):
            msg = "History ID is an int, but an ai chat has not been found"
            raise ValueError(msg)  # noqa: TRY004

        if isinstance(obj.channel, disnake.TextChannel):
            extra_print = f"{obj.channel.name}"
        elif isinstance(obj.channel, disnake.DMChannel):
            extra_print = f"{obj.channel.recipient}"
        else:
            extra_print = f"{obj.channel.id}"

        self.chats[context_id] = AIChat(
            extra_print=extra_print,
        )
        return self.chats[context_id]

    def _check_if_user_on_cooldown(self, user_id: int) -> bool:
        """Check if a user is on cooldown or not.

        Parameters
        ----------
        user_id : int
            The id of the user to rate limit

        Returns
        -------
        bool
            Returns True if the user needs to be rate limited

        """
        current_time = datetime.datetime.now(tz=datetime.UTC)
        user_cooldown = self.user_cooldown_map[user_id]
        time_difference = (current_time - user_cooldown.last_interaction).seconds

        # Check if exceeded rate limit
        if user_cooldown.count > BotSettings.cogs.artificial_intelligence.response_rate_limit:
            # If exceeded rate limit, check if cooldown period has passed
            if time_difference > BotSettings.cogs.artificial_intelligence.rate_limit_interval:
                # reset count and update last_interaction time
                user_cooldown.count = 1
                user_cooldown.last_interaction = current_time
                return False
            # still under cooldown
            return True
        # hasn't exceeded rate limit, update count and last_interaction
        user_cooldown.count += 1
        user_cooldown.last_interaction = current_time

        return False

    @staticmethod
    async def _send_fallback_response_to_prompt(message: disnake.Message, *, dont_tag_user: bool = False) -> None:
        """Send a fallback response using the markov chain.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.
        dont_tag_user: bool
            Whether or not to tag the user or not, optional

        """
        await send_message_to_channel(
            markov.generate_text_from_markov_chain(markov.MARKOV_MODEL, "?random", 1),  # type: ignore
            message,
            dont_tag_user=dont_tag_user,  # In a DM, we won't @ the user
        )

    async def _get_attached_images_from_message(self, message: Message) -> list[VisionImage]:
        """Retrieve the URLs for images attached or embedded in a Discord message.

        Parameters
        ----------
        message : Message
            The Discord message object to extract image URLs from.

        Returns
        -------
        List[Image]
            A list of `Image` dataclasses containing the URL, base64-encoded image
            data and the MIME type of the image.

        """
        image_urls = [
            attachment.url
            for attachment in message.attachments
            if attachment.content_type and attachment.content_type.startswith("image/")
        ]
        image_urls += [embed.url for embed in message.embeds if embed.type == "image" and embed.url]

        images = []
        for url in image_urls:
            image = VisionImage(url)
            if not BotSettings.cogs.artificial_intelligence.prefer_image_urls:
                try:
                    await image.download_and_encode()
                except Exception:  # noqa: BLE001
                    self.log_exception("Failed to download image from %s", url)
            images.append(image)

        return images

    async def _get_attached_videos_from_message(self, message: Message) -> list[VisionVideo]:
        """Retrieve the URLs for YouTube videos embedded in a Discord message.

        Note that we won't deal with video attachments, because then we have
        to download the image and encode to b64, which is a bit costly.

        Parameters
        ----------
        message : Message
            The Discord message object to extract video URLs from.

        Returns
        -------
        List[VisionVideo]
            A list of `VisionVideo` dataclasses containing the URL of the video.

        """
        video_urls = [embed.url for embed in message.embeds if embed.type == "video" and embed.url]

        return [VisionVideo(url) for url in set(video_urls)]

    async def _get_highlighted_discord_message(self, original_message: disnake.Message) -> disnake.Message:
        """Retrieve a message from a message reply.

        Parameters
        ----------
        original_message : disnake.Message
            The message containing the reference

        Returns
        -------
        disnake.Message:
            The associated meassage in Discord

        """
        message_reference = original_message.reference
        if not message_reference:
            return original_message
        previous_message = message_reference.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                    return original_message
                if not message_reference.message_id:
                    return original_message
                previous_message = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return original_message

        return previous_message

    async def _get_response(self, discord_message: disnake.Message) -> str:
        """Generate a response to a prompt for a conversation of messages.

        A copy of the conversation is made before updating it with the user
        prompt and response to avoid a race condition when multiple people are
        talking to the bot at once.

        Parameters
        ----------
        discord_message : disnake.Message
            The message to generate a response to.
        send_to_dm: bool
            Whether or not the prompt was sent in a direct message, optional

        Returns
        -------
        str
            The response from the AI.

        """
        conversation = self._get_ai_chat_for_id(discord_message)

        # If we are in a guild, we need to get the bot's display name for that
        # guild. Otherwise, we can use the bot's given name.
        # Then we need to remove the bot's name from the message content,
        # otherwise it can get very confused for some reason
        if discord_message.guild:
            bot_user = discord_message.guild.get_member(self.bot.user.id)
            bot_name = bot_user.display_name if bot_user else self.bot.user.name
        else:
            bot_name = self.bot.user.name
        user_prompt = discord_message.clean_content.replace(f"@{bot_name}", "")

        images = await self._get_attached_images_from_message(discord_message)
        videos = await self._get_attached_videos_from_message(discord_message)

        if discord_message.reference:
            referenced_message = await self._get_highlighted_discord_message(discord_message)
            images += await self._get_attached_images_from_message(referenced_message)
            videos += await self._get_attached_videos_from_message(referenced_message)
            user_prompt = (
                'Previous message to respond to with the prompt: "'
                + referenced_message.clean_content
                + '"\nPrompt: '
                + user_prompt
            )

        async with self._lock:
            try:
                message = TextGenerationInput(user_prompt, images=images, videos=videos)
                bot_response = await conversation.send_message(message)
            except GenerationFailureError:
                self.log_warning("Failed to generate response, falling back to markov sentence")
                bot_response = self.get_random_markov_sentence()
                if isinstance(bot_response, list):
                    bot_response = bot_response[0]

        return bot_response

    async def _respond_to_unprompted_message(self, message: disnake.Message) -> None:
        """Respond to a discord message with a random LLM response.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to

        """
        prompt = read_in_prompt("data/prompts/_random-response.yaml")
        chat = self._get_ai_chat_for_id(message)
        content = chat.create_request_json(TextGenerationInput(message.clean_content), system_prompt=prompt.prompt)
        llm_response = await chat.send_raw_request(content)
        await send_message_to_channel(llm_response, message, dont_tag_user=True)

    async def _respond_to_prompted_message(
        self, discord_message: disnake.Message, *, message_in_dm: bool = False
    ) -> None:
        """Respond to a user's message prompt.

        This method handles user prompts by checking for rate limits,
        sending responses, and logging response time if profiling is enabled.

        Parameters
        ----------
        discord_message : disnake.Message
            The Discord message containing the user's prompt.
        message_in_dm : bool, optional
            Whether the prompt was sent in a direct message (default is False).

        """
        self._start_profiler()
        async with discord_message.channel.typing():
            on_cooldown = self._check_if_user_on_cooldown(discord_message.author.id)
            if on_cooldown:
                await send_message_to_channel(
                    f"Stop abusing me {discord_message.author.mention}!",
                    discord_message,
                    dont_tag_user=True,
                )
            else:
                response = await self._get_response(discord_message)
                await send_message_to_channel(
                    response,
                    discord_message,
                    dont_tag_user=message_in_dm,
                )
        self._stop_profiler()

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def _append_to_history(self, message: disnake.Message) -> None:
        if message.type in [disnake.MessageType.application_command]:
            return
        if not message.content:
            return

        clean_message = message.clean_content.replace(f"@{self.bot.user.name}", "[directed at me]")
        for user in message.mentions:
            clean_message = clean_message.replace(f"@{user.name}", f"[directed at {user.display_name}]")

        channel_history = self._get_ai_summary_for_id(message)
        channel_history.add_message_to_history(
            SummaryMessage(
                user=message.author.display_name if message.author != self.bot.user else "me",
                content=clean_message,
            )
        )

    @commands.Cog.listener("on_message")
    async def _listen_for_prompts(self, message: disnake.Message) -> None:
        if message.author.bot:
            return

        # Don't respond to replies, or mentions, which have a reference to a
        # slash command response or interaction UNLESS explicitly mentioned with
        # an @
        mentioned_in_message = self.bot.user.mention in message.content
        if await is_reply_to_slash_command_response(message) and not mentioned_in_message:
            return

        bot_mentioned = self.bot.user in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            await self._respond_to_prompted_message(message, message_in_dm=message_in_dm)
            return

        if random.random() < BotSettings.cogs.artificial_intelligence.random_response_chance:
            await self._respond_to_unprompted_message(message)

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(
        name="generate_chat_summary",
        description="Generate a summary of the conversation",
        dm_permission=False,
    )
    async def chat_generate_summary(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Summarize the chat history.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction object representing the user's command interaction.

        """
        channel_history = self._get_ai_summary_for_id(inter)
        if len(channel_history) == 0:
            await inter.response.send_message("There are no messages to summarise.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        summary = await channel_history.generate_summary(requesting_user=inter.user.display_name)
        await inter.delete_original_response()
        await send_message_to_channel(summary, inter)

    @slash_command_with_cooldown(name="reset_chat_history", description="Reset the AI conversation history")
    async def chat_reset_context(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        chat = self._get_ai_chat_for_id(inter)
        chat.reset_history()
        await inter.response.send_message(
            f"Conversation history has been reset with prompt: {shorten(chat.system_prompt, 1500)}", ephemeral=True
        )

    @slash_command_with_cooldown(
        name="select_chat_prompt",
        description="Set the AI conversation prompt from a list of pre-made prompts",
    )
    async def chat_select_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt_name: str = commands.Param(
            autocomplete=lambda _, user_input: [
                choice for choice in slashbot.watchers.AVAILABLE_LLM_PROMPTS if user_input in choice
            ],
            description="The name of the prompt to use",
        ),
    ) -> None:
        """Select a system prompt from a set of pre-defined prompts.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        prompt_name : str
            The name of the system prompt to use

        """
        try:
            prompt = slashbot.watchers.AVAILABLE_LLM_PROMPTS[prompt_name]
        except KeyError:
            await inter.response.send_message(
                "You probably meant to use /set_custom_chat_prompt instead of this command."
            )
            return

        chat = self._get_ai_chat_for_id(inter)
        chat.set_system_prompt(prompt, prompt_name=prompt_name)
        self.log_info("%s set new prompt [%s]: %s", inter.author.display_name, prompt_name, prompt)

        await inter.response.send_message(
            f"Conversation history been reset and system prompt set to:\n> {shorten(prompt, 1500)}", ephemeral=True
        )

    @slash_command_with_cooldown(name="set_chat_model", description="Set the AI model to use")
    async def chat_set_model(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model_name: str = commands.Param(choices=SUPPORTED_MODELS, description="The model to use"),  # type: ignore
    ) -> None:
        """Set the AI model to use.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        model_name : str
            The name of the model to set.

        """
        await inter.response.defer(ephemeral=True)

        chat = self._get_ai_chat_for_id(inter)
        summary = self._get_ai_summary_for_id(inter)
        original_model = chat.model
        chat.set_model(model_name)
        summary.set_model(model_name)
        self.log_info("%s set new model: %s", inter.author.display_name, model_name)

        await inter.edit_original_response(
            content=f"LLM model updated from {original_model} to {model_name}.",
        )

    @slash_command_with_cooldown(
        name="set_custom_chat_prompt", description="Change the AI conversation prompt to one you write"
    )
    async def chat_set_custom_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to set", max_length=1950),
    ) -> None:
        """Set a new system message for the location were the interaction came from.

        This typically does not override the default system message, and will
        append a new system message.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        prompt : str
            The new system prompt to set.

        """
        chat = self._get_ai_chat_for_id(inter)
        chat.set_system_prompt(prompt)
        self.log_info("%s set new prompt: %s", inter.author.display_name, prompt)

        await inter.response.send_message(
            f"Conversation history been reset and system prompt set to:\n> {shorten(prompt, 1500)}", ephemeral=True
        )

    @slash_command_with_cooldown(
        name="show_chat_prompt", description="Print information about the current AI conversation"
    )
    async def chat_show_prompt(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Print the system prompt to the screen.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        chat = self._get_ai_chat_for_id(inter)
        response = f"**Model**: {chat.model}\n"
        response += f"**Token size**: {chat.size_tokens}\n"
        response += f"**Prompt [*{chat.system_prompt_name}*]**:\n> {shorten(chat.system_prompt, 1500)}\n"

        await inter.response.send_message(response, ephemeral=True)


def setup(bot: CustomInteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    try:
        bot.add_cog(ArtificialIntelligence(bot))
    except:  # noqa: E722
        bot.log_error("Failed to initialise ArtificialIntelligence cog, probably due to a missing API key")
