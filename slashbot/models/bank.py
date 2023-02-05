#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bank ORM class.
"""

from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

from slashbot.db import Base
from slashbot.db import User


class BankAccount(Base):
    """Bank ORM class."""

    __tablename__ = "bank_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), unique=True)

    balance = Column(Integer)
    status = Column(String)

    user = relationship(User)
