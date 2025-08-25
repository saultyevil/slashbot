import datetime
from dataclasses import asdict, dataclass

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
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

    reminders: Mapped[list["Reminder"]] = relationship(back_populates="user")


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


class WikiFeetModel(DeclarativeBase):
    """SQLAlchemy ORM model for a model on WikiFeet."""

    __tablename__ = "wikifeet_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    model_name: Mapped[str] = mapped_column(String, unique=True)
    last_updated: Mapped[datetime.datetime] = mapped_column(DateTime)

    foot_score: Mapped[float] = mapped_column(Float)
    shoe_size: Mapped[int] = mapped_column(Integer)

    pictures: Mapped[list["WikiFeetPicture"]] = relationship(back_populates="model")
    comments: Mapped[list["WikiFeetComment"]] = relationship(back_populates="model")


class WikiFeetPicture(DeclarativeBase):
    """SQLAlchemy ORM model for an image from WikiFeet."""

    __tablename__ = "wikifeet_pictures"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("wikifeet_models.id"))
    picture_id: Mapped[int] = mapped_column(Integer, unique=True)
    model: Mapped["WikiFeetModel"] = relationship(back_populates="pictures")


class WikiFeetComment(DeclarativeBase):
    """SQLAlchemy ORM model for comments on WikiFeet."""

    __tablename__ = "wikifeet_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("wikifeet_models.id"))

    comment: Mapped[str] = mapped_column(String(512), unique=True)  # comment
    user: Mapped[str] = mapped_column(String(64))  # nickname
    user_title: Mapped[str] = mapped_column(String(64))  # title

    model: Mapped["WikiFeetModel"] = relationship(back_populates="comments")
