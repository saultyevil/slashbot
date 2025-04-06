from typing import Any

from slashbot.bot.custom_types import ApplicationCommandInteraction


def convert_string_to_lower(_inter: ApplicationCommandInteraction, variable: Any) -> Any:
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


def convert_yes_no_to_bool(_inter: ApplicationCommandInteraction, choice: str) -> bool:
    """Convert a yes/no input to a boolean.

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
    return choice.lower() == "yes"
