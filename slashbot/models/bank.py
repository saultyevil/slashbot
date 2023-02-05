#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Bank ORM class.
"""


from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey

from slashbot.db import Base
from slashbot.db import User


class BankAccount(Base):
    """Bank ORM class."""

    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), unique=True)

    balance: Mapped[int]
    status: Mapped[str]

    user: Mapped["User"] = relationship(back_populates="bank_accounts")
