#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This module contains functions for modifying the slashbot database."""

import json
import pathlib
import logging

from sqlalchemy import create_engine
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session

from slashbot.config import App

# Models -----------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for ORM definition."""


class User(Base):
    """User ORM class.

    Parameters
    ----------
    Base : _type_
        _description_
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True, index=True)
    user_name = Column(String(64), unique=True)

    city = Column(Integer, nullable=True)
    country_code = Column(String(2), nullable=True)
    bad_word = Column(String(32), nullable=True)

    bank_account = relationship("BankAccount")
    reminders = relationship("Reminder")


class BadWord(Base):
    """Bad word storage."""

    __tablename__ = "bad_words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String(32), unique=True)


class BankAccount(Base):
    """Bank ORM class."""

    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), unique=True)

    balance = Column(Integer)
    status = Column(String)

    user = relationship("User", back_populates="bank_account")


class OracleWord(Base):
    """Oracle word storage."""

    __tablename__ = "oracle_words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String, unique=True)


class Reminder(Base):
    """User ORM class.

    Parameters
    ----------
    Base : _type_
        _description_
    """

    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))

    channel = Column(String)
    tagged_users = Column(String, nullable=True)
    date = Column(DateTime(timezone=True))
    reminder = Column(String(1024))
    tagged_users = Column(String(1024), nullable=True)

    user = relationship("User", back_populates="reminders")


class Image(Base):
    """_summary_

    Parameters
    ----------
    Base : _type_
        _description_
    """

    __tablename__ = "images"
    id = Column(Integer, primary_key=True, autoincrement=True)
    image_url = Column(String(256), index=True)


class Tweet(Base):
    """_summary_

    Parameters
    ----------
    Base : _type_
        _description_
    """

    __tablename__ = "tweets"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user = Column(String(64), index=True)
    date = Column(DateTime(), index=True)
    tweet = Column(String(280), nullable=True)
    image_url = Column(String(256))
    tweet_url = Column(String(256))


# Functions --------------------------------------------------------------------

logger = logging.getLogger(App.config("LOGGER_NAME"))


def connect_to_database_engine(location: str = None):
    """Create a database engine.

    Creates an Engine object which is used to create a database session.

    Parameters
    ----------
    location : str
        The location of the SQLite database to load, default is None where the
        value is then taken from App.config.
    """
    if not location:
        location = App.config("DATABASE_LOCATION")

    engine = create_engine(f"sqlite:///{location}")
    Base.metadata.create_all(bind=engine)

    return engine


async def migrate_old_json_to_db(client) -> None:
    """Migrate data stuck in a JSON backup to the database.

    This is typically run each time the bot is started up, as the JSON files
    should be unchanging. If a user is already in the database, then whatever
    is in the JSON is ignored.
    """
    with Session(connect_to_database_engine()) as session:
        if (path := pathlib.Path("data/users.json")).exists():
            with open(path, "r", encoding="utf-8") as file_in:
                user_json = json.load(file_in)
            for user_id, items in user_json.items():
                query = session.query(User).filter(User.user_id == int(user_id))
                if query.count() != 0:
                    continue
                user = await client.fetch_user(int(user_id))
                if user is None:
                    logger.error("Unable to find a user with id %d", int(user_id))
                    continue
                session.add(
                    User(
                        user_id=int(user_id),
                        user_name=user.name,
                        city=items.get("location", None),
                        country_code=items.get("country", None),
                        bad_word=items.get("badword", None),
                    )
                )

        # reminders.json and bank.json would go here, but I think there's
        # usually nothing worthwhile migrating over to an empty database.

        session.commit()


def create_new_user(session: Session, user_id: int, user_name: str) -> User:
    """Create a new user row.

    Creates a new user row, populating only the user ID and user name. The
    new row is returned.

    Parameters
    ----------
    session : Session
        A session to the slashbot database.
    user_id : int
        The Discord user ID for the new entry.
    user_name : str
        The Discord user name for the new entry.

    Returns
    -------
    User :
        The newly created User entry.
    """
    session.add(
        new_user := User(
            user_id=user_id,
            user_name=user_name,
        )
    )
    session.commit()

    # refresh to return the user instead of having to query again
    session.refresh(new_user)

    return new_user


def get_user(session: Session, user_id: int, user_name: str) -> User:
    """Get a user from the database.

    Parameters
    ----------
    session : Session
        A session for the slashbot database.
    user_id : int
        The Discord ID of the user.
    user_name : str
        The Discord name of the user.

    Returns
    -------
    User
        The user database entry.
    """
    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        user = create_new_user(session, user_id, user_name)

    return user


def populate_word_tables_with_new_words() -> None:
    """Populate the bad word and oracle world tables in the database."""

    with open(App.config("BAD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
        words = file_in.read().splitlines()
    with Session(connect_to_database_engine()) as session:
        for word in words:
            query = session.query(BadWord).filter(BadWord.word == word)
            if query.count() == 0:
                session.add(BadWord(word=word))
        session.commit()

    with open(App.config("GOD_WORDS_FILE"), "r", encoding="utf-8") as file_in:
        words = file_in.read().splitlines()
    with Session(connect_to_database_engine()) as session:
        for word in words:
            query = session.query(OracleWord).filter(OracleWord.word == word)
            if query.count() == 0:
                session.add(OracleWord(word=word))
        session.commit()


def create_new_bank_account(session: Session, user_id: int) -> BankAccount:
    """Create a new back account row.

    Parameters
    ----------
    session : Session
        A session for the slashbot database.
    user_id : int
        The Discord ID of the user.

    Returns
    -------
    BankAccount
        The newly created BankAccount entry.
    """

    session.add(
        new_account := BankAccount(
            user_id=user_id,
            balance=App.config("CONTENT_BANK_STARTING_BALANCE"),
            status="Newfag",
        )
    )
    session.commit()

    # refresh to return the user instead of having to query again
    session.refresh(new_account)

    return new_account


def get_bank_account(session: Session, user_id: int) -> BankAccount:
    """Get a bank account from the database.

    Parameters
    ----------
    session : Session
        A session for the slashbot database.
    user_id : int
        The Discord ID of the user.

    Returns
    -------
    BankAccount
        The BankAccount database entry.
    """
    account = session.query(BankAccount).filter(BankAccount.user_id == user_id).first()
    if not account:
        account = create_new_bank_account(session, user_id)

    return account
