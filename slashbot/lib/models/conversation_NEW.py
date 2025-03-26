import logging

from slashbot.lib.text_generation_NEW import TextGeneratorLLM


class AIConversation(TextGeneratorLLM):
    """AI Conversation class for an LLM chatbot."""

    def __init__(self) -> None:
        """Initialise a conversation, with default values."""
        super().__init__()
        self.system_prompt = ""
        self.token_window = 0
        self.context = [{"role": "system", "content": self.system_prompt}]

    def _add_user_message_to_context(self) -> None:
        raise NotImplementedError

    def _add_assistant_message_to_context(self) -> None:
        raise NotImplementedError

    def _prepare_images_for_context(self) -> None:
        raise NotImplementedError

    def _remove_message_from_context(self, index: int) -> None:
        raise NotImplementedError

    def _set_system_prompt(self, prompt: str) -> None:
        raise NotImplementedError

    def _shrink_messages_to_token_window(self) -> None:
        raise NotImplementedError

    def clear_message_context(self) -> None:
        """Clear the messages in the conversation, keeping the system prompt."""
        raise NotImplementedError

    def generate_response(self, message: str, images: list[str] | None = None) -> list[dict]:
        """Add a new message to the conversation history.

        Parameters
        ----------
        message : str
            The message to add
        images : list[str]
            Any images to add to the conversation

        """
        raise NotImplementedError

    def set_system_message(self, new_prompt: str) -> None:
        """Set the system prompt and clear the conversation.

        Parameters
        ----------
        new_prompt : str
            The new system prompt to set.

        """
        raise NotImplementedError
