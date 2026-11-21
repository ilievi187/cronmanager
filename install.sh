#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
APP_ID="cronmanager"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
APPS_DIR="${HOME}/.local/share/applications"

mkdir -p "${ICON_DIR}" "${APPS_DIR}"
cp "${APP_DIR}/${APP_ID}.svg" "${ICON_DIR}/${APP_ID}.svg"
chmod +x "${APP_DIR}/run.sh" "${APP_DIR}/gui.py"

cat > "${APPS_DIR}/${APP_ID}.desktop" << EOF
[Desktop Entry]
Type=Application
Name=Cron Manager
Comment=Native Linux scheduled task manager (systemd timers & crontab)
Exec=${APP_DIR}/run.sh
Icon=${APP_ID}
Categories=System;Utility;
Keywords=cron;timer;systemd;schedule;tasks;
Terminal=false
StartupWMClass=cronmanager
EOF

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "${APPS_DIR}" || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
echo "Installed Cron Manager shortcut -> ${APPS_DIR}/${APP_ID}.desktop"
