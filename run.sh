#!/usr/bin/env bash
# Launcher for the Cron Manager GUI.
# Auto-detect DISPLAY so the GUI can connect to a working X server.
try_display() {
    local d="$1"
    if DISPLAY="$d" python3 -c "import tkinter as tk; tk.Tk()" >/dev/null 2>&1; then
        echo "$d"
        return 0
    fi
    return 1
}

# Prefer the existing DISPLAY, but verify it; fall back to common ones.
candidates=()
[ -n "$DISPLAY" ] && candidates+=("$DISPLAY")
candidates+=(":0")
candidates+=(":99")

found=""
for cand in "${candidates[@]}"; do
    if found=$(try_display "$cand"); then
        break
    fi
done

if [ -z "$found" ]; then
    echo "ERROR: no working X display found (tried ${candidates[*]})" >&2
    exit 1
fi
export DISPLAY="$found"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
exec python3 "$(dirname "$0")/gui.py" "$@"
