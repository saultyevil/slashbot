import logging
import random
from textwrap import shorten

import disnake
from disnake.ext import commands
from pyinstrument import Profiler

import slashbot.watchers
from slashbot.ai import SUPPORTED_MODELS, GenerationFailureError
from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.cogs.chatbot.chat_registry import ChatRegistry
from slashbot.cogs.chatbot.response_generator import ResponseGenerator
from slashbot.errors import deferred_error_response
from slashbot.messages import is_reply_to_slash_command_response, send_message_to_channel
from slashbot.settings import BotSettings


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
        self._chat_registry = ChatRegistry()
        self._responder = ResponseGenerator(self._chat_registry, bot)
        self._profiler = Profiler(async_mode="enabled")

        file_handler = logging.FileHandler("logs/profile.log")
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
        self._profiler_logger = logging.getLogger("ProfilerLogger")
        self._profiler_logger.handlers.clear()
        self._profiler_logger.addHandler(file_handler)
        self._profiler_logger.setLevel(logging.INFO)

    def _start_profiler(self) -> None:
        """Start the pyinstrument profiler if profiling is enabled.

        Resets any previously running session before starting a new one.
        Has no effect when BotSettings.cogs.chatbot.enable_profiling is
        False.
        """
        if not BotSettings.cogs.chatbot.enable_profiling:
            return
        if self._profiler.is_running:
            self._profiler.stop()
            self._profiler.reset()
        self._profiler.start()

    def _stop_profiler(self) -> None:
        """Stop the profiler and write its output to the profile log."""
        if not BotSettings.cogs.chatbot.enable_profiling:
            return
        if not self._profiler.is_running:
            self.log_error("Attempted to stop the profiler when it's not running -- resetting profiler")
            self._profiler.reset()
            return
        self._profiler.stop()
        self._profiler_logger.info("\n%s", self._profiler.output_text())
        self._profiler.reset()

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def _append_message_to_history(self, message: disnake.Message) -> None:
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
        self._chat_registry.append_to_history(message, self.bot.user.name)

    @commands.Cog.listener("on_message")
    async def _listen_for_prompts(self, message: disnake.Message) -> None:
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
            self._start_profiler()
            await self._responder.respond_to_prompted(message, message_in_dm=message_in_dm)
            self._stop_profiler()
            return

        if random.random() < BotSettings.cogs.chatbot.random_response_chance:
            await self._responder.respond_to_unprompted(message)

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(
        name="generate_chat_summary",
        description="Generate a summary of the conversation",
        contexts=disnake.InteractionContextTypes(guild=True),
    )
    async def create_chat_summary(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Summarise the recent channel conversation using the current LLM.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        history = self._chat_registry.get_summary(inter)
        if len(history) == 0:
            await inter.response.send_message("There are no messages to summarise.", ephemeral=True)
            return
        await inter.response.defer(ephemeral=True)
        try:
            summary = await history.generate_summary(requesting_user=None)
        except GenerationFailureError:
            await deferred_error_response(inter, "There was an error trying to generate the summary")
            return
        await inter.delete_original_response()
        await send_message_to_channel(summary, inter)

    @slash_command_with_cooldown(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_conversation(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clear the AI conversation history for the current channel.

        The system prompt is preserved; only the message history is reset.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        chat = self._chat_registry.get_chat(inter)
        chat.reset_history()
        await inter.response.send_message(
            f"Conversation history has been reset with prompt: {shorten(chat.system_prompt, 1500)}",
            ephemeral=True,
        )

    @slash_command_with_cooldown(
        name="select_chat_prompt",
        description="Set the AI conversation prompt from a list of pre-made prompts",
    )
    async def select_existing_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt_name: str = commands.Param(
            autocomplete=lambda _, user_input: [c for c in slashbot.watchers.AVAILABLE_LLM_PROMPTS if user_input in c],
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
        try:
            prompt = slashbot.watchers.AVAILABLE_LLM_PROMPTS[prompt_name]
        except KeyError:
            await inter.response.send_message(
                "You probably meant to use /set_custom_chat_prompt instead of this command."
            )
            return
        chat = self._chat_registry.get_chat(inter)
        chat.set_chat_prompt(prompt, prompt_name=prompt_name)
        self.log_info("%s set new prompt [%s]: %s", inter.author.display_name, prompt_name, prompt)
        await inter.response.send_message(
            f"Conversation history been reset and system prompt set to:\n> {shorten(prompt, 1500)}",
            ephemeral=True,
        )

    @slash_command_with_cooldown(name="set_chat_model", description="Set the AI model to use")
    async def set_model(
        self,
        inter: disnake.ApplicationCommandInteraction,
        model_name: str = commands.Param(choices=SUPPORTED_MODELS, description="The model to use"),
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
        chat = self._chat_registry.get_chat(inter)
        summary = self._chat_registry.get_summary(inter)
        original_model = chat.model
        chat.set_model(model_name)
        summary.set_model(model_name)
        self.log_info("%s set new model: %s", inter.author.display_name, model_name)
        await inter.edit_original_response(content=f"LLM model updated from {original_model} to {model_name}.")

    @slash_command_with_cooldown(
        name="set_custom_chat_prompt",
        description="Change the AI conversation prompt to one you write",
    )
    async def set_custom_prompt(
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
        chat = self._chat_registry.get_chat(inter)
        chat.set_chat_prompt(prompt)
        self.log_info("%s set new prompt: %s", inter.author.display_name, prompt)
        await inter.response.send_message(
            f"Conversation history been reset and system prompt set to:\n> {shorten(prompt, 1500)}",
            ephemeral=True,
        )

    @slash_command_with_cooldown(
        name="show_chat_prompt",
        description="Print information about the current AI conversation",
    )
    async def show_prompt(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Display the current model, token usage, and system prompt.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        chat = self._chat_registry.get_chat(inter)
        response = (
            f"**Model**: {chat.model}\n"
            f"**Token size**: {chat.size_tokens}\n"
            f"**Prompt [*{chat.system_prompt_name}*]**:\n> {shorten(chat.system_prompt, 1500)}\n"
        )
        await inter.response.send_message(response, ephemeral=True)
