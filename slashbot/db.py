#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This module contains functions for modifying the slashbot database."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase

from slashbot.config import App


class Base(DeclarativeBase):
    pass


from slashbot.models.users import User
from slashbot.models.reminders import Reminder


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
