"""AI chat and text-to-image features.

The purpose of this cog is to enable AI features in the Discord chat. This
currently implements AI chat/vision using ChatGPT and Claude, as well as
text-to-image generation using Monster API.
"""

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
from slashbot.core import markov
from slashbot.core.channel_summary import AIChannelSummary, SummaryMessage
from slashbot.core.conversation import AIConversation
from slashbot.core.custom_bot import CustomInteractionBot
from slashbot.core.custom_cog import CustomCog
from slashbot.core.custom_command import slash_command_with_cooldown
from slashbot.core.custom_types import ApplicationCommandInteraction, Message
from slashbot.messages import get_attached_images_from_message, send_message_to_channel
from slashbot.prompts import read_in_prompt_json
from slashbot.responses import is_reply_to_slash_command_response
from slashbot.settings import BotConfig

MAX_MESSAGE_LENGTH = BotConfig.get_config("MAX_CHARS")


@dataclass
class Cooldown:
    """Dataclass for tracking cooldowns for a user."""

    count: int
    last_interaction: datetime.datetime


def get_history_id(obj: Message | ApplicationCommandInteraction) -> str | int:
    """Determine the history ID to use given the origin of the message.

    Historically, this used to return different values for text channels and
    direct messages.

    Parameters
    ----------
    obj
        The Disnake object to get the history ID from.

    Returns
    -------
    int
        The ID to use for history purposes.

    """
    return obj.channel.id


class TextGeneration(CustomCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: CustomInteractionBot) -> None:
        """Initialize the AIChatbot class.

        Parameters
        ----------
        bot : SlashbotInterationBot
            The instance of the SlashbotInterationBot class.

        """
        super().__init__(bot)
        self.ai_conversations = {}
        self.channel_histories = defaultdict(lambda: AIChannelSummary())
        self.user_cooldown_map = defaultdict(lambda: Cooldown(0, datetime.datetime.now(tz=datetime.UTC)))

        self._lock = asyncio.Lock()
        self._profiler = Profiler(async_mode="enabled")
        file_handler = logging.FileHandler("logs/ai_chat_profile.log")
        file_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
        self._profiler_logger = logging.getLogger("ProfilerLogger")
        self._profiler_logger.handlers.clear()
        self._profiler_logger.addHandler(file_handler)

    def _start_profiler(self) -> None:
        if not BotConfig.get_config("AI_CHAT_PROFILE_RESPONSE_TIME"):
            return
        if self._profiler.is_running:
            self._profiler.stop()
            self._profiler.reset()
        self._profiler.start()

    def _stop_profiler(self) -> None:
        if not BotConfig.get_config("AI_CHAT_PROFILE_RESPONSE_TIME"):
            return
        self._profiler.stop()
        profiler_output = self._profiler.output_text()
        self._profiler_logger.info("\n%s", profiler_output)
        self._profiler.reset()

    def _get_channel_history(self, obj: Message | ApplicationCommandInteraction) -> AIChannelSummary:
        history_id = get_history_id(obj)
        return self.channel_histories.setdefault(
            history_id,
            AIChannelSummary(
                token_window_size=BotConfig.get_config("AI_CHAT_TOKEN_WINDOW_SIZE"), extra_print=f"{obj.channel.name}"
            ),
        )

    async def _get_conversation(self, obj: int | Message | ApplicationCommandInteraction) -> AIConversation:
        history_id = get_history_id(obj) if not isinstance(obj, int) else obj
        self.log_debug("Getting conversation for history ID: %s", history_id)

        if history_id in self.ai_conversations:
            return self.ai_conversations[history_id]

        self.ai_conversations[history_id] = AIConversation(
            token_window_size=BotConfig.get_config("AI_CHAT_TOKEN_WINDOW_SIZE"),
            extra_print=f"{obj.channel.name}",
        )
        return self.ai_conversations[history_id]

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
        if user_cooldown.count > BotConfig.get_config("AI_CHAT_RATE_LIMIT"):
            # If exceeded rate limit, check if cooldown period has passed
            if time_difference > BotConfig.get_config("AI_CHAT_RATE_INTERVAL"):
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
            markov.generate_text_from_markov_chain(markov.MARKOV_MODEL, "?random", 1),
            message,
            dont_tag_user=dont_tag_user,  # In a DM, we won't @ the user
        )

    async def _reset_conversation_history(self, history_id: str | int) -> None:
        """Clear chat history and reset the token counter.

        Parameters
        ----------
        history_id : str | int
            The index to reset in chat history.

        """
        conversation = await self._get_conversation(history_id)
        conversation.reset_history()

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
        previous_message = message_reference.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                previous_message = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return original_message

        return previous_message

    async def _get_response_from_llm(self, discord_message: disnake.Message) -> None:
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

        """
        conversation = await self._get_conversation(discord_message)
        user_prompt = discord_message.clean_content.replace(f"@{self.bot.user.name}", "")
        images = await get_attached_images_from_message(discord_message)

        if discord_message.reference:
            referenced_message = await self._get_highlighted_discord_message(discord_message)
            images += await get_attached_images_from_message(referenced_message)
            user_prompt = (
                'Previous message to respond to with the prompt: "'
                + referenced_message.clean_content
                + '"\nPrompt: '
                + user_prompt
            )

        try:
            bot_response = await conversation.send_message(user_prompt, images)
        except:
            self.log_exception("Failed to get response from AI, reverting to markov sentence")
            bot_response = self.get_random_markov_sentence()

        return bot_response

    async def _respond_with_random_llm_response(self, message: disnake.Message) -> None:
        """Respond to a discord message with a random LLM response.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to

        """
        prompt = read_in_prompt_json("data/prompts/_random-response-prompt.json")
        messages = [
            {"role": "system", "content": prompt["prompt"]},
            {"role": "user", "content": message.clean_content},
        ]
        conversation = await self._get_conversation(message)
        response = await conversation.generate_text_from_llm(messages)
        await send_message_to_channel(response.message, message, dont_tag_user=True)

    async def _respond_to_user_prompt(self, discord_message: disnake.Message, *, message_in_dm: bool = False) -> None:
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
                response = await self._get_response_from_llm(discord_message)
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

        clean_message = message.clean_content.replace(f"@{self.bot.user.name}", "[directed at me]")
        for user in message.mentions:
            clean_message = clean_message.replace(f"@{user.name}", f"[directed at {user.display_name}]")

        channel_history = self._get_channel_history(message)
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
            await self._respond_to_user_prompt(message, message_in_dm=message_in_dm)
            return

        if random.random() < BotConfig.get_config("AI_CHAT_RANDOM_RESPONSE_CHANCE"):
            await self._respond_with_random_llm_response(message)

    # Commands -----------------------------------------------------------------

    @slash_command_with_cooldown(
        name="summarise_chat_history",
        description="Get a summary of the previous conversation",
        dm_permission=False,
    )
    async def generate_chat_summary(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Summarize the chat history.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction object representing the user's command interaction.

        """
        channel_history = self._get_channel_history(inter)
        if len(channel_history) == 0:
            await inter.response.send_message("There are no messages to summarise.", ephemeral=True)
            return
        await inter.response.defer(with_message="Generating summary...", ephemeral=True)
        summary = await channel_history.generate_summary(requesting_user=inter.user.display_name)
        await inter.delete_original_response()
        await send_message_to_channel(summary, inter)

    @slash_command_with_cooldown(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_conversation_history(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        await self._reset_conversation_history(get_history_id(inter))
        await inter.response.send_message("Conversation history cleared.", ephemeral=True)

    @slash_command_with_cooldown(
        name="select_chat_prompt",
        description="Set the AI conversation prompt from a list of choices",
    )
    async def select_existing_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        choice: str = commands.Param(
            autocomplete=lambda _, user_input: [
                choice for choice in slashbot.watchers.AVAILABLE_LLM_PROMPTS if user_input in choice
            ],
            description="The choice of prompt to use",
        ),
    ) -> None:
        """Select a system prompt from a set of pre-defined prompts.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        choice : str
            The choice of system prompt

        """
        prompt = slashbot.watchers.AVAILABLE_LLM_PROMPTS[choice]
        self.log_info("%s set new prompt: %s", inter.author.display_name, prompt)
        conversation = await self._get_conversation(inter)
        conversation.set_system_message(prompt)
        await inter.response.send_message("History cleared and system message updated", ephemeral=True)

    @slash_command_with_cooldown(
        name="set_chat_prompt", description="Change the AI conversation prompt to one you write"
    )
    async def set_chat_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to set", max_length=2000),
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
        self.log_info("%s set new prompt: %s", inter.author.display_name, prompt)
        conversation = await self._get_conversation(inter)
        conversation.set_system_message(prompt)
        await inter.response.send_message("History cleared and system prompt updated", ephemeral=True)

    @slash_command_with_cooldown(
        name="show_chat_prompt", description="Print information about the current AI conversation"
    )
    async def show_chat_prompt(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Print the system prompt to the screen.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.

        """
        conversation = await self._get_conversation(inter)

        prompt_name = "Unknown"
        prompt = conversation.system_prompt
        for name, text in slashbot.watchers.AVAILABLE_LLM_PROMPTS.items():
            if prompt == text:
                prompt_name = name

        response = ""
        response += f"**Model name**: {conversation.model}\n"
        response += f"**Token usage**: {conversation.tokens}\n"
        response += f"**Prompt name**: {prompt_name}\n"
        response += f"**Prompt**: {shorten(prompt, 1800)}\n"

        await inter.response.send_message(response, ephemeral=True)


def setup(bot: commands.InteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.

    """
    if BotConfig.get_config("OPENAI_API_KEY"):
        bot.add_cog(TextGeneration(bot))
    else:
        TextGeneration.log_error(TextGeneration, "No API key found for OpenAI, unable to load AIChatBot cog")
