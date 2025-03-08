#!/bin/bash
poetry install
if [ "$DEVELOPMENT_MODE" = true ]; then
    exec poetry run slashbot --debug
else
    exec poetry run slashbot
fi
