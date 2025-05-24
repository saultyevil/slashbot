from dataclasses import dataclass

from slashbot.core.text_generation import GenerationFailureError, TextGenerationInput, TextGenerator, read_in_prompt


@dataclass
class SummaryMessage:
    """Dataclass for a message from a text channel."""

    user: str
    content: str
    tokens: int = 0


class AIChatSummary(TextGenerator):
    """Dataclass for generating AI summaries for text channels."""

    SUMMARY_PROMPT = read_in_prompt("data/prompts/_summarise.yaml").prompt

    def __init__(self, *, token_window_size: int = 8096, extra_print: str = "") -> None:
        """Initialise the AI channel summary."""
        extra_print = f"[SummaryObject:{extra_print}] " if extra_print else ""
        super().__init__(extra_print=extra_print)
        self._token_size = 0
        self._token_window_size = token_window_size
        self._history_context = []

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the number of messages in the history.

        Returns
        -------
        int
            The number of messages in the history.

        """
        return len(self._history_context)

    # --------------------------------------------------------------------------

    def _remove_message_from_history_context(self, index: int) -> None:
        removed_message = self._history_context.pop(index)
        self._token_size -= removed_message.tokens

    def _shrink_history_to_token_window_size(self) -> None:
        while self._token_size > self._token_window_size and len(self) > 1:
            self._remove_message_from_history_context(0)

    # --------------------------------------------------------------------------

    def add_message_to_history(self, message: SummaryMessage) -> None:
        """Add a message to the history.

        Parameters
        ----------
        message : disnake.Message
            The message to add

        """
        self._shrink_history_to_token_window_size()
        if message.tokens == 0:
            try:
                message.tokens = self.count_tokens_for_message(message.content)
            except GenerationFailureError:
                message.tokens = len(message.content)
        self._history_context.append(message)

    def get_history(self, *, amount: int = 0) -> list[SummaryMessage]:
        """Get the current history.

        Parameters
        ----------
        amount : int
            The number of messages to return, starting from the end. If <= 0,
            return all messages.

        Returns
        -------
        list[SummaryMessage]
            The current history.

        """
        if amount > 0:
            return self._history_context[-amount:]

        return self._history_context

    async def generate_summary(self, *, requesting_user: str | None = None) -> str:
        """Generate a summary of the current history.

        Parameters
        ----------
        requesting_user : str | None
            The user requesting the summary, to referred to in the summary as
            "you".

        """
        history_message = "Summarise the following conversation between multiple users:\n" + "\n".join(
            [f"{message.user}: {message.content}" for message in self._history_context]
        )
        if requesting_user:
            history_message += (
                f".\nPlease refer to me, {requesting_user}, as 'you' in the summary like we were having a conversation."
            )
        request = self.create_request_json(
            TextGenerationInput(history_message), system_prompt=self.SUMMARY_PROMPT.prompt
        )
        response = await self.send_response_request(request)

        return response.message
