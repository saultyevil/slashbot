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
        if role not in ["system", "user", "assistant"]:
            msg = f"Unknown role {role}. Allowed: user, assistant"
            raise ValueError(msg)
        self.content = content
        self.role = role
        self.tokens = tokens
        self.user = user


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
        return [f"<{message.user}> {message.content}" for message in self.messages[-amount:]]
