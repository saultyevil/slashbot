import openai

from slashbot.ai.clients.abstract_client import TextGenerationAbstractClient
from slashbot.ai.models import TextGenerationInput, TextGenerationResponse, VisionImage, VisionVideo
from slashbot.settings import BotSettings


class OpenAIClient(TextGenerationAbstractClient):
    """Asynchronous OpenAI client."""

    SUPPORTED_MODELS = (
        "gpt-4.1-nano",
        "gpt-4.1-mini",
        "gpt-5-nano",
    )
    VISION_MODELS = SUPPORTED_MODELS
    SEARCH_MODELS = ()
    AUDIO_MODELS = ()
    VIDEO_MODELS = ()

    # --------------------------------------------------------------------------

    def __len__(self) -> int:
        """Get the length of the conversation, excluding the system prompt.

        Returns
        -------
        int
            The length of the conversation.

        """
        return len(self._model_context_message_content)

    # --------------------------------------------------------------------------

    @property
    def _model_context_message_content(self) -> list[dict]:
        """Return a reference to the contents of the context.

        This reference exists because the request objects are different for
        each LLM.

        Returns
        -------
        list[dict]
            The contents of the context.

        """
        return self._model_context[1:]  # first message is system prompt

    @property
    def client_type(self) -> str:
        """Get the client type.

        Returns
        -------
        str
            A string representation of the client type.

        """
        return "openai"

    # --------------------------------------------------------------------------

    def _check_context_contains_images(self, contents: dict) -> bool:
        """Check if an image is present in the client's content.

        Parameters
        ----------
        contents : dict
            An individual message object which has been passed to LLM, e.g.
            {"role": "user", "content": [{"type": "text", "text": "hello"}]}

        Returns
        -------
        bool
            If an image, returns True. Otherwise, returns False.

        """
        content_blocks = contents["content"]
        return any(block["type"] == "image" for block in content_blocks)

    def _create_image_input_object(self, images: VisionImage | list[VisionImage]) -> list[dict]:
        """Create a payload for an image request.

        Parameters
        ----------
        images : VisionImage | list[VisionImage]
            The image(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        if self.model_name not in self.VISION_MODELS:
            return []
        if not isinstance(images, list):
            images = [images]
        return [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/{image.mime_type};base64,{image.b64image}" if image.b64image else image.url,
                    "detail": "low",
                },
            }
            for image in images
        ]

    def _create_text_input_object(self, text: str | list[str]) -> dict | list[dict]:
        """Create a payload for a text request.

        Parameters
        ----------
        text : str | list[str]
            The text messages(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        return {"type": "text", "text": text}

    def _create_video_input_object(self, videos: VisionVideo | list[VisionVideo]) -> list[dict]:  # noqa: ARG002
        """Create a payload for a video request.

        Parameters
        ----------
        videos : VisionVideo | list[VisionVideo]
            The videos(s) to format into a payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        return []

    def _create_assistant_response_object(self, message: str) -> dict:
        """Create a payload for the response from the LLM.

        Parameters
        ----------
        message : str
            The response message from the LLM.

        Returns
        -------
        dict
            The correctly formatted payload.

        """
        return {"role": "assistant", "content": [self._create_text_input_object(message)]}

    def _create_user_input_object(
        self, text_content: dict | list[dict], image_content: dict | list[dict], video_content: dict | list[dict]
    ) -> dict | list[dict]:
        """Create a payload for a payload, including text, images and videos.

        Parameters
        ----------
        text_content : str | list[str]
            The text messages(s) to add to the payload.
        image_content : VisionImage | list[VisionImage]
            The image(s) to add to the payload.
        video_content : VisionVideo | list[VisionVideo]
            The videos(s) to add to the  payload.

        Returns
        -------
        dict | list[dict]
            The correctly formatted payload.

        """
        return {"role": "user", "content": [*text_content, *image_content, *video_content]}

    # --------------------------------------------------------------------------

    def count_tokens(self, messages: dict | list[dict[str, str]] | str) -> int:
        """Get the token count for a given message for the current LLM model.

        Parameters
        ----------
        messages : dict | list[str] | str
            The message for which the token count needs to be computed.

        Returns
        -------
        int
            The count of tokens in the given message for the current model.

        """
        if not self._client:
            msg = "No API client is available to query the tokens endpoint"
            raise ValueError(msg)
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        client = openai.Client(api_key=self._client.api_key, base_url=self._client.base_url)
        response = client.responses.input_tokens.count(model=self.model_name, input=messages)  # type: ignore
        self.log_debug("Count token response %s for messages %s", response, messages)

        return response.input_tokens

    def init_client(self, model_name: str) -> None:
        """Initialise the client to use a model.

        Parameters
        ----------
        model_name : str
            The name of the model to initialise the client for.

        """
        self.model_name = model_name
        self._client = openai.AsyncClient(api_key=BotSettings.keys.openai, base_url="http://localhost:11434/v1")

    def create_content_payload_object(
        self, messages: TextGenerationInput | list[TextGenerationInput], *, system_prompt: str | None = None
    ) -> dict | list:
        """Create a request JSON for the current LLM model.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.
        system_prompt : str | None
            The system prompt to use. If None, the current system prompt is
            used.

        """
        request = super().create_content_payload_object(messages)

        if not isinstance(request, list):
            msg = "Internal issue: an invalid type has been returned from OpenAIClient.create_content_payload_object()"
            raise TypeError(msg)

        if system_prompt:
            request.insert(0, {"role": "system", "content": system_prompt})

        return request

    async def generate_response(self, content: list[dict] | dict) -> TextGenerationResponse:
        """Send a request to the API client.

        Parameters
        ----------
        content : list[dict]
            The (correctly) formatted content to send to the API.

        """
        if not self._client:
            self.init_client(self.model_name)

        await self._log_request("%s", content)
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=content,  # type: ignore
            max_completion_tokens=self._max_completion_tokens,
            temperature=BotSettings.cogs.chatbot.model_temperature,
        )
        await self._log_response("%s", response)

        response_message = response.choices[0].message.content
        if not response_message:
            msg = "A valid response was not generated by the OpenAI client."
            raise ValueError(msg)

        return TextGenerationResponse(  # Ternary to shut the linter up
            response_message, response.usage.total_tokens if response.usage else self.token_size
        )

    async def generate_response_with_context(
        self, messages: TextGenerationInput | list[TextGenerationInput]
    ) -> TextGenerationResponse:
        """Generate a text response, gievn a message and image inputs.

        Text generation includes the entire context history, and not just the
        most recent inputs.

        Parameters
        ----------
        messages : ContextMessage | list[ContextMessage]
            Input message(s), from the user, including attached images and
            videos.

        """
        if not self._client:
            self.init_client(self.model_name)

        self._shrink_model_context_to_window_size()

        user_contents = self._create_content_payload(messages)
        if isinstance(user_contents, list):
            for content in user_contents:
                self._add_to_model_context(content)
        else:
            self._add_to_model_context(user_contents)

        response = await self.generate_response(self._model_context)
        if not response.message:
            msg = "A valid response was not generated by the OpenAI client."
            raise ValueError(msg)

        self._model_context.append(self._create_assistant_response_object(response.message))
        self.token_size = response.tokens_used

        return response

    def set_system_prompt(self, prompt: str, *, prompt_name: str = "unset name") -> None:
        """Set the system prompt.

        Parameters
        ----------
        prompt : str
            The system prompt to set.
        prompt_name : str
            The name of the system prompt.

        """
        self.system_prompt = prompt
        self.system_prompt_name = prompt_name
        self._model_context = [{"role": "system", "content": prompt}]
        self.token_size = self.count_tokens(prompt)
