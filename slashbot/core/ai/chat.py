from slashbot.core.ai.models import TextGenerationInput
from slashbot.core.ai.text_generator import TextGenerator


class AIChat(TextGenerator):
    """AI Conversation class for an LLM chatbot."""

    def __init__(self, *, system_prompt: str | None = None, extra_print: str | None = None) -> None:
        """Initialise a conversation, with default values.

        Parameters
        ----------
        system_prompt : str, optional
            The system prompt of the conversation. If not provided, the default
            system prompt is used.
        extra_print : str, optional
            Additional information to print at the start of the log message.

        """
        extra_print = f"[ChatObject:{extra_print}] " if extra_print else ""
        super().__init__(extra_print=extra_print)

        if system_prompt:
            self.set_system_prompt(system_prompt)

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return self.size_messages

    # --------------------------------------------------------------------------

    def get_history(self) -> list[dict]:
        """Get the conversation context history.

        Returns
        -------
        list[dict]
            The conversation history, formatted for the LLM API.

        """
        return self._client.context

    def reset_history(self) -> None:
        """Reset the conversation history back to the system prompt."""
        self.set_system_prompt(self.system_prompt, prompt_name=self.system_prompt_name)

    async def send_message(
        self,
        messages: TextGenerationInput | list[TextGenerationInput],
    ) -> str:
        """Add a new message to the conversation history.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.

        Returns
        -------
        str
            The message response from the AI.

        """
        response = await self.generate_response_with_context(messages)
        self._token_size = response.tokens_used

        return response.message

    async def send_raw_request(self, content: list[dict] | dict) -> str:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict] |  dict
            The (correctly) formatted content to send to the API.

        """
        response = await self.send_response_request(content)

        return response.message

    def set_chat_prompt(self, new_prompt: str) -> None:
        """Set the system prompt and clear the conversation.

        Parameters
        ----------
        new_prompt : str
            The new system prompt to set.

        """
        self.set_system_prompt(new_prompt)
