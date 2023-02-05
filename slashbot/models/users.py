#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""User ORM class.
"""

from sqlalchemy import String
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped

from slashbot.db import Base


class User(Base):
    """User ORM class.

    Parameters
    ----------
    Base : _type_
        _description_
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(unique=True, index=True)

    city: Mapped[str]
    country_code: Mapped[str] = mapped_column(String(2))
    badword: Mapped[str]
