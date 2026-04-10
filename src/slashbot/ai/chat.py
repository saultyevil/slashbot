from slashbot.ai.models import TextGenerationInput
from slashbot.ai.text_generator import TextGenerator

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


class AIChat(TextGenerator):
    """AI Conversation class for an LLM chatbot."""

    def __init__(
        self, *, system_prompt: str | None = None, prompt_name: str = "unset name", extra_print: str | None = None
    ) -> None:
        """Initialise a conversation, with default values.

        Parameters
        ----------
        system_prompt : str, optional
            The system prompt of the conversation. If not provided, the default
            system prompt is used.
        prompt_name : str
            The name of the system prompt for the conversation. If not provided,
            the default system prompt name is used.
        extra_print : str, optional
            Additional information to print at the start of the log message.

        """
        extra_print = f"[ChatObject:{extra_print}] " if extra_print else ""
        super().__init__(extra_print=extra_print)

        if system_prompt:
            self.set_chat_prompt(system_prompt, prompt_name=prompt_name)

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

    def set_chat_prompt(self, new_prompt: str, *, prompt_name: str = "unset name") -> None:
        """Set the system prompt and clear the conversation.

        Parameters
        ----------
        new_prompt : str
            The new system prompt to set.
        prompt_name : str
            Optional name for the new prompt.

        """
        self.set_system_prompt(new_prompt + USER_CONVERSATION_CONTEXT_PROMPT, prompt_name=prompt_name)
