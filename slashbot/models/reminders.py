#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Reminders ORM class.
"""

from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from slashbot.db import Base
from slashbot.db import User


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
    date = Column(DateTime)
    reminder = Column(String(1024))
    tagged_users = Column(String(1024), nullable=True)

    user = relationship(User)
