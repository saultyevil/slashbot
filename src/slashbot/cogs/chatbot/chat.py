import datetime
from dataclasses import dataclass, field
from typing import Any

from slashbot.llm import LLM, InputRole, TextGenerationInput, TextGenerationResponse, TextInput, load_prompt
from slashbot.logger import Logger
from slashbot.settings import BotSettings

SETTINGS = BotSettings.cogs.chatbot
DEFAULT_SYSTEM_PROMPT = load_prompt(SETTINGS.default_chat_prompt)
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
class Messages:
    """Dataclass for storing messages."""

    tokens: int = 0
    messages: list[TextGenerationInput] = field(default_factory=list)

    def __add__(self, content: TextGenerationInput) -> list[TextGenerationInput]:
        return [*self.messages, content]

    def __len__(self) -> int:
        return len(self.messages)

    def __str__(self) -> str:
        return f"Messages(tokens={self.tokens} messages={self.messages})"

    def __getitem__(self, index: int) -> TextGenerationInput:
        return self.messages[index]

    def append_message(self, content: TextGenerationInput, num_tokens: int) -> None:
        """Append a new message.

        Parameters
        ----------
        content : TextGenerationInput
            The content of the new message to append.
        num_tokens : int
            The number of tokens the message is.

        """
        self.tokens += num_tokens
        content.tokens = num_tokens
        self.messages.append(content)

    def clear_messages(self) -> None:
        """Clear all the messages."""
        self.messages = []

    def remove_message(self, index: int) -> TextGenerationInput:
        """Remove a message.

        Parameters
        ----------
        index : int
            The index of the message to remove.

        Returns
        -------
        TextGenerationInput
            The message which has been removed.

        """
        message = self.messages.pop(index)
        self.tokens -= message.tokens

        return message


class Chat(Logger):
    """Chat object for having a conversation with an LLM."""

    SUPPORTED_MODELS = LLM.SUPPORTED_MODELS

    def __init__(self, chat_id: str, model: str, system_prompt: str | None = None, **kwargs: Any) -> None:
        """Create an LLM chat."""
        super().__init__(**kwargs)

        system_prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT.prompt

        self.chat_id: str = chat_id
        self.llm: LLM = LLM(model, USER_CONVERSATION_CONTEXT_PROMPT + system_prompt)
        self.messages: Messages = Messages()

    def __len__(self) -> int:
        return len(self.messages)

    @property
    def model(self) -> str:
        """The model used for the chat."""
        return self.llm.model

    @property
    def provider(self) -> str:
        """The name of the model provider."""
        return self.llm.provider

    @property
    def system_prompt(self) -> str:
        """The system prompt for the chat."""
        return self.llm.system_prompt if self.llm.system_prompt else ""

    @property
    def tokens(self) -> int:
        """The size of the chat in tokens."""
        return self.messages.tokens

    @property
    def size(self) -> int:
        """The number of messages in the chat."""
        return len(self.messages)

    async def _count_tokens_in_chat(self) -> None:
        """Count the number of tokens in the chat."""
        for message in self.messages:
            if self.messages.tokens == 0:
                await message.count_tokens(self.llm)

    def shrink_messages_to_token_window(self) -> None:
        """Remove messages which take the chat over the context window."""
        if self.tokens <= SETTINGS.token_window_size:
            return

        tokens_removed = 0
        messages_removed = 0
        while self.tokens > SETTINGS.token_window_size and len(self) > 2:
            for _ in range(2):
                message = self.messages.remove_message(0)
                tokens_removed += message.tokens
            messages_removed += 2

        self.log_debug("Removed %d tokens from %d messages in chat %s", tokens_removed, messages_removed, self.chat_id)

    async def chat(self, username: str, content: TextGenerationInput) -> TextGenerationResponse:
        """Respond to a message.

        Parameters
        ----------
        username: str
            The username of the person who sent a message.
        content : TextGenerationInput
            The new message to respond to.

        Returns
        -------
        TextGenerationResponse
            The response to the message.

        """
        self.shrink_messages_to_token_window()
        starting_tokens = self.messages.tokens

        now_ts = datetime.datetime.now(tz=datetime.UTC).strftime("%a %d %b %Y %H:%M:%S %Z")
        content.text.text = f"{username} at {now_ts}: " + content.text.text.strip()

        messages = self.messages + content
        response = await self.llm.generate_response(messages)

        self.messages.append_message(content, response.input_tokens - starting_tokens)
        self.messages.append_message(
            TextGenerationInput(text=TextInput(response.message), role=InputRole.assistant), response.output_tokens
        )

        return response

    def reset(self) -> None:
        """Reset a conversation back to the start."""
        self.messages.clear_messages()

    def set_model(self, model: str) -> None:
        """Change the LLM.

        Parameters
        ----------
        model : str
            The name of the model to use.

        """
        self.llm = LLM(model, self.system_prompt)

    def set_system_prompt(self, system_prompt: str) -> None:
        """Set the system prompt for the chat.

        Parameters
        ----------
        system_prompt : str
            The new system prompt.

        """
        self.llm = LLM(self.model, USER_CONVERSATION_CONTEXT_PROMPT + system_prompt)


class ChatStore:
    """Dataclass for storing Chats."""

    SUPPORTED_MODELS = Chat.SUPPORTED_MODELS

    def __len__(self) -> int:
        return len(self.chats)

    def __str__(self) -> str:
        return f"ChatStore(chats={self.chats})"

    def __getitem__(self, index: str | Any) -> Chat:
        if not isinstance(index, str):
            index = str(index)
        if index not in self.chats:
            self.chats[index] = Chat(index, self.model, self.prompt)

        return self.chats[index]

    def __init__(self, default_model: str, default_prompt: str) -> None:
        """Create a ChatStore for storing multiple chats.

        Parameters
        ----------
        default_model : str
            The default model to use for chats.
        default_prompt : str
            The default system prompt to use for chats.

        """
        self.model: str = default_model
        self.prompt: str = default_prompt
        self.chats: dict[str, Chat] = {}
