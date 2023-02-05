#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bad word ORM class.
"""

from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped

from slashbot.db import Base


class BadWord(Base):
    """Bad word storage."""

    __tablename__ = "bad_words"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    bad_word: Mapped[str] = mapped_column(unique=True)
