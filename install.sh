#!/bin/sh
set -eu

APP_DIR="$HOME/.local/share/linux-webapp-maker"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

mkdir -p "$APP_DIR" "$BIN_DIR" "$DESKTOP_DIR"
cp "$(dirname "$0")/webapp_maker.py" "$APP_DIR/webapp_maker.py"
cp "$(dirname "$0")/electron_runner.js" "$APP_DIR/electron_runner.js"
cp "$(dirname "$0")/package.json" "$APP_DIR/package.json"
cp "$(dirname "$0")/webapp-maker.svg" "$APP_DIR/webapp-maker.svg"
chmod +x "$APP_DIR/webapp_maker.py"

cat > "$BIN_DIR/linux-webapp-maker" <<EOF
#!/bin/sh
exec "$APP_DIR/webapp_maker.py" "\$@"
EOF
chmod +x "$BIN_DIR/linux-webapp-maker"

cat > "$BIN_DIR/linux-webapp-runner" <<EOF
#!/bin/sh
set -eu
APP_DIR="$APP_DIR"
ELECTRON="\$APP_DIR/node_modules/.bin/electron"
if [ ! -x "\$ELECTRON" ]; then
  ELECTRON="\$(command -v electron || true)"
fi
if [ -z "\$ELECTRON" ]; then
  echo "Electron is not installed. Run: $APP_DIR/install-deps.sh" >&2
  exit 127
fi
export ELECTRON_DISABLE_SANDBOX=1
exec "\$ELECTRON" --no-sandbox --disable-setuid-sandbox "\$APP_DIR/electron_runner.js" "\$@"
EOF
chmod +x "$BIN_DIR/linux-webapp-runner"

cat > "$APP_DIR/install-deps.sh" <<EOF
#!/bin/sh
set -eu
cd "$APP_DIR"
npm install --omit=dev
echo "Electron runtime installed."
EOF
chmod +x "$APP_DIR/install-deps.sh"

cat > "$DESKTOP_DIR/linux-webapp-maker.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Web App Maker
Comment=Create Linux web apps from URLs
Exec=$BIN_DIR/linux-webapp-maker
Icon=$APP_DIR/webapp-maker.svg
Terminal=false
Categories=Network;Utility;
StartupNotify=true
StartupWMClass=linux-webapp-maker
EOF
chmod +x "$DESKTOP_DIR/linux-webapp-maker.desktop"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

echo "Installed. Open 'Web App Maker' from the app menu or run: $BIN_DIR/linux-webapp-maker"
echo "If created apps do not open yet, run: $APP_DIR/install-deps.sh"
