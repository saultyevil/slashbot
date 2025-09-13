import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

DeclarativeBase = declarative_base()


class UserSQL(DeclarativeBase):
    """SQLAlchemy ORM model for a user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(Integer, unique=True)
    username: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    country_code: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    bad_word: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    letterboxd_username: Mapped[str] = mapped_column(String(64), default=None, nullable=True)

    reminders: Mapped[list["ReminderSQL"]] = relationship(back_populates="user")
    watched_movies: Mapped[list["WatchedMovieSQL"]] = relationship(back_populates="user")


class ReminderSQL(DeclarativeBase):
    """SQLAlchemy ORM model for a reminder."""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel_id: Mapped[int] = mapped_column(Integer)
    date: Mapped[datetime.datetime] = mapped_column(DateTime)
    content: Mapped[str] = mapped_column(String(1024))
    tagged_users: Mapped[str] = mapped_column(String(256), nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["UserSQL"] = relationship(back_populates="reminders")


class WatchedMovieSQL(DeclarativeBase):
    """SQLAlchemy ORM model for a watched movie."""

    __tablename__ = "watched_movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    film_year: Mapped[int] = mapped_column(Integer)
    user_rating: Mapped[float] = mapped_column(Float, default=None, nullable=True)
    watched_date: Mapped[datetime.datetime] = mapped_column(DateTime, default=None, nullable=True)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(512))
    poster_url: Mapped[str] = mapped_column(String(512))

    user: Mapped["UserSQL"] = relationship(back_populates="movies")
