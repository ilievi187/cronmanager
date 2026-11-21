# Cron Manager

A sleek, human-friendly **native Linux scheduled task manager** built with **Python + Qt 6 (`PySide6`)** that adapts **live** to your active **Omarchy** desktop theme.

[![License: MIT](https://img.shields.io/badge/License-MIT-7376b7.svg)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Support-Buy%20Me%20a%20Coffee-FFDD00?logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/aurorauap)

## Features

- **Native Linux Scheduling:** Automatically manages real Linux **`systemd --user` timers** (works out of the box on Arch/Omarchy, Ubuntu, Debian, Fedora, openSUSE — no `sudo` or `cronie` required) with automatic **`crontab`** fallback on non-systemd setups.
- **Live Omarchy Theme Sync:** Reads `~/.local/state/omarchy/current/theme/colors.toml` and Hyprland's `decoration:rounding` in real time — switching Omarchy themes immediately updates colors, gradients, and hover glow effects.
- **Human-Friendly UI:**
  - Card-based task list with status badges, human-readable schedules, monospace command pills, and real `Next:` trigger times.
  - Inline quick actions (**Run Now**, **Pause / Resume**, **Logs**, **Edit**, **Delete**) with smooth animated accent glow on hover.
  - Visual task creator with 1-click schedule presets (`Every 5 min`, `Every 15 min`, `Every hour`, `Daily 09:00`, `Mondays 09:00`, `At Startup`), friendly interval builder, script file browser, and starter command examples.
  - Live search (`Ctrl+F`), status filters (`All`, `Active`, `Paused`), keyboard shortcuts (`Ctrl+N`, `Ctrl+R`, `Ctrl+Q`), and execution log viewer (`journalctl` + manual run history).

## Requirements

- Linux (Wayland or X11)
- Python 3.11+
- `PySide6` (`sudo pacman -S pyside6` on Arch/Omarchy, or `pip install PySide6`)

## Quick Start

```bash
git clone https://github.com/ilievi187/cronmanager.git
cd cronmanager
./run.sh
```

## License

Licensed under the [MIT License](LICENSE).
