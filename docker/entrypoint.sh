#!/bin/bash

# Install missing python dependencies as the Dockerfile uses --no-root. Capture
# the output and only print if something went wrong
output=$(poetry install 2>&1)
if [ $? -ne 0 ]; then
    echo "Poetry install failed:"
    echo "$output"
    exit 1
fi

# Create a virtual display, required for selenium scraping
export DISPLAY=:0
Xvfb :0 -ac -screen 0 1920x1080x8 &
sleep 2

# Run the bot
if [ "$DEVELOPMENT_MODE" = true ]; then
    exec poetry run slashbot --debug
else
    exec poetry run slashbot
fi
