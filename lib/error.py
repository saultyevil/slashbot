#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Commands for getting the weather."""

import disnake


async def deferred_error_message(inter: disnake.ApplicationCommandInteraction, message: str, delay: int = 10) -> None:
    """Send and delete an error message for a delayed response.

    Parameters
    ----------
    inter : disnake.ApplicationCommandInteraction
        _description_
    message : str
        _description_
    delay : int, optional
        _description_, by default 10
    """
    await inter.edit_original_message(content=message)
    await inter.delete_original_message(delay=delay)
