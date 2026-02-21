#!/bin/bash

set -euo pipefail

case "${DEBUG:-}" in
  1|true|yes|on)
    echo "Launching Slashbot in debug mode"
    exec uv run src/slashbot/cli/run.py --debug
    ;;
  *)
    exec uv run src/slashbot/cli/run.py
    ;;
esac
