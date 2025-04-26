import requests

from slashbot.core.text_generation.clients.abstract_client import TextGenerationAbstractClient
from slashbot.core.text_generation.models import GenerationFailureError, TextGenerationResponse, VisionImage
from slashbot.settings import BotSettings


class GeminiClient(TextGenerationAbstractClient):
    """Synchronous Gemini client."""

    SUPPORTED_MODELS = ()
    VISION_MODELS = ("gemini-1.5-turbo", "gemini-1.5-turbo-vision")
    SEARCH_MODELS = ()
    AUDIO_MODELS = ()

    def _make_assistant_message_content(self, message: str) -> dict:
        pass

    def _make_image_content(self, images: VisionImage | list[VisionImage]) -> list[dict]:
        pass

    def _make_user_message_content(self, messages: str | list[str]) -> dict:
        pass

    def _prepare_content(
        self, message: str | list[str], images: VisionImage | list[VisionImage] | None = None
    ) -> dict | list[dict]:
        pass

    def _set_system_prompt_and_clear_context(self, prompt: str, *, prompt_name: str = "unknown") -> None:
        pass

    def _send_request(self) -> None:
        pass

    # --------------------------------------------------------------------------

    @property
    def context(self) -> list[dict]:
        """Get the context, minus the system prompt."""
        return self.context

    def count_tokens_for_message(self, messages: list[dict[str, str]] | str) -> int:
        """Count the number of tokens in a message.

        Parameters
        ----------
        messages : list[dict[str, str]] | str
            The message to count the number of tokens.

        """

    def generate_response_including_context(
        self, messages: str | list[str], images: VisionImage | list[VisionImage] | None = None
    ) -> TextGenerationResponse:
        """Generate a text response, given new text input and previous context.

        Text generation includes the entire context history, and not just the
        most recent inputs.

        Parameters
        ----------
        messages : str | list[str]
            Input message(s), from the user.
        images : VisionImage | list[VisionImage] | None
            Input image(s), from the user.

        """

    def init_client(self, model_name: str) -> None:
        """Initialise the client to use a model.

        Parameters
        ----------
        model_name : str
            The name of the model to initialise the client for.

        """
        self.model_name = model_name
        self._base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={BotSettings.keys.gemini}"

    def send_response_request(self, content: list[dict]) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        request = requests.post(
            url=self._base_url,
            json=content,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )

        if request.status_code != request.ok:
            self.log_debug("Request content: %s", content)
            msg = f"Gemini API request failed with {request.json()['error']['message']}"
            raise GenerationFailureError(msg, code=request.status_code)

        request = request.json()

        return TextGenerationResponse(
            request["candidates"][0]["content"]["parts"][0]["text"],
            request["usageMetadata"]["totalTokenCount"],
        )

    def set_system_prompt(self, prompt: str, *, prompt_name: str = "unknown") -> None:
        """Set the system prompt.

        Parameters
        ----------
        prompt : str
            The system prompt to set.
        prompt_name : str
            The name of the system prompt.

        """
