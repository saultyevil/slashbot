"""Models/classes used by Slashbot cogs.

These classes are used to marshal data
"""

import uuid


class Message:
    """Dataclass for messages returned from an LLM API.

    This data class should be agnostic to the API used and contains fields which
    are generic across APIs.
    """

    def __init__(self: "Message", content: str, tokens: int, role: str) -> None:
        """Initialise the message.

        Parameters
        ----------
        content : str
            The message contents
        tokens : int
            The number of tokens of the message
        role : str
            The role the message belongs to, e.g. user or assistant.

        """
        self.id = uuid.uuid4()
        self.content = content
        self.tokens = int(tokens)
        if role not in ["user", "assistant"]:
            raise ValueError("Unknown role %s. Allowed: user, assistant" % role)
        self.role = role


class Conversation:
    """Dataclass for LLM conversations.

    This data class should be used as a wrapper around a list of messages.
    """

    def __init__(self: "Conversation", location_id: int, system_prompt: str, system_prompt_tokens: int) -> None:
        """Initialise a conversation.

        Parameters
        ----------
        location_id : int
            The ID of the location where the conversation is, typically a
            channel ID.
        system_prompt : str
            The system prompt of the conversation.
        system_prompt_tokens : int
            The number of tokens in the system prompt

        """
        self.id = location_id
        self.tokens = system_prompt_tokens
        self.system_prompt_tokens = system_prompt_tokens
        self.system_prompt = system_prompt
        self.messages = [Message(system_prompt, system_prompt_tokens, "system")]
        self.conversation = [{"role": "system", "content": system_prompt}]

    def __getitem__(self: "Conversation", index: int) -> dict[str, str]:
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
        return self.conversation[index]

    def add(self: "Conversation", message: Message) -> None:
        """Add a new message to the conversation history.

        Parameters
        ----------
        message : Message
            The message to add to the conversation history.

        """
        self.messages.append(message)
        self.conversation.append({"role": message.role, "content": message.content})

    def remove(self: "Conversation", message: Message) -> None:
        """Remove a message from the conversation history.

        Parameters
        ----------
        message : Message
            The message to remove.

        """
        self.messages.append(message)
        self.conversation.remove({"role": message.role, "content": message.content})

    def clear(self: "Conversation") -> None:
        """Clear a conversation.

        This resets the conversation back to just the system prompt, including
        the number of tokens.
        """
        self.tokens = self.system_prompt_tokens
        self.conversation = [{"role": "system", "content": self.system_prompt}]
        self.system_prompt = self.conversation[0]
