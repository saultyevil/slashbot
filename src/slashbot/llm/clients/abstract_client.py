from abc import ABCMeta, abstractmethod
from typing import Any

from slashbot.llm.models import (
    GenerationFailureError,
    ImageInput,
    InputRole,
    TextGenerationInput,
    TextGenerationResponse,
    TextInput,
    VideoInput,
)
from slashbot.logger import Logger


class AbstractClient(Logger, metaclass=ABCMeta):
    """Abstract class for a TextGenerationClient."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialise the text generation class.

        Parameters
        ----------
        model_name : str
            The name of the model.
        **kwargs : Any
            A list of key word arguments to use for the model.

        """
        super().__init__(**kwargs)

    def _assemble_payload_from_inputs(self, model: str, message: TextGenerationInput) -> dict | list[dict]:
        """Create the contents payload for a request.

        The input object(s), TextGenerationInput, can contain text, image and
        video (url) data to add to the contents payload. The methods inside this
        method are all abstract and must be implemented by the current client.

        Parameters
        ----------
        model : str
            The name of the model to use.
        message : TextGenerationInput
            The input message to create a contents payload for,

        Returns
        -------
        dict | list [dict]
            An appropriately formatted dict or list of dict's for the current
            active client.

        """
        if message.text == "":
            error_message = "Can only generate when there is text input"
            self.log_error("%s", error_message)
            raise GenerationFailureError(error_message, 1)

        image_content = []
        video_content = []
        text_content = self._create_text_input_object(message.text)

        if message.images:
            image_content.extend(self._create_image_input_object(model, message.images))
        if message.videos:
            video_content.extend(self._create_video_input_object(model, message.videos))

        payload = self._construct_final_payload(message.role, text_content, image_content, video_content)
        self.log_debug("Assemebled payload from %s for %s: %s", message, model, payload)

        return payload

    def transform_input_to_payload(
        self, model: str, input_content: TextGenerationInput | list[TextGenerationInput]
    ) -> dict | list:
        """Create a request JSON for the current LLM model.

        Parameters
        ----------
        model : str
            The name of the model to generate input for.
        input_content : TextGenerationInput | list[TextGenerationInput]
            Input message(s), from the user, including attached images and
            videos.

        """
        if not isinstance(input_content, list):
            input_content = [input_content]

        content = [self._assemble_payload_from_inputs(model, message) for message in input_content]
        self.log_debug("Transformed %s into for %s: %s", input_content, model, content)

        return content

    # --------------------------------------------------------------------------
    # ABSTRACT METHODS WHICH REQUIRE IMPLEMENTATION
    # --------------------------------------------------------------------------

    @abstractmethod
    def _create_image_input_object(self, model: str, images: ImageInput | list[ImageInput]) -> dict | list[dict]:
        """Create a payload for an image request.

        Parameters
        ----------
        model : str
            The name of the model to generate input for.
        images : ImageInput| list[ImageInput]
            The image(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """

    @abstractmethod
    def _create_text_input_object(self, text: TextInput) -> dict:
        """Create a payload for a text request.

        Does not require a model parameter as all models will support text
        input.

        Parameters
        ----------
        text : TextInput
            The text message to format into a payload.

        Returns
        -------
        dict
            The correctly formatted payload.

        """

    @abstractmethod
    def _construct_final_payload(
        self, role: InputRole, text_content: dict, image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict | list[dict]:
        """Create a payload for a payload, including text, images and videos.

        Parameters
        ----------
        role : InpuRole
            The role of the message, e.g. user or assistant
        text_content : dict
            The text messages to add to the payload.
        image_content : dict | list[dict]
            The image(s) to add to the payload.
        video_content : dict | list[dict]
            The videos(s) to add to the  payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """

    @abstractmethod
    def _create_video_input_object(self, model: str, videos: VideoInput | list[VideoInput]) -> dict | list[dict]:
        """Create a payload for a video request.

        Parameters
        ----------
        model : str
            The name of the model to generate input for.
        videos : VideoInput | list[VideoInput]
            The videos(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """

    @abstractmethod
    async def count_tokens(self, model: str, content: TextGenerationInput | list[TextGenerationInput]) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        model : str
            The name of the model to generate a response with.
        content : TextGenerationInput | list[TextGenerationInput]
            The (correctly) formatted content to send to the API.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """

    @abstractmethod
    async def generate_response(
        self, model: str, content: TextGenerationInput | list[TextGenerationInput], system_prompt: str | None = None
    ) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        model : str
            The name of the model to generate a response with.
        content : TextGenerationInput | list[TextGenerationInput]
            The (correctly) formatted content to send to the API.
        system_prompt : str
            The system prompt to use to generate the response with.

        Returns
        -------
        TextGenerationResponse
            The response from the LLM.

        """
