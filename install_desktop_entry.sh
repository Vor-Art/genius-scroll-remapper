#!/usr/bin/env bash
set -euo pipefail

APP_ID="genius-remapper"
APP_NAME="Genius Mouse Scroll Remapper"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
ICON_SRC="$APP_DIR/assets/genius_remapper.svg"
ICON_DST="$ICON_DIR/${APP_ID}.svg"
DESKTOP_FILE="$DESKTOP_DIR/${APP_ID}.desktop"
EXEC_CMD="/usr/bin/env python3 $APP_DIR/mouse_remapper_app.py"

mkdir -p "$DESKTOP_DIR" "$ICON_DIR"

if [[ -f "$ICON_SRC" ]]; then
  cp "$ICON_SRC" "$ICON_DST"
else
  echo "Warning: icon not found at $ICON_SRC" >&2
fi

cat > "$DESKTOP_FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=$APP_NAME
Exec=$EXEC_CMD
Icon=${APP_ID}
Terminal=false
Categories=Utility;Accessibility;
StartupNotify=true
Path=$APP_DIR
DESKTOP

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo "Desktop entry installed to $DESKTOP_FILE"
echo "Icon installed to $ICON_DST"
