"""Contains functions for modifying the slashbot database."""

import pickle
from multiprocessing import Pool

import markovify
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship

# Models -----------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for ORM definition."""


class ChannelMessage(Base):
    __tablename__ = "channel_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True)
    message_id = Column(Integer, index=True)
    channel_id = Column(Integer, nullable=True)
    server_id = Column(Integer, nullable=True)
    date = Column(DateTime, index=True)
    user_name = Column(String(64))
    message = Column(String(2048))
    attachments = relationship("MessageAttachment")


class MessageAttachment(Base):
    __tablename__ = "message_attachments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("channel_messages.message_id"), index=True)
    content_type = Column(String(64))
    url = Column(String(256))
    message = relationship("ChannelMessage", back_populates="attachments")


# Functions --------------------------------------------------------------------


def connect_to_database_engine(location):
    engine = create_engine(f"sqlite:///{location}")
    Base.metadata.create_all(bind=engine)

    return engine


def train_model(state_size, messages):
    print("Starting state size:", state_size)
    new_model = markovify.NewlineText(messages, state_size=state_size)
    with open(f"chain-{state_size}.pickle", "wb") as chain_out:
        pickle.dump(new_model.chain, chain_out)
    print("Completed state size:", state_size)


num_processes = 4
state_sizes = range(1, 5, 1)

database = connect_to_database_engine("/home/saultyevil/slashbot/data/scrapebot.sqlite.db")
with Session(database) as session:
    messages = "\n".join([result.message for result in session.query(ChannelMessage.message).all()])

with Pool(num_processes) as pool:
    pool.starmap(train_model, [(size, messages) for size in state_sizes])
