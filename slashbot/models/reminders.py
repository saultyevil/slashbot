#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Reminders ORM class.
"""

import datetime

from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from sqlalchemy import ForeignKey

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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))

    whofor: Mapped[str]
    channel: Mapped[int]
    tag: Mapped[str]
    when: Mapped[datetime.datetime]
    what: Mapped[str]

    user: Mapped[User] = relationship(back_populates="reminders")
