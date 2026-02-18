from typing import Any

from slashbot.bot.custom_types import ApplicationCommandInteraction
from slashbot.database import UserSQL


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


async def get_user_reminders(inter: ApplicationCommandInteraction, _: str) -> list[str]:
    """Interface to get reminders for /forget_reminder autocomplete.

    Parameters
    ----------
    inter : disnake.ApplicationCommandInteraction
        The interaction this is ued with.
    _ : str
        The user input, which is unused.

    Returns
    -------
    List[str]
        A list of reminders

    """
    user = await inter.bot.db.get_user("discord_id", inter.author.id)  # type: ignore
    if not user:
        user = await inter.bot.db.upsert_row(  # type: ignore
            UserSQL(
                discord_id=inter.author.id,
                username=inter.author.name,
            ),
        )
    reminders = await inter.bot.db.get_users_reminders(inter.author.id)  # type: ignore
    return [f"{reminder.date}: {reminder.content}" for reminder in reminders]
