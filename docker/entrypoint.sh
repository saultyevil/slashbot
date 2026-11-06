#!/bin/bash

set -euo pipefail

# Clean up Xvfb if it's already running, otherwise we won't be able to start a
# virtual display with the correct DISPLAY variable (required for Firefox for
# Selenium scraping)
pkill Xvfb >/dev/null 2>&1 || true
rm -f /tmp/.X0-lock

# Now create a new virtual display, 1920x1080 so it's big enough
export DISPLAY=:0
Xvfb :0 -ac -screen 0 1920x1080x8 &>/dev/null &
timeout=10  # count down from 10 seconds
while [ ! -e /tmp/.X11-unix/X0 ] && [ $timeout -gt 0 ]; do
  sleep 1
  timeout=$((timeout - 1))
done
if [ $timeout -eq 0 ]; then
  echo "Xvfb failed to start within timeout"
  exit 1
fi

# Tell uv where to create a venv, then sync the packages and run the bot
export UV_PROJECT_ENVIRONMENT=/venv
uv sync --link-mode=copy --no-dev
args=()
case "${DEBUG:-}" in
  1|true|yes|on)
    echo "Launching Slashbot in debug mode"
    args+=(--debug)
    ;;
esac
case "${MARKOV_ON_THE_FLY:-}" in
  1|true|yes|on)
    echo "Using on-the-fly Markov generation"
    args+=(--on-the-fly-markov)
    ;;
esac
exec uv run slashbot "${args[@]}"
