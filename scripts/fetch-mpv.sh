#!/usr/bin/env bash
# Download the distro mpv binary (X11/NVIDIA) without installing packages.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/.tools/bin/mpv"
WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

cd "$WORKDIR"
apt-get download mpv
dpkg-deb -x mpv_*.deb extracted
mkdir -p "$(dirname "$DEST")"
cp extracted/usr/bin/mpv "$DEST"
chmod +x "$DEST"
echo "Installed $DEST"
"$DEST" --version | head -3
