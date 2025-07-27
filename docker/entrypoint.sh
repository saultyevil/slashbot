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

# Install missing python dependencies as the Dockerfile uses --no-root. Capture
# the output and only print if something went wrong
if ! poetry install >poetry_install.log 2>&1; then
    echo "Poetry install failed, see poetry_install.log:"
    cat poetry_install.log
    exit 1
fi

# Run the bot
if [ "$DEVELOPMENT_MODE" = true ]; then
    exec poetry run slashbot --debug
else
    exec poetry run slashbot
fi
