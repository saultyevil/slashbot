import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

DeclarativeBase = declarative_base()


class UserSQL(DeclarativeBase):
    """SQLAlchemy ORM model for a user.

    Attributes
    ----------
    id : int
        Primary key for the user.
    discord_id : int
        Discord user ID (unique). Required.
    username : str
        Username of the user. Required.
    city : str, optional
        City of the user (nullable).
    country_code : str, optional
        Country code of the user (nullable).
    bad_word : str, optional
        Custom bad word for the user (nullable).
    letterboxd_username : str, optional
        Letterboxd username (unique, nullable).
    reminders : list[ReminderSQL]
        List of reminders associated with the user.
    watched_movies : list[WatchedMovieSQL]
        List of watched movies associated with the user.

    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int] = mapped_column(Integer, unique=True)
    username: Mapped[str] = mapped_column(String(64))
    city: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    country_code: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    bad_word: Mapped[str] = mapped_column(String(64), default=None, nullable=True)
    letterboxd_username: Mapped[str] = mapped_column(String(64), default=None, nullable=True, unique=True)

    reminders: Mapped[list["ReminderSQL"]] = relationship(back_populates="user")
    watched_movies: Mapped[list["WatchedMovieSQL"]] = relationship(back_populates="user")


class ReminderSQL(DeclarativeBase):
    """SQLAlchemy ORM model for a reminder.

    Attributes
    ----------
    id : int
        Primary key for the reminder.
    user_id : int
        Foreign key referencing the user.
    channel_id : int
        Discord channel ID for the reminder.
    date : datetime.datetime
        Date and time for the reminder.
    content : str
        Content of the reminder.
    tagged_users : str, optional
        Comma-separated list of tagged users (nullable).
    notified : bool
        Whether the reminder has been notified.
    user : UserSQL
        Reference to the associated user.

    """

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
    """SQLAlchemy ORM model for a watched movie.

    Attributes
    ----------
    id : int
        Primary key for the watched movie.
    user_id : int
        Foreign key referencing the user.
    username : str
        Username of the user who watched the movie.
    title : str
        Title of the movie.
    film_year : int
        Year the film was released.
    published_date : datetime.datetime
        Date the review or entry was published.
    user_rating : float, optional
        User's rating for the movie (nullable).
    watched_date : datetime.datetime, optional
        Date the movie was watched (nullable).
    tmdb_id : int
        TMDB ID for the movie.
    url : str
        URL to the movie entry.
    poster_url : str
        URL to the movie poster.
    user : UserSQL
        Reference to the associated user.

    """

    __tablename__ = "watched_movies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    film_year: Mapped[int] = mapped_column(Integer)
    published_date: Mapped[datetime.datetime] = mapped_column(DateTime)
    user_rating: Mapped[float] = mapped_column(Float, default=None, nullable=True)
    watched_date: Mapped[datetime.datetime] = mapped_column(DateTime, default=None, nullable=True)
    tmdb_id: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(512))
    poster_url: Mapped[str] = mapped_column(String(512))

    user: Mapped["UserSQL"] = relationship(back_populates="watched_movies")
