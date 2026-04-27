import asyncio
import contextlib
import datetime
from collections import defaultdict
from dataclasses import dataclass

import disnake

from slashbot import markov
from slashbot.ai import (
    GenerationFailureError,
    TextGenerationInput,
    VisionImage,
    VisionVideo,
    read_in_prompt,
)
from slashbot.bot.custom_types import Message
from slashbot.cogs.chatbot.chat_registry import ChatRegistry
from slashbot.messages import send_message_to_channel
from slashbot.settings import BotSettings


@dataclass
class Cooldown:
    """Rate-limit state for a single user.

    Attributes
    ----------
    count : int
        Number of interactions recorded in the current window.
    last_interaction : datetime.datetime
        UTC timestamp of the most recent interaction.

    """

    count: int
    last_interaction: datetime.datetime


class ResponseGenerator:
    """Handles response generation and per-user rate limiting."""

    def __init__(self, history_manager: ChatRegistry, bot: disnake.Client) -> None:
        """Initialise the responder with a chat registry and bot client.

        Parameters
        ----------
        history_manager : HistoryManager
            Shared store of per-channel chat and summary instances.
        bot : disnake.Client
            The running bot client.

        """
        self.bot = bot
        self.chat_registry = history_manager

        self._lock = asyncio.Lock()
        self._cooldowns: dict[int, Cooldown] = defaultdict(lambda: Cooldown(0, datetime.datetime.now(tz=datetime.UTC)))

    def is_on_cooldown(self, user_id: int) -> bool:
        """Determine whether a user is currently rate-limited.

        Increments the interaction count on each call. When the count exceeds
        the configured limit, the user is considered on cooldown until the
        cooldown interval has elapsed, at which point the count resets.

        Parameters
        ----------
        user_id : int
            Discord user ID to check.

        Returns
        -------
        bool
            True if the user should be rate-limited, False otherwise.

        """
        now = datetime.datetime.now(tz=datetime.UTC)
        cd = self._cooldowns[user_id]
        elapsed = (now - cd.last_interaction).seconds
        if cd.count > BotSettings.cogs.chatbot.response_rate_limit:
            if elapsed > BotSettings.cogs.chatbot.rate_limit_interval:
                cd.count = 1
                cd.last_interaction = now
                return False
            return True
        cd.count += 1
        cd.last_interaction = now

        return False

    async def get_attached_images(self, message: Message) -> list[VisionImage]:
        """Extract image attachments and embeds from a Discord message.

        When BotSettings.cogs.chatbot.prefer_image_urls is False, each
        image is downloaded and base64-encoded in place. Failures are
        ignored so that a single bad URL does not abort the whole response.

        Parameters
        ----------
        message : Message
            The Discord message to inspect for image content.

        Returns
        -------
        list of VisionImage
            VisionImage instances for every image attachment or embed found in
            the message.

        """
        image_urls = [a.url for a in message.attachments if a.content_type and a.content_type.startswith("image/")]
        image_urls += [e.url for e in message.embeds if e.type == "image" and e.url]
        images = []
        for url in image_urls:
            image = VisionImage(url)
            if not BotSettings.cogs.chatbot.prefer_image_urls:
                with contextlib.suppress(Exception):
                    await image.download_and_encode()
            images.append(image)

        return images

    async def get_attached_videos(self, message: Message) -> list[VisionVideo]:
        """Extract YouTube video embeds from a Discord message.

        Only embedded videos are considered; raw video file attachments are
        excluded to avoid the cost of downloading and encoding them.

        Parameters
        ----------
        message : Message
            The Discord message to inspect for video embeds.

        Returns
        -------
        list of VisionVideo
            Deduplicated VisionVideo instances for every video embed found in
            the message.

        """
        urls = [e.url for e in message.embeds if e.type == "video" and e.url]

        return [VisionVideo(url) for url in set(urls)]

    async def _resolve_referenced_message(self, message: disnake.Message) -> disnake.Message:
        """Fetch the message referenced by a reply, falling back to the original.

        Attempts to use the cached reference first; if unavailable, fetches
        the message from the Discord API. Returns message unchanged if the
        reference cannot be resolved.

        Parameters
        ----------
        message : disnake.Message
            The message that contains a reply reference.

        Returns
        -------
        disnake.Message
            The referenced message, or message itself if resolution fails.

        """
        ref = message.reference
        if not ref:
            return message
        previous_message = ref.cached_message
        if not previous_message:
            try:
                channel = await self.bot.fetch_channel(ref.channel_id)
                if not isinstance(channel, disnake.TextChannel | disnake.DMChannel):
                    return message
                if not ref.message_id:
                    return message
                previous_message = await channel.fetch_message(ref.message_id)
            except disnake.NotFound:
                return message

        return previous_message

    async def generate_response(self, discord_message: disnake.Message) -> str:
        """Generate an AI response to a Discord message.

        Resolves the bot's display name, extracts any attached media, and
        optionally injects a referenced message as context. Falls back to a
        Markov-chain sentence if the AI generation fails.

        The underlying conversation history is updated inside an async lock to
        prevent race conditions when multiple users message simultaneously.

        Parameters
        ----------
        discord_message : disnake.Message
            The message to respond to.

        Returns
        -------
        str
            The generated response text.

        """
        conversation = self.chat_registry.get_chat(discord_message)

        if discord_message.guild:
            bot_member = discord_message.guild.get_member(self.bot.user.id)
            bot_name = bot_member.display_name if bot_member else self.bot.user.name
        else:
            bot_name = self.bot.user.name

        user_prompt = discord_message.clean_content.replace(f"@{bot_name}", "")
        images = await self.get_attached_images(discord_message)
        videos = await self.get_attached_videos(discord_message)

        if discord_message.reference:
            referenced = await self._resolve_referenced_message(discord_message)
            images += await self.get_attached_images(referenced)
            videos += await self.get_attached_videos(referenced)
            user_prompt = (
                f'Previous message to respond to with the prompt: "{referenced.clean_content}"\nPrompt: {user_prompt}'
            )

        async with self._lock:
            user_label = f"{discord_message.author.display_name}: "
            try:
                msg_input = TextGenerationInput(user_label + user_prompt, images=images, videos=videos)
                return await conversation.send_message(msg_input)
            except GenerationFailureError:
                fallback = markov.generate_text_from_markov_chain(markov.MARKOV_MODEL, "?random", 1)
                return fallback[0] if isinstance(fallback, list) else fallback

    async def respond_to_unprompted(self, message: disnake.Message) -> None:
        """Send an unprompted AI reply to a message, without tagging the author.

        Uses a dedicated random-response prompt rather than the main
        conversation prompt, and does not prepend a user mention.

        Parameters
        ----------
        message : disnake.Message
            The message to respond to.

        """
        prompt = read_in_prompt("data/prompts/_random-response.yaml")
        chat = self.chat_registry.get_chat(message)
        content = chat.create_request_json(TextGenerationInput(message.clean_content), system_prompt=prompt.prompt)
        response = await chat.send_raw_request(content)

        await send_message_to_channel(response, message, dont_tag_user=True)

    async def respond_to_prompted(self, discord_message: disnake.Message, *, message_in_dm: bool = False) -> None:
        """Respond to a user-directed message, respecting rate limits.

        Shows a typing indicator while the response is being generated. If the
        user is on cooldown, sends an abuse warning instead of a real reply.

        Parameters
        ----------
        discord_message : disnake.Message
            The message to respond to.
        message_in_dm : bool, optional
            When True, the author mention is omitted from the reply.
            Defaults to False.

        """
        async with discord_message.channel.typing():
            if self.is_on_cooldown(discord_message.author.id):
                await send_message_to_channel(
                    f"Stop abusing me {discord_message.author.mention}!",
                    discord_message,
                    dont_tag_user=True,
                )
            else:
                response = await self.generate_response(discord_message)
                await send_message_to_channel(response, discord_message, dont_tag_user=message_in_dm)
