"""Module for vision tasks with LLMs.

The functions in this module are designed for OpenAI's API.
"""

import base64
from dataclasses import dataclass

import requests

from slashlib.config import Bot


@dataclass
class Image:
    """Dataclass for images for LLM usage."""

    url: str
    encoded_image: str
    mime_type: str

    def __init__(self, url: str, encoded_image: str | None, mime_type: str | None) -> None:
        """Initialise the dataclass instance.

        Parameters
        ----------
        url : str
            The URL to the original image
        encoded_image : str
            The base64-encoded image data
        mime_type : str
            The MIME type of the image

        """
        self.url = url
        self.encoded_image = encoded_image
        self.mime_type = mime_type


def download_and_encode_image(url: str) -> Image:
    """Download and encode an image for vision tasks with OpenAI.

    Parameters
    ----------
    url : str
        The URL of the image to encode.

    Returns
    -------
    encoded_image : str
        The base64-encoded image data.
    mime_type : str
        The MIME type of the image.

    """
    if Bot.get_config("AI_CHAT_PREFER_IMAGE_URLS"):
        encoded_image = mime_type = None
    else:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        mime_type = response.headers["Content-Type"]
        encoded_image = base64.b64encode(response.content).decode("utf-8")

    return Image(url, encoded_image, mime_type)
