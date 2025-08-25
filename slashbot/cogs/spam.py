"""Commands designed to spam the chat with various things."""

import random

import aiofiles
import disnake
from ddgs import DDGS
from disnake.ext import commands

from slashbot.bot.custom_bot import CustomInteractionBot
from slashbot.bot.custom_cog import CustomCog
from slashbot.bot.custom_command import slash_command_with_cooldown
from slashbot.settings import BotSettings


class Spam(CustomCog):
    """A collection of commands to spam the chat with."""

    @slash_command_with_cooldown(name="bad_word", description="send a naughty word")
    async def bad_word(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a bad word to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        async with aiofiles.open(BotSettings.files.bad_words, encoding="utf-8") as file_in:
            bad_words = await file_in.readlines()
        bad_word = random.choice(bad_words).strip()
        await inter.response.send_message(f"{bad_word.capitalize()}.")

    @slash_command_with_cooldown(name="evil_wii", description="evil wii")
    async def evil_wii(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send the Evil Wii, a cursed image.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to respond to.

        """
        message = random.choice(
            ["evil wii", "evil wii?", "have you seen this?", "||evil wii||", "||evil|| ||wii||"],
        )
        file = disnake.File("data/images/evil_wii.png")
        file.filename = f"SPOILER_{file.filename}"

        await inter.response.send_message(content=message, file=file)

    @slash_command_with_cooldown(name="oracle", description="a message from god")
    async def oracle(self, inter: disnake.ApplicationCommandInteraction) -> None:
        """Send a Terry Davis inspired "God message" to the chat.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to possibly remove the cooldown from.

        """
        async with aiofiles.open(BotSettings.files.god_words, encoding="utf-8") as file_in:
            oracle_words = await file_in.readlines()

        await inter.response.send_message(
            f"{' '.join([word.strip() for word in random.sample(oracle_words, random.randint(5, 25))])}",
        )

    @slash_command_with_cooldown(
        name="image", description="search for an image", guilds=BotSettings.discord.development_servers
    )
    async def image_search(
        self,
        inter: disnake.ApplicationCommandInteraction,
        query: str = commands.Param(description="your search query for an image"),
    ) -> None:
        """Search for an image using DDGS.

        Parameters
        ----------
        inter: disnake.ApplicationCommandInteraction
            The interaction to respond to.
        query : str
            The image search query.

        """
        image_results = DDGS().images(query, max_results=10)
        image = random.choice(image_results)
        await inter.response.send_message(image["image"])


def setup(bot: CustomInteractionBot) -> None:
    """Set up the entry function for load_extensions().

    Parameters
    ----------
    bot : CustomInteractionBot
        The bot to pass to the cog.

    """
    bot.add_cog(Spam(bot))
