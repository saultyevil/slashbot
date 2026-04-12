from dataclasses import dataclass

import disnake

from slashbot.ai import GenerationFailureError, TextGenerationInput, read_in_prompt
from slashbot.ai.text_generator import TextGenerator
from slashbot.settings import BotSettings

DEFAULT_SYSTEM_PROMPT = read_in_prompt(BotSettings.cogs.chatbot.default_chat_prompt)
USER_CONVERSATION_CONTEXT_PROMPT = """

Each user message is prefixed with their username in the format "Username: message".

Multiple users may be talking simultaneously on different topics. When responding, identify which user sent the most
recent message and respond only to their query. Use the conversation history to maintain context for each user's
individual topic thread. Do not conflate separate users' conversations. Never include a username prefix in your own
responses.

If a user's latest message clearly pivots to engage with another user's topic rather than continuing their own, respond
in the context of the topic they are now discussing. Use common sense to determine whether a message is a continuation
of the user's own thread or a deliberate shift to join another conversation/query/prompt from another user.
""".replace("\n", "")


@dataclass
class SummaryMessage:
    """Dataclass for a message from a text channel."""

    user: str
    content: str
    tokens: int = 0


class AIChatSummary(TextGenerator):
    """Dataclass for generating AI summaries for text channels."""

    SUMMARY_PROMPT = read_in_prompt("data/prompts/_summarise.yaml").prompt

    def __init__(self, *, token_window_size: int = 8096, extra_print: str = "") -> None:
        """Initialise the AI channel summary."""
        extra_print = f"[SummaryObject:{extra_print}] " if extra_print else ""
        super().__init__(extra_print=extra_print)
        self._token_size = 0
        self._token_window_size = token_window_size
        self._history_context = []

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the number of messages in the history.

        Returns
        -------
        int
            The number of messages in the history.

        """
        return len(self._history_context)

    # --------------------------------------------------------------------------

    def _remove_message_from_history_context(self, index: int) -> None:
        removed_message = self._history_context.pop(index)
        self._token_size -= removed_message.tokens

    def _shrink_history_to_token_window_size(self) -> None:
        while self._token_size > self._token_window_size and len(self) > 1:
            self._remove_message_from_history_context(0)

    # --------------------------------------------------------------------------

    def add_message_to_history(self, message: SummaryMessage) -> None:
        """Add a message to the history.

        Parameters
        ----------
        message : disnake.Message
            The message to add

        """
        self._shrink_history_to_token_window_size()
        if message.tokens == 0:
            try:
                message.tokens = self.count_tokens_for_message(message.content)
            except GenerationFailureError:
                message.tokens = len(message.content)
        self._history_context.append(message)

    def get_history(self, *, amount: int = 0) -> list[SummaryMessage]:
        """Get the current history.

        Parameters
        ----------
        amount : int
            The number of messages to return, starting from the end. If <= 0,
            return all messages.

        Returns
        -------
        list[SummaryMessage]
            The current history.

        """
        if amount > 0:
            return self._history_context[-amount:]

        return self._history_context

    async def generate_summary(self, *, requesting_user: str | None = None) -> str:
        """Generate a summary of the current history.

        Parameters
        ----------
        requesting_user : str | None
            The user requesting the summary, to referred to in the summary as
            "you".

        """
        history_message = "Summarise the following conversation between multiple users:\n" + "\n".join(
            [f"{message.user}: {message.content}" for message in self._history_context]
        )
        if requesting_user:
            history_message += (
                f".\nPlease refer to me, {requesting_user}, as 'you' in the summary like we were having a conversation."
            )
        request = self.create_request_json(TextGenerationInput(history_message), system_prompt=self.SUMMARY_PROMPT)
        response = await self.send_response_request(request)

        return response.message


class AIChat(TextGenerator):
    """AI Conversation class for an LLM chatbot."""

    def __init__(
        self, *, system_prompt: str | None = None, prompt_name: str = "unset name", extra_print: str | None = None
    ) -> None:
        """Initialise a conversation, with default values.

        Parameters
        ----------
        system_prompt : str, optional
            The system prompt of the conversation. If not provided, the default
            system prompt is used.
        prompt_name : str
            The name of the system prompt for the conversation. If not provided,
            the default system prompt name is used.
        extra_print : str, optional
            Additional information to print at the start of the log message.

        """
        extra_print = f"[ChatObject:{extra_print}] " if extra_print else ""
        super().__init__(extra_print=extra_print)

        if system_prompt:
            self.set_chat_prompt(system_prompt, prompt_name=prompt_name)

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return self.size_messages

    # --------------------------------------------------------------------------

    def reset_history(self) -> None:
        """Reset the conversation history back to the system prompt."""
        self.set_system_prompt(self.system_prompt, prompt_name=self.system_prompt_name)

    async def send_message(
        self,
        messages: TextGenerationInput | list[TextGenerationInput],
    ) -> str:
        """Add a new message to the conversation history.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.

        Returns
        -------
        str
            The message response from the AI.

        """
        response = await self.generate_response_with_context(messages)
        self._token_size = response.tokens_used

        return response.message

    async def send_raw_request(self, content: list[dict] | dict) -> str:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict] |  dict
            The (correctly) formatted content to send to the API.

        """
        response = await self.send_response_request(content)

        return response.message

    def set_chat_prompt(self, new_prompt: str, *, prompt_name: str = "unset name") -> None:
        """Set the system prompt and clear the conversation.

        Parameters
        ----------
        new_prompt : str
            The new system prompt to set.
        prompt_name : str
            Optional name for the new prompt.

        """
        self.set_system_prompt(new_prompt + USER_CONVERSATION_CONTEXT_PROMPT, prompt_name=prompt_name)


class ChatRegistry:
    """Manages per-channel AIChat and AIChatSummary instances.

    One :class:`~slashbot.ai.AIChat` and one
    :class:`~slashbot.ai.AIChatSummary` are created lazily per Discord channel
    and stored by channel ID.
    """

    def __init__(self) -> None:
        """Initialise empty chat and summary stores."""
        self.chats: dict[int, AIChat] = {}
        self.channel_histories: dict[int, AIChatSummary] = {}

    @staticmethod
    def _context_id(obj: int | disnake.Message | disnake.ApplicationCommandInteraction) -> int:
        """Resolve a context identifier from a Discord object or bare integer.

        Parameters
        ----------
        obj : int or disnake.Message or disnake.ApplicationCommandInteraction
            Source from which to extract the channel ID.

        Returns
        -------
        int
            The channel ID, or ``obj`` itself when already an integer.

        """
        return obj if isinstance(obj, int) else obj.channel.id

    @staticmethod
    def _extra_print(obj: disnake.Message | disnake.ApplicationCommandInteraction) -> str:
        """Build a human-readable label for the channel associated with ``obj``.

        Parameters
        ----------
        obj : disnake.Message or disnake.ApplicationCommandInteraction
            The Discord object whose channel is inspected.

        Returns
        -------
        str
            The channel name for guild text channels, the recipient's name for
            DM channels, or the raw channel ID as a string for all other types.

        """
        if isinstance(obj.channel, disnake.TextChannel):
            return obj.channel.name
        if isinstance(obj.channel, disnake.DMChannel):
            return str(obj.channel.recipient)
        return str(obj.channel.id)

    def get_chat(self, obj: int | disnake.Message | disnake.ApplicationCommandInteraction) -> AIChat:
        """Retrieve or create the :class:`~slashbot.ai.AIChat` for a channel.

        Parameters
        ----------
        obj : int or disnake.Message or disnake.ApplicationCommandInteraction
            Used to determine the channel ID. When an ``int`` is passed, the
            chat must already exist in the store.

        Returns
        -------
        AIChat
            The existing or newly created chat instance for the channel.

        Raises
        ------
        ValueError
            If ``obj`` is an ``int`` and no chat has been registered for that
            ID yet.

        """
        cid = self._context_id(obj)
        if cid not in self.chats:
            if isinstance(obj, int):
                msg = "No AIChat found for this ID"
                raise ValueError(msg)
            self.chats[cid] = AIChat(
                system_prompt=DEFAULT_SYSTEM_PROMPT.prompt,
                prompt_name=DEFAULT_SYSTEM_PROMPT.name,
                extra_print=self._extra_print(obj),
            )
        return self.chats[cid]

    def get_summary(self, obj: int | disnake.Message | disnake.ApplicationCommandInteraction) -> AIChatSummary:
        """Retrieve or create the :class:`~slashbot.ai.AIChatSummary` for a channel.

        Parameters
        ----------
        obj : int or disnake.Message or disnake.ApplicationCommandInteraction
            Used to determine the channel ID. When an ``int`` is passed, the
            summary must already exist in the store.

        Returns
        -------
        AIChatSummary
            The existing or newly created summary instance for the channel.

        Raises
        ------
        ValueError
            If ``obj`` is an ``int`` and no summary has been registered for
            that ID yet.

        """
        cid = self._context_id(obj)
        if cid not in self.channel_histories:
            if isinstance(obj, int):
                msg = "No AIChatSummary found for this ID"
                raise ValueError(msg)
            self.channel_histories[cid] = AIChatSummary(
                token_window_size=BotSettings.cogs.chatbot.token_window_size,
                extra_print=self._extra_print(obj),
            )
        return self.channel_histories[cid]

    def append_to_history(self, message: disnake.Message, bot_name: str) -> None:
        """Append a Discord message to the channel's conversation history.

        Bot and user mentions are replaced with readable labels before the
        content is stored.

        Parameters
        ----------
        message : disnake.Message
            The incoming Discord message to record.
        bot_name : str
            The bot's current display name, used to identify bot-authored
            messages and to replace ``@bot`` mentions in the content.

        """
        clean = message.clean_content.replace(f"@{bot_name}", "[directed at me]")
        for user in message.mentions:
            clean = clean.replace(f"@{user.name}", f"[directed at {user.display_name}]")
        summary = self.get_summary(message)
        summary.add_message_to_history(
            SummaryMessage(
                user=message.author.display_name if message.author.name != bot_name else "me",
                content=clean,
            )
        )
