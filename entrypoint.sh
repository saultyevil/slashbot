#!/bin/bash
poetry install > /dev/null
if [ "$DEVELOPMENT_MODE" = true ]; then
    exec poetry run slashbot --debug
else
    exec poetry run slashbot
fi
