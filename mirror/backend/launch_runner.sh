#!/bin/bash
# Detection Runner Launch Script — invoked by launchd (com.a8ra.mirror-runner)
# Runs dexter pipeline every 5m (market open) or 30m (closed), writes detection JSON.
# Auto-restarts on crash via launchd KeepAlive.

cd "$(dirname "$0")" || exit 1

export DEXTER_ROOT="${DEXTER_ROOT:-$HOME/dexter}"
export RIVER_ROOT="${RIVER_ROOT:-$HOME/phoenix-river}"
export PYTHONPATH="$HOME/dexter/dexter:$HOME/dexter/scripts"
export PYTHONUNBUFFERED=1

if [ -f "$HOME/dexter/.venv/bin/python3" ]; then
    exec "$HOME/dexter/.venv/bin/python3" detection_runner.py "$@"
else
    echo "ERROR: dexter venv not found at $HOME/dexter/.venv/bin/python3" >&2
    exit 1
fi
