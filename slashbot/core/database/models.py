from dataclasses import asdict, dataclass
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
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
    tagged_users: str | None = None
    reminder_id: int = ID_UNSET


WikiFeetSqlBase = declarative_base()


class WikiFeetModel(WikiFeetSqlBase):
    """SQLAlchemy ORM model for a model on WikiFeet."""

    __tablename__ = "wikifeet_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime)

    foot_score: Mapped[float] = mapped_column(Float)
    shoe_size: Mapped[int] = mapped_column(Integer)
    height_cm: Mapped[float] = mapped_column(Float)
    age: Mapped[int] = mapped_column(Integer)
    nationality: Mapped[str] = mapped_column(String)

    pictures: Mapped[list["WikiFeetPicture"]] = relationship(back_populates="model")


class WikiFeetPicture(WikiFeetSqlBase):
    """SQLAlchemy ORM model for an image from WikiFeet."""

    __tablename__ = "wikifeet_pictures"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("wikifeet_models.id"))
    picture_id: Mapped[int] = mapped_column(Integer)
    model: Mapped["WikiFeetModel"] = relationship(back_populates="pictures")
