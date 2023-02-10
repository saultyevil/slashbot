#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Various utility functions used through slashbot."""

from typing import Any
import disnake


def convert_string_to_lower(_inter: disnake.ApplicationCommandInteraction, variable: Any) -> Any:
    """Slash command convertor to transform a string into all lower case.

    Parameters
    ----------
    _inter : disnake.ApplicationCommandInteraction
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


def convert_yes_no_to_bool(_inter: disnake.ApplicationCommandInteraction, choice: str) -> bool:
    """_summary_

    Parameters
    ----------
    _inter : disnake.ApplicationCommandInteraction
        The slash command interaction. Currently unused.
    choice : str
        The yes/no string to convert into a bool.

    Returns
    -------
    bool
        True or False depending on yes or no.
    """
    return True if choice.lower() == "yes" else False
