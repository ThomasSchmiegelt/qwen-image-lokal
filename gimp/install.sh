#!/usr/bin/env bash
# Verknuepft das Qwen-Plugin mit GIMPs Plugin-Verzeichnis.
#
# Achtung: GIMP 3.2 benutzt ~/.config/GIMP/3.2/, auch wenn es als Snap laeuft.
# Das Verzeichnis ~/snap/gimp/*/.config/GIMP/3.0/ ist ein Ueberbleibsel und
# wird nicht gelesen.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

TARGET="$(ls -d "$HOME"/.config/GIMP/*/plug-ins 2>/dev/null | sort -V | tail -1 || true)"
if [ -z "$TARGET" ]; then
  CONFIG="$(ls -d "$HOME"/.config/GIMP/* 2>/dev/null | sort -V | tail -1 || true)"
  [ -z "$CONFIG" ] && { echo "Kein GIMP-Konfigurationsverzeichnis gefunden. GIMP einmal starten." >&2; exit 1; }
  TARGET="$CONFIG/plug-ins"
  mkdir -p "$TARGET"
fi

rm -rf "$TARGET/qwen-image"
ln -s "$HERE/qwen-image" "$TARGET/qwen-image"
chmod +x "$HERE/qwen-image/qwen-image.py"

echo "Verknüpft: $TARGET/qwen-image -> $HERE/qwen-image"
echo "GIMP neu starten, dann unter Filter › Qwen."
