#!/bin/bash
if [ "$DEVELOPMENT_MODE" = true ]; then
    exec python run.py --development
else
    exec python run.py
fi