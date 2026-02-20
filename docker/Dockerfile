# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

# Install dependencies for git and selenium functionality
RUN apt update && \
    apt install -y --no-install-recommends git \
    openssh-client \
    wget \
    firefox-esr \
    tar \
    xvfb \
    gcc \
    build-essential \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# If on aarch65, we have to install Geckodriver ourselves. But we'll automate
# installing it for x64 and aarch64, as it's probably less confusing when
# debugging build issues why it only happens on aarch64
RUN ARCH=$(uname -m); \
    case "$ARCH" in \
    x86_64) GD_ARCH=linux64 ;; \
    aarch64) GD_ARCH=linux-aarch64 ;; \
    *) echo "Unsupported arch $ARCH"; exit 0 ;; \
    esac; \
    VERSION=v0.36.0; \
    URL="https://github.com/mozilla/geckodriver/releases/download/$VERSION/geckodriver-$VERSION-$GD_ARCH.tar.gz"; \
    wget -q "$URL" && \
    tar -xzf geckodriver-$VERSION-$GD_ARCH.tar.gz -C /usr/local/bin && \
    chmod +x /usr/local/bin/geckodriver && \
    rm geckodriver-$VERSION-$GD_ARCH.tar.gz && \
    geckodriver --version

# Create slashbot user, required for ssh key shenanigans and update command. Also
# enable git to be OK with the bot directory
RUN useradd -m slashbot && \
    mkdir -p /home/slashbot/.ssh && \
    chown -R slashbot:slashbot /home/slashbot/.ssh && \
    git config --global --add safe.directory /bot && \
    echo "slashbot ALL=(root) NOPASSWD: /usr/bin/Xvfb" >> /etc/sudoers

# Creating a directory for the uv venv. This is on the container, to doesn't
# interfere with the venv in the project directory due to the bind mount
RUN mkdir /venv && chown slashbot:slashbot /venv

# Switch to slashbot and /bot working directory and launch the bot via the
# entrypoint script
USER slashbot
WORKDIR /bot
CMD ["./docker/entrypoint.sh"]
