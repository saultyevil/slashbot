# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim

# Install dependencies for some commands
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

# Install Geckodriver which is often missing
RUN ARCH=$(uname -m); \
    case "$ARCH" in \
    x86_64) GD_ARCH=linux64 ;; \
    aarch64) GD_ARCH=linux-aarch64 ;; \
    *) echo "Unsupported arch $ARCH, skipping geckodriver install"; exit 0 ;; \
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

# Switch to slashbot and run bot
WORKDIR /bot
RUN mkdir /venv && chown slashbot:slashbot /venv
USER slashbot
CMD ["./docker/entrypoint.sh"]
