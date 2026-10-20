"""Make the bundled Inter files visible before Tk opens a display."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

FONTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
)
SYSTEM_FONTCONFIG = "/etc/fonts/fonts.conf"


def fontconfig_source(fonts_dirs, system_config=SYSTEM_FONTCONFIG):
    """Fontconfig document that adds directories and keeps system fonts."""
    if isinstance(fonts_dirs, (str, os.PathLike)):
        fonts_dirs = [fonts_dirs]
    system = os.path.abspath(system_config)
    lines = [
        '<?xml version="1.0"?>',
        "<fontconfig>",
        f'  <include ignore_missing="yes">{_xml(system)}</include>',
    ]
    for fonts_dir in fonts_dirs:
        lines.append(f"  <dir>{_xml(os.path.abspath(fonts_dir))}</dir>")
    lines.append("</fontconfig>")
    return "\n".join(lines) + "\n"


def font_directories():
    """Bundled Inter, plus faces shipped with the Python environment."""
    dirs = [FONTS_DIR]
    prefix_fonts = os.path.join(sys.prefix, "fonts")
    if os.path.isdir(prefix_fonts) and prefix_fonts not in dirs:
        dirs.append(prefix_fonts)
    return dirs


def register_app_fonts():
    """Publish Inter to fontconfig and, as a fallback, to the X font path.

    Pixi's default Tk is built without Xft, so it cannot ask fontconfig for a
    TTF and falls back to a bitmap face. The xft build uses fontconfig. A
    leftover FONTCONFIG_FILE that omits the system config would hide every
    family except the one directory it lists.
    """
    os.environ.pop("FONTCONFIG_FILE", None)
    regular = os.path.join(FONTS_DIR, "Inter-Regular.ttf")
    if not os.path.isfile(regular):
        return
    _publish_fontconfig()
    _ensure_font_index()
    _add_x_font_path()


def _publish_fontconfig():
    path = os.path.join(
        tempfile.gettempdir(), f"cinema-player-fonts-{os.getuid()}.conf"
    )
    payload = fontconfig_source(font_directories())
    try:
        current = ""
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                current = handle.read()
        if current != payload:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
    except OSError:
        return
    os.environ["FONTCONFIG_FILE"] = path


def _xml(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ensure_font_index():
    if os.path.isfile(os.path.join(FONTS_DIR, "fonts.dir")):
        return
    for command in (["mkfontscale", FONTS_DIR], ["mkfontdir", FONTS_DIR]):
        try:
            subprocess.run(command, capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return


def _add_x_font_path():
    """Core-font fallback for a Tk built without Xft."""
    try:
        query = subprocess.run(
            ["xset", "q"], capture_output=True, text=True, timeout=2
        )
        if FONTS_DIR in (query.stdout or ""):
            return
        subprocess.run(
            ["xset", "+fp", FONTS_DIR], capture_output=True, timeout=2, check=False
        )
        subprocess.run(
            ["xset", "fp", "rehash"], capture_output=True, timeout=2, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


register_app_fonts()
