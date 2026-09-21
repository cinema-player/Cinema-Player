#!/usr/bin/env bash
# Install Cinema Player dependencies, the application icon, and a launcher.
set -euo pipefail

ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$ROOT"
export PATH="${HOME}/.pixi/bin:${PATH}"

APT_PACKAGES=(
  mpv
  ffmpeg
  x11-xserver-utils
  xfonts-utils
  mutter-common-bin
  edid-decode
  curl
  ca-certificates
)

log() {
  printf '%s\n' "$*"
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_apt_packages() {
  local missing=()
  local pkg
  if ! need_cmd dpkg; then
    log "Kein Debian/Ubuntu erkannt. Bitte mpv, ffmpeg, xrandr und gdctl manuell installieren."
    return 0
  fi
  for pkg in "${APT_PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
      missing+=("$pkg")
    fi
  done
  if ((${#missing[@]} == 0)); then
    log "Systempakete sind bereits installiert."
    return 0
  fi
  log "Installiere Systempakete: ${missing[*]}"
  sudo apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}"
}

install_pixi() {
  if need_cmd pixi; then
    log "Pixi ist bereits installiert."
    return 0
  fi
  log "Installiere Pixi…"
  curl -fsSL https://pixi.sh/install.sh | bash
  export PATH="${HOME}/.pixi/bin:${PATH}"
  if ! need_cmd pixi; then
    echo "Pixi wurde installiert, ist aber nicht im PATH. Terminal neu öffnen und ./install.sh erneut ausführen." >&2
    exit 1
  fi
}

install_python_env() {
  log "Installiere die Python-Umgebung (Pixi)…"
  pixi install
}

install_icon() {
  log "Lege das Anwendungsicon an…"
  "$ROOT/scripts/install-icon.sh"
}

write_desktop_file() {
  local dest="$1"
  mkdir -p "$(dirname "$dest")"
  cat > "$dest" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Cinema Player
Comment=Video player for a cinematic experience
Exec=${ROOT}/start
Icon=cinema-player
Path=${ROOT}
Terminal=false
StartupNotify=true
Categories=AudioVideo;Player;Video;
EOF
  chmod +x "$dest"
}

install_launchers() {
  local applications="${HOME}/.local/share/applications/cinema-player.desktop"
  local desktop="${HOME}/Desktop/cinema-player.desktop"
  log "Installiere Starter…"
  write_desktop_file "$applications"
  if [[ -d "${HOME}/Desktop" ]]; then
    write_desktop_file "$desktop"
    if need_cmd gio; then
      gio set "$desktop" metadata::trusted true 2>/dev/null || true
    fi
  fi
  if need_cmd update-desktop-database; then
    update-desktop-database "${HOME}/.local/share/applications" 2>/dev/null || true
  fi
}

install_decklink_support() {
  if ! need_cmd dpkg; then
    return 0
  fi
  if dpkg -s gstreamer1.0-plugins-bad >/dev/null 2>&1; then
    log "GStreamer DeckLink-Plugin ist installiert."
    return 0
  fi
  if apt-cache show gstreamer1.0-plugins-bad >/dev/null 2>&1; then
    log "Installiere gstreamer1.0-plugins-bad (DeckLink)…"
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y gstreamer1.0-plugins-bad \
      || log "Hinweis: gstreamer1.0-plugins-bad konnte nicht installiert werden."
  fi
}

log "Cinema Player Installation"
log "Verzeichnis: $ROOT"
install_apt_packages
install_decklink_support
install_pixi
install_python_env
install_icon
install_launchers
log "Fertig. Start mit ${ROOT}/start oder über den Starter Cinema Player."
log "Für DeckLink: Blackmagic Desktop Video installieren. Distro-ffmpeg hat oft kein DeckLink; dann gstreamer1.0-plugins-bad (decklinkvideosink) verwenden."
