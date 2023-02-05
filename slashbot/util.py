#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Various utility functions used through slashbot."""

from typing import Any
import disnake


def convert_string_to_lower(_inter: disnake.ApplicationCommandInteraction, variable: Any):
    """Slash command convertor to transform a string into all lower case.

    Parameters
    ----------
    -inter : disnake.ApplicationCommandInteraction
        The slash command interaction. Currently unused.
    variable : Any
        The possible string to convert into lower case.

    Returns
    -------
    Any :
        If a string was passed, the lower version of the string is returned.
        Otherwise the original variable is returned.
    """
    return variable.lower() if isinstance(variable, str) else variable
