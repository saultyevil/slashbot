import datetime
from dataclasses import asdict, dataclass

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

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
class UserKVModel(BaseDataClass):
    """User dataclass."""

    user_id: int
    user_name: str
    city: str = ""
    country_code: str = ""
    bad_word: str = ""


@dataclass
class ReminderKVModel(BaseDataClass):
    """Reminder dataclass."""

    user_id: int
    channel_id: int
    date_iso: str
    content: str
    tagged_users: str | None = None
    reminder_id: int = ID_UNSET


DeclarativeBase = declarative_base()


class User(DeclarativeBase):
    """SQLAlchemy ORM model for a user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(Integer, unique=True)
    username: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    country_code: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    bad_word: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    letterboxd_user: Mapped[str] = mapped_column(String(64), default=None, nullable=True)

    reminders: Mapped[list["Reminder"]] = relationship(back_populates="user")
    movies: Mapped[list["WatchedMovie"]] = relationship(back_populates="user")


class Reminder(DeclarativeBase):
    """SQLAlchemy ORM model for a reminder."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime.datetime] = mapped_column(DateTime)
    content: Mapped[str] = mapped_column(String(1024))
    tagged_users: Mapped[str] = mapped_column(String(256), nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="reminders")


class WatchedMovie(DeclarativeBase):
    """SQLAlchemy ORM model for a watched movie."""

    __tablename__ = "movies_watched"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    date: Mapped[datetime.datetime] = mapped_column(DateTime)
    tmbd_id: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(512))
    poster_url: Mapped[str] = mapped_column(String(512))

    user: Mapped["User"] = relationship(back_populates="movies")
