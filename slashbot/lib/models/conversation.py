"""Models/classes used by Slashbot cogs.

These classes are used to marshal data
"""

import logging
import sys

from slashbot.lib.config import BotConfig
from slashbot.lib.text_generation import get_token_count

LOGGER = logging.getLogger(BotConfig.get_config("LOGGER_NAME"))


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
        self.system_prompt = system_prompt
        self._set_first_message_as_system_prompt()

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
        message = self._messages[index]
        return Message(message["content"], message["role"])

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return len(self._messages[1:])

    def __str__(self) -> str:
        """Print the raw conversation.

        Returns
        -------
        str
            The raw conversation, stored in self._messages.

        """
        return f"{self._messages}"

    def __repr__(self) -> str:
        """Print the raw conversation.

        Returns
        -------
        str
            The raw conversation, stored in self._messages.

        """
        return repr(self._messages)

    def _add_user_message(self, message: str, images: list[str] | None = None) -> None:
        """Add a user message to the conversation.

        Parameters
        ----------
        message : str
            The new message to add
        images : list[str], optional
            Any images to add, by default None

        """
        if not message and images:
            message = "Describe the following image(s):"
        if not message:
            LOGGER.error("No message to add to the conversation")
            return
        message = (
            BotConfig.get_config("AI_CHAT_PROMPT_PREPEND") + message + BotConfig.get_config("AI_CHAT_PROMPT_APPEND")
        )
        if images:
            image_urls = []
            for image in images:
                if image.encoded_image:
                    image_urls.append(f"data:{image.mime_type};base64,{image.encoded_image}")
                else:
                    image_urls.append(image.url)
            message_images = [
                {
                    "type": "image_url",
                    "image_url": {"url": url, "detail": "low"},
                }
                for url in image_urls
            ]
            self._messages.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": message}, *message_images],
                },
            )
        else:
            self._messages.append({"role": "user", "content": message})

    def _add_assistant_message(self, message: str) -> None:
        """Add an assistant message to the conversation.

        Parameters
        ----------
        message : str
            The assistant message to add.

        """
        self._messages.append({"role": "assistant", "content": message})

    def _shrink_conversation_to_token_size(self) -> None:
        """Shrink the conversation to within the token window."""
        token_start = self.tokens
        messages_start = len(self._messages)

        # Minimum number of messages to keep. This takes into account the system
        # prompt and keeps at least one assistant -> user sequence
        min_messages = 3

        # Keep removing the 1st message and response until under the token size.
        # To remove the prompt and response, we remove 2 messages at index 1 as
        # the message at index 0 is the system prompt
        while self.tokens > BotConfig.get_config("AI_CHAT_TOKEN_WINDOW_SIZE") and len(self._messages) > min_messages:
            self.remove_message(1)
            self.remove_message(1)

        if self.tokens != token_start:
            LOGGER.info(
                "Removed %d tokens and %d messages from conversation",
                token_start - self.tokens,
                messages_start - len(self),
            )

    def _get_byte_size_of_conversation(self) -> int:
        """Get the byte size of the conversation.

        Returns
        -------
        int
            The byte size of the conversation.

        """
        seen = set()

        def sizeof(o: any) -> int:
            if id(o) in seen:
                return 0
            seen.add(id(o))
            size = sys.getsizeof(o)
            if isinstance(o, dict):
                size += sum(sizeof(k) + sizeof(v) for k, v in o.items())
            elif isinstance(o, list | tuple | set):
                size += sum(sizeof(i) for i in o)
            elif hasattr(o, "__dict__"):
                size += sizeof(vars(o))
            elif hasattr(o, "__slots__"):
                size += sum(sizeof(getattr(o, slot)) for slot in o.__slots__ if hasattr(o, slot))
            return size

        return sizeof(self._messages)

    def _set_first_message_as_system_prompt(self) -> None:
        self.tokens = self._system_prompt_tokens
        if BotConfig.get_config("AI_CHAT_CHAT_MODEL") in ["o1", "o1-mini"]:  # noqa: SIM108
            role = "user"
        else:
            role = "system"
        self._messages = [{"role": role, "content": self.system_prompt}]

    def add_message(  # noqa: PLR0913
        self,
        message: str,
        role: str,
        *,
        tokens: int = 0,
        images: list[str] | None = None,
        shrink_conversation: bool = True,
    ) -> list[dict]:
        """Add a new message to the conversation history.

        Parameters
        ----------
        message : str
            The message to add
        role : str
            The role of the message, e.g. user or assistant
        images : list[str]
            Any images to add to the conversation
        tokens : int
            The number of tokens in the conversation, optional
        discord_message : disnake.Message
            The Discord message associated with the message, optional
        shrink_conversation : bool
            Whether or not to shrink the conversation to within the token window

        """
        if role not in ("user", "assistant"):
            msg = "unknown role, valid is either 'user' or 'assistant'"
            raise ValueError(msg)
        if shrink_conversation:
            self._shrink_conversation_to_token_size()
        message = message.strip()
        if role == "user":
            self._add_user_message(message, images)
        else:
            self._add_assistant_message(message)
        self.tokens = tokens

        return self._messages[-1]

    def clear_messages(self) -> list[dict]:
        """Clear a conversation.

        This resets the conversation back to just the system prompt, including
        the number of tokens.
        """
        self._set_first_message_as_system_prompt()
        return self._messages

    def get_messages(self) -> list[dict]:
        """Get the messages in a conversation.

        Returns
        -------
        list[dict]
            The messages in the conversation

        """
        return self._messages

    def get_size_of_conversation(self) -> int:
        """Get the size of the conversation.

        Returns
        -------
        int
            The size of the conversation.

        """
        return self._get_byte_size_of_conversation()

    def remove_message(self, index: int) -> Message:
        """Remove a message from the conversation history.

        The token count is also updated.

        Parameters
        ----------
        index : int
            The index of the message to remove.

        Returns
        -------
        Message
            The removed message.

        """
        if self._messages[index]["role"] == "system" or index == 0:
            msg = "Trying to remove system prompt"
            raise ValueError(msg)
        message = self._messages.pop(index)
        self.tokens -= get_token_count(BotConfig.get_config("AI_CHAT_CHAT_MODEL"), message["content"])
        return Message(message["content"], message["role"])

    def remove_images_from_messages(self) -> list[dict]:
        """Remove image URLs from the conversation.

        This is generally most useful when the OpenAI API is complaining that it
        can't open the URL for some reason. Could also be useful when switching
        between DeepSeek and OpenAI, for example.

        Returns
        -------
        list[dict]
            List containing a dict with the message index, item index, and the
            item inside the "content" window

        """
        removed_images = []

        for i, message in enumerate(self._messages):
            content = message["content"]
            # if content is a list, then it has images attached
            if not isinstance(content, list):
                continue
            # remove any image urls, but not base64 encoded strings. in theory,
            # we could also try converting image urls to base64 strings...
            for j, item in enumerate(content):
                if item["type"] == "image_url" and ";base64," not in item["image_url"]:
                    removed_images.append(
                        {
                            "message_index": i,
                            "item_index": j,
                            "image": self._messages[i]["content"].pop(j),
                        }
                    )

        return removed_images

    def set_conversation_point(self, message: str) -> list[dict]:
        """Get the conversation.

        Can either get all of the messages, or will return messages up to the
        provided, optional, message.

        Parameters
        ----------
        message: str, optional
            The last message to retrieve, by default None

        Returns
        -------
        list[dict]
            The conversation

        """
        message_to_find = (
            BotConfig.get_config("AI_CHAT_PROMPT_PREPEND") + message + BotConfig.get_config("AI_CHAT_PROMPT_APPEND")
        )
        matching_dict = next((d for d in self._messages if d["content"] == message_to_find), None)
        if matching_dict:
            index = self._messages.index(matching_dict)
            self._messages = self._messages[: index + 1]
            LOGGER.debug("set_conversation_point: messages now are: %s", self._messages)
        else:
            LOGGER.debug("Failed to find message in conversation, so not setting new reference point")

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
        self.clear_messages()
