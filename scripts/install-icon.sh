#!/usr/bin/env bash
# Register the Cinema Player icon in the user icon theme.
# .desktop Icon=cinema-player must resolve here — relative paths do not work
# for Desktop shortcuts.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
ICON_SRC="$ROOT/assets/logo/cinema-player-icon.png"

if [[ ! -f "$ICON_SRC" ]]; then
  echo "Cinema Player: Icon nicht gefunden: $ICON_SRC" >&2
  exit 1
fi

for size in 32 48 64 128; do
  dest="${HOME}/.local/share/icons/hicolor/${size}x${size}/apps"
  mkdir -p "$dest"
  ln -sfn "$ICON_SRC" "$dest/cinema-player.png"
done
