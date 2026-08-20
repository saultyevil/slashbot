from typing import Any

from disnake import channel

from slashbot.llm import (
    LLM,
    GenerationFailureError,
    TextGenerationInput,
    TextGenerationResponse,
    TextInput,
    load_prompt,
)
from slashbot.logger import Logger
from slashbot.settings import BotSettings

from .messages import Messages

SETTINGS = BotSettings.cogs.chatbot


class Channel(Logger):
    """Channel class for creating summaries of Discord channels."""

    SUPPORTED_MODELS = LLM.SUPPORTED_MODELS

    def __init__(self, channel_id: str, model: str, **kwargs: Any) -> None:
        """Create a channel summary."""
        super().__init__(**kwargs, prepend_msg=f"[Channel {channel_id}]")

        system_prompt = load_prompt("data/prompts/_summarise.yaml")

        self.channel_id: str = channel_id
        self.llm: LLM = LLM(model, system_prompt=system_prompt.prompt)

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

    def shrink_messages_to_token_window(self) -> None:
        """Remove messages which take the chat over the context window."""
        if self.tokens <= SETTINGS.channel_token_window_size:
            return

        tokens_removed = 0
        messages_removed = 0
        keep_messages = 1
        while self.tokens > SETTINGS.channel_token_window_size and len(self) > keep_messages:
            for _ in range(2):
                message = self.messages.remove_message(0)
                tokens_removed += message.tokens
            messages_removed += 2

        self.log_info("Removed %d tokens from %d messages", tokens_removed, messages_removed)

    async def append_message(self, content: TextGenerationInput) -> None:
        """Append a new message.

        Parameters
        ----------
        content : TextGenerationInput
            The message to add.

        """
        tokens = await self.llm.count_tokens(content)
        self.messages.append_message(content, tokens)
        self.shrink_messages_to_token_window()

    async def summarise(self) -> TextGenerationResponse:
        """Summarise the messages.

        Returns
        -------
        TextGenerationResponse
            The response from the LLM.

        """
        content = ""
        for message in self.messages:
            content += f"{message.text}\n"
        try:
            response = await self.llm.generate_response(TextGenerationInput(TextInput(content)))
        except GenerationFailureError:
            return TextGenerationResponse(
                message="Failed to generate a channel summary", tokens_used=0, input_tokens=0, output_tokens=0
            )

        return response


class Channels(Logger):
    """Dataclass for storing Chats."""

    SUPPORTED_MODELS = Channel.SUPPORTED_MODELS

    def __len__(self) -> int:
        return len(self.channels)

    def __str__(self) -> str:
        return f"Channels(channels={self.channels})"

    def __getitem__(self, index: str | Any) -> Channel:
        if not isinstance(index, str):
            index = str(index)
        if index not in self.channels:
            self.channels[index] = Channel(index, self.model)

        self.log_debug("Retrived channel %s", index)

        return self.channels[index]

    def __init__(self, default_model: str, **kwargs: Any) -> None:
        """Create a ChatStore for storing multiple chats.

        Parameters
        ----------
        default_model : str
            The default model to use for chats.
        default_prompt : str
            The default system prompt to use for chats.
        kwargs : Any
            Key word arguments.

        """
        super().__init__(**kwargs, prepend_msg="[ChatStore]")

        self.model: str = default_model
        self.channels: dict[str, Channel] = {}
