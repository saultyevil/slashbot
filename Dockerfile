# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

WORKDIR /bot
SHELL ["/bin/bash", "-c"]

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV PYTHONPATH="${PYTHONPATH}:/bot/lib"

RUN apt update && apt install -y git openssh-client

# This enables git to be OK with adding this directory, so we can use the
# git update command
RUN git config --global --add safe.directory /bot

# Update Python packages
COPY requirements.txt .
RUN pip install -r requirements.txt

#  We need SSH keys for github
RUN useradd -m slashbot
RUN mkdir -p /home/slashbot/.ssh
RUN chown -R slashbot:slashbot /home/slashbot/.ssh
USER slashbot

CMD ["./entrypoint.sh"]
