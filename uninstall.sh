#!/bin/sh
set -eu

rm -f "$HOME/.local/bin/linux-webapp-maker"
rm -f "$HOME/.local/bin/linux-webapp-runner"
rm -f "$HOME/.local/share/applications/linux-webapp-maker.desktop"
rm -rf "$HOME/.local/share/linux-webapp-maker"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

echo "Web App Maker removed. Existing generated .desktop files may remain in ~/.local/share/applications."
