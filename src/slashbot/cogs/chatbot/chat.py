import asyncio
import datetime
import logging
import threading
from logging.handlers import RotatingFileHandler
from textwrap import shorten
from typing import Any

from slashbot.cogs.chatbot.messages import Messages
from slashbot.llm import (
    LLM,
    InputRole,
    LLMGenerationFailureError,
    LLMInput,
    LLMResponse,
    TextInput,
    load_prompt,
)
from slashbot.logger import Logger
from slashbot.settings import BotSettings

SETTINGS = BotSettings.cogs.chatbot
DEFAULT_SYSTEM_PROMPT = load_prompt(SETTINGS.default_chat_prompt)
USER_CONVERSATION_CONTEXT_PROMPT = """

Each user message is prefixed with their username in the format "Username [Timestamp of message]: message".

Multiple users may be talking simultaneously on different topics. When responding, identify which user sent the most
recent message and respond only to their query. Use the conversation history to maintain context for each user's
individual topic thread. Do not conflate separate users' conversations. Never include a username prefix in your own
responses.

If a user's latest message clearly pivots to engage with another user's topic rather than continuing their own, respond
in the context of the topic they are now discussing. Use common sense to determine whether a message is a continuation
of the user's own thread or a deliberate shift to join another conversation/query/prompt from another user.
""".replace("\n", "")


CHAT_LOG_MAX_BYTES = 10 * 1024 * 1024
CHAT_LOG_BACKUP_COUNT = 5
CHAT_LOG_HANDLER_LOCK = threading.Lock()
CHAT_LOG_HANDLERS: dict[str, logging.Logger] = {}


def _get_chat_log_logger(log_path: str) -> logging.Logger:
    """Get or create the rotating logger for a model transcript."""
    with CHAT_LOG_HANDLER_LOCK:
        if log_path not in CHAT_LOG_HANDLERS:
            chat_logger = logging.getLogger(f"slashbot.chat_log.{log_path}")
            chat_logger.setLevel(logging.INFO)
            chat_logger.propagate = False
            handler = RotatingFileHandler(
                filename=log_path,
                mode="a",
                encoding="utf-8",
                maxBytes=CHAT_LOG_MAX_BYTES,
                backupCount=CHAT_LOG_BACKUP_COUNT,
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            chat_logger.addHandler(handler)
            CHAT_LOG_HANDLERS[log_path] = chat_logger

        return CHAT_LOG_HANDLERS[log_path]


class Chat(Logger):
    """Chat object for having a conversation with an LLM."""

    SUPPORTED_MODELS = LLM.SUPPORTED_MODELS

    def __init__(self, chat_id: str, model: str, system_prompt: str | None = None, **kwargs: Any) -> None:
        """Create an LLM chat."""
        super().__init__(**kwargs, prepend_msg=f"[Chat {chat_id}]")

        self._prompt: str = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT.prompt

        self.chat_id: str = chat_id
        self.llm: LLM = LLM(model, self._combined_system_prompt)
        self.messages: Messages = Messages()
        self._log_tasks: set[asyncio.Task[None]] = set()
        self.log_info("Created new chat")

    def __len__(self) -> int:
        return len(self.messages)

    @property
    def model(self) -> str:
        """The model used for the chat."""
        return self.llm.model

    @property
    def provider(self) -> str:
        """The name of the model provider."""
        return self.llm.provider

    @property
    def prompt(self) -> str:
        """The user-visible system prompt for the chat."""
        return self._prompt

    @prompt.setter
    def prompt(self, prompt: str) -> None:
        self._prompt = prompt

    @property
    def _combined_system_prompt(self) -> str:
        """The system prompt sent to the LLM, including hidden context."""
        return "\n\n".join([prompt for prompt in (USER_CONVERSATION_CONTEXT_PROMPT, self.prompt) if prompt])

    @property
    def tokens(self) -> int:
        """The size of the chat in tokens."""
        return self.messages.tokens

    @property
    def size(self) -> int:
        """The number of messages in the chat."""
        return len(self.messages)

    async def _count_tokens_in_chat(self) -> None:
        """Count the number of tokens in the chat."""
        for message in self.messages:
            if self.messages.tokens == 0:
                await message.count_tokens(self.llm)

    async def shrink_images_to_window(self) -> None:
        """Remove images from the oldest messages until the chat is within the maximum allowed images."""
        total_images = sum(len(message.images) for message in self.messages)
        if total_images <= SETTINGS.max_images_in_window:
            return

        images_removed = 0

        for message in self.messages:
            if total_images - images_removed <= SETTINGS.max_images_in_window:
                break
            if message.images:
                images_removed += len(message.images)
                message.images = []
                start_tokens = message.tokens
                await message.count_tokens(self.llm)
                self.messages.tokens -= start_tokens - message.tokens

        self.log_debug("Removed %d images to fit within the image window", images_removed)

    async def shrink_messages_to_token_window(self) -> None:
        """Remove messages which take the chat over the context window."""
        if self.tokens <= SETTINGS.chat_token_window_size:
            return

        tokens_removed = 0
        messages_removed = 0
        num_to_keep = 2

        # this makes the asssumption to chat is *always* user -> assistant -> user -> assistant
        # and etc. If it's not like this, then oh well. I'm sure it'll be fine.
        while self.tokens > SETTINGS.chat_token_window_size and len(self) - 2 >= num_to_keep:
            for _ in range(2):
                message = self.messages.remove_message(0)
                tokens_removed += message.tokens
            messages_removed += 2

        self.log_debug("Removed %d tokens from %d messages", tokens_removed, messages_removed)

    async def _write_chat_log(
        self, log_path: str, timestamp: str, username: str, request: str, response: LLMResponse
    ) -> None:
        """Append a request and response to the model's transcript file.

        Parameters
        ----------
        log_path : str
            The path to the model's transcript file.
        timestamp : str
            The timestamp associated with the request.
        username : str
            The username associated with the request.
        request : str
            The complete serialized request, including conversation history.
        response : LLMResponse
            The response generated by the LLM.

        """
        original_response = getattr(response, "_original_response", None)
        response_to_log = original_response if original_response is not None else response
        metadata = f"[Chat {self.chat_id}] [{timestamp}] [{username}] "
        log_lines = ["Request:", *request.splitlines(), "Response:", *repr(response_to_log).splitlines(), ""]
        log_entry = "\n".join(f"{metadata}{line}" for line in log_lines) + "\n"
        try:
            chat_logger = await asyncio.to_thread(_get_chat_log_logger, log_path)
            await asyncio.to_thread(chat_logger.info, log_entry.rstrip("\n"))
        except OSError:
            self.log_exception("Failed to write chat transcript to %s", log_path)

    def _log_chat(self, timestamp: str, username: str, request: str, response: LLMResponse) -> None:
        """Schedule a chat transcript write without blocking the response.

        Parameters
        ----------
        timestamp : str
            The timestamp associated with the request.
        username : str
            The username associated with the request.
        request : str
            The complete serialized request, including conversation history.
        response : LLMResponse
            The response generated by the LLM.

        """
        log_path = f"logs/{self.model}.log"
        log_task = asyncio.create_task(self._write_chat_log(log_path, timestamp, username, request, response))
        self._log_tasks.add(log_task)
        log_task.add_done_callback(self._handle_log_task_result)

    def _handle_log_task_result(self, task: asyncio.Task[None]) -> None:
        """Remove a transcript task and report unexpected failures."""
        self._log_tasks.discard(task)
        if task.cancelled():
            self.log_debug("Chat transcript task cancelled")
            return
        if task.exception() is not None:
            self.log_exception("Chat transcript task failed")

    async def chat(self, username: str, content: LLMInput) -> LLMResponse:
        """Respond to a message.

        Parameters
        ----------
        username: str
            The username of the person who sent a message.
        content : LLMInput
            The new message to respond to.

        Returns
        -------
        LLMResponse
            The response to the message.

        """
        await self.shrink_images_to_window()
        await self.shrink_messages_to_token_window()

        starting_tokens = self.messages.tokens
        now_ts = datetime.datetime.now(tz=datetime.UTC).strftime("%a %d %b %Y %H:%M:%S %Z")
        content.text.text = f"{username} [{now_ts}]: " + content.text.text.strip()
        messages = self.messages + content

        generation_failed = False
        try:
            response = await self.llm.generate_response(messages)
        except LLMGenerationFailureError as exc:
            generation_failed = True
            response = LLMResponse(
                message=f"Failed to generate a response: {exc!s}", tokens_used=0, input_tokens=0, output_tokens=0
            )
        self._log_chat(now_ts, username, repr(messages), response)
        if generation_failed:
            return response

        assistant_content = LLMInput(text=TextInput(response.message), role=InputRole.assistant)
        self.messages.append_message(
            content, response.input_tokens - starting_tokens - (self.llm.prompt_tokens if self.llm.prompt_tokens else 0)
        )
        self.messages.append_message(assistant_content, response.output_tokens)
        await self.shrink_messages_to_token_window()

        return response

    def clear_messages(self) -> None:
        """Reset a conversation back to the start."""
        self.messages.clear()
        self.log_debug("Cleared all messages")

    def set_model(self, model: str) -> None:
        """Change the LLM.

        Parameters
        ----------
        model : str
            The name of the model to use.

        """
        self.llm = LLM(model, self._combined_system_prompt)
        self.log_info("Set model to %s", model)

    def set_system_prompt(self, system_prompt: str) -> None:
        """Set the system prompt for the chat.

        Parameters
        ----------
        system_prompt : str
            The new system prompt.

        """
        self.clear_messages()
        self.prompt = system_prompt
        self.llm = LLM(self.model, self._combined_system_prompt)
        self.log_info("Set new system prompt: %s", shorten(system_prompt, 512))


class Chats(Logger):
    """Dataclass for storing Chats."""

    SUPPORTED_MODELS = Chat.SUPPORTED_MODELS

    def __len__(self) -> int:
        return len(self.chats)

    def __str__(self) -> str:
        return f"ChatStore(chats={self.chats})"

    def __getitem__(self, index: str | Any) -> Chat:
        if not isinstance(index, str):
            index = str(index)
        if index not in self.chats:
            self.chats[index] = Chat(index, self.model, self.prompt)

        self.log_debug("Retrived chat %s", index)

        return self.chats[index]

    def __init__(self, default_model: str, default_prompt: str, **kwargs: Any) -> None:
        """Create a ChatStore for storing multiple chats.

        Parameters
        ----------
        default_model : str
            The default model to use for chats.
        default_prompt : str
            The default system prompt to use for chats.
        kwargs : Any
            Key word arguments.

        """
        super().__init__(**kwargs, prepend_msg="[ChatStore]")

        self.model: str = default_model
        self.prompt: str = default_prompt
        self.chats: dict[str, Chat] = {}
