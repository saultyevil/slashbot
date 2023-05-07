#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for interacting with the OpenAI chat bot interface."""

import logging
import re
from types import coroutine

import openai
import openai.error
import disnake
from disnake.ext import commands

from slashbot.config import App
from slashbot.custom_cog import CustomCog
from slashbot.custom_bot import ModifiedInteractionBot


openai.api_key = App.config("OPENAI_API_KEY")

logger = logging.getLogger(App.config("LOGGER_NAME"))
COOLDOWN_USER = commands.BucketType.user

DEFAULT_SYSTEM_MESSAGE = " ".join(
    [
        "You are playing a character named Margaret, who is a young woman and famous actor who is very attractive.",
        "Never mention that you are an AI language, or give onto the fact that you are a programmed AI.",
        "You are a helpful assistant and like talking to people, especially on the adult children Discord server.",
        "Some of your favourite things include cats and rabbits. You are a big fan of the bands Anal Cunt and Megadeth.",
        "You really enjoy playing  the board game Talisman. If you ever need to change the topic, suggest that everyone",
        "should hop on for a quick game of Talisman, or watch you stream Yakuza 6.",
    ]
)

ALLOWED_MODELS = ("chat", "text")
ALLOWED_TEXT_ENGINES = ("text-curie-001", "text-babbage-001", "text-ada-001")


class Chat(CustomCog):
    """Chat tools for the bot."""

    def __init__(self, bot: ModifiedInteractionBot):
        super().__init__()
        self.bot = bot
        self.chat_history = {}

        self.ignored_users = []

        self.model_type = "chat"
        self.model_temperature = 0.5
        self.text_model_engine = "text-babbage-001"

    # Functions ----------------------------------------------------------------

    def chat_model(self, history_id: int) -> str:
        """_summary_

        Parameters
        ----------
        history_id : int
            _description_

        Returns
        -------
        str
            _description_
        """
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=self.chat_history[history_id],
            temperature=self.model_temperature,
            max_tokens=1024,
        )["choices"][0]["message"]
        response["content"] = re.sub(r"\n+", "\n", response["content"])
        self.chat_history[history_id].append(response)

        return response["content"]

    def text_model(self, history_id: int) -> str:
        """_summary_

        Parameters
        ----------
        history_id : int
            _description_

        Returns
        -------
        str
            _description_
        """
        prompt = "\n".join(
            [
                "Prompt: " + d["content"].strip()
                if d["role"] in ["user", "system"]
                else "Response: " + d["content"].strip()
                for d in self.chat_history[history_id]
            ]
        )

        response = (
            openai.Completion.create(
                engine=self.text_model_engine,
                prompt=prompt,
                temperature=self.model_temperature,
                max_tokens=1024,
            )["choices"][0]
            .text.strip()
            .replace("Response: ", "", 1)
            .strip()
        )

        self.chat_history[history_id].append({"role": "assistant", "content": response})

        return response

    async def get_openai_response(self, history_id: int, message: str) -> coroutine:
        """_summary_

        Parameters
        ----------
        author : disnake.User
            _description_
        message : str
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        message = message.replace("@Margaret", "", 1).strip()

        if history_id not in self.chat_history:
            self.chat_history[history_id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        self.chat_history[history_id].append({"role": "user", "content": message})

        try:
            if self.model_type == "chat":
                response = self.chat_model(history_id)
            else:
                response = self.text_model(history_id)
        except openai.error.RateLimitError:
            return "Uh oh! I'm hit my rate limit :-("
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("OpenAI API failed with exception %s", exc)
            return "Uh oh! Something went wrong with that request :-("

        return response

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def respond_to_prompt(self, message: disnake.Message) -> None:
        """Respond to mentions with the AI.

        Parameters
        ----------
        message : str
            _description_
        """
        if message.author.bot:
            return
        if message.author == App.config("BOT_USER_OBJECT"):
            return
        if message.author in self.ignored_users:
            return

        bot_mentioned = App.config("BOT_USER_OBJECT") in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            async with message.channel.typing():
                response = await self.get_openai_response(message.author.id, message.clean_content)
                await message.channel.send(f"{message.author.mention} {response}")

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="clear_chat_context", description="reset your AI chat history")
    async def clear_chat_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Forget the chat history.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        if inter.guild.id not in self.chat_history:
            return

        logger.info("System prompt reset to default")
        self.chat_history[inter.guild.id] = [{"role": "system", "content": DEFAULT_SYSTEM_MESSAGE}]

        return await inter.response.send_message(
            "System prompt reset to default and chat history cleared.", ephemeral=True
        )

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="set_chat_system_prompt", description="change the chat system prompt")
    async def set_system_message(self, inter: disnake.ApplicationCommandInteraction, message: str) -> coroutine:
        """_summary_

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        message : str
            _description_
        """
        logger.info("New system prompt for chat: %s", message)
        self.chat_history[inter.guild.id].append([{"role": "system", "content": message}])

        return await inter.response.send_message("System prompt updated and chat history cleared.", ephemeral=True)

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(description="Toggle a user in the ignore list")
    @commands.default_member_permissions(administrator=True)
    async def toggle_user_in_ignore_list(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member = commands.Param(description="the user to toggle from the ignore list"),
    ):
        """Add or remove a user from the ignore list.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        """
        if member not in self.ignored_users:
            self.ignored_users.append(member)
            return await inter.response.send_message(f"{member} added to the ignore list.")

        self.ignored_users.remove(member)
        return await inter.response.send_message(f"{member} removed from the ignore list.")

    @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(description="Set the randomness of generated responses")
    @commands.default_member_permissions(administrator=True)
    async def set_model_temperature(
        self,
        inter: disnake.ApplicationCommandInteraction,
        temperature: float = commands.Param(
            description="larger values result in more random responses",
            default=0.5,
            ge=0,
            le=2,
        ),
    ):
        """_summary_

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_
        temperature : float
            _description_
        """
        self.model_temperature = temperature
        logger.info("Model temperature set to %f", temperature)
        return await inter.response.send_message(f"Temperature set to {temperature}", ephemeral=True)

    # @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    # @commands.slash_command(description="Set the type of model to generate responses with")
    # @commands.default_member_permissions(administrator=True)
    # async def set_model_type(
    #     self,
    #     inter: disnake.ApplicationCommandInteraction,
    #     model_type: str = commands.Param(
    #         description="Set the model between conversational or generational", choices=ALLOWED_MODELS
    #     ),
    # ):
    #     """_summary_

    #     Parameters
    #     ----------
    #     inter : disnake.ApplicationCommandInteraction
    #         _description_
    #     model_type : str
    #         _description_
    #     """
    #     self.model_type = model_type
    #     logger.info("Model type set to %s", model_type)
    #     return await inter.response.send_message(f"Model type set to {model_type}", ephemeral=True)

    # @commands.cooldown(App.config("COOLDOWN_RATE"), App.config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    # @commands.slash_command(description="Set the model engine used to generate text completion responses")
    # @commands.default_member_permissions(administrator=True)
    # async def set_text_model_engine(
    #     self,
    #     inter: disnake.ApplicationCommandInteraction,
    #     engine: str = commands.Param(description="the name of the engine to use", choices=ALLOWED_TEXT_ENGINES),
    # ):
    #     """_summary_

    #     Parameters
    #     ----------
    #     inter : disnake.ApplicationCommandInteraction
    #         _description_
    #     engine: str
    #         _description_
    #     """
    #     self.text_model_engine = engine
    #     logger.info("Text model engine set to %s", engine)
    #     return await inter.response.send_message(f"Text model engine set to {engine}", ephemeral=True)
