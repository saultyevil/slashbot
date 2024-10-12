import asyncio
import json
import logging
import time

import requests

from slashbot.config import App

MAX_WAIT_TIME_SECONDS = 300
LOGGER = logging.getLogger(App.get_config("LOGGER_NAME"))


def check_image_request_status(process_id: str) -> str:
    """Check the progress of a request.

    Parameters
    ----------
    process_id : str
        The UUID for the process to check.

    Returns
    -------
    str
        If the process has finished, the URL to the finished process is
        returned. Otherwise an empty string is returned.

    """
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {App.get_config('MONSTER_API_KEY')}",
    }
    response = requests.request(
        "GET",
        f"https://api.monsterapi.ai/v1/status/{process_id}",
        headers=headers,
        timeout=5,
    )

    response_data = json.loads(response.text)
    response_status = response_data.get("status", None)

    if response_status == "COMPLETED":
        return "COMPLETED", response_data["result"]["output"][0]
    if response_status == "FAILED":
        return "FAILED", response_data["result"]["error_message"]

    return "IN PROGRESS", ""


def send_image_request(prompt: str, steps: int, aspect_ratio: str) -> str:
    """Send an image request to the API.

    Parameters
    ----------
    prompt : str
        The prompt to generate an image for.
    steps : int
        The number of sampling steps to use.
    aspect_ratio : str
        The aspect ratio of the image.

    Returns
    -------
    str
        The process ID if successful, or an empty string if unsuccessful.

    """
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {App.get_config('MONSTER_API_KEY')}",
    }
    payload = {
        "prompt": prompt,
        "samples": 1,
        "steps": steps,
        "aspect_ratio": aspect_ratio,
        "safe_filter": False,
    }
    response = requests.request(
        "POST",
        "https://api.monsterapi.ai/v1/generate/txt2img",
        headers=headers,
        json=payload,
        timeout=5,
    )

    response_data = json.loads(response.text)
    return response_data.get("process_id", ""), response_data


async def retrieve_image_request(process_id: str) -> tuple[str, str]:
    """Retrieve a generated image from the API.

    Checks the status of the request every second until it is complete, or until
    MAX_WAIT_TIME_SECONDS is reached.

    Parameters
    ----------
    process_id : str
        The

    Returns
    -------
    status : str
        The status of the final status request
    result : str
        The result, either an error message or url

    """
    start = time.time()
    elapsed_time = 0

    status = "IN PROGRESS"
    result = None

    while status == "IN PROGRESS" and elapsed_time < MAX_WAIT_TIME_SECONDS:
        LOGGER.debug("image request %s: status %s result %s", process_id, status, result)
        try:
            status, result = check_image_request_status(process_id)
        except requests.exceptions.Timeout:
            status = "FAILED"
            result = "Request to image generation API timed out"

        await asyncio.sleep(1)
        elapsed_time = time.time() - start

    if elapsed_time >= MAX_WAIT_TIME_SECONDS:
        status = "FAILED"
        result = "Request to image generation API timed out"

    return status, result
