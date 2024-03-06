#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
The purpose of this cog is to enable the bot to communicate with the OpenAI API
and to generate responses to prompts given.
"""

import copy
import json
import logging
from collections import defaultdict
from types import coroutine

import disnake
import openai
import openai.error
import openai.version
import tiktoken
from disnake.ext import commands
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from slashbot.config import App
from slashbot.custom_bot import SlashbotInterationBot
from slashbot.custom_cog import SlashbotCog
from slashbot.markov import generate_markov_sentence
from slashbot.util import (
    create_prompt_dict,
    read_in_prompt_json,
    split_text_into_chunks,
)

openai.api_key = App.get_config("OPENAI_API_KEY")
logger = logging.getLogger(App.get_config("LOGGER_NAME"))

COOLDOWN_USER = commands.BucketType.user

# this is all global so you can use it as a choice in interactions
DEFAULT_SYSTEM_PROMPT = read_in_prompt_json("data/prompts/prompt-discord.json")["prompt"]
MAX_MESSAGE_LENGTH = 1920
TOKEN_COUNT_UNSET = -1
PROMPT_CHOICES = create_prompt_dict()
AVAILABLE_MODELS = ("gpt-3.5-turbo",)  # Remove GPT-4, as it was too expensive
DEFAULT_GPT_MODEL = AVAILABLE_MODELS[0]
DEFAULT_SYSTEM_TOKEN_COUNT = len(tiktoken.encoding_for_model(DEFAULT_GPT_MODEL).encode(DEFAULT_SYSTEM_PROMPT))
SUMMARY_START = "Summary of"


class ArtificialChat(SlashbotCog):
    """AI chat features powered by OpenAI."""

    def __init__(self, bot: SlashbotInterationBot):
        super().__init__(bot)

        self.token_window_size = TOKEN_COUNT_UNSET
        self.set_token_window_size(DEFAULT_GPT_MODEL)
        # todo: this data structure should be a class
        self.channel_histories = defaultdict(
            lambda: {
                "history": {"tokens": 0, "messages": [], "last_summary": ""},
                "prompts": {
                    "model": DEFAULT_GPT_MODEL,
                    "tokens": DEFAULT_SYSTEM_TOKEN_COUNT,
                    "messages": [{"role": "system", "content": DEFAULT_SYSTEM_PROMPT}],
                },
            }
        )

    # Static -------------------------------------------------------------------

    @staticmethod
    def get_history_id(obj: disnake.Message | disnake.ApplicationCommandInteraction) -> str | int:
        """Determine the history ID to use given the origin of the message.

        Historically, this used to return different values for text channels and
        direct messages.

        Parameters
        ----------
        obj
            The recent message.
        Returns
        -------
        int
            The ID to use for history purposes.
        """
        return obj.channel.id

    @staticmethod
    async def send_response_to_channel(
        response: str, obj: disnake.Message | disnake.ApplicationCommandInteraction, dont_tag_user: bool
    ):
        """Send a response to the provided message channel and author.

        Parameters
        ----------
        response : str
            The response to send to chat.
        message : disnake.Message | disnake.ApplicationCommandInteraction
            The message to respond to.
        in_dm : bool
            Boolean to indicate if DM channel.
        """
        if len(response) > MAX_MESSAGE_LENGTH:
            response_chunks = split_text_into_chunks(response, MAX_MESSAGE_LENGTH)
            for i, response_chunk in enumerate(response_chunks):
                user_mention = obj.author.mention if not dont_tag_user else ""
                await obj.channel.send(f"{user_mention if i == 0 else ''} {response_chunk}")
        else:
            await obj.channel.send(f"{obj.author.mention if not dont_tag_user else ''} {response}")

    @staticmethod
    def get_token_count_for_string(model: str, message: str) -> int:
        """_summary_

        Parameters
        ----------
        model : str
            _description_
        message : str
            _description_

        Returns
        -------
        int
            _description_
        """
        return len(tiktoken.encoding_for_model(model).encode(message))

    @staticmethod
    async def is_slash_interaction_highlight(message: disnake.Message) -> bool:
        """Check if a message is in response to a slash command.

        Parameters
        ----------
        message : disnake.Message
            The message to check.

        Returns
        -------
        bool
            If the message is a reply to a slash command, True is returned.
            Otherwise, False is returned.
        """
        if not message.reference:
            return False

        reference = message.reference
        old_message = (
            reference.cached_message if reference.cached_message else await message.channel.fetch_message(message.id)
        )

        # can't see how this can happen (unless no message intents, but then the
        # chat cog won't work at all) but should take into account just in case
        if not old_message:
            logger.error("Message %d not found in internal cache or through channel.fetch_message()", message.id)
            return False

        # if old_message is an interaction response, this will return true
        return isinstance(old_message.interaction, disnake.InteractionReference)

    @staticmethod
    async def get_api_response(model: str, messages: list) -> str:
        """_summary_

        Parameters
        ----------
        model : str
            _description_
        messages : list
            _description_

        Returns
        -------
        str
            _description_
        """
        response = await openai.ChatCompletion.acreate(
            messages=messages,
            model=model,
            temperature=App.get_config("AI_CHAT_MODEL_TEMPERATURE"),
            max_tokens=App.get_config("AI_CHAT_MAX_OUTPUT_TOKENS"),
        )

        return response["choices"][0]["message"]["content"], response["usage"]["total_tokens"]

    def reset_prompt_history(self, history_id: str | int):
        """Clear chat history and reset the token counter.

        Parameters
        ----------
        history_id : str | int
            The index to reset in chat history.
        """
        model = self.channel_histories[history_id]["prompts"]["model"]
        current_prompt = self.channel_histories[history_id]["prompts"]["messages"][0]
        self.channel_histories[history_id]["prompts"]["tokens"] = self.get_token_count_for_string(model, current_prompt)
        self.channel_histories[history_id]["prompts"]["messages"] = [current_prompt]

    def set_token_window_size(self, model_name: str):
        """Set the max allowed tokens.

        Parameters
        ----------
        model_name : str
            The name of the model.
        """
        if model_name != "gpt-3.5-turbo":
            self.token_window_size = 1000  # smaller because gpt-4 is expensive!
        else:
            self.token_window_size = 10000

    async def get_messages_from_reference_point(
        self, message_reference: disnake.MessageReference, messages: list
    ) -> list:
        """_summary_

        Parameters
        ----------
        message_reference : disnake.MessageReference
            _description_
        messages : list
            _description_

        Returns
        -------
        list
            _description_
        """
        # we need the message first, to find it in the messages list
        message_to_find = message_reference.cached_message
        if not message_to_find:
            try:
                channel = await self.bot.fetch_channel(message_reference.channel_id)
                message_to_find = await channel.fetch_message(message_reference.message_id)
            except disnake.NotFound:
                return messages

        # so now we have the message, let's try and find it in the messages
        # list. We munge it into the dict format for the OpenAI API, so we can
        # use the index method
        message_to_find = {
            "role": "assistant",
            "content": message_to_find.clean_content.replace(f"@{self.bot.user.name}", ""),
        }
        try:
            index = messages.index(message_to_find)
        except ValueError:
            return messages

        return messages[: index + 1]

    async def get_chat_prompt_response(self, message: disnake.Message) -> str:
        """_summary_

        Parameters
        ----------
        message : disnake.Message
            _description_

        Returns
        -------
        str
            _description_
        """
        history_id = self.get_history_id(message)
        clean_message = message.clean_content.replace(f"@{self.bot.user.name}", "")

        # we work on a copy, to try and avoid race conditions
        prompt_messages = copy.deepcopy(self.channel_histories[history_id]["prompts"]["messages"])

        # if the response is a reply, let's find that message and present that as the last
        if message.reference:
            prompt_messages = await self.get_messages_from_reference_point(message.reference, prompt_messages)

        # append the latest prompt from a user
        prompt_messages.append({"role": "user", "content": clean_message})

        try:
            ai_message, tokens_used = await self.get_api_response(
                self.channel_histories[history_id]["prompts"]["model"], prompt_messages
            )
            self.channel_histories[history_id]["prompts"]["messages"] += [
                {"role": "user", "content": clean_message},
                {"role": "assistant", "content": ai_message},
            ]
            self.channel_histories[history_id]["prompts"]["tokens"] = tokens_used
        except Exception as e:
            logger.exception("`get_chat_prompt_response` failed with %s", e)
            ai_message = generate_markov_sentence()

        return ai_message

    async def reduce_prompt_history(self, history_id: int | str) -> None:
        """Remove messages from a chat history.

        Removes a fraction of the messages from the chat history if the number
        of tokens exceeds a threshold controlled by
        `self.model.max_history_tokens`.

        Parameters
        ----------
        history_id : int | str
            The chat history ID. Usually the guild or user id.
        """
        removed_count = 0
        while self.channel_histories[history_id]["prompts"]["tokens"] > self.token_window_size:
            message = self.channel_histories[history_id]["prompts"]["messages"][1]
            self.channel_histories[history_id]["prompts"]["tokens"] -= self.get_token_count_for_string(
                self.channel_histories[history_id]["prompts"]["model"], message
            )
            self.channel_histories[history_id]["prompts"]["messages"].pop(1)
            removed_count += 1
        logger.debug(
            "%d messages removed from channel %s due to token limit. There are now %d messages.",
            removed_count,
            history_id,
            len(self.channel_histories[history_id]["prompts"]["messages"][1:]),
        )

    def record_channel_history(self, history_id: int, user: str, message: str) -> None:
        """_summary_

        Parameters
        ----------
        history_id : int
            _description_
        user : str
            _description_
        message : str
            _description_
        """
        message = f"{user}: {message}"
        num_tokens = self.get_token_count_for_string(DEFAULT_GPT_MODEL, message)
        self.channel_histories[history_id]["history"]["messages"].append({"tokens": num_tokens, "message": message})
        # increment number of tokens of latest message
        self.channel_histories[history_id]["history"]["tokens"] += num_tokens

        # remove last summary if set
        summary_removed = False
        for i, message in enumerate(self.channel_histories[history_id]["history"]["messages"]):
            if message["message"] == self.channel_histories[history_id]["history"]["last_summary"]:
                self.channel_histories[history_id]["history"]["tokens"] -= message["tokens"]
                self.channel_histories[history_id]["history"]["messages"].pop(i)
                summary_removed = True
        if summary_removed:
            self.channel_histories[history_id]["history"]["last_summary"] = ""

        logger.debug("%d history: %s", history_id, self.channel_histories[history_id]["history"])

        # if over the limit, remove messages until under the limit
        while self.channel_histories[history_id]["history"]["tokens"] > self.token_window_size:
            self.channel_histories[history_id]["history"]["tokens"] -= self.channel_messages[history_id]["history"][
                "messages"
            ][0]["tokens"]
            self.channel_histories[history_id]["history"]["messages"].pop(0)

    # Listeners ----------------------------------------------------------------

    @commands.Cog.listener("on_message")
    async def listen_to_channel(self, message: disnake.Message) -> None:
        """Listen for mentions which are prompts for the AI.

        Parameters
        ----------
        message : str
            The message to process for mentions.
        """
        history_id = self.get_history_id(message)

        # don't record bot interactions
        if message.type != disnake.MessageType.application_command:
            self.record_channel_history(history_id, message.author.name, message.clean_content)

        # ignore other bot messages and itself
        if message.author.bot:
            return

        # Don't respond to replies, or mentions, which have a reference to a
        # slash command response or interaction
        if await self.is_slash_interaction_highlight(message):
            return

        # only respond when mentioned or in DM
        bot_mentioned = self.bot.user in message.mentions
        message_in_dm = isinstance(message.channel, disnake.channel.DMChannel)

        if bot_mentioned or message_in_dm:
            async with message.channel.typing():
                ai_response = await self.get_chat_prompt_response(message)
                await self.send_response_to_channel(ai_response, message, message_in_dm)  # In a DM, we won't @ the user

    # Commands -----------------------------------------------------------------

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="summarise_chat_history", description="Get a summary of the previous conversation", dm_permission=False
    )
    async def summarise_chat_history(
        self,
        inter: disnake.ApplicationCommandInteraction,
        amount: int = commands.Param(
            default=0, name="amount", description="The last X amount of messages to summarise"
        ),
    ) -> coroutine:
        """_summary_

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            _description_

        Returns
        -------
        coroutine
            _description_
        """
        history_id = self.get_history_id(inter)
        if self.channel_histories[history_id]["history"]["tokens"] == 0:
            return inter.response.send_message("There are no messages to summarise.", ephemeral=True)

        await inter.response.defer(ephemeral=True)

        messages = [e["message"] for e in self.channel_histories[history_id]["history"]["messages"][-amount:]]
        user_prompt = "Summarise the following conversation between multiple users.\n\n" + "\n".join(messages)
        summary_prompt = [
            {"role": "system", "content": App.get_config("AI_SUMMARY_PROMPT")},
            {"role": "user", "content": user_prompt},
        ]
        summary_message, token_count = await self.get_api_response(DEFAULT_GPT_MODEL, summary_prompt)

        # add summary to the prompt history too. not sure if we need to do this...
        self.channel_histories[history_id]["prompts"]["messages"] += summary_prompt + [
            {"role": "assistant", "content": summary_message}
        ]
        self.channel_histories[history_id]["prompts"]["tokens"] += token_count
        self.channel_histories[history_id]["history"]["last_summary"] = f"{self.bot.user.name}: {summary_message}"

        await self.send_response_to_channel(summary_message, inter, True)
        await inter.edit_original_message(content="...")

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="reset_chat_history", description="Reset the AI conversation history")
    async def reset_history(self, inter: disnake.ApplicationCommandInteraction) -> coroutine:
        """Clear history context for where the interaction was called from.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        self.reset_prompt_history(self.get_history_id(inter))
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{DEFAULT_SYSTEM_PROMPT}",
            ephemeral=True,
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="select_chat_prompt", description="Set the AI conversation prompt from a list of choices"
    )
    async def select_existing_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        choice: str = commands.Param(
            autocomplete=lambda _inter, user_input: [
                choice for choice in PROMPT_CHOICES.keys() if user_input in choice
            ],
            description="The choice of prompt to use",
        ),
    ) -> coroutine:
        """Select a system prompt from a set of pre-defined prompts.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        choice : str
            The choice of system prompt
        """
        prompt = PROMPT_CHOICES.get(choice, None)
        if not prompt:
            return await inter.response.send_message(
                "An error with the Discord API has occurred and allowed you to pick a prompt which doesn't exist",
                ephemeral=True,
            )

        history_id = self.get_history_id(inter)
        self.channel_histories[history_id]["prompts"]["messages"] = [{"role": "system", "content": prompt}]
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{prompt[:1928]}",
            ephemeral=True,
        )
        # calculate token count after responding to interaction, as it may take a little time
        self.channel_histories[history_id]["prompts"]["tokens"] = self.get_token_count_for_string(
            self.channel_histories[history_id]["prompts"]["model"], prompt
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(
        name="set_custom_chat_prompt", description="Change the AI conversation prompt to one you write"
    )
    async def set_custom_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        new_prompt: str = commands.Param(description="The prompt to set"),
    ) -> coroutine:
        """Set a new system message for the location were the interaction came
        from.

        This typically does not override the default system message, and will
        append a new system message.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        message : str
            The new system prompt to set.
        """
        history_id = self.get_history_id(inter)
        self.channel_histories[history_id]["prompts"]["messages"] = [{"role": "system", "content": new_prompt}]
        await inter.response.send_message(
            f"History cleared and system prompt changed to:\n\n{new_prompt}",
            ephemeral=True,
        )
        self.channel_histories[history_id]["prompts"]["tokens"] = self.get_token_count_for_string(
            self.channel_histories[history_id]["prompts"]["model"], new_prompt
        )

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="save_chat_prompt", description="Save a AI conversation prompt to the bot's selection")
    async def save_prompt(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: str = commands.Param(description="The name to save the prompt as"),
        prompt: str = commands.Param(description="The prompt to save"),
    ):
        """Add a new prompt to the bot's available prompts.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        name : str
            The name of the new prompt.
        prompt : str
            The contents of the prompt.
        """
        if len(name) > 64:
            return await inter.response.send_message("The prompt name should not exceed 64 characters.", ephemeral=True)
        await inter.response.defer(ephemeral=True)
        with open(f"data/prompts/prompt-{name}.json", "w", encoding="utf-8") as file_out:
            json.dump(
                {"name": name, "prompt": prompt},
                file_out,
            )
        await inter.edit_original_message(content=f"Your prompt {name} has been saved.")

    @commands.cooldown(App.get_config("COOLDOWN_RATE"), App.get_config("COOLDOWN_STANDARD"), COOLDOWN_USER)
    @commands.slash_command(name="show_chat_prompt", description="Print information about the current AI conversation")
    async def echo_info(self, inter: disnake.ApplicationCommandInteraction):
        """Print the system prompt to the screen.

        Parameters
        ----------
        inter : disnake.ApplicationCommandInteraction
            The slash command interaction.
        """
        await inter.response.defer(ephemeral=True)
        history_id = self.get_history_id(inter)

        prompt_name = "Unknown"
        prompt = self.channel_histories[history_id]["prompts"]["messages"][0].get("content", None)
        for name, text in PROMPT_CHOICES.items():
            if prompt == text:
                prompt_name = name

        response = ""
        response += f"**GPT model**: {self.channel_histories[history_id]['prompts']['model']}\n"
        response += f"**Token usage**: {self.channel_histories[history_id]['prompts']['tokens']}\n"
        response += "**Prompt name**: " + prompt_name + "\n"
        response += f"**Prompt**: {prompt[:1024] if prompt else '???'}\n"

        await inter.edit_original_message(content=response)


class PromptFileWatcher(FileSystemEventHandler):
    """FileSystemEventHandler specifically for JSON files in the data/prompts
    directory."""

    def on_any_event(self, event):
        global PROMPT_CHOICES  # pylint: disable=W0603

        if event.is_directory:
            return
        if event.event_type in ["created", "modified"]:
            if event.src_path.endswith(".json"):
                prompt = read_in_prompt_json(event.src_path)
                PROMPT_CHOICES[prompt["name"]] = prompt["prompt"]
        if event.event_type == "deleted":
            if event.src_path.endswith(".json"):
                PROMPT_CHOICES = create_prompt_dict()


observer = Observer()
observer.schedule(PromptFileWatcher(), "data/prompts", recursive=True)
observer.start()


def setup(bot: commands.InteractionBot):
    """Setup entry function for load_extensions().

    Parameters
    ----------
    bot : commands.InteractionBot
        The bot to pass to the cog.
    """
    bot.add_cog(ArtificialChat(bot))
