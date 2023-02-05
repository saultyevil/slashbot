#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This module contains functions for modifying the slashbot database."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Session

from slashbot.config import App


class Base(DeclarativeBase):
    pass


from slashbot.models.users import User
from slashbot.models.reminders import Reminder
from slashbot.models.bad_words import BadWord
from slashbot.models.oracle_words import OracleWord


def connect_to_database_engine(location: str = None):
    """Create a database engine.

    Creates an Engine object which is used to create a database session.

    Parameters
    ----------
    location : str
        The location of the SQLite database to load, deafault is None where the
        value is then taken from App.config.
    """
    if not location:
        location = App.config("DATABASE_LOCATION")

    engine = create_engine(f"sqlite:///{location}")
    Base.metadata.create_all(bind=engine)

    return engine


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
