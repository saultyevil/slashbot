#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bad word ORM class.
"""

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Column

from slashbot.db import Base


class OracleWord(Base):
    """Oracle word storage."""

    __tablename__ = "oracle_words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    word = Column(String, unique=True)
