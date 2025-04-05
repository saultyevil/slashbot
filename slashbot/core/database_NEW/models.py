from dataclasses import asdict, dataclass
from datetime import datetime

ID_UNSET = -1


@dataclass
class BaseDataClass:
    """Base dataclass model."""

    def to_dict(self) -> dict:
        """Return the dataclass as a dict.

        Returns
        -------
        dict
            Dict representation of the dataclass.

        """
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BaseDataClass":
        """Initialise the dataclass from a dict.

        Parameters
        ----------
        data : dict
            Dict representation of the dataclass.

        Returns
        -------
        cls
            The dataclass initialised from the dict.

        """
        return cls(**data)


@dataclass
class User(BaseDataClass):
    """User dataclass."""

    user_id: int
    user_name: str
    city: str = ""
    country_code: str = ""
    bad_word: str = ""


@dataclass
class Reminder(BaseDataClass):
    """Reminder dataclass."""

    user_id: int
    channel_id: int
    date_iso: str
    content: str
    tagged_users: list[str] | None = None
    reminder_id: int = ID_UNSET
