from slashbot.core.logger import Logger
from slashbot.core.text_generation.clients.openai_client import OpenAIClient
from slashbot.core.text_generation.models import TextGenerationResponse, VisionImage
from slashbot.settings import BotSettings


class TextGenerator(Logger):
    """Base class for text generation using LLMs."""

    SUPPORTED_OPENAI_MODELS = OpenAIClient.SUPPORTED_MODELS
    SUPPORTED_CLAUDE_MODELS = ()
    SUPPORTED_GOOGLE_MODELS = ()
    SUPPORTED_MODELS = SUPPORTED_OPENAI_MODELS + SUPPORTED_CLAUDE_MODELS + SUPPORTED_GOOGLE_MODELS
    VISION_MODELS = (*OpenAIClient.VISION_MODELS,)
    SEARCH_MODELS = (*OpenAIClient.SEARCH_MODELS,)
    AUDIO_MODELS = (*OpenAIClient.AUDIO_MODELS,)

    def __init__(self, *, model_name: str | None = None, extra_print: str = "") -> None:
        """Initialise a TextGeneratorLLM with default values.

        Parameters
        ----------
        model_name : str | None
            The name of the LLM model to use
        extra_print : str, optional
            Additional information to print at the start of the log message.

        """
        super().__init__(prepend_msg=extra_print)
        model: str = model_name or BotSettings.cogs.ai_chat.default_llm_model
        self._extra_print: str = extra_print

        if model in self.SUPPORTED_OPENAI_MODELS:
            self._client = OpenAIClient(model)
        else:
            msg = f"{model} is not available"
            raise NotImplementedError(msg)

    # --------------------------------------------------------------------------

    @property
    def client_system_prompt(self) -> str:
        """Get the system prompt of the client."""
        return self._client.system_prompt

    @property
    def client_system_prompt_name(self) -> str:
        """Get the name of the system prompt of the client."""
        return self._client.system_prompt_name

    @property
    def size_messages(self) -> int:
        """Get the size of the context, in messages."""
        return len(self._client.context)

    @property
    def size_tokens(self) -> int:
        """Get the size of the context, in tokens."""
        return self._client.token_size

    # --------------------------------------------------------------------------

    def client_count_tokens_for_message(self, message: list[dict[str, str]] | str) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        message : list[str] | str
            The message for which the token count needs to be computed.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        return self._client.count_tokens_for_message(message)

    def client_generate_response_including_context(
        self, message: str, images: VisionImage | list[VisionImage] | None = None
    ) -> TextGenerationResponse:
        """Generate text from the current LLM model.

        Parameters
        ----------
        message : str
            The message to respond to.
        images : VisionImage | list[VisionImage] | None
            The image(s) to respond to. By default, None.

        """
        return self._client.generate_response_including_context(message, images)

    def client_send_response_request(self, content: list[dict]) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        return self._client.send_response_request(content)

    def client_set_model(self, model: str) -> None:
        """Set the current LLM model.

        Parameters
        ----------
        model : str
            The name of the model to use.

        """
        self._client.init_client(model)

    def client_set_system_prompt(self, prompt: str, *, prompt_name: str = "unknown") -> None:
        """Set the system prompt.

        Parameters
        ----------
        prompt : str
            The system prompt to set.
        prompt_name : str
            The name of the system prompt.

        """
        self._client.set_system_prompt(prompt, prompt_name=prompt_name)
