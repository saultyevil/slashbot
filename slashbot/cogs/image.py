#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import logging
import time

import disnake
import requests
from disnake.ext import commands

from slashbot.config import App
from slashbot.custom_bot import SlashbotInterationBot
from slashbot.custom_cog import SlashbotCog

MAX_ELAPSED_TIME = 300
logger = logging.getLogger(App.config("LOGGER_NAME"))


class ImageGen(SlashbotCog):
    """Cog for text to image generation using Monster API.

    Possibly in the future, we'll use OpenAI instead.
    """

    def __init__(self, bot: SlashbotInterationBot):
        super().__init__()
        self.bot = bot
        self.running_tasks = {}

    @staticmethod
    def check_request_status(process_id: str) -> str:
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
        payload = '{\n    "process_id" :  "%s"\n}' % process_id  # pylint: disable=C0209
        headers = {
            "x-api-key": App.config("MONSTER_API_KEY"),
            "Authorization": App.config("MONSTER_TOKEN"),
        }
        response = requests.request(
            "POST", "https://api.monsterapi.ai/apis/task-status", headers=headers, data=payload, timeout=5
        )

        response_data = json.loads(response.text)
        response_data = response_data["response_data"]
        response_status = response_data.get("status", None)

        if response_status == "COMPLETED":
            url = response_data["result"]["output"][0]
        else:
            url = ""

        return url

    @staticmethod
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
        payload = json.dumps(
            {
                "model": "txt2img",
                "data": {
                    "prompt": prompt,
                    "samples": 1,
                    "steps": steps,
                    "aspect_ratio": aspect_ratio,
                },
            }
        )
        headers = {
            "x-api-key": App.config("MONSTER_API_KEY"),
            "Authorization": App.config("MONSTER_TOKEN"),
            "Content-Type": "application/json",
        }
        response = requests.request(
            "POST",
            "https://api.monsterapi.ai/apis/add-task",
            headers=headers,
            data=payload,
            timeout=5,
        )

        response_data = json.loads(response.text)
        process_id = response_data.get("process_id", "")

        return process_id

    async def cog_before_slash_command_invoke(self, inter: disnake.ApplicationCommandInteraction):
        """Remove CustomCog before cog interaction."""
        pass

    @commands.cooldown(rate=1, per=300, type=commands.BucketType.user)
    @commands.slash_command(description="Generate an image from a text prompt", dm_permission=False)
    async def text_to_image(
        self,
        inter: disnake.ApplicationCommandInteraction,
        prompt: str = commands.Param(description="The prompt to generate an image for"),
        steps: int = commands.Param(default=30, ge=30, lt=500, description="The number of sampling steps"),
        aspect_ratio: str = commands.Param(
            default="square", choices=["square", "landscape", "portrait"], description="The aspect ratio of the image"
        ),
    ):
        """Generate an image from a text prompt.

        Uses Monster API. The request to the API is not made asynchronously.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The interaction to respond to.
        prompt : str, optional
            The prompt to generate an image for.
        steps : int, optional
            The number of sampling steps
        aspect_ratio : str, optional
            The aspect ratio of the image.
        """
        if inter.author.id in self.running_tasks:
            return await inter.response.send_message("You already have a request processing.", ephemeral=True)

        next_interaction = inter.followup
        await inter.response.defer(ephemeral=True)

        try:
            process_id = self.send_image_request(prompt, steps, aspect_ratio)
        except requests.exceptions.Timeout:
            return inter.edit_original_message(content="The image generation API took too long to respond.")

        if process_id == "":
            return await inter.edit_original_message("There was an error when submitting your request.")

        self.running_tasks[inter.author.id] = process_id
        logger.info("text2image: Request %s for user %s (%d)", process_id, inter.author.name, inter.author.id)
        await inter.edit_original_message(content=f"Request submitted: {process_id}")

        start = time.time()
        elapsed_time = 0

        while elapsed_time < MAX_ELAPSED_TIME:
            try:
                url = self.check_request_status(process_id)
            except requests.exceptions.Timeout:
                url = ""
            if url:
                self.running_tasks.pop(inter.author.id)
                break

            await asyncio.sleep(3)
            elapsed_time = time.time() - start

        if elapsed_time >= MAX_ELAPSED_TIME:
            logger.error("text2image: timed out %s", process_id)
            await next_interaction.send(f'{inter.author.name}\'s request ({process_id}) for "{prompt}" timed out.')
        else:
            await next_interaction.send(f'{inter.author.name}\'s request for "{prompt}" {url}')
