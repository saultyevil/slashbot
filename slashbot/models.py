"""Models/classes used by Slashbot cogs.

These classes are used to marshal data
"""


class Message:
    """Dataclass for messages returned from an LLM API.

    This data class should be agnostic to the API used and contains fields which
    are generic across APIs.
    """

    def __init__(self, content: str, role: str, *, user: str = "", tokens: int = 0) -> None:
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
        user : str
            The user who sent the message, optional.
        tokens : int
            The number of tokens in the message, optional.

        """
        self.content = content
        if role not in ["system", "user", "assistant"]:
            raise ValueError("Unknown role %s. Allowed: user, assistant" % role)
        self.role = role
        self.tokens = tokens
        self.user = user


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
        self.system_prompt = system_prompt
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

    def add_message(self, content: str, role: str, *, tokens: int = 0) -> None:
        """Add a new message to the conversation history.

        Parameters
        ----------
        content : str
            The content of the message
        role : str
            The role of the message, e.g. user or assistant
        tokens : int
            The number of tokens in the message, optional

        """
        self.conversation.append({"role": role, "content": content})
        self.tokens += tokens

    def clear_conversation(self) -> None:
        """Clear a conversation.

        This resets the conversation back to just the system prompt, including
        the number of tokens.
        """
        self.tokens = self._system_prompt_tokens
        self.conversation = [{"role": "system", "content": self.system_prompt}]

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
        self.system_prompt = new_prompt
        self._system_prompt_tokens = new_prompt_tokens
        self.clear_conversation()


class ChannelHistory:
    """Dataclass for channel history."""

    def __init__(self) -> None:
        """Initialise a channel history.

        The channel history is a list of messages and a summary of the conversation.
        """
        self.tokens = 0
        self.messages = []

    def __getitem__(self, index: int) -> Message:
        """Get a message at index in the channel history.

        Parameters
        ----------
        index : int
            The index to retrieve a message at.

        Returns
        -------
        Message
            The message at the index.

        """
        return self.messages[index]

    def __len__(self) -> int:
        """Return the number of messages in the channel history.

        Returns
        -------
        int
            The number of messages in the channel history.

        """
        return len(self.messages)

    def add_message(self, content: str, user: str, tokens: int) -> None:
        """Add a message to the channel history.

        Parameters
        ----------
        content : str
            The content of the message.
        user : str
            The user who sent the message.
        tokens : int
            The number of tokens the message is comprised of.

        """
        self.tokens += tokens
        self.messages.append(Message(content, "user", user=user, tokens=tokens))

    def remove_message(self, index: int) -> Message:
        """Remove a message from the channel history.

        Parameters
        ----------
        index : int
            The index of the message to remove.

        Returns
        -------
        Message
            The removed message.

        """
        message = self.messages.pop(index)
        self.tokens -= message.tokens
        return message

    def get_messages(self, amount: int) -> list[str]:
        """Get the last amount messages in the channel history.

        Parameters
        ----------
        amount : int
            The number of messages to retrieve.

        Returns
        -------
        list[str]
            The last amount messages in the channel history.

        """
        return [f"{message.user}: {message.content}" for message in self.messages[-amount:]]
