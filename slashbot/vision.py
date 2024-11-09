"""Module for vision tasks with LLMs.

The functions in this module are designed for OpenAI's API.
"""

import base64
import logging
from dataclasses import dataclass

import requests

from slashbot.config import Bot

LOGGER = logging.getLogger(Bot.get_config("LOGGER_NAME"))


@dataclass
class Image:
    """Dataclass for images for LLM usage."""

    url: str
    encoded_image: str
    mime_type: str

    def __init__(self, url: str, encoded_image: str, mime_type: str) -> None:
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
        LOGGER.debug("<Image> %s %s", self.url, self.mime_type)


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
    response = requests.get(url, timeout=5)
    response.raise_for_status()  # Ensure the request was successful

    mime_type = response.headers["Content-Type"]
    encoded_image = base64.b64encode(response.content).decode("utf-8")

    return Image(url, encoded_image, mime_type)
