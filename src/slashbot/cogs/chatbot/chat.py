from dataclasses import dataclass, field
from typing import Any

from slashbot.llm import LLM, InputRole, TextGenerationInput, TextGenerationResponse, TextInput, load_prompt
from slashbot.logger import Logger
from slashbot.settings import BotSettings

DEFAULT_SYSTEM_PROMPT = load_prompt(BotSettings.cogs.chatbot.default_chat_prompt)
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
        self.messages.append(content)


class Chat(Logger):
    """Chat object for having a conversation with an LLM."""

    def __init__(self, chat_id: str, model: str, system_prompt: str | None = None, **kwargs: Any) -> None:
        """Create an LLM chat."""
        super().__init__(**kwargs)

        system_prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT.prompt
        system_prompt = USER_CONVERSATION_CONTEXT_PROMPT + system_prompt

        self.chat_id: str = chat_id
        self.llm: LLM = LLM(model, system_prompt)
        self.messages: Messages = Messages()

        self.model: str = self.llm.model
        self.provider: str = self.llm.provider

    def __len__(self) -> int:
        return len(self.messages)

    async def respond_to_message(self, content: TextGenerationInput) -> TextGenerationResponse:
        """Respond to a message.

        Parameters
        ----------
        content : TextGenerationInput
            The new message to respond to.

        Returns
        -------
        TextGenerationResponse
            The response to the message.

        """
        starting_tokens = self.messages.tokens

        messages = self.messages + content
        response = await self.llm.generate_response(messages)

        self.messages.append_message(content, response.input_tokens - starting_tokens)
        self.messages.append_message(
            TextGenerationInput(text=TextInput(response.message), role=InputRole.assistant), response.output_tokens
        )

        return response
