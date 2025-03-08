#!/bin/bash
if [ "$DEVELOPMENT_MODE" = true ]; then
    exec python run.py --debug
else
    exec python run.py
fi
