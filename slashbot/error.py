#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for getting the weather."""

import disnake


async def deferred_error_message(
    inter: disnake.ApplicationCommandInteraction,
    message: str,
    delay: int = 30,
) -> None:
    """Send and delete an error message for a delayed response.

    Parameters
    ----------
    inter : disnake.ApplicationCommandInteraction
        The deferred interaction.
    message : str
        An error message to send to chat.
    delay : int, optional
        The delay (in seconds) before the error message is deleted, by
        default 10
    """
    await inter.edit_original_message(content=message)
    await inter.delete_original_message(delay=delay)
