"""Models/classes used by Slashbot cogs.

These classes are used to marshal data
"""

import uuid


class Message:
    """Dataclass for messages returned from an LLM API.

    This data class should be agnostic to the API used and contains fields which
    are generic across APIs.
    """

    def __init__(self, content: str, tokens: int, role: str) -> None:
        """Initialise the message.

        Parameters
        ----------
        model : str
            The name of the model used to generate the message
        content : str
            The message contents
        tokens : int
            The number of tokens of the message
        role : str
            The role the message belongs to, e.g. user or assistant.

        """
        self.content = content
        self.tokens = int(tokens)
        if role not in ["user", "assistant"]:
            raise ValueError("Unknown role %s. Allowed: user, assistant" % role)
        self.role = role


class Conversation:
    """Dataclass for LLM conversations.

    This data class should be used as a wrapper around a list of messages.
    """

    def __init__(self, system_prompt: str, system_prompt_tokens: int) -> None:
        """Initialise a conversation.

        Parameters
        ----------
        system_prompt : str
            The system prompt of the conversation.
        system_prompt_tokens : int
            The number of tokens in the system prompt

        """
        self.tokens = system_prompt_tokens
        self.prompt = system_prompt
        self.messages = [Message(system_prompt, system_prompt_tokens, "system")]

        self._raw_conversation = [{"role": "system", "content": system_prompt}]
        self._system_prompt_tokens = system_prompt_tokens

    def __getitem__(self, index: int) -> dict[str, str]:
        """Get a message at index in the conversation history.

        Parameters
        ----------
        index : int
            The index to retrieve a message at.

        Returns
        -------
        dict[str, str]
            The message

        """
        return self.messages[index]

    def add(self, content: str, tokens: int, role: str) -> None:
        """Add a new message to the conversation history.

        Parameters
        ----------
        content : str
            The content of the message
        tokens : int
            The number of tokens in the message
        role : str
            The role of the message, e.g. user or assistant

        """
        self.tokens += tokens
        message = Message(content, tokens, role)
        self.messages.append(message)
        self._raw_conversation.append({"role": role, "content": content})

    def get_conversation(self) -> list[dict[str, str]]:
        """Get the conversation history.

        Returns
        -------
        list[dict[str, str]]
            The conversation history

        """
        return self._raw_conversation

    def clear(self) -> None:
        """Clear a conversation.

        This resets the conversation back to just the system prompt, including
        the number of tokens.
        """
        self.tokens = self._system_prompt_tokens
        self.messages = [Message(self.prompt, self._system_prompt_tokens, "system")]
        self._raw_conversation = [{"role": "system", "content": self.prompt}]
        self.prompt = self._raw_conversation[0]
