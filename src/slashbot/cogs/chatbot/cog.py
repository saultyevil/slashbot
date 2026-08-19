import asyncio
import contextlib
import datetime
import logging
from collections.abc import Callable
from pathlib import Path
from textwrap import shorten
from typing import Any

import disnake
from disnake.ext import commands
from pyinstrument import Profiler

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.llm import ImageInput, TextGenerationInput, TextInput, VideoInput, load_prompt
from slashbot.messages import is_reply_to_slash_command_response, send_message_to_channel
from slashbot.settings import BotSettings

from .channel import Channels
from .chat import Chats

file_handler = logging.FileHandler("logs/profile.log")
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
_profiler_logger = logging.getLogger("ProfilerLogger")
_profiler_logger.handlers.clear()
_profiler_logger.addHandler(file_handler)
_profiler_logger.setLevel(logging.INFO)
_profiler = Profiler(async_mode="enabled")


_PROMPTS_LIST = [load_prompt(path) for path in Path("data/prompts").glob("*.yaml") if not str(path).startswith("_")]
AVAILABLE_PROMPTS = {prompt.name: prompt.path for prompt in _PROMPTS_LIST}


def _start_profiler() -> None:
    """Start the pyinstrument profiler if profiling is enabled.

    Resets any previously running session before starting a new one.
    Has no effect when BotSettings.cogs.chatbot.enable_profiling is
    False.
    """
    if not BotSettings.cogs.chatbot.enable_profiling:
        return
    if _profiler.is_running:
        _profiler.stop()
        _profiler.reset()
    _profiler.start()


def _stop_profiler() -> None:
    """Stop the profiler and write its output to the profile log."""
    if not BotSettings.cogs.chatbot.enable_profiling:
        return
    if not _profiler.is_running:
        _profiler.reset()
        return
    _profiler.stop()
    _profiler_logger.info("\n%s", _profiler.output_text())
    _profiler.reset()


def profile_response(func: Callable) -> Callable:
    """Profile function execution using pyinstrument."""

    def _profile(*args: Any, **kwargs: dict[str, Any]) -> Any:
        _start_profiler()
        ret = func(*args, **kwargs)
        _stop_profiler()

        return ret

    return _profile


class ChatBot(CustomCog):
    """AI chatbot cog for Discord."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialise the cog.

        Parameters
        ----------
        bot : CustomInteractionBot
            The running bot instance.

        """
        super().__init__(bot)

        default_prompt = load_prompt(BotSettings.cogs.chatbot.default_chat_prompt)
        self.chats = Chats(BotSettings.cogs.chatbot.default_model, default_prompt.prompt)
        self.channels = Channels(BotSettings.cogs.chatbot.default_model)

        self._lock = asyncio.Lock()

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def track_channel_message(self, message: disnake.Message) -> None:
        """Record an incoming message in the channel's conversation history.

        Application command messages and messages with no text content are
        ignored.

        Parameters
        ----------
        message : disnake.Message
            The Discord message received by the on_message event.

        """
        if message.type in [disnake.MessageType.application_command]:
            return
        if not message.content:
            return

        now_ts = datetime.datetime.now(tz=datetime.UTC).strftime("%a %d %b %Y %H:%M:%S %Z")
        content = f"{message.author.display_name} {now_ts}: {message.clean_content}"

        await self.channels[message.channel.id].append_message(TextGenerationInput(TextInput(content)))
        self.log_debug("XXX REMOVE Added message %s", content)

    @commands.Cog.listener("on_message")
    # @profile_response
    async def send_message_to_chat_assistant(self, message: disnake.Message) -> None:
        """Decide whether and how to respond to an incoming message.

        Ignores messages from bots. Ignores replies to slash command responses
        unless the bot is explicitly mentioned. Responds directly when
        mentioned or messaged in a DM; otherwise responds randomly according to
        BotSettings.cogs.chatbot.random_response_chance.

        Parameters
        ----------
        message : disnake.Message
            The Discord message received by the on_message event.

        """
        if message.author.bot:
            return
        mentioned_in_message = self.bot.user.mention in message.content
        if await is_reply_to_slash_command_response(message) and not mentioned_in_message:
            return

        bot_mentioned = self.bot.user in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            input_from_message = TextGenerationInput(
                text=await self.get_text_in_message(message),
                images=await self.get_images_in_message(message),
                videos=await self.get_videos_in_message(message),
            )
            if message.reference:
                referenced_message = await self.get_referenced_message(message)
                if referenced_message != message:
                    text_input_for_reference = await self.get_text_in_message(referenced_message)
                    text_input_for_reference.text = (
                        f'Previous message to respond to: "{text_input_for_reference.text}"\n'
                    )
                    input_from_message = (
                        TextGenerationInput(
                            text=text_input_for_reference,
                            images=await self.get_images_in_message(referenced_message),
                            videos=await self.get_videos_in_message(referenced_message),
                        )
                        + input_from_message
                    )
            async with self._lock:
                response = await self.chats[message.channel.id].chat(message.author.display_name, input_from_message)

            await send_message_to_channel(response.message, message)

    # Methods

    async def get_referenced_message(self, message: disnake.Message) -> disnake.Message:
        """Fetch the message referenced by a reply, falling back to the original.

        Attempts to use the cached reference first; if unavailable, fetches
        the message from the Discord API. Returns message unchanged if the
        reference cannot be resolved.

        Parameters
        ----------
        message : disnake.Message
            The message that contains a reply reference.

        Returns
        -------
        disnake.Message
            The referenced message, or message itself if resolution fails.

        """
        message_reference = message.reference
        if not message_reference:
            return message
        previous_message = message_reference.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                    return message
                if not message_reference.message_id:
                    return message
                previous_message = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return message

        return previous_message

    async def get_text_in_message(self, message: disnake.Message) -> TextInput:
        """Extract text from a Discord message.

        Parameters
        ----------
        message : Message
            The Discord message to inspect for image content.

        Returns
        -------
        TextInput
            An instance of a TextInput containing the text content of the
            message.

        """
        return TextInput(message.clean_content.replace(f"@{self.bot.user.display_name}", ""))

    async def get_images_in_message(self, message: disnake.Message) -> list[ImageInput]:
        """Extract image attachments and embeds from a Discord message.

        When BotSettings.cogs.chatbot.prefer_image_urls is False, each
        image is downloaded and base64-encoded in place. Failures are
        ignored so that a single bad URL does not abort the whole response.

        Parameters
        ----------
        message : Message
            The Discord message to inspect for image content.

        Returns
        -------
        list[ImageInput]
            ImageInput instances for every image attachment or embed found in
            the message.

        """
        image_urls = [a.url for a in message.attachments if a.content_type and a.content_type.startswith("image/")]
        image_urls += [e.url for e in message.embeds if e.type == "image" and e.url]
        images = []
        for url in image_urls:
            image = ImageInput(url)
            if not BotSettings.cogs.chatbot.prefer_image_urls:
                with contextlib.suppress(Exception):
                    await image.download_and_encode()
            images.append(image)

        return images

    async def get_videos_in_message(self, message: disnake.Message) -> list[VideoInput]:
        """Extract YouTube video embeds from a Discord message.

        Only embedded videos are considered; raw video file attachments are
        excluded to avoid the cost of downloading and encoding them.

        Parameters
        ----------
        message : Message
            The Discord message to inspect for video embeds.

        Returns
        -------
        list[VideoInput]
            VideoInput instances for every video embed found in the message.

        """
        urls = [e.url for e in message.embeds if e.type == "video" and e.url]

        return [VideoInput(url) for url in set(urls)]

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(
        name="summarise_channel",
        description="Generate a summary of the messages in the channel",
        contexts=disnake.InteractionContextTypes(guild=True),
    )
    async def summarise_channel(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Summarise the recent channel conversation using the current LLM.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        channel = self.channels[inter.channel.id]
        if len(channel) == 0:
            await inter.response.send_message("There are no messages to summarise.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)

        summary = await channel.summarise()
        await inter.delete_original_response()
        await send_message_to_channel(summary.message, inter)

    @slash_command_with_cooldown(name="reset_chat", description="Reset the history of the chat assistant")
    async def reset_chat(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clear the AI conversation history for the current channel.

        The system prompt is preserved; only the message history is reset.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        chat = self.chats[inter.channel.id]
        chat.reset()
        await inter.response.send_message(
            f"Conversation history has been reset with prompt: {shorten(chat.system_prompt, 1500)}",
            ephemeral=True,
        )

    @slash_command_with_cooldown(
        name="select_chat_prompt",
        description="Select a pre-made system prompt for the chat assistant",
    )
    async def select_chat_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt_name: str = commands.Param(
            choices=sorted(AVAILABLE_PROMPTS.keys(), key=str.lower),
            description="The name of the prompt to use",
        ),
    ) -> None:
        """Set the system prompt from a pre-defined list of named prompts.

        Resets conversation history as a side effect.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        prompt_name : str
            The key of the desired prompt in AVAILABLE_LLM_PROMPTS.

        """
        self.log_debug("Setting prompt to %s", prompt_name)
        self.log_debug("Available prompts %s:", AVAILABLE_PROMPTS)
        try:
            prompt = load_prompt(AVAILABLE_PROMPTS[prompt_name]).prompt  # type: ignore
        except KeyError:
            await inter.response.send_message(
                "You probably meant to use /set_custom_chat_prompt instead of this command."
            )
            return
        chat = self.chats[inter.channel.id]
        chat.set_system_prompt(prompt)
        self.log_info("%s set new prompt [%s]: %s", inter.author.display_name, prompt_name, prompt)
        await inter.response.send_message(
            f"Conversation history been reset and system prompt set to:\n> {shorten(prompt, 1500)}",
            ephemeral=True,
        )

    @slash_command_with_cooldown(name="set_chat_model", description="Set the LLM to use for the chat assistant")
    async def set_chat_model(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model_name: str = commands.Param(choices=Chats.SUPPORTED_MODELS, description="The model to use"),
    ) -> None:
        """Switch the AI model used for both chat and summary generation.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        model_name : str
            The identifier of the model to switch to; must be one of
            SUPPORTED_MODELS.

        """
        await inter.response.defer(ephemeral=True)
        chat = self.chats[inter.channel.id]
        original_model = chat.model
        chat.set_model(model_name)
        self.log_info("%s set new model: %s", inter.author.display_name, model_name)
        await inter.edit_original_response(content=f"LLM model updated from {original_model} to {model_name}.")

    @slash_command_with_cooldown(
        name="set_custom_chat_prompt",
        description="Set a system prompt for the chat assistant",
    )
    async def set_custom_chat_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to set", max_length=1950),
    ) -> None:
        """Set a free-text system prompt for the current channel.

        Resets conversation history as a side effect.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        prompt : str
            The custom system prompt text, up to 1950 characters.

        """
        chat = self.chats[inter.channel.id]
        chat.set_system_prompt(prompt)
        self.log_info("%s set new prompt: %s", inter.author.display_name, prompt)
        await inter.response.send_message(
            f"Conversation history been reset and system prompt set to:\n> {shorten(prompt, 1500)}",
            ephemeral=True,
        )

    @slash_command_with_cooldown(
        name="show_chat_prompt",
        description="Display the current system prompt and other details from the chat assistant",
    )
    async def show_chat_prompt(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Display the current model, token usage, and system prompt.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        chat = self.chats[inter.channel.id]
        response = (
            f"**Model:** {chat.model}\n"
            f"**Token size:** {chat.tokens}\n"
            f"**Prompt:**\n> {shorten(chat.system_prompt, 1500)}\n"
            if chat.system_prompt
            else ""
        )
        await inter.response.send_message(response, ephemeral=True)
