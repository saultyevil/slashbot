#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""User ORM class.
"""

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Column

from slashbot.db import Base


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
