#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bad word ORM class.
"""

from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped

from slashbot.db import Base


class OracleWord(Base):
    """Oracle word storage."""

    __tablename__ = "oracle_words"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    oracle_word: Mapped[str] = mapped_column(unique=True)

