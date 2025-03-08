# syntax=docker/dockerfile:1

FROM python:3.11-slim-buster

# Create slashbot user, required for ssh key shenanigans and update command
RUN useradd -m slashbot
RUN mkdir -p /home/slashbot/.ssh
RUN chown -R slashbot:slashbot /home/slashbot/.ssh

# Install git and openssh, required for update command
RUN apt update && apt install -y git openssh-client

# This enables git to be OK with adding this directory, so we can use the
# git update command
RUN git config --global --add safe.directory /bot

# Install poetry via pip
USER slashbot
RUN pip install poetry
ENV PATH="/home/slashbot/.local/bin:$PATH"

# Copy the poetry files to cache them in docker layer
WORKDIR /bot
COPY poetry.lock pyproject.toml README.md ./
RUN poetry install --no-interaction --no-ansi --no-root

# Switch to slashbot and run bot
CMD ["./entrypoint.sh"]
