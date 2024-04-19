"""Models/classes used by Slashbot cogs.

These classes are used to marshal data
"""


class Message:
    """Dataclass for messages returned from an LLM API.

    This data class should be agnostic to the API used and contains fields which
    are generic across APIs.
    """

    def __init__(self, content: str, role: str) -> None:
        """Dataclass for messages returned from an LLM API.

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
        self._system_prompt_tokens = system_prompt_tokens

        self.tokens = system_prompt_tokens
        self.prompt = system_prompt
        self.messages = [Message(system_prompt, "system")]
        self.conversation = [{"role": "system", "content": system_prompt}]

    def __getitem__(self, index: int) -> dict[str, str]:
        """Get a message at index in the conversation history.

        This is the number of messages in the conversation, from both the user
        and the assistant.

        Parameters
        ----------
        index : int
            The index to retrieve a message at.

        Returns
        -------
        dict[str, str]
            The message

        """
        message = self.conversation[index]
        return Message(message["content"], message["role"])

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return len(self.conversation[1:])

    def add_message(self, content: str, role: str) -> None:
        """Add a new message to the conversation history.

        Parameters
        ----------
        content : str
            The content of the message
        role : str
            The role of the message, e.g. user or assistant

        """
        self.conversation.append({"role": role, "content": content})

    def clear_conversation(self) -> None:
        """Clear a conversation.

        This resets the conversation back to just the system prompt, including
        the number of tokens.
        """
        self.tokens = self._system_prompt_tokens
        self.conversation = [{"role": "system", "content": self.prompt}]

    def remove_message(self, index: int) -> Message:
        """Remove a message from the conversation history.

        Parameters
        ----------
        index : int
            The index of the message to remove.

        Returns
        -------
        Message
            The removed message.

        """
        message = self.conversation.pop(index)
        return Message(message["content"], message["role"])

    def set_prompt(self, new_prompt: str, new_prompt_tokens: int) -> None:
        """Set a new system prompt for the conversation.

        Parameters
        ----------
        new_prompt : str
            The new prompt to set.
        new_prompt_tokens : int
            The number of tokens in the new prompt.

        """
        self.prompt = new_prompt
        self._system_prompt_tokens = new_prompt_tokens
        self.clear_conversation()
