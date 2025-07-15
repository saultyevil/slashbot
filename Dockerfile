# syntax=docker/dockerfile:1

FROM python:3.11-slim-bookworm

# Install dependencies for some commands
RUN apt update && \
    apt install -y git openssh-client wget firefox-esr tar xvfb

RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux-aarch64.tar.gz && \
    tar -xzvf geckodriver-v0.33.0-linux-aarch64.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/geckodriver && \
    geckodriver -V

# Create slashbot user, required for ssh key shenanigans and update command
RUN useradd -m slashbot
RUN mkdir -p /home/slashbot/.ssh
RUN chown -R slashbot:slashbot /home/slashbot/.ssh

# This enables git to be OK with adding this directory, so we can use the
# git update command
RUN git config --global --add safe.directory /bot
RUN echo "slashbot ALL=(root) NOPASSWD: /usr/bin/Xvfb" >> /etc/sudoers

# Install poetry via pip
USER slashbot
RUN pip install poetry
ENV PATH="/home/slashbot/.local/bin:$PATH"

# Copy the poetry files to cache them in docker layer
WORKDIR /bot
COPY poetry.lock pyproject.toml README.md ./
RUN poetry install --no-interaction --no-ansi --no-root

# Switch to slashbot and run bot
CMD ["./docker/entrypoint.sh"]
