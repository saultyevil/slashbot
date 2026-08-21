from dataclasses import dataclass, field

from slashbot.llm import LLMInput


@dataclass
class Messages:
    """Dataclass for storing messages."""

    tokens: int = 0
    messages: list[LLMInput] = field(default_factory=list)

    def __add__(self, content: LLMInput) -> list[LLMInput]:
        return [*self.messages, content]

    def __len__(self) -> int:
        return len(self.messages)

    def __str__(self) -> str:
        return f"Messages(tokens={self.tokens} messages={self.messages})"

    def __getitem__(self, index: int) -> LLMInput:
        return self.messages[index]

    def append_message(self, content: LLMInput, num_tokens: int) -> None:
        """Append a new message.

        Parameters
        ----------
        content : LLMInput
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

    def remove_message(self, index: int) -> LLMInput:
        """Remove a message.

        Parameters
        ----------
        index : int
            The index of the message to remove.

        Returns
        -------
        LLMInput
            The message which has been removed.

        """
        message = self.messages.pop(index)
        self.tokens -= message.tokens

        return message
