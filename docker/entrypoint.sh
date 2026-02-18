#!/bin/bash

set -e

# Clean up Xvfb if it's running
pkill Xvfb || true
rm -f /tmp/.X0-lock

# Create a virtual display, required for selenium scraping
export DISPLAY=:0
Xvfb :0 -ac -screen 0 1920x1080x8 &
timeout=10
while [ ! -e /tmp/.X11-unix/X0 ] && [ $timeout -gt 0 ]; do
  sleep 1
  timeout=$((timeout - 1))
done
if [ $timeout -eq 0 ]; then
  echo "Xvfb failed to start within timeout"
  exit 1
fi

# Install package dependencies
export UV_PROJECT_ENVIRONMENT=/bot/docker-venv
uv sync --link-mode=copy

# Run the bot
if [ "$DEVELOPMENT_MODE" = true ]; then
    exec uv run slashbot --debug
else
    exec uv run slashbot
fi
