#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import json

import asyncio
import disnake
import requests
from disnake.ext import commands

# from disnake.ext import tasks

from slashbot.custom_bot import ModifiedInteractionBot
from slashbot.custom_cog import CustomCog
from slashbot.config import App
from slashbot.error import deferred_error_message

MAX_ELAPSED_TIME = 300


class ImageGen(CustomCog):
    def __init__(self, bot: ModifiedInteractionBot):
        super().__init__()
        self.bot = bot

        self.current_tasks = {}

        # self.check_for_completed_tasks.start()

    @staticmethod
    def check_progress(process_id: str):
        """Check the progress."""
        payload = '{\n    "process_id" :  "%s"\n}' % process_id
        headers = {
            "x-api-key": App.config("MONSTER_API_KEY"),
            "Authorization": App.config("MONSTER_TOKEN"),
        }

        response = requests.request(
            "POST", "https://api.monsterapi.ai/apis/task-status", headers=headers, data=payload, timeout=5
        )

        content = json.loads(response.text)

        print(content)

        content = content["response_data"]
        status = content.get("status", None)

        url = None
        if status == "COMPLETED":
            url = content["result"]["output"][0]

        return url

    @staticmethod
    def send_request(prompt: str, steps: int, aspect_ratio: str) -> str:
        """Send a request to Monster API."""

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

        content = json.loads(response.text)

        print(content)

        process_id = content.get("process_id", None)

        return process_id

    @commands.slash_command(
        description="Generate an image from a text prompt",
        guild_ids=[App.config("ID_SERVER_ADULT_CHILDREN"), App.config("ID_SERVER_FREEDOM")],
    )
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

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction

        prompt : str, optional

        steps : int, optional

        aspect_ratio : str, optional

        """
        if inter.author.id != App.config("ID_USER_SAULTYEVIL"):
            return inter.response.send_message("You don't get to use this command yet")

        if inter.author.id in self.current_tasks:
            return await inter.response.send_message("You already have a request processing.", ephemeral=True)

        follow_up = inter.followup
        await inter.response.defer(ephemeral=False)

        try:
            process_id = self.send_request(prompt, steps, aspect_ratio)
        except requests.exceptions.Timeout:
            return deferred_error_message(inter, "There has been an error with the API. Try again later.")

        self.current_tasks[inter.author.id] = process_id

        print(self.current_tasks)

        await inter.edit_original_message(content=f"{process_id}")

        start = time.time()
        elapsed_time = 0

        while elapsed_time < MAX_ELAPSED_TIME:
            try:
                print(f"checking progress for {process_id}")
                url = self.check_progress(process_id)
            except requests.exceptions.Timeout:
                pass

            print(url)

            if url:
                self.current_tasks.pop(inter.author.id)
                print(self.current_tasks)
                break

            await asyncio.sleep(5)
            elapsed_time = time.time() - start

        if elapsed_time > MAX_ELAPSED_TIME:
            await follow_up.send("Command timed out :-(")
        else:
            await follow_up.send(f"{url}")

    # @tasks.loop(seconds=20)
    # async def check_for_completed_tasks(self):
    #     if len(self.current_tasks) == 0:
    #         return

    #     for user, process_id in self.current_tasks:
    #         pass
