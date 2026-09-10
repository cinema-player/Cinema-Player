"""Register the bundled Inter files with the X server before Tk starts."""

from __future__ import annotations

import os
import subprocess

FONTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "assets", "fonts")
)


def register_app_fonts():
    """Add the local Inter TTF files to the X11 font path.

    Pixi's Tk is built without Xft, so fontconfig cannot feed it a TTF.
    The X server can still rasterise the files once they are on its font path.
    """
    # A leftover FONTCONFIG_FILE (from tests or a wrapper) starves this Tk of fonts.
    os.environ.pop("FONTCONFIG_FILE", None)
    regular = os.path.join(FONTS_DIR, "Inter-Regular.ttf")
    if not os.path.isfile(regular):
        return
    _ensure_font_index()
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


def _ensure_font_index():
    if os.path.isfile(os.path.join(FONTS_DIR, "fonts.dir")):
        return
    for command in (["mkfontscale", FONTS_DIR], ["mkfontdir", FONTS_DIR]):
        try:
            subprocess.run(command, capture_output=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return


register_app_fonts()
