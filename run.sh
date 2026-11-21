#!/usr/bin/env bash
# Launcher for the Cron Manager GUI.
exec python3 "$(dirname "$0")/gui.py" "$@"
