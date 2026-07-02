#!/bin/sh
set -eu

APP_DIR="$HOME/.local/share/linux-webapp-maker"
mkdir -p "$APP_DIR"

cp "$(dirname "$0")/electron_runner.js" "$APP_DIR/electron_runner.js"
cp "$(dirname "$0")/package.json" "$APP_DIR/package.json"

cd "$APP_DIR"
npm install --omit=dev

echo "Electron runtime installed at $APP_DIR."
