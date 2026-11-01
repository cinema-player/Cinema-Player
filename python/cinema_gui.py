"""Cinema Player control GUI matching the layout mockup."""

from __future__ import annotations

import font_setup  # noqa: F401  — load Inter before tkinter opens fontconfig

import json
import math
import os
import platform
import re
import shutil
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

_dialog_owner = None


def _front_dialog_parent():
    """Popup that should own a standard Tk dialog, if one is already open."""
    owner = _dialog_owner
    if owner is None:
        return None
    try:
        if not owner.root.winfo_exists():
            return None
    except (tk.TclError, AttributeError):
        return None
    try:
        return owner._front_popup()
    except (tk.TclError, AttributeError):
        return None


def _prefer_front_parent(parent):
    """Open a standard dialog above the popup that is already on screen."""
    front = _front_dialog_parent()
    if front is None:
        return parent
    root = getattr(_dialog_owner, "root", None)
    if parent is None or parent is root:
        return front
    return parent


def _bind_dialog_parent(func):
    def wrapped(*args, **kwargs):
        parent = _prefer_front_parent(kwargs.get("parent"))
        if parent is None:
            kwargs.pop("parent", None)
        else:
            kwargs["parent"] = parent
        return func(*args, **kwargs)

    wrapped.__name__ = func.__name__
    wrapped.__doc__ = func.__doc__
    return wrapped


for _dialog_name in (
    "showinfo", "showwarning", "showerror", "askquestion",
    "askokcancel", "askyesno", "askyesnocancel", "askretrycancel",
):
    if hasattr(messagebox, _dialog_name):
        setattr(messagebox, _dialog_name, _bind_dialog_parent(getattr(messagebox, _dialog_name)))

for _dialog_name in (
    "askopenfilename", "askopenfilenames", "asksaveasfilename",
    "askopenfile", "askopenfiles", "asksaveasfile", "askdirectory",
):
    if hasattr(filedialog, _dialog_name):
        setattr(filedialog, _dialog_name, _bind_dialog_parent(getattr(filedialog, _dialog_name)))

for _dialog_name in ("askstring", "askinteger", "askfloat"):
    if hasattr(simpledialog, _dialog_name):
        setattr(simpledialog, _dialog_name, _bind_dialog_parent(getattr(simpledialog, _dialog_name)))

from language import LANGUAGES, t, set_language, current_language
from remote_api import DEFAULT_PORT, RemoteAPIServer, clip_span, clip_times, connect_url
import qr_code
import dmx
from cinema_player import (
    APP_VERSION,
    FONT_FAMILY,
    FONT_ROW,
    FONT_ROW_BOLD,
    FONT_SMALL,
    FONT_STATUS,
    FONT_UI,
    FONT_UI_BOLD,
    IMAGE_EXTS,
    MPVController,
    PlaylistEntry,
    ROOT_DIR,
    VIDEO_EXTS,
    VIDEO_OUTPUT,
    VideoOutputManager,
    TEXT_SIZE_DELTAS,
    TEXT_SIZE_LABELS,
    apply_playlist_warnings,
    apply_text_size,
    clip_needs_settings_warning,
    current_text_size,
    clamp_volume,
    find_mpv,
    find_ffmpeg,
    about_package_rows,
    read_copyright,
    header_version_text,
    read_mpv_version,
    format_bitrate,
    format_clock,
    format_codec_rate,
    format_fps_label,
    format_hwdec_current,
    frames_were_dropped,
    format_colorspace_label,
    format_loudness,
    gpu_context_for_mpv,
    hwdec_for_gpu,
    media_file_available,
    reload_entry_metadata,
    parse_bitrate_bps,
    parse_mpv_count,
    delete_import_directory,
    delete_import_media,
    library_playlists,
    list_removable_volumes,
    merge_import_directories,
    normalize_media_directories,
    path_is_inside,
    place_playlist,
    playlist_entries,
    playlist_for_saved_file,
    media_root_for_playlist,
    resolve_stored_media_path,
    path_is_on_removable_volume,
    playlist_folder_name,
    playlist_location_label,
    playlist_location_short,
    probe_audio,
    probe_media,
    compose_mpv_vf,
    mpv_picture_filter,
    sixteen_nine_hint_fields,
    same_aspect_ratio,
    session_display_name,
    session_is_wayland,
    AUDIO_PATCH_NONE,
    audio_device_menu_label,
    list_mpv_audio_devices,
    normalize_audio_patch_choice,
    unique_audio_device_labels,
    video_output_menu_label,
    audio_route_commands,
    PLAYBACK_AF,
)

LOGO_BG = "#000000"
LOGO_ACCENT = "#4d9be6"
FONT_LOGO = (FONT_FAMILY, 17, "bold")
FONT_LOGO_LIGHT = (FONT_FAMILY, 17)
FONT_BEAMER_PICK = (FONT_FAMILY, 13, "bold")
FONT_TOOLTIP = (FONT_FAMILY, 11)
FONT_EDID = ("DejaVu Sans Mono", 10)
FONT_PLACEHOLDER = (FONT_FAMILY, 16)
FONT_CLOCK = (FONT_FAMILY, 18, "bold")
FONT_HEADER_CLOCK = ("DejaVu Sans Mono", 20, "bold")
MONO_FAMILIES = ("DejaVu Sans Mono", "Liberation Mono", "Ubuntu Mono")


def installed_font_family(candidates, fallback):
    """First candidate Tk can actually load, otherwise the bundled face.

    A missing family becomes the bitmap ``fixed`` and is scaled up. At the
    clock size that looks like large pixels.
    """
    root = getattr(tk, "_default_root", None)
    if root is None:
        return candidates[0] if candidates else fallback
    try:
        import tkinter.font as tkfont
        installed = {name.casefold() for name in tkfont.families(root)}
    except (tk.TclError, ImportError):
        return candidates[0] if candidates else fallback
    for name in candidates:
        if name.casefold() in installed:
            return name
    return fallback


def sync_fonts():
    """Copy scaled fonts from cinema_player into this module's aliases."""
    global FONT_FAMILY, FONT_ROW, FONT_ROW_BOLD, FONT_SMALL, FONT_STATUS
    global FONT_UI, FONT_UI_BOLD, FONT_LOGO, FONT_LOGO_LIGHT
    global FONT_BEAMER_PICK, FONT_TOOLTIP, FONT_EDID, FONT_PLACEHOLDER, FONT_CLOCK
    global FONT_HEADER_CLOCK
    import cinema_player as player

    FONT_FAMILY = player.FONT_FAMILY
    FONT_ROW = player.FONT_ROW
    FONT_ROW_BOLD = player.FONT_ROW_BOLD
    FONT_SMALL = player.FONT_SMALL
    FONT_STATUS = player.FONT_STATUS
    FONT_UI = player.FONT_UI
    FONT_UI_BOLD = player.FONT_UI_BOLD
    delta = player.current_text_size()
    mono = installed_font_family(MONO_FAMILIES, FONT_FAMILY)
    FONT_LOGO = (FONT_FAMILY, max(6, 17 + delta), "bold")
    FONT_LOGO_LIGHT = (FONT_FAMILY, max(6, 17 + delta))
    FONT_BEAMER_PICK = (FONT_FAMILY, max(6, 13 + delta), "bold")
    FONT_TOOLTIP = (FONT_FAMILY, max(6, 11 + delta))
    FONT_EDID = (mono, max(6, 10 + delta))
    FONT_PLACEHOLDER = (FONT_FAMILY, max(6, 16 + delta))
    FONT_CLOCK = (FONT_FAMILY, max(6, 18 + delta), "bold")
    FONT_HEADER_CLOCK = (mono, max(6, 20 + delta), "bold")


LOGO_HEADER_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-logo-header.png")
LOGO_ABOUT_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-logo.png")
LOGO_ICON_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-icon.png")
BEAMER_TEST_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-logo.png")
# mpv log2 zoom: -0.8 ≈ 57% size, so the wide logo does not fill the screen width.
BEAMER_TEST_ZOOM = -0.8
ICONS_DIR = os.path.join(ROOT_DIR, "assets", "icons")
TESTDATA_DIR = os.path.join(ROOT_DIR, "media", "testdata", "videotestdata")
AUDIOSYNC_DIR = os.path.join(ROOT_DIR, "media", "testdata", "audiosyncdata")
IDLE_DIR = os.path.join(ROOT_DIR, "media", "idle")
TRANSPORT_ICON_PX = 52
DRAG_THRESHOLD = 12
AUDIO_DELAY_MIN_MS = -50
AUDIO_DELAY_MAX_MS = 50
AUDIO_DELAY_STEP_MS = 1


def default_idle_media_path():
    """Return the first video or image in the project's idle folder, if any."""
    if not os.path.isdir(IDLE_DIR):
        return ""
    try:
        names = os.listdir(IDLE_DIR)
    except OSError:
        return ""
    paths = [
        os.path.join(IDLE_DIR, name)
        for name in sorted(names)
        if os.path.splitext(name)[1].lower() in VIDEO_EXTS | IMAGE_EXTS
    ]
    return paths[0] if paths else ""

# Status colours keep their meaning in every design.
COLOR_OFF = "#c62828"
COLOR_PROGRAM = "#1565c0"
COLOR_PLAYING = "#2e9d3a"
# How long a Weiter press stays lit if playback itself returns quickly.
RESUME_REACTION_SECONDS = 0.45


def resume_reaction_name(program_state):
    """Colour of a Weiter press: blue arms a stopped show, green rolls or continues."""
    return "program" if program_state == "OFF" else "playing"


def resume_reaction_color(name):
    return COLOR_PROGRAM if name == "program" else COLOR_PLAYING
COLOR_PREVIEW = "#c9a227"
COLOR_CALIBRATION = "#500070"
COLOR_WARNING = "#d32f2f"
COLOR_WHITE = "#ffffff"
# Same warm light-control card as the phone remote.
LIGHT_PANEL = "#241c14"
LIGHT_BORDER = "#6a4a22"
LIGHT_CAPTION = "#e0b060"
LIGHT_BUTTON = "#3a2a18"
LIGHT_BUTTON_TEXT = "#f3e2c4"
LIGHT_ACTIVE = "#c9a227"
LIGHT_ACTIVE_TEXT = "#1a1408"


def light_meter_fill(height, percent):
    """Pixel height of a channel bar, measured up from the bottom."""
    usable = max(0, int(height) - 2)
    span = max(0.0, min(100.0, float(percent))) / 100.0
    return int(round(usable * span))


# Program output eases to a new level instead of stepping. One second is long
# enough to hear the move and short enough to stay with the operator's hand.
PROGRAM_VOLUME_GLIDE_SECONDS = 1.0
PROGRAM_VOLUME_GLIDE_TICK_MS = 40


def program_volume_glide(start, target, elapsed, duration=PROGRAM_VOLUME_GLIDE_SECONDS):
    """Level between start and target after elapsed seconds.

    Smoothstep (3t² − 2t³) so the ramp leaves the old level and settles on the
    new one without a corner. At half the duration the level is the midpoint.
    """
    start = float(start)
    target = float(target)
    try:
        elapsed = float(elapsed)
    except (TypeError, ValueError):
        elapsed = 0.0
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = PROGRAM_VOLUME_GLIDE_SECONDS
    if not math.isfinite(elapsed):
        elapsed = 0.0
    if not math.isfinite(duration) or duration <= 0 or elapsed >= duration:
        return target
    if elapsed <= 0 or start == target:
        return start
    t = elapsed / duration
    smooth = t * t * (3.0 - 2.0 * t)
    return start + (target - start) * smooth

PALETTES = {
    "light": {
        "bg": "#d0d0d0",
        "panel": "#e6e6e6",
        "row": "#efefef",
        "text": "#222222",
        "muted": "#555555",
        "played": "#888888",
        "border": "#b0b0b0",
        "readout": "#ececec",
        "badge_idle": "#bdbdbd",
        "button": "#d9d9d9",
        "button_active": "#ececec",
        "field": "#ffffff",
        "video": "#9a9a9a",
        "track": "#c5c5c5",
        "track_edge": "#9a9a9a",
        "range": "#3b8fd4",
        "playhead": "#1a1a1a",
        "marker": "#16324f",
        "accent": "#1565c0",
        "volume": "#0c8f88",
        "tip_bg": "#f2e6a6",
        "tip_fg": "#1a1a1a",
    },
    "dark": {
        "bg": "#262626",
        "panel": "#303030",
        "row": "#3a3a3a",
        "text": "#e8e8e8",
        "muted": "#a0a0a0",
        "played": "#8b8b8b",
        "border": "#4a4a4a",
        "readout": "#3a3a3a",
        "badge_idle": "#4d4d4d",
        "button": "#414141",
        "button_active": "#4f4f4f",
        "field": "#1f1f1f",
        "video": "#1b1b1b",
        "track": "#4a4a4a",
        "track_edge": "#5f5f5f",
        "range": "#3b8fd4",
        "playhead": "#f5f5f5",
        "marker": "#9dc4ec",
        "accent": "#6cb0ee",
        "volume": "#2ee8dc",
        "tip_bg": "#f2e6a6",
        "tip_fg": "#1a1a1a",
    },
}

DEFAULT_THEME = "dark"
THEME = DEFAULT_THEME


def apply_theme(name):
    """Rebind the palette names so widgets built afterwards use the chosen design."""
    global THEME, COLOR_BG, COLOR_PANEL, COLOR_ROW, COLOR_TEXT, COLOR_MUTED, COLOR_PLAYED
    global COLOR_BORDER, COLOR_READOUT, COLOR_BADGE_IDLE, COLOR_BUTTON, COLOR_BUTTON_ACTIVE
    global COLOR_FIELD, COLOR_VIDEO, TRACK_BG, TRACK_EDGE, RANGE_FILL, PLAYHEAD, MARKER, ACCENT, COLOR_VOLUME
    global COLOR_TIP_BG, COLOR_TIP_FG

    THEME = name if name in PALETTES else DEFAULT_THEME
    palette = PALETTES[THEME]
    COLOR_BG = palette["bg"]
    COLOR_PANEL = palette["panel"]
    COLOR_ROW = palette["row"]
    COLOR_TEXT = palette["text"]
    COLOR_MUTED = palette["muted"]
    COLOR_PLAYED = palette["played"]
    COLOR_BORDER = palette["border"]
    COLOR_READOUT = palette["readout"]
    COLOR_BADGE_IDLE = palette["badge_idle"]
    COLOR_BUTTON = palette["button"]
    COLOR_BUTTON_ACTIVE = palette["button_active"]
    COLOR_FIELD = palette["field"]
    COLOR_VIDEO = palette["video"]
    TRACK_BG = palette["track"]
    TRACK_EDGE = palette["track_edge"]
    RANGE_FILL = palette["range"]
    PLAYHEAD = palette["playhead"]
    MARKER = palette["marker"]
    ACCENT = palette["accent"]
    COLOR_VOLUME = palette["volume"]
    COLOR_TIP_BG = palette["tip_bg"]
    COLOR_TIP_FG = palette["tip_fg"]
    return THEME


apply_theme(THEME)


class RangeProgressBar(tk.Canvas):
    """Seek bar that highlights the In/Out play range."""

    def __init__(self, master, on_seek, can_seek=None, **kwargs):
        kwargs.setdefault("height", 36)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("bg", COLOR_PANEL)
        super().__init__(master, **kwargs)
        self.on_seek = on_seek
        self.can_seek = can_seek
        self.duration = 0.0
        self.position = 0.0
        self.in_point = None
        self.out_point = None
        self.dragging = False
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def set_state(self, duration, position, in_point=None, out_point=None):
        self.duration = self._finite_time(duration)
        if not self.dragging:
            self.position = self._finite_time(position)
        self.in_point = in_point
        self.out_point = out_point
        self.redraw()

    @staticmethod
    def _finite_time(value):
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return 0.0
        if not math.isfinite(seconds) or seconds < 0:
            return 0.0
        return seconds

    def _track_box(self):
        left, top, right, bottom = 8, 8, 8, 6
        width = max(1, self.winfo_width() - left - right)
        height = max(8, self.winfo_height() - top - bottom)
        return left, top, left + width, top + height

    def _x_for_time(self, seconds):
        x0, _, x1, _ = self._track_box()
        if self.duration <= 0:
            return x0
        ratio = max(0.0, min(1.0, seconds / self.duration))
        return x0 + ratio * (x1 - x0)

    def _time_for_x(self, x):
        x0, _, x1, _ = self._track_box()
        if x1 <= x0 or self.duration <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
        return ratio * self.duration

    def _range(self):
        if self.duration <= 0:
            return None
        if self.in_point is None and self.out_point is None:
            return None
        start = 0.0 if self.in_point is None else max(0.0, self.in_point)
        end = self.duration if self.out_point is None else min(self.duration, self.out_point)
        if end < start:
            start, end = end, start
        return start, end

    def redraw(self):
        if self.winfo_width() <= 1:
            return
        self.delete("all")
        x0, y0, x1, y1 = self._track_box()
        self.create_rectangle(x0, y0, x1, y1, fill=TRACK_BG, outline=TRACK_EDGE, width=1)
        play_range = self._range()
        if play_range:
            rx0 = self._x_for_time(play_range[0])
            rx1 = self._x_for_time(play_range[1])
            self.create_rectangle(
                rx0, y0 + 1, max(rx0 + 2, rx1), y1 - 1,
                fill=RANGE_FILL, outline="",
            )
            self.create_line(rx0, y0 - 3, rx0, y1 + 3, fill=MARKER, width=2)
            self.create_line(rx1, y0 - 3, rx1, y1 + 3, fill=MARKER, width=2)
            if rx1 - rx0 > 48:
                self.create_text(rx0 + 3, 1, text=t("in_mark"), anchor="nw", fill=MARKER, font=FONT_SMALL)
                self.create_text(rx1 - 3, 1, text=t("out_mark"), anchor="ne", fill=MARKER, font=FONT_SMALL)
            else:
                self.create_text(rx0, 1, text=t("in_mark"), anchor="n", fill=MARKER, font=FONT_SMALL)
                self.create_text(rx1, 1, text=t("out_mark"), anchor="n", fill=MARKER, font=FONT_SMALL)
        if self.duration > 0:
            px = self._x_for_time(self.position)
            self.create_line(px, y0, px, y1, fill=PLAYHEAD, width=2)
            self.create_polygon(
                px, y0 - 2,
                px + 5, y0 + 7,
                px - 5, y0 + 7,
                fill=PLAYHEAD, outline=COLOR_WHITE,
            )

    def _seek_at(self, event, dragging):
        if self.duration <= 0:
            return
        self.position = self._time_for_x(event.x)
        self.redraw()
        self.on_seek(self.position, dragging=dragging)

    def _press(self, event):
        if self.can_seek is not None and not self.can_seek():
            return
        self.dragging = True
        self._seek_at(event, dragging=True)

    def _drag(self, event):
        if self.dragging:
            self._seek_at(event, dragging=True)

    def _release(self, event):
        if not self.dragging:
            return
        self.dragging = False
        self._seek_at(event, dragging=False)


class VolumeBar(tk.Canvas):
    """Filled bar from the left up to the current volume; click or drag to set it."""

    def __init__(self, master, on_change, fill=None, **kwargs):
        kwargs.setdefault("height", 22)
        kwargs.setdefault("width", 80)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("bg", COLOR_PANEL)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self.fill = COLOR_VOLUME if fill is None else fill
        self.volume = 100
        self.dragging = False
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def set_volume(self, volume, notify=False):
        self.volume = clamp_volume(volume)
        self.redraw()
        if notify:
            self.on_change(self.volume)

    def _track_box(self):
        pad = 1
        width = max(1, self.winfo_width() - pad * 2)
        height = max(8, self.winfo_height() - 6)
        top = (self.winfo_height() - height) // 2
        return pad, top, pad + width, top + height

    def _volume_for_x(self, x):
        x0, _, x1, _ = self._track_box()
        if x1 <= x0:
            return 0
        ratio = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
        return clamp_volume(round(ratio * 100))

    def redraw(self):
        self.delete("all")
        x0, y0, x1, y1 = self._track_box()
        self.create_rectangle(x0, y0, x1, y1, fill=TRACK_BG, outline=TRACK_EDGE, width=1)
        fill_x = x0 + (x1 - x0) * (self.volume / 100.0)
        if self.volume > 0:
            self.create_rectangle(
                x0 + 1, y0 + 1, max(x0 + 2, fill_x), y1 - 1,
                fill=self.fill, outline="",
            )

    def _set_at(self, event, dragging):
        self.volume = self._volume_for_x(event.x)
        self.redraw()
        self.on_change(self.volume)

    def _press(self, event):
        self.dragging = True
        self._set_at(event, dragging=True)

    def _drag(self, event):
        if self.dragging:
            self._set_at(event, dragging=True)

    def _release(self, event):
        if not self.dragging:
            return
        self.dragging = False
        self._set_at(event, dragging=False)


class EnvelopeCanvas(tk.Canvas):
    """Stored peak envelope under a progress bar, with a playhead.

    When ``on_seek`` is set, dragging the envelope moves the same playhead as
    the bar above it, gated by ``can_seek``.
    """

    def __init__(self, master, on_seek=None, can_seek=None, **kwargs):
        kwargs.setdefault("height", 36)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("bg", COLOR_PANEL)
        super().__init__(master, **kwargs)
        self.on_seek = on_seek
        self.can_seek = can_seek
        self.peaks = []
        self.duration = 0.0
        self.position = 0.0
        self.dragging = False
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        if on_seek is not None:
            self.config(cursor="hand2")

    def set_envelope(self, peaks):
        self.peaks = list(peaks or [])
        self.redraw()

    def set_playhead(self, duration, position):
        try:
            self.duration = max(0.0, float(duration or 0.0))
        except (TypeError, ValueError):
            self.duration = 0.0
        try:
            position = max(0.0, float(position or 0.0))
        except (TypeError, ValueError):
            position = 0.0
        if not math.isfinite(self.duration):
            self.duration = 0.0
        if not math.isfinite(position):
            position = 0.0
        if not self.dragging:
            self.position = position
        self.redraw()

    def _track_box(self):
        left, right = 8, 8
        top, bottom = 2, 2
        width = max(1, self.winfo_width() - left - right)
        height = max(12, self.winfo_height() - top - bottom)
        return left, top, left + width, top + height

    def redraw(self):
        if self.winfo_width() <= 1:
            return
        self.delete("all")
        x0, y0, x1, y1 = self._track_box()
        self.create_rectangle(x0, y0, x1, y1, fill=TRACK_BG, outline=TRACK_EDGE, width=1)
        mid = (y0 + y1) / 2.0
        self.create_line(x0 + 1, mid, x1 - 1, mid, fill=TRACK_EDGE)
        if len(self.peaks) >= 2:
            amp = max(1.0, (y1 - y0) / 2.0 - 1.5)
            width = x1 - x0
            count = len(self.peaks)
            top = []
            bottom = []
            for index, peak in enumerate(self.peaks):
                try:
                    level = max(0.0, min(1.0, float(peak)))
                except (TypeError, ValueError):
                    level = 0.0
                x = x0 + (index + 0.5) * width / count
                height = level * amp
                top.append((x, mid - height))
                bottom.append((x, mid + height))
            points = [coord for pair in top for coord in pair]
            points.extend(coord for pair in reversed(bottom) for coord in pair)
            self.create_polygon(points, fill=COLOR_VOLUME, outline="", smooth=False)
        if self.duration > 0:
            ratio = max(0.0, min(1.0, self.position / self.duration))
            px = x0 + ratio * (x1 - x0)
            self.create_line(px, y0, px, y1, fill=COLOR_WHITE, width=2)

    def _time_for_x(self, x):
        x0, _, x1, _ = self._track_box()
        if x1 <= x0 or self.duration <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
        return ratio * self.duration

    def _seek_at(self, event, dragging):
        if self.on_seek is None or self.duration <= 0:
            return
        self.position = self._time_for_x(event.x)
        self.redraw()
        self.on_seek(self.position, dragging=dragging)

    def _press(self, event):
        if self.on_seek is None:
            return
        if self.can_seek is not None and not self.can_seek():
            return
        self.dragging = True
        self._seek_at(event, dragging=True)

    def _drag(self, event):
        if self.dragging:
            self._seek_at(event, dragging=True)

    def _release(self, event):
        if not self.dragging:
            return
        self.dragging = False
        self._seek_at(event, dragging=False)


def program_eof_should_finish(
    playing,
    idle,
    keepalive,
    waiting_to_roll,
    test_image,
    loop_active,
    still,
    playback_started,
    file_matches,
):
    """True when mpv EOF belongs to the clip that is actually rolling."""
    if not playing or idle or keepalive or waiting_to_roll or test_image:
        return False
    if loop_active or still:
        return False
    return bool(playback_started and file_matches)


def program_file_loaded_starts_clip(playing, keepalive, file_matches):
    """file-loaded of the rolling clip may set volume; it must not arm EOF.

    The keepalive WAV can still report eof-reached after this event.
    """
    return bool(playing and file_matches and not keepalive)


def program_playback_restart_starts_clip(playing, keepalive, idle, file_matches):
    """playback-restart arms EOF only for the clip that is actually on screen."""
    return bool(playing and file_matches and not keepalive and not idle)


def playback_out_point(entry, looping=False):
    """Out point that should stop this clip, or None to play through.

    Zero and negative values are not a real Out. They used to be sent to mpv
    and the file then ended on the first frame.
    """
    if looping or entry is None or entry.out_point is None:
        return None
    try:
        end = float(entry.out_point)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(end) or end <= 0:
        return None
    return end


def program_end_signal_is_real(position, duration, out_point):
    """True when an mpv eof belongs to this clip, not to the file it replaced.

    Between pictures the projector loops a one-second silent file. Opening the
    next movie makes mpv report eof while the new picture is still at the
    start. That report may advance the program only once the playhead has
    reached this clip's end.
    """
    try:
        position = float(position)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(position) or position < 0:
        return False
    end = None
    if out_point is not None:
        try:
            end = float(out_point)
        except (TypeError, ValueError):
            end = None
        if end is not None and (not math.isfinite(end) or end <= 0):
            end = None
    if end is None:
        try:
            end = float(duration)
        except (TypeError, ValueError):
            end = 0.0
        if not math.isfinite(end) or end <= 0:
            return position >= 1.0
    # The keepalive playhead never gets far past one second. A clip has to be
    # that close to its own end before eof is allowed to finish it.
    margin = 0.08 if end <= 0.25 else 0.75
    return position >= max(0.0, end - margin)


def program_clock_drives_playhead(waiting_to_roll, playing, idle, file_matches):
    """The playhead follows mpv only for the clip that is actually on the projector.

    During a light fade the next title is already armed, but the projector is
    still showing the previous file. That clock must not move the program bar.
    """
    if waiting_to_roll:
        return False
    if idle:
        return True
    if playing and not file_matches:
        return False
    return True


def remote_clip_envelope(entry, volume_setup):
    """Peak envelope for the phone remote, only while setting house volume."""
    if not volume_setup or entry is None:
        return None
    if getattr(entry, "missing", False) or getattr(entry, "is_image", False):
        return None
    peaks = getattr(entry, "audio_envelope", None)
    if not peaks:
        return None
    out = []
    for item in peaks:
        try:
            value = float(item)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            out.append(round(max(0.0, min(1.0, value)), 4))
    return out or None


def format_delay_ms(ms):
    value = int(ms)
    if value > 0:
        return f"+{value} ms"
    return f"{value} ms"


def snap_delay_ms(value):
    try:
        ms = int(round(float(value) / AUDIO_DELAY_STEP_MS) * AUDIO_DELAY_STEP_MS)
    except (TypeError, ValueError):
        ms = 0
    return max(AUDIO_DELAY_MIN_MS, min(AUDIO_DELAY_MAX_MS, ms))


def audiosync_format_key(width, height, fps):
    if not width or not height or not fps:
        return ""
    return f"{int(width)}x{int(height)}@{format_fps_label(fps)}"


class DelayBar(tk.Canvas):
    """Bipolar slider for audio delay in 1 ms steps (mpv audio-delay seconds)."""

    def __init__(self, master, on_change, **kwargs):
        kwargs.setdefault("height", 22)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("bg", COLOR_PANEL)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, **kwargs)
        self.on_change = on_change
        self.delay_ms = 0
        self.dragging = False
        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Button-4>", self._wheel_up)
        self.bind("<Button-5>", self._wheel_down)
        self.bind("<MouseWheel>", self._wheel)

    def set_delay(self, delay_ms, notify=False):
        self.delay_ms = snap_delay_ms(delay_ms)
        self.redraw()
        if notify:
            self.on_change(self.delay_ms)

    def _track_box(self):
        pad = 1
        width = max(1, self.winfo_width() - pad * 2)
        height = max(8, self.winfo_height() - 6)
        top = (self.winfo_height() - height) // 2
        return pad, top, pad + width, top + height

    def _delay_for_x(self, x):
        x0, _, x1, _ = self._track_box()
        if x1 <= x0:
            return 0
        ratio = max(0.0, min(1.0, (x - x0) / (x1 - x0)))
        span = AUDIO_DELAY_MAX_MS - AUDIO_DELAY_MIN_MS
        return snap_delay_ms(AUDIO_DELAY_MIN_MS + ratio * span)

    def redraw(self):
        self.delete("all")
        x0, y0, x1, y1 = self._track_box()
        self.create_rectangle(x0, y0, x1, y1, fill=TRACK_BG, outline=TRACK_EDGE, width=1)
        span = AUDIO_DELAY_MAX_MS - AUDIO_DELAY_MIN_MS
        centre = x0 + (x1 - x0) * (0 - AUDIO_DELAY_MIN_MS) / span
        fill_x = x0 + (x1 - x0) * (self.delay_ms - AUDIO_DELAY_MIN_MS) / span
        left = min(centre, fill_x)
        right = max(centre, fill_x)
        if abs(self.delay_ms) >= AUDIO_DELAY_STEP_MS:
            self.create_rectangle(
                left, y0 + 1, max(left + 1, right), y1 - 1,
                fill=COLOR_VOLUME, outline="",
            )
        self.create_line(centre, y0 - 2, centre, y1 + 2, fill=PLAYHEAD, width=2)

    def _set_at(self, event):
        self.delay_ms = self._delay_for_x(event.x)
        self.redraw()
        self.on_change(self.delay_ms)

    def _press(self, event):
        self.dragging = True
        self._set_at(event)

    def _drag(self, event):
        if self.dragging:
            self._set_at(event)

    def _release(self, event):
        if not self.dragging:
            return
        self.dragging = False
        self._set_at(event)

    def _nudge(self, delta):
        self.set_delay(self.delay_ms + delta, notify=True)
        return "break"

    def _wheel_up(self, _event):
        return self._nudge(AUDIO_DELAY_STEP_MS)

    def _wheel_down(self, _event):
        return self._nudge(-AUDIO_DELAY_STEP_MS)

    def _wheel(self, event):
        delta = AUDIO_DELAY_STEP_MS if event.delta > 0 else -AUDIO_DELAY_STEP_MS
        return self._nudge(delta)


_PEAK_LEVEL_RE = re.compile(r"^lavfi\.astats\.(\d+)\.Peak_level$")
METER_FLOOR_DB = -60.0
METER_CEILING_DB = 0.0
METER_TICKS_DB = (0, -6, -12, -18, -24, -36, -48, -60)


def _parse_db(value):
    if value is None:
        return None
    try:
        db = float(value)
    except (TypeError, ValueError):
        text = str(value).strip().lower()
        if text in ("-inf", "inf", "nan"):
            return None
        try:
            db = float(text)
        except ValueError:
            return None
    if not math.isfinite(db):
        return None
    return db


def parse_preview_levels(data):
    """Peak dBFS per channel from mpv lavfi astats metadata."""
    if not isinstance(data, dict):
        return []
    channels = {}
    for key, value in data.items():
        match = _PEAK_LEVEL_RE.match(str(key))
        if not match:
            continue
        db = _parse_db(value)
        if db is None:
            continue
        channels[int(match.group(1))] = db
    if channels:
        return [channels[index] for index in sorted(channels)]
    overall = _parse_db(data.get("lavfi.astats.Overall.Peak_level"))
    return [overall] if overall is not None else []


def volume_gain_db(volume):
    """mpv volume is linear amplitude; 100 is unity (0 dB), 0 is silence."""
    percent = clamp_volume(volume)
    if percent <= 0:
        return None
    return 20.0 * math.log10(percent / 100.0)


class LevelMeter(tk.Canvas):
    """Vertical peak meter with a dB scale."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("width", 58)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("bg", COLOR_PANEL)
        self.meter_bg = kwargs["bg"]
        super().__init__(master, **kwargs)
        self.levels = []
        self.holds = []
        self._hold_until = []
        self.bind("<Configure>", lambda e: self.redraw())

    def set_levels(self, levels):
        values = [max(METER_FLOOR_DB, min(METER_CEILING_DB, float(db))) for db in levels]
        now = time.monotonic()
        if len(values) != len(self.holds):
            self.holds = list(values)
            self._hold_until = [now + 1.2] * len(values)
        else:
            for index, db in enumerate(values):
                if db >= self.holds[index] - 0.05:
                    self.holds[index] = db
                    self._hold_until[index] = now + 1.2
                elif now >= self._hold_until[index]:
                    self.holds[index] = max(db, self.holds[index] - 12.0 * 0.05)
        self.levels = values
        self.redraw()

    def reset(self):
        self.levels = []
        self.holds = []
        self._hold_until = []
        self.redraw()

    def _y_for_db(self, db, top, bottom):
        span = METER_CEILING_DB - METER_FLOOR_DB
        clamped = max(METER_FLOOR_DB, min(METER_CEILING_DB, db))
        ratio = (clamped - METER_FLOOR_DB) / span
        return bottom - ratio * (bottom - top)

    def redraw(self):
        self.delete("all")
        self.configure(bg=self.meter_bg)
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        top = 16
        bottom = height - 14
        if bottom - top < 20:
            top = 4
            bottom = height - 4
        scale_width = 28
        bars_right = max(12, width - scale_width)
        count = max(1, min(2, len(self.levels) or 2))
        gap = 3
        bar_width = max(6, (bars_right - 6 - gap * (count - 1)) // count)
        levels = list(self.levels)
        holds = list(self.holds)
        if not levels:
            levels = [METER_FLOOR_DB] * count
            holds = [METER_FLOOR_DB] * count
        elif len(levels) == 1 and count == 2:
            levels = [levels[0], levels[0]]
            holds = [holds[0] if holds else levels[0]] * 2
        else:
            levels = levels[:count]
            holds = (holds + levels)[:count]

        for index, db in enumerate(levels):
            x0 = 4 + index * (bar_width + gap)
            x1 = x0 + bar_width
            self.create_rectangle(x0, top, x1, bottom, fill=TRACK_BG, outline=TRACK_EDGE, width=1)
            fill_top = self._y_for_db(db, top, bottom)
            if fill_top < bottom - 1:
                # Colour the column in green / yellow / red segments.
                for low, high, color in (
                    (METER_FLOOR_DB, -18, COLOR_PLAYING),
                    (-18, -6, COLOR_PREVIEW),
                    (-6, METER_CEILING_DB, COLOR_OFF),
                ):
                    seg_bottom = min(bottom - 1, self._y_for_db(low, top, bottom))
                    seg_top = max(fill_top, self._y_for_db(high, top, bottom))
                    if seg_bottom - seg_top >= 1:
                        self.create_rectangle(
                            x0 + 1, seg_top, x1 - 1, seg_bottom,
                            fill=color, outline="",
                        )
            hold_y = self._y_for_db(holds[index], top, bottom)
            self.create_line(x0 + 1, hold_y, x1 - 1, hold_y, fill=PLAYHEAD, width=2)

        self.create_text(
            width - 2, 2, text="dB", anchor="ne", fill=COLOR_MUTED, font=FONT_SMALL,
        )
        for tick in METER_TICKS_DB:
            y = self._y_for_db(tick, top, bottom)
            label = "0" if tick == 0 else str(tick)
            self.create_line(bars_right - 2, y, bars_right + 2, y, fill=COLOR_MUTED)
            self.create_text(
                width - 2, y, text=label, anchor="e", fill=COLOR_MUTED, font=FONT_SMALL,
            )
        if count == 2:
            self.create_text(4 + bar_width / 2, height - 2, text="L", anchor="s",
                             fill=COLOR_MUTED, font=FONT_SMALL)
            self.create_text(4 + bar_width + gap + bar_width / 2, height - 2, text="R",
                             anchor="s", fill=COLOR_MUTED, font=FONT_SMALL)


class IconTooltip:
    """Translated hover text for icon-only buttons."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self._window = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(400, self._show)

    def _cancel(self):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _hide(self, _event=None):
        self._cancel()
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _show(self):
        self._after_id = None
        if self._window is not None or not self.text:
            return
        try:
            anchor_x = self.widget.winfo_rootx()
            below = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            above_anchor = self.widget.winfo_rooty() - 6
        except tk.TclError:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.configure(bg=COLOR_TIP_BG)
        label = tk.Label(
            tip, text=self.text, font=FONT_TOOLTIP, bg=COLOR_TIP_BG, fg=COLOR_TIP_FG,
            relief="flat", bd=0, padx=10, pady=6, justify="left",
        )
        label.pack()
        try:
            tip.update_idletasks()
            width = max(tip.winfo_reqwidth(), 1)
            height = max(tip.winfo_reqheight(), 1)
            left, top, right, bottom = self._monitor_edges()
            margin = 4
            room = max(40, right - left - 2 * margin)
            if width > room:
                label.configure(wraplength=max(20, room - 20))
                tip.update_idletasks()
                width = max(tip.winfo_reqwidth(), 1)
                height = max(tip.winfo_reqheight(), 1)
            x = anchor_x
            y = below
            if x + width > right - margin:
                x = right - margin - width
            if x < left + margin:
                x = left + margin
            if y + height > bottom - margin:
                y = above_anchor - height
            if y < top + margin:
                y = top + margin
            if y + height > bottom - margin:
                y = max(top + margin, bottom - margin - height)
            tip.wm_geometry(f"{width}x{height}+{int(x)}+{int(y)}")
        except tk.TclError:
            tip.destroy()
            return
        self._window = tip

    def _monitor_edges(self):
        """Control-monitor rectangle. Falls back to the window that owns the widget."""
        root = self.widget.winfo_toplevel()
        getter = getattr(root, "tooltip_screen_bounds", None)
        bounds = None
        if callable(getter):
            try:
                bounds = getter()
            except Exception:
                bounds = None
        if bounds:
            width, height, x, y = bounds
            return x, y, x + width, y + height
        try:
            x = root.winfo_rootx()
            y = root.winfo_rooty()
            return x, y, x + max(root.winfo_width(), 1), y + max(root.winfo_height(), 1)
        except tk.TclError:
            return 0, 0, self.widget.winfo_screenwidth(), self.widget.winfo_screenheight()


class DropdownMenu(tk.Frame):
    """In-window menu so GNOME/Wayland cannot place it on another output."""

    def __init__(self, master, gui):
        super().__init__(
            master,
            bg=COLOR_PANEL,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            bd=0,
        )
        self._gui = gui
        self._cascades = []
        self._cascade_side = "right"

    def delete(self, *_args):
        for cascade in self._cascades:
            try:
                cascade.destroy()
            except tk.TclError:
                pass
        self._cascades = []
        for child in list(self.winfo_children()):
            child.destroy()

    def add_command(
        self, label="", command=None, state="normal", accelerator="",
        foreground=None, **_kwargs,
    ):
        text = f"{label}    {accelerator}" if accelerator else label
        self._add_row(text, command, state, foreground)

    def add_checkbutton(
        self, label="", variable=None, command=None, accelerator="", **_kwargs,
    ):
        checked = bool(variable.get()) if variable is not None else False
        text = f"✔  {label}" if checked else label
        if accelerator:
            text = f"{text}    {accelerator}"

        def run():
            if variable is not None:
                variable.set(not bool(variable.get()))
            self._gui._close_menus()
            if command:
                command()

        self._add_row(text, run, "normal", self._gui._menu_check_fg() if checked else None)

    def add_separator(self):
        tk.Frame(self, bg=COLOR_BORDER, height=1).pack(fill="x", padx=8, pady=4)

    def add_entry(self, label="", variable=None, width=5, suffix=""):
        """Keep an editable field in the menu without closing it on click."""
        row = tk.Frame(self, bg=COLOR_PANEL)
        tk.Label(
            row, text=label, font=FONT_UI, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        ).pack(side="left", padx=(14, 4), pady=6)
        tk.Entry(row, textvariable=variable, width=width, font=FONT_UI).pack(side="left")
        if suffix:
            tk.Label(
                row, text=suffix, font=FONT_UI, bg=COLOR_PANEL, fg=COLOR_TEXT,
            ).pack(side="left", padx=(4, 14), pady=6)
        row.pack(fill="x")

    def add_cascade(self, label="", menu=None, state="normal", **_kwargs):
        self._cascades.append(menu)

        def open_cascade(event, submenu=menu):
            self._show_cascade(event.widget, submenu)

        self._add_row(f"{label}  >", None, state, None, on_press=open_cascade)

    def _add_row(self, text, command, state, foreground, on_press=None):
        fg = foreground or COLOR_TEXT
        if state == "disabled":
            fg = COLOR_PLAYED

        def activate(_event=None, action=command, press=on_press):
            if state == "disabled":
                return
            if press is not None:
                press(_event)
                return
            self._gui._close_menus()
            if action:
                action()

        row = tk.Label(
            self, text=text, font=FONT_UI, bg=COLOR_PANEL, fg=fg,
            anchor="w", padx=14, pady=6,
            cursor="arrow" if state == "disabled" else "hand2",
        )
        row.pack(fill="x")
        if state != "disabled":
            idle_fg = fg
            row.bind(
                "<Enter>",
                lambda _e, item=row: item.config(bg=COLOR_BUTTON_ACTIVE, fg=COLOR_WHITE),
            )
            row.bind(
                "<Leave>",
                lambda _e, item=row, color=idle_fg: item.config(bg=COLOR_PANEL, fg=color),
            )
            row.bind("<Button-1>", activate)
        return row

    def _show_cascade(self, row, submenu):
        if submenu is None:
            return
        for other in self._cascades:
            if other is not None and other is not submenu:
                other.unpost()
        if isinstance(submenu, DropdownMenu):
            submenu._cascade_side = self._cascade_side
        self.update_idletasks()
        root = self.master
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        y = row.winfo_rooty() - ry
        if self._cascade_side == "left":
            submenu.place(x=self.winfo_rootx() - rx, y=y, anchor="ne")
        else:
            submenu.place(x=self.winfo_rootx() - rx + self.winfo_width(), y=y, anchor="nw")
        submenu.lift()

    def unpost(self):
        self.place_forget()
        for cascade in self._cascades:
            if cascade is not None:
                try:
                    cascade.unpost()
                except tk.TclError:
                    pass

    def post_below(self, widget, side="left"):
        self._cascade_side = "left" if side == "right" else "right"
        root = self.master
        root.update_idletasks()
        x = widget.winfo_rootx() - root.winfo_rootx()
        y = widget.winfo_rooty() - root.winfo_rooty() + widget.winfo_height()
        if side == "right":
            self.place(x=x + widget.winfo_width(), y=y, anchor="ne")
        else:
            self.place(x=x, y=y, anchor="nw")
        self.lift()


class CheckLabel(tk.Label):
    """Clickable ✔ toggle matching the in-window burger menu, without native Checkbutton."""

    def __init__(self, master, text, variable, command=None, bg=None, **kwargs):
        bg = bg or COLOR_PANEL
        kwargs.setdefault("font", FONT_UI)
        kwargs.setdefault("bg", bg)
        kwargs.setdefault("fg", COLOR_TEXT)
        kwargs.setdefault("anchor", "w")
        kwargs.setdefault("cursor", "hand2")
        kwargs.setdefault("padx", 8)
        kwargs.setdefault("pady", 4)
        super().__init__(master, **kwargs)
        self.variable = variable
        self.command = command
        self.label_text = text
        self._idle_bg = bg
        self._hover = False
        self._trace = variable.trace_add("write", lambda *_args: self._paint())
        self.bind("<Destroy>", self._on_destroy)
        self.bind("<Button-1>", self._toggle)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._paint()

    def _on_destroy(self, _event=None):
        token = getattr(self, "_trace", None)
        if token:
            try:
                self.variable.trace_remove("write", token)
            except (tk.TclError, ValueError):
                pass
            self._trace = None

    def _toggle(self, _event=None):
        self.variable.set(not bool(self.variable.get()))
        if self.command:
            self.command()

    def _on_enter(self, _event=None):
        self._hover = True
        self._paint()

    def _on_leave(self, _event=None):
        self._hover = False
        self._paint()

    def _paint(self):
        checked = bool(self.variable.get())
        mark = "✔  " if checked else "    "
        if self._hover:
            self.config(
                text=f"{mark}{self.label_text}",
                bg=COLOR_BUTTON_ACTIVE,
                fg=COLOR_WHITE,
            )
            return
        fg = COLOR_VOLUME if THEME == "dark" else COLOR_PROGRAM
        self.config(
            text=f"{mark}{self.label_text}",
            bg=self._idle_bg,
            fg=fg if checked else COLOR_TEXT,
        )


def format_seconds(value):
    seconds = max(0.0, float(value or 0))
    return str(int(seconds)) if seconds == int(seconds) else f"{seconds:g}"


def still_level_filter(level):
    """mpv video filter for one step of a still fade.

    An empty string is the untouched picture. ffmpeg's eq brightness runs from
    -1 (black) to 0 (unchanged). The mpv brightness property is not used: on a
    still it can freeze the first black frame.
    """
    level = max(0.0, min(1.0, float(level)))
    if level >= 0.999:
        return ""
    return f"lavfi=[eq=brightness={-1.0 + level:.3f}]"


def still_fade_plan(display_seconds, dim_seconds, enabled):
    """When a timed still should start fading out, and how long that fade lasts.

    ``None`` means the still stays until the operator continues. A fade of 0
    means the picture ends at full level. The fade fits inside the display time,
    and a short display keeps half of that time for the fade-in.
    """
    display = max(0.0, float(display_seconds or 0))
    dim = max(0.0, float(dim_seconds or 0))
    if display <= 0:
        return None
    if not enabled or dim <= 0:
        return (int(round(display * 1000)), 0.0)
    # Leave as much time for the fade-in, so a short display still reaches the picture.
    fade = min(dim, display / 2.0)
    delay = int(round(max(0.0, display - fade) * 1000))
    return (delay, fade)


def settings_path():
    return os.path.join(os.path.expanduser("~"), ".config", "cinema-player", "settings.json")


class BeamerChoiceLine(tk.Frame):
    """Wraps beamer rates/resolutions; the active value has a border."""

    def __init__(self, master, **kwargs):
        kwargs.setdefault("bg", COLOR_PANEL)
        super().__init__(master, **kwargs)
        self.pack_propagate(False)
        self.configure(height=FONT_BEAMER_PICK[1] + 14)
        self._labels = []
        self._signature = None
        self._laid_width = 0
        self._reflowing = False
        self.bind("<Configure>", self._reflow)

    def set_choices(self, prefix, tokens, selected=None, program=None, preview=None):
        program_set = self._token_set(program)
        preview_set = self._token_set(preview)
        signature = (prefix, tuple(tokens or ()), selected, program_set, preview_set)
        if signature == self._signature:
            return
        self._signature = signature
        for widget in self._labels:
            widget.destroy()
        self._labels = []
        if prefix:
            self._labels.append(
                self._chip(prefix.strip(), picked=False, program=False, preview=False)
            )
        values = list(tokens) if tokens else ["--"]
        for token in values:
            self._labels.append(self._chip(
                token,
                picked=token == selected,
                program=token in program_set,
                preview=token in preview_set,
            ))
        self._laid_width = 0
        self._reflow()

    @staticmethod
    def _token_set(value):
        if not value:
            return frozenset()
        if isinstance(value, (set, frozenset, list, tuple)):
            return frozenset(item for item in value if item)
        return frozenset((value,))

    def _chip(self, text, picked, program=False, preview=False):
        if program:
            fg = ACCENT
        elif preview:
            fg = COLOR_PREVIEW
        elif picked:
            fg = COLOR_TEXT
        else:
            fg = COLOR_MUTED
        font = FONT_BEAMER_PICK if (program or preview) else FONT_SMALL
        ring = COLOR_PANEL
        if picked:
            ring = COLOR_WHITE if THEME == "dark" else COLOR_TEXT
        return tk.Label(
            self,
            text=text,
            font=font,
            fg=fg,
            bg=COLOR_PANEL,
            padx=3,
            pady=1,
            bd=0,
            highlightthickness=1,
            highlightbackground=ring,
            highlightcolor=ring,
        )

    def _reflow(self, _event=None):
        if self._reflowing or not self._labels:
            return
        width = max(self.winfo_width(), 1)
        if width == self._laid_width:
            return
        self._reflowing = True
        try:
            gap = 8
            rows = []
            row = []
            x = 0
            for widget in self._labels:
                needed = widget.winfo_reqwidth()
                extra = 0 if not row else gap
                if row and x + extra + needed > width:
                    rows.append(row)
                    row = []
                    x = 0
                    extra = 0
                row.append((widget, extra, needed, widget.winfo_reqheight()))
                x += extra + needed
            if row:
                rows.append(row)
            y = 0
            for row in rows:
                row_h = max(item[3] for item in row)
                x = 0
                for widget, extra, needed, height in row:
                    widget.place(x=x + extra, y=y + max(0, row_h - height) // 2)
                    x += extra + needed
                y += row_h
            height = max(y + 2, FONT_BEAMER_PICK[1] + 14)
            self._laid_width = width
            if abs(int(self.cget("height") or 0) - height) > 1:
                self.configure(height=height)
        finally:
            self._reflowing = False


def load_settings():
    path = settings_path()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_settings(settings):
    path = settings_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)


# Playlist metadata columns. Widths are in characters so the header and the
# rows share one alignment.
PLAYLIST_META_COLUMNS = (
    ("duration", "col_duration", 8),
    ("fps", "col_fps", 13),
    ("aspect", "col_format", 14),
    ("par", "col_par", 16),
    ("colorspace", "col_color", 25),
    ("volume", "col_volume", 5),
    ("loudness", "col_lufs", 9),
    ("notes", "col_notes", 16),
)


def source_color_label(entry):
    """Source status only; do not assume mpv output conversion."""
    status = getattr(entry, "hdr_status", "Unknown")
    return {"HDR": "HDR (output unverified)", "SDR": "Native SDR"}.get(status, "HDR/SDR unknown")


def playlist_color_text(entry):
    """SDR/HDR on the first line, the colorspace underneath."""
    return f"{source_color_label(entry)}\n{format_colorspace_label(entry)}"


def playlist_warning_keys(entry):
    """Which technical values on a row need a short warning word."""
    keys = []
    if (
        not getattr(entry, "is_image", False)
        and getattr(entry, "fps", 0)
        and not getattr(entry, "refresh_ok", True)
    ):
        keys.append("rate")
    if getattr(entry, "aspect_warning", False):
        keys.append("zoom")
    if getattr(entry, "par_warning", False):
        keys.append("par")
    if getattr(entry, "colorspace_warning", False):
        keys.append("color")
    return keys


def playlist_note_text(entry, projection_zoom):
    """Badges and the warnings that do not fit beside a value."""
    notes = []
    if getattr(entry, "missing", False):
        notes.append(t("missing_badge"))
    if getattr(entry, "colorspace_warning", False):
        notes.append(t("warn_color"))
    specific = (
        getattr(entry, "aspect_warning", False)
        or getattr(entry, "par_warning", False)
        or getattr(entry, "colorspace_warning", False)
    )
    if clip_needs_settings_warning(entry, projection_zoom) and not specific:
        notes.append(t("setting_badge"))
    if not getattr(entry, "missing", False):
        if getattr(entry, "autoplay", False):
            notes.append(t("auto_badge"))
        if getattr(entry, "loop", False) and not getattr(entry, "is_image", False):
            notes.append(t("loop_badge"))
        play = dmx.play_preset(getattr(entry, "light_start", ""))
        if play == "medium":
            notes.append(t("light_medium_badge"))
        elif play == "bright":
            notes.append(t("light_bright_badge"))
    return " ".join(notes)


def warned_meta_text(value, warning, word, hint=False, hint_word=""):
    """Keep a warning word in the same cell as the value it belongs to."""
    text = value or "--"
    if hint and hint_word:
        text = f"{text} {hint_word}"
    if warning and word:
        return f"{text} {word}"
    return text


def playlist_aspect_text(entry, pad_16x9=True):
    """Format cell: 4:3 →16:9, plus Zoom when the beamer setting changes."""
    hint = "aspect" in sixteen_nine_hint_fields(entry, enabled=pad_16x9)
    return warned_meta_text(
        getattr(entry, "aspect", None),
        getattr(entry, "aspect_warning", False),
        t("warn_zoom"),
        hint=hint,
        hint_word=t("hint_16x9"),
    )


def playlist_par_text(entry, pad_16x9=True):
    """PAR cell: 64:45 →16:9 when non-square pixels are corrected to 16:9."""
    hint = "par" in sixteen_nine_hint_fields(entry, enabled=pad_16x9)
    return warned_meta_text(
        getattr(entry, "pixel_aspect", None),
        getattr(entry, "par_warning", False),
        t("warn_par"),
        hint=hint,
        hint_word=t("hint_16x9"),
    )


def next_program_label(playlist, program_index, program_state, projection_zoom):
    """Status-line hint for the clip that follows the program pointer."""
    if program_state not in ("PROGRAM", "PLAYING") or not playlist:
        return ""
    try:
        index = int(program_index) + 1
    except (TypeError, ValueError):
        return ""
    if index < 0 or index >= len(playlist):
        return ""
    entry = playlist[index]
    name = getattr(entry, "filename", "") or os.path.basename(getattr(entry, "path", "") or "")
    if not name:
        return ""
    text = t("next_clip", name=name)
    extras = []
    if "rate" in playlist_warning_keys(entry):
        extras.append(t("warn_rate"))
    if getattr(entry, "aspect_warning", False) and getattr(entry, "aspect", "") not in ("", "--", None):
        extras.append(t("next_zoom", aspect=entry.aspect))
    if getattr(entry, "par_warning", False):
        extras.append(t("warn_par"))
    if getattr(entry, "colorspace_warning", False):
        extras.append(t("warn_color"))
    if clip_needs_settings_warning(entry, projection_zoom) and not (
        getattr(entry, "aspect_warning", False)
        or getattr(entry, "par_warning", False)
        or getattr(entry, "colorspace_warning", False)
    ):
        extras.append(t("setting_badge"))
    if extras:
        text = f"{text} · {' · '.join(extras)}"
    return text


def entry_video_seconds(entry):
    """Play length of one video, from In to Out. Stills are not part of the total."""
    if entry is None or getattr(entry, "is_image", False):
        return 0.0
    _start, _end, total, _elapsed, _remaining = clip_span(
        getattr(entry, "duration", 0) or 0,
        0,
        getattr(entry, "in_point", None),
        getattr(entry, "out_point", None),
    )
    return total


def playlist_video_seconds(playlist):
    return sum(entry_video_seconds(entry) for entry in playlist or [])


def entry_waits_for_operator(entry):
    """A looping video or a still without a display time does not end by itself."""
    if entry is None:
        return False
    if getattr(entry, "is_image", False):
        try:
            return float(getattr(entry, "display_time", 0) or 0) <= 0
        except (TypeError, ValueError):
            return True
    return bool(getattr(entry, "loop", False))


def _later_program_entry(playlist, index):
    for entry in playlist[index + 1:]:
        if not getattr(entry, "missing", False):
            return True
    return False


def _entry_remaining_seconds(entry, position, playing):
    """Play time left in one clip. A clip that has not started counts in full."""
    if getattr(entry, "is_image", False):
        try:
            span = max(0.0, float(getattr(entry, "display_time", 0) or 0))
        except (TypeError, ValueError):
            span = 0.0
        if not playing:
            return span
        try:
            pos = float(position or 0)
        except (TypeError, ValueError):
            pos = 0.0
        if not math.isfinite(pos) or pos < 0:
            pos = 0.0
        return max(0.0, span - pos)
    if not playing:
        return entry_video_seconds(entry)
    duration = getattr(entry, "duration", 0) or 0
    in_point = getattr(entry, "in_point", None)
    out_point = getattr(entry, "out_point", None)
    start, end, total, _elapsed, _remaining = clip_span(
        duration, position, in_point, out_point, playing=True,
    )
    try:
        pos = float(position or 0)
    except (TypeError, ValueError):
        pos = 0.0
    if not math.isfinite(pos) or pos < start:
        return total
    return max(0.0, min(total, end - pos))


def program_remaining_seconds(playlist, index, position, playing, autoplay_delay=0.0):
    """Seconds from the playhead to the end of the program.

    Videos count from In to Out. The clip on air counts only what is left.
    A still counts its display time. The autoplay gap is included before the
    next clip. None means a remaining clip waits for the operator, so the
    program has no fixed end.
    """
    items = list(playlist or [])
    if not items:
        return 0.0
    try:
        index = int(index)
    except (TypeError, ValueError):
        index = 0
    if index < 0:
        index = 0
    if index >= len(items):
        return 0.0
    try:
        delay = max(0.0, float(autoplay_delay or 0))
    except (TypeError, ValueError):
        delay = 0.0
    total = 0.0
    for cursor, entry in enumerate(items[index:], start=index):
        if getattr(entry, "missing", False):
            continue
        if entry_waits_for_operator(entry):
            return None
        total += _entry_remaining_seconds(entry, position, playing and cursor == index)
        if delay and getattr(entry, "autoplay", False) and _later_program_entry(items, cursor):
            total += delay
    return total


def program_end_clock(playlist, index, position, playing, now, autoplay_delay=0.0):
    """Wall time when the program finishes, or '--:--' when it cannot be known."""
    remaining = program_remaining_seconds(
        playlist, index, position, playing, autoplay_delay,
    )
    if remaining is None:
        return "--:--"
    return (now + timedelta(seconds=remaining)).strftime("%H:%M:%S")


def program_times_text(index, clip_clock, playlist, end_clock=None):
    """Clip index and length, the video runtime, then when the program ends."""
    total = format_clock(playlist_video_seconds(playlist))
    text = f"{index} / {clip_clock}   {total}"
    if end_clock:
        text = f"{text}   {t('end')} {end_clock}"
    return text


_DRIVE_ICON_ROWS = (
    "                        ",
    "                        ",
    "         ##  ##         ",
    "         ##  ##         ",
    "         ##  ##         ",
    "       ##########       ",
    "      ############      ",
    "      ############      ",
    "      ###  ##  ###      ",
    "      ###  ##  ###      ",
    "      ###  ##  ###      ",
    "      ############      ",
    "      ############      ",
    "      ###      ###      ",
    "      ###      ###      ",
    "      ############      ",
    "      ############      ",
    "       ##########       ",
    "                        ",
    "                        ",
    "                        ",
    "                        ",
    "                        ",
    "                        ",
)


def _bitmap_photo(rows, color):
    """RGBA photo from ASCII rows. '#' is the colour, anything else is clear."""
    import base64
    import struct
    import zlib

    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    width = len(rows[0])
    height = len(rows)
    raw = bytearray()
    for line in rows:
        raw.append(0)
        for pixel in line:
            if pixel == "#":
                raw.extend((red, green, blue, 255))
            else:
                raw.extend((0, 0, 0, 0))

    def chunk(tag, data):
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    return tk.PhotoImage(data=base64.b64encode(png))


def removable_drive_photo(color):
    """Small USB-stick icon. Transparent pixels let the row colour show through."""
    return _bitmap_photo(_DRIVE_ICON_ROWS, color)


# Picture frame, sun, and a hill. One pixel per character.
_STILL_ICON_ROWS = (
    "################",
    "#           ## #",
    "#           ## #",
    "#  ##          #",
    "# ####         #",
    "##   ##   #    #",
    "# ###### ###   #",
    "#              #",
    "################",
)
_STILL_ICON_CACHE = {}


def still_icon_photo(color):
    """Small picture mark for a still. Cached per colour, rebuilt if Tk dropped it."""
    photo = _STILL_ICON_CACHE.get(color)
    if photo is not None:
        try:
            photo.width()
            return photo
        except tk.TclError:
            photo = None
    photo = _bitmap_photo(_STILL_ICON_ROWS, color)
    _STILL_ICON_CACHE[color] = photo
    return photo


class ImportFolderList(tk.Frame):
    """Chooser rows for saved folders and plugged-in drives.

    Removable volumes keep a drive icon, including while the row is selected.
    """

    def __init__(self, master):
        super().__init__(master, bg=COLOR_PANEL)
        self.canvas = tk.Canvas(
            self, bg=COLOR_FIELD, highlightthickness=1,
            highlightbackground=COLOR_BORDER, highlightcolor=COLOR_PROGRAM,
            bd=0, takefocus=True,
        )
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner = tk.Frame(self.canvas, bg=COLOR_FIELD)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", self._stretch)
        self.inner.bind("<Configure>", self._scrollregion)
        self.canvas.bind("<Up>", lambda _event: self._move(-1))
        self.canvas.bind("<Down>", lambda _event: self._move(1))
        self.canvas.bind("<Return>", self._activate)
        self.canvas.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(3, "units"))
        self._icon_idle = None
        self._icon_selected = None
        self._rows = []
        self._selected = 0
        self.on_activate = None

    def focus_set(self):
        self.canvas.focus_set()

    def set_items(self, items):
        for child in self.inner.winfo_children():
            child.destroy()
        self._rows = []
        try:
            if self._icon_idle is None:
                self._icon_idle = removable_drive_photo(COLOR_TEXT)
                self._icon_selected = removable_drive_photo(COLOR_WHITE)
        except tk.TclError:
            self._icon_idle = None
            self._icon_selected = None
        icon_width = self._icon_idle.width() if self._icon_idle is not None else 24
        for index, item in enumerate(items):
            row = tk.Frame(self.inner, bg=COLOR_FIELD)
            row.pack(fill="x")
            slot = tk.Frame(row, bg=COLOR_FIELD, width=icon_width, height=icon_width)
            slot.pack(side="left", fill="y", padx=(8, 0), pady=4)
            slot.pack_propagate(False)
            icon = None
            if item.get("removable") and self._icon_idle is not None:
                icon = tk.Label(slot, image=self._icon_idle, bg=COLOR_FIELD, bd=0)
                icon.place(relx=0.5, rely=0.5, anchor="center")
            label = tk.Label(
                row, text=item.get("text") or item.get("path") or "",
                anchor="w", justify="left", font=FONT_UI,
                bg=COLOR_FIELD, fg=COLOR_TEXT,
            )
            label.pack(side="left", fill="x", expand=True, padx=(8, 8), pady=4)
            widgets = [row, slot, label]
            if icon is not None:
                widgets.append(icon)
            for widget in widgets:
                widget.bind("<Button-1>", lambda _event, row_index=index: self._click(row_index))
                widget.bind("<Double-Button-1>", lambda _event, row_index=index: self._activate_index(row_index))
                widget.bind("<Button-4>", lambda _event: self.canvas.yview_scroll(-3, "units"))
                widget.bind("<Button-5>", lambda _event: self.canvas.yview_scroll(3, "units"))
            self._rows.append({
                "path": item.get("path") or "",
                "removable": bool(item.get("removable")),
                "pinned": bool(item.get("pinned")),
                "frame": row,
                "slot": slot,
                "label": label,
                "icon": icon,
            })
        self._selected = 0 if self._rows else -1
        self._paint()
        self._scrollregion()

    def select(self, index):
        if not self._rows:
            self._selected = -1
            return
        self._selected = max(0, min(int(index), len(self._rows) - 1))
        self._paint()
        self._see(self._selected)

    def selected_path(self):
        if not 0 <= self._selected < len(self._rows):
            return ""
        return self._rows[self._selected]["path"]

    def selected_removable(self):
        if not 0 <= self._selected < len(self._rows):
            return False
        return bool(self._rows[self._selected].get("removable"))

    def has_icon(self, index):
        if not 0 <= index < len(self._rows):
            return False
        return self._rows[index]["icon"] is not None

    def icon_label(self, index):
        if not 0 <= index < len(self._rows):
            return None
        return self._rows[index]["icon"]

    def _click(self, index):
        self.select(index)
        self.focus_set()

    def _activate(self, _event=None):
        self._activate_index(self._selected)
        return "break"

    def _activate_index(self, index):
        self.select(index)
        if self.on_activate is not None:
            self.on_activate(index)

    def _move(self, delta):
        if self._rows:
            self.select(self._selected + delta)
        return "break"

    def _paint(self):
        for index, row in enumerate(self._rows):
            selected = index == self._selected
            pinned = bool(row.get("pinned"))
            if selected and pinned:
                background = ACCENT
                foreground = COLOR_WHITE
            elif selected:
                background = COLOR_PROGRAM
                foreground = COLOR_WHITE
            elif pinned:
                background = COLOR_FIELD
                foreground = ACCENT
            else:
                background = COLOR_FIELD
                foreground = COLOR_TEXT
            row["frame"].configure(bg=background)
            row["slot"].configure(bg=background)
            row["label"].configure(bg=background, fg=foreground)
            icon = row["icon"]
            if icon is None:
                continue
            image = self._icon_selected if selected else self._icon_idle
            icon.configure(bg=background, image=image)

    def _see(self, index):
        if not 0 <= index < len(self._rows):
            return
        self.inner.update_idletasks()
        row = self._rows[index]["frame"]
        y = row.winfo_y()
        height = max(row.winfo_height(), 1)
        total = max(self.inner.winfo_height(), 1)
        top = self.canvas.canvasy(0)
        bottom = top + max(self.canvas.winfo_height(), 1)
        if y < top:
            self.canvas.yview_moveto(y / total)
        elif y + height > bottom:
            self.canvas.yview_moveto(max(0, y + height - (bottom - top)) / total)

    def _stretch(self, event):
        self.canvas.itemconfigure(self._window, width=event.width)

    def _scrollregion(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


_file_dialog_new_folder_ready = False


def install_file_dialog_new_folder(root):
    """Add a New-folder button to the Tk file and directory dialogs."""
    global _file_dialog_new_folder_ready
    if _file_dialog_new_folder_ready:
        return
    root.tk.call("auto_load", "::tk::dialog::file::")
    root.tk.call("auto_load", "::tk::dialog::file::chooseDir::")
    root.tk.createcommand("cinema_new_folder_label", lambda: t("file_dialog_new_folder"))
    root.tk.createcommand(
        "cinema_new_folder",
        lambda window_path: _create_folder_in_file_dialog(root, window_path),
    )
    root.tk.eval(
        r"""
        namespace eval ::cinema {}
        if {[info commands ::tk::dialog::file::CreateOriginal] eq ""} {
            rename ::tk::dialog::file::Create ::tk::dialog::file::CreateOriginal
        }
        proc ::tk::dialog::file::Create {w class} {
            ::tk::dialog::file::CreateOriginal $w $class
            if {![winfo exists $w.contents.f2.newfolder]} {
                set btn [::tk::AmpWidget ttk::button $w.contents.f2.newfolder \
                    -command [list cinema_new_folder $w]]
                if {$class eq "TkFDialog"} {
                    grid $btn -row 3 -column 0 -columnspan 2 -padx 4 -pady 3 -sticky w
                } else {
                    grid $btn -row 2 -column 0 -columnspan 2 -padx 4 -pady 3 -sticky w
                }
            }
            bind $w <Map> +[list ::cinema::refreshFileDialogFolder $w]
            ::cinema::refreshFileDialogFolder $w
        }
        proc ::cinema::refreshFileDialogFolder {w} {
            if {[winfo exists $w.contents.f2.newfolder]} {
                ::tk::SetAmpText $w.contents.f2.newfolder [cinema_new_folder_label]
            }
        }
        """
    )
    _file_dialog_new_folder_ready = True


def _folder_name_is_plain(name):
    if not name or name in (".", "..") or "\\" in name or "\0" in name:
        return False
    return os.path.basename(name) == name


class _ExistingWindow(tk.Misc):
    """A Tk window created in Tcl, usable as a dialog parent."""

    def __init__(self, root, path):
        self.tk = root.tk
        self._w = path
        self.children = {}
        self._last_child_ids = {}
        self.master = root


def _create_folder_in_file_dialog(root, window_path):
    if not root.tk.call("winfo", "exists", window_path):
        return
    window = _ExistingWindow(root, window_path)
    data_name = window_path.split(".")[-1]
    try:
        current = str(root.tk.call("set", f"::tk::dialog::file::{data_name}(selectPath)"))
    except tk.TclError:
        current = ""
    if not current or not os.path.isdir(current):
        current = os.getcwd()
    title = t("file_dialog_new_folder").replace("&", "")
    name = simpledialog.askstring(
        title,
        t("file_dialog_new_folder_prompt"),
        parent=window,
    )
    if name is None:
        return
    name = name.strip()
    if not name:
        return
    if not _folder_name_is_plain(name):
        messagebox.showerror(title, t("file_dialog_new_folder_invalid"), parent=window)
        return
    path = os.path.abspath(os.path.join(current, name))
    try:
        os.mkdir(path)
    except OSError as exc:
        messagebox.showerror(
            title,
            t("file_dialog_new_folder_error").format(error=exc),
            parent=window,
        )
        return
    try:
        root.tk.call("set", f"::tk::dialog::file::{data_name}(selectPath)", path)
    except tk.TclError:
        return
    if str(root.tk.call("winfo", "class", window_path)) == "TkChooseDir":
        entry = window_path + ".contents.f2.ent"
        try:
            root.tk.call(entry, "delete", 0, "end")
            root.tk.call(entry, "insert", 0, path)
        except tk.TclError:
            pass
    try:
        root.tk.call("::tk::dialog::file::UpdateWhenIdle", window_path)
    except tk.TclError:
        pass


def header_clock_text(moment):
    """Local wall time for the header. Always 24-hour, with seconds."""
    return moment.strftime("%H:%M:%S")


class _CopyCancelled(Exception):
    """The operator stopped a file copy from the progress dialog."""


class VideoPlayerGUI:
    def __init__(self, root):
        global _dialog_owner
        self.root = root
        _dialog_owner = self
        self._popup_stack = []
        self.root.title(f"Cinema Player {APP_VERSION}")
        self.icon_image = self._load_image(LOGO_ICON_FILE)
        if self.icon_image is not None:
            self.root.iconphoto(True, self.icon_image)
        self.root.minsize(1280, 720)
        self.root.geometry("1600x900")

        self.settings = load_settings()
        self.language = set_language(self.settings.get("language", "en"))
        install_file_dialog_new_folder(self.root)
        self.text_size = apply_text_size(self.settings.get("text_size", 0))
        sync_fonts()
        self.theme = apply_theme(self.settings.get("theme", DEFAULT_THEME))
        self.root.configure(bg=COLOR_BG)
        self.apply_widget_defaults()
        self.transport_icons = {}

        preferred_output = self.settings.get("video_output") or VIDEO_OUTPUT
        self.output_manager = VideoOutputManager(preferred_output)
        try:
            if preferred_output:
                self.output_manager.select_video_output(preferred_output)
            else:
                self.output_manager.select_video_output()
        except Exception:
            self.output_manager.video_output = None
            try:
                self.output_manager.select_video_output()
            except Exception:
                pass
        self.mpv_path = find_mpv()
        self.main_mpv = MPVController("main", self.mpv_path)
        self.preview_mpv = MPVController("preview", self.mpv_path)

        self.playlist = []
        self.playlist_path = ""
        self.program_state = "OFF"
        # The phone may still be touching the offline veil when the server appears.
        self._remote_ready_at = time.monotonic() + 1.0
        self.playlist_tools_open = False
        self.calibration_mode = None
        self.volume_setup = False
        self.program_index = 0
        self.zoom_confirmed_index = None
        self.preview_index = None
        self.preview_live = True
        self.live_parked = None
        self.current_file = None
        self.duration = 0.0
        self.position = 0.0
        self.preview_duration = 0.0
        self.preview_position = 0.0
        self.preview_paused = True
        self.preview_stopped = False
        self._preview_full_file = False
        self.preview_levels = []
        self.preview_levels_at = 0.0
        self._meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        self.program_levels = []
        self.program_levels_at = 0.0
        self._program_meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        self._meter_after_id = None
        self.program_video_bps = 0
        self.program_audio_bps = 0
        self.program_hwdec = ""
        self.program_frame_drops = 0
        self.program_decoder_drops = 0
        self.preview_video_bps = 0
        self.preview_audio_bps = 0
        self.main_pause = False
        self.blackout = False
        self.idle_media_path = ""
        self.idle_showing = False
        self.hdmi_audio_keepalive = False
        self._program_playback_started = False
        self._program_load_id = 0
        self._program_loaded_id = 0
        self._program_playhead = None
        self.beamer_test_active = False
        self.edid_window = None
        self.media_dirs_window = None
        self.audiosync_list_window = None
        self.idle_after_id = None
        self.autoplay_after_id = None
        self.still_after_id = None
        self.still_started = None
        self.still_waiting = False
        self.still_fade_after = None
        self._still_fade_done = None
        self._still_fade_span = None
        self._still_fading_out = False
        self._still_fade_out_done = False
        self._still_level = 1.0
        self._picture_brightness = 0
        self.drag_index = None
        self.drag_y = 0
        self.drag_moved = False
        self.drop_marker = None
        self.row_widgets = []
        self.row_menu = None
        self._posted_menu = None
        self._menu_ignore_press = False
        self._menu_binds_armed = False
        self.last_import_dir = self.settings.get("last_import_dir") or ""
        if self.last_import_dir and not os.path.isdir(self.last_import_dir):
            self.last_import_dir = ""
        self.media_directories = normalize_media_directories(
            self.settings.get("media_directories", [])
        )
        self.settings["media_directories"] = self.media_directories
        self._media_dir_name_var = None
        self._media_dir_name_entry = None
        self._media_dir_name_index = None
        self._media_dir_name_guard = False
        self.import_path = self._stored_import_path()
        self.audiosync_delays = self._normalize_audiosync_delays(
            self.settings.get("audiosync_delays", {})
        )
        self.audiosync_delay_ms = tk.IntVar(value=0)
        self.last_playlist_dir = self.settings.get("last_playlist_dir") or ""
        if self.last_playlist_dir and not os.path.isdir(self.last_playlist_dir):
            self.last_playlist_dir = ""
        self.last_playlist_path = self.settings.get("last_playlist_path") or ""
        if self.last_playlist_path and not os.path.isfile(self.last_playlist_path):
            self.last_playlist_path = ""

        self.projection_zoom = tk.BooleanVar(value=False)
        self.pad_16x9 = tk.BooleanVar(value=bool(self.settings.get("pad_16x9", True)))
        self.autosave_on_program_change = tk.BooleanVar(
            value=bool(self.settings.get("autosave_on_program_change", False))
        )
        self.still_dim = tk.BooleanVar(value=bool(self.settings.get("still_dim", False)))
        self.still_dim_seconds = tk.StringVar(
            value=format_seconds(self.settings.get("still_dim_seconds", 1))
        )
        self.load_last_playlist_at_start = tk.BooleanVar(
            value=bool(self.settings.get("load_last_playlist_at_start", False))
        )
        self.window_fullscreen = tk.BooleanVar(
            value=bool(self.settings.get("window_fullscreen", False))
        )
        self.use_default_idle_media = tk.BooleanVar(
            value=bool(self.settings.get("use_default_idle_media", False))
        )
        self.remote_api_enabled = tk.BooleanVar(
            value=bool(self.settings.get("remote_api_enabled", True))
        )
        try:
            remote_port = int(self.settings.get("remote_api_port", DEFAULT_PORT))
        except (TypeError, ValueError):
            remote_port = DEFAULT_PORT
        self.remote_api_port = tk.StringVar(value=str(remote_port))
        self.remote_api_token = tk.StringVar(value=str(self.settings.get("remote_api_token", "") or ""))
        self.remote_api = RemoteAPIServer(self)
        self.remote_window = None
        self.remote_window_indicator = None
        self.lights_window = None
        self.lights_window_indicator = None
        self.patch_window = None
        self.output_manager.set_audio_patch(self.settings.get("audio_patch"))
        lights_cfg = self.settings.get("lights") if isinstance(self.settings.get("lights"), dict) else {}
        (
            self.dmx_output,
            self.lights_scenes,
            self.lights_transition_ms,
            lights_on,
            self.lights_start_lead_ms,
            self.lights_end_lead_ms,
            self.lights_sequences,
        ) = dmx.load_lights_config(lights_cfg)
        self.lights_control = tk.BooleanVar(value=lights_on)
        self.settings_lights_check = None
        self.lights_current = ""
        self._sequence_run = None
        self.lights_fading = False
        self.lights_fade_after = None
        self.lights_blink_after = None
        self.lights_blink_on = False
        self.lights_shown_levels = {}
        self._light_meter_fade = None
        self.lights_meter_after = None
        self.program_light_meters = None
        self.program_light_meter_bars = {}
        self.lights_play_after = None
        self.lights_end_sent = False
        self._light_errors = []
        self._light_error_lock = threading.Lock()
        self.program_light_buttons = {}
        self.settings_light_buttons = {}
        self.program_light_bar = None
        self.settings_light_bar = None
        self._scene_draft = None
        self._scene_edit_id = ""
        self._scene_guard = False
        self._scene_listbox = None
        self._scene_name_var = None
        self._scene_level_vars = {}
        self._scene_levels_frame = None
        self._scene_delete_button = None
        self._remote_action = False
        self._windowed_geometry = None
        self._fullscreen_applied = False
        self.autoplay_delay = tk.StringVar(value="0")
        self.idle_media = tk.StringVar(value=t("idle_none"))
        self.idle_status = None
        self.settings_warning_status = None
        self.autoplay_var = tk.BooleanVar(value=False)
        self.clip_settings_warning_var = tk.BooleanVar(value=False)
        self.loop_var = tk.BooleanVar(value=False)
        self.played_var = tk.BooleanVar(value=False)
        self.display_time = tk.StringVar(value="0")
        self.audio_var = tk.StringVar(value="--")
        self.subtitle_var = tk.StringVar(value="--")
        self.light_start_var = tk.StringVar(value="")
        self.light_end_var = tk.StringVar(value="")
        self.program_volume = tk.DoubleVar(value=100)
        self.preview_volume = tk.DoubleVar(value=100)
        self.preview_muted = False
        self.beamer_output = tk.StringVar(value=self.output_manager.video_output or "")
        self.beamer_details_open = False
        self._volume_preview_key = None
        self._volume_program_key = None
        # Last level actually sent to the program player. None until the first
        # clip, so a show does not fade up out of silence.
        self._program_volume_output = None
        self._program_volume_glide = None
        self._program_volume_glide_after = None
        self.root.tooltip_screen_bounds = self._tooltip_screen_bounds

        self.create_gui()
        self._arm_menu_dismiss_binds()
        self.main_mpv.add_callback(self.main_mpv_event)
        self.preview_mpv.add_callback(self.preview_mpv_event)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind_all("<Control-F4>", self.close)
        self.root.bind_all("<F11>", self.toggle_window_fullscreen)
        self.root.bind_all("<KeyPress-i>", self._on_key_set_in, add="+")
        self.root.bind_all("<KeyPress-I>", self._on_key_set_in, add="+")
        self.root.bind_all("<KeyPress-o>", self._on_key_set_out, add="+")
        self.root.bind_all("<KeyPress-O>", self._on_key_set_out, add="+")
        self.root.after_idle(self._apply_window_fullscreen)
        self.root.after(200, self.start_preview_player)
        # Honor a saved / forced output even if it is the primary display.
        explicit_output = bool(self.settings.get("video_output") or VIDEO_OUTPUT)
        # Cover the projector before any mode switch so GNOME desktop icons
        # never appear on the beamer during startup.
        self.ensure_main_output(auto=not explicit_output)
        self.root.after(500, self._warn_if_no_beamer_output)
        self.update_gui()
        self._tick_meters()
        self.refresh_all()
        self._restore_last_playlist()
        if self.use_default_idle_media.get():
            self._apply_default_idle_media(show_error=False)
        self._start_remote_api()
        self._sync_lights_control()
        self._apply_lights("bright", force=True)
        self._remember_saved_playlist()

    def _warn_if_no_beamer_output(self):
        if not self.output_manager.has_dedicated_beamer():
            messagebox.showwarning(t("beamer_no_output_title"), t("beamer_no_output"))
        self._offer_playlist_library()

    def create_gui(self):
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        self._build_logo()

        left = tk.Frame(self.root, bg=COLOR_BG)
        left.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(4, weight=1)

        right = tk.Frame(self.root, bg=COLOR_BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        self._build_program_status(left)
        self._build_show_strip(left)
        self._build_program_block(left)
        self._build_playlist_block(left)
        self._build_beamer(right)
        self._build_preview(right)

    def _build_logo(self):
        header = tk.Frame(self.root, bg=COLOR_BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6))

        tools = tk.Frame(header, bg=COLOR_BG)
        tools.pack(side="right")
        self.header_tools = tools
        self.app_menu = self._burger_button(
            tools, t("app_menu"), self._fill_app_menu, side="right",
        )
        self._help_button(tools)
        self._build_remote_indicator(tools)
        self._build_lights_indicator(tools)
        self._build_header_clock(header)

        self.logo_image = self._load_image(LOGO_HEADER_FILE)
        if self.logo_image is not None:
            tk.Label(header, image=self.logo_image, bg=LOGO_BG, bd=0).pack(side="left")
        else:
            plate = tk.Frame(header, bg=LOGO_BG)
            plate.pack(side="left")
            tk.Label(
                plate, text="CINEMA", bg=LOGO_BG, fg=COLOR_WHITE, font=FONT_LOGO,
            ).pack(side="left", padx=(10, 0), pady=4)
            tk.Label(
                plate, text="PLAYER", bg=LOGO_BG, fg=LOGO_ACCENT, font=FONT_LOGO_LIGHT,
            ).pack(side="left", padx=(7, 10), pady=4)
        self.header_version = tk.Label(
            header,
            text=header_version_text(
                APP_VERSION,
                read_mpv_version(getattr(self, "mpv_path", "")),
                session_display_name(),
            ),
            bg=COLOR_BG, fg=COLOR_MUTED, font=FONT_UI,
        )
        self.header_version.pack(side="left", padx=(10, 0), pady=(0, 8), anchor="s")

    def _build_header_clock(self, parent):
        """Wall clock immediately left of the header icons."""
        self.header_clock = tk.Label(
            parent,
            text=header_clock_text(datetime.now()),
            bg=COLOR_BG,
            fg=COLOR_TEXT,
            font=FONT_HEADER_CLOCK,
        )
        self.header_clock.pack(side="right", padx=(12, 16))
        self._start_header_clock()

    def _start_header_clock(self):
        self._cancel_header_clock()
        self._tick_header_clock()

    def _tick_header_clock(self):
        label = getattr(self, "header_clock", None)
        try:
            if label is None or not label.winfo_exists():
                self.header_clock_after = None
                return
            label.configure(text=header_clock_text(datetime.now()))
        except tk.TclError:
            self.header_clock_after = None
            return
        self._cancel_header_clock()
        self.header_clock_after = self.root.after(250, self._tick_header_clock)

    def _cancel_header_clock(self):
        after_id = getattr(self, "header_clock_after", None)
        self.header_clock_after = None
        if not after_id:
            return
        try:
            self.root.after_cancel(after_id)
        except tk.TclError:
            pass

    def _load_image(self, path):
        try:
            return tk.PhotoImage(file=path)
        except tk.TclError:
            return None

    def _load_icon(self, name, size=TRANSPORT_ICON_PX):
        """Load a transport PNG and scale it down for the button bar."""
        image = self._load_image(os.path.join(ICONS_DIR, f"{name}.png"))
        if image is None:
            return None
        # Scale by height so wide icons such as reset-played match the others.
        factor = max(1, round(image.height() / size))
        if factor > 1:
            image = image.subsample(factor)
        return image

    def _transport_icon(self, name):
        if name not in self.transport_icons:
            self.transport_icons[name] = self._load_icon(name)
        return self.transport_icons[name]

    def _use_outline_named_fonts(self):
        """Point Tk's built-in fonts at faces FreeType can draw smoothly."""
        mono = FONT_EDID[0]
        for name in (
            "TkDefaultFont",
            "TkTextFont",
            "TkMenuFont",
            "TkHeadingFont",
            "TkCaptionFont",
            "TkSmallCaptionFont",
            "TkIconFont",
            "TkTooltipFont",
        ):
            self._configure_named_font(name, FONT_FAMILY)
        self._configure_named_font("TkFixedFont", mono)

    @staticmethod
    def _configure_named_font(name, family):
        try:
            import tkinter.font as tkfont
            tkfont.nametofont(name).configure(family=family)
        except (tk.TclError, ImportError):
            pass

    def apply_widget_defaults(self):
        """Colour the widget classes that are built without explicit colours."""
        self._use_outline_named_fonts()
        for pattern, value in (
            ("*Font", f"{FONT_FAMILY} {FONT_UI[1]}"),
            ("*Label.foreground", COLOR_TEXT),
            ("*Button.background", COLOR_BUTTON),
            ("*Button.foreground", COLOR_TEXT),
            ("*Button.activeBackground", COLOR_BUTTON_ACTIVE),
            ("*Button.activeForeground", COLOR_TEXT),
            ("*Button.highlightBackground", COLOR_BG),
            ("*Entry.background", COLOR_FIELD),
            ("*Entry.foreground", COLOR_TEXT),
            ("*Entry.insertBackground", COLOR_TEXT),
            ("*Entry.highlightBackground", COLOR_BORDER),
            ("*TCombobox*Listbox.background", COLOR_FIELD),
            ("*TCombobox*Listbox.foreground", COLOR_TEXT),
            ("*TCombobox*Listbox.selectBackground", COLOR_PROGRAM),
            ("*TCombobox*Listbox.selectForeground", COLOR_WHITE),
        ):
            self.root.option_add(pattern, value)

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "TCombobox", fieldbackground=COLOR_FIELD, background=COLOR_BUTTON,
            foreground=COLOR_TEXT, arrowcolor=COLOR_TEXT, bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BUTTON, darkcolor=COLOR_BUTTON, selectbackground=COLOR_FIELD,
            selectforeground=COLOR_TEXT,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLOR_FIELD)],
            foreground=[("readonly", COLOR_TEXT)],
            background=[("active", COLOR_BUTTON_ACTIVE)],
        )
        style.configure(
            "BoothLight.TCombobox",
            fieldbackground=LIGHT_BUTTON,
            background=LIGHT_BUTTON,
            foreground=LIGHT_BUTTON_TEXT,
            arrowcolor=LIGHT_CAPTION,
            bordercolor=LIGHT_BORDER,
            lightcolor=LIGHT_BORDER,
            darkcolor=LIGHT_BORDER,
            selectbackground=LIGHT_BUTTON,
            selectforeground=LIGHT_BUTTON_TEXT,
        )
        style.map(
            "BoothLight.TCombobox",
            fieldbackground=[("readonly", LIGHT_BUTTON), ("disabled", LIGHT_PANEL)],
            foreground=[("readonly", LIGHT_BUTTON_TEXT), ("disabled", "#8a7a66")],
            background=[("readonly", LIGHT_BUTTON), ("active", LIGHT_ACTIVE)],
            arrowcolor=[("disabled", "#8a7a66")],
            selectbackground=[("readonly", LIGHT_BUTTON)],
            selectforeground=[("readonly", LIGHT_BUTTON_TEXT)],
        )
        style.configure(
            "Vertical.TScrollbar", background=COLOR_BUTTON, troughcolor=COLOR_BG,
            arrowcolor=COLOR_TEXT, bordercolor=COLOR_BORDER, lightcolor=COLOR_BUTTON,
            darkcolor=COLOR_BUTTON,
        )
        style.map("Vertical.TScrollbar", background=[("active", COLOR_BUTTON_ACTIVE)])
        style.configure(
            "Horizontal.TScrollbar", background=COLOR_BUTTON, troughcolor=COLOR_BG,
            arrowcolor=COLOR_TEXT, bordercolor=COLOR_BORDER, lightcolor=COLOR_BUTTON,
            darkcolor=COLOR_BUTTON,
        )
        style.map("Horizontal.TScrollbar", background=[("active", COLOR_BUTTON_ACTIVE)])
        style.configure(
            "Copy.Horizontal.TProgressbar",
            troughcolor=COLOR_FIELD,
            background=COLOR_PROGRAM,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_PROGRAM,
            darkcolor=COLOR_PROGRAM,
        )

    def toggle_theme(self):
        self.theme = apply_theme("dark" if self.theme == "light" else "light")
        self.settings["theme"] = self.theme
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self.rebuild_gui()

    def _tooltip_screen_bounds(self):
        """Rectangle tooltips must stay inside: the control monitor, never the projector."""
        try:
            geometry = self._control_fullscreen_geometry()
        except Exception:
            geometry = None
        return geometry

    def _control_fullscreen_geometry(self):
        """Size/position of the control monitor; never the beamer output."""
        prefer_x = prefer_y = None
        try:
            self.root.update_idletasks()
            prefer_x = self.root.winfo_rootx() + max(self.root.winfo_width(), 1) // 2
            prefer_y = self.root.winfo_rooty() + max(self.root.winfo_height(), 1) // 2
        except tk.TclError:
            pass
        try:
            return self.output_manager.get_control_output_geometry(
                prefer_x=prefer_x, prefer_y=prefer_y,
            )
        except Exception:
            return None

    def _remember_windowed_geometry(self):
        try:
            self.root.update_idletasks()
            geometry = self.root.geometry()
        except tk.TclError:
            return
        if geometry and not geometry.startswith("1x1"):
            self._windowed_geometry = geometry

    def _release_window_grabs(self):
        self._close_menus()
        try:
            self.root.grab_release()
        except tk.TclError:
            pass

    def _window_overlaps_beamer(self):
        beamer = self.output_manager.video_output
        if not beamer:
            return False
        try:
            rect = self.output_manager.get_output_geometry(beamer)
            self.root.update_idletasks()
            wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
            ww, wh = self.root.winfo_width(), self.root.winfo_height()
        except (tk.TclError, Exception):
            return False
        if not rect:
            return False
        bw, bh, bx, by = rect
        overlap_w = min(wx + ww, bx + bw) - max(wx, bx)
        overlap_h = min(wy + wh, by + bh) - max(wy, by)
        return overlap_w > 40 and overlap_h > 40

    def _fill_control_monitor(self, geometry):
        """Size the decorated window to the control screen without WM spanning."""
        width, height, x, y = geometry
        try:
            self.root.attributes("-fullscreen", False)
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def _apply_window_fullscreen(self):
        """Fullscreen on the control monitor only, as a normal WM window.

        Do not use overrideredirect: it recreates the X11 window, drops keyboard
        focus, and leaves a stuck grab so transport buttons stop working.
        """
        self._release_window_grabs()
        try:
            self.root.overrideredirect(False)
        except tk.TclError:
            pass

        enabled = bool(self.window_fullscreen.get())
        if not enabled:
            try:
                self.root.attributes("-fullscreen", False)
            except tk.TclError:
                pass
            if self._windowed_geometry:
                try:
                    self.root.geometry(self._windowed_geometry)
                except tk.TclError:
                    pass
            self._fullscreen_applied = False
            return

        if not self._fullscreen_applied:
            self._remember_windowed_geometry()
        geometry = self._control_fullscreen_geometry()
        if geometry:
            _width, _height, x, y = geometry
            try:
                self.root.geometry(f"+{x}+{y}")
                self.root.update_idletasks()
            except tk.TclError:
                pass
        try:
            self.root.attributes("-fullscreen", True)
            self.root.update_idletasks()
        except tk.TclError:
            return
        if geometry and self._window_overlaps_beamer():
            self._fill_control_monitor(geometry)
        self._fullscreen_applied = True

    def _on_window_fullscreen(self):
        self._close_menus()
        self.settings["window_fullscreen"] = bool(self.window_fullscreen.get())
        try:
            save_settings(self.settings)
        except OSError:
            pass
        # Apply after the burger menu has closed and released its X11 grab.
        self.root.after_idle(self._apply_window_fullscreen)

    def toggle_window_fullscreen(self, _event=None):
        self.window_fullscreen.set(not self.window_fullscreen.get())
        self._on_window_fullscreen()
        return "break"

    def change_language(self, code):
        if set_language(code) == self.language:
            return
        self.language = code
        self.settings["language"] = code
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self.rebuild_gui()

    def change_text_size(self, delta):
        size = apply_text_size(delta)
        if size == self.text_size:
            return
        self.text_size = size
        sync_fonts()
        self.settings["text_size"] = size
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self.rebuild_gui()

    def rebuild_gui(self):
        """Rebuild the window for the current design and re-embed the preview player."""
        self._cancel_program_volume_glide()
        self._cancel_header_clock()
        if getattr(self, "lights_window", None) is not None:
            self._commit_lights_settings()
            self._scene_draft = None
            self._scene_listbox = None
            self._scene_levels_frame = None
            self._scene_delete_button = None
            self.settings_light_bar = None
        self.preview_mpv.quit()
        self._close_menus()
        self._close_patch_window()
        self.edid_window = None
        self.media_dirs_window = None
        self.audiosync_list_window = None
        self.remote_window = None
        self.lights_window = None
        for child in self.root.winfo_children():
            child.destroy()
        self.row_widgets = []
        self.drop_marker = None
        self.drag_index = None
        self.drag_moved = False
        self.row_menu = None
        self._posted_menu = None
        self._volume_preview_key = None
        self._volume_program_key = None
        self.root.configure(bg=COLOR_BG)
        sync_fonts()
        self.apply_widget_defaults()
        self.create_gui()
        self._show_audiosync_controls(self.calibration_mode == "audio")
        self.refresh_all()
        self.root.after(200, self.restore_preview)

    def restore_preview(self):
        self.start_preview_player()
        entry = self.selected_entry()
        if not entry:
            return
        if self.preview_live and self.program_state == "PLAYING":
            self.show_preview_clip(entry, follow_live=True, start=self.position)
        else:
            self.show_preview_clip(entry, start=self.preview_position)

    def _menu_check_fg(self):
        """Selected-item colour: cyan on dark menus, program-blue on light menus."""
        return COLOR_VOLUME if THEME == "dark" else COLOR_PROGRAM

    def _menu(self, parent, **kwargs):
        """Popup menu colours. Dark: light checkbox fill. Light: blue fill for contrast."""
        if isinstance(parent, DropdownMenu):
            return DropdownMenu(self.root, self)
        options = dict(
            tearoff=0,
            bg=COLOR_PANEL,
            fg=COLOR_TEXT,
            activebackground=COLOR_PROGRAM,
            activeforeground=COLOR_WHITE,
            disabledforeground=COLOR_PLAYED,
            selectcolor="#f2f2f2" if THEME == "dark" else COLOR_PROGRAM,
        )
        options.update(kwargs)
        return tk.Menu(parent, **options)

    def _panel(self, parent, **kwargs):
        return tk.Frame(parent, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER,
                        highlightthickness=1, **kwargs)

    def _group_frame(self, parent):
        """Subtle block matching the playlist entry colour."""
        return tk.Frame(
            parent,
            bg=COLOR_PANEL,
            highlightbackground=COLOR_ROW,
            highlightthickness=1,
        )

    def _checkbutton(self, parent, text, variable, command, bg):
        return tk.Checkbutton(
            parent, text=text, variable=variable, command=command, font=FONT_UI,
            bg=bg, fg=COLOR_TEXT, activebackground=bg, activeforeground=COLOR_TEXT,
            selectcolor=COLOR_FIELD, highlightthickness=0,
        )

    def _build_program_status(self, parent):
        bar = tk.Frame(parent, bg=COLOR_BG)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.columnconfigure(1, weight=1)

        self.state_label = tk.Label(
            bar, text=t("state_off"), font=FONT_STATUS, bg=COLOR_OFF, fg=COLOR_WHITE,
            width=12, pady=6,
        )
        self.state_label.grid(row=0, column=0, sticky="nsw")

        self.now_playing = tk.Label(
            bar, text=t("no_program"), font=FONT_UI_BOLD, bg=COLOR_READOUT,
            fg=COLOR_TEXT, anchor="w", padx=10,
        )
        self.now_playing.grid(row=0, column=1, sticky="nsew")

        self.program_times = tk.Label(
            bar, text="-- / --:--", font=FONT_STATUS, bg=COLOR_READOUT,
            fg=COLOR_TEXT, padx=10,
        )
        self.program_times.grid(row=0, column=2, sticky="nse")

        self.next_clip = tk.Label(
            bar, text="", font=FONT_SMALL, bg=COLOR_BG, fg=COLOR_TEXT, anchor="w",
        )
        self.next_clip.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        self.next_clip.grid_remove()
        self.idle_status = tk.Label(
            bar, text="", font=FONT_SMALL, bg=COLOR_BG, fg=COLOR_TEXT, anchor="e",
        )
        self.idle_status.grid(row=1, column=2, sticky="e", padx=(12, 0), pady=(4, 0))
        self.idle_status.grid_remove()

    def _build_show_strip(self, parent):
        """House lights and the clip dimmer, clear of the playlist file tools."""
        strip = tk.Frame(parent, bg=COLOR_BG)
        strip.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.show_strip = strip

        panel = tk.Frame(
            strip, bg=LIGHT_PANEL, padx=10, pady=4,
            highlightthickness=1, highlightbackground=LIGHT_BORDER, highlightcolor=LIGHT_BORDER,
        )
        panel.pack(side="left")
        self.program_light_bar = panel
        scenes = tk.Frame(panel, bg=LIGHT_PANEL)
        scenes.pack(side="left", anchor="w")
        self.program_light_scenes = scenes
        self.program_light_buttons = {}
        self._fill_light_buttons(
            scenes, self.program_light_buttons, self._on_light_preset, face="booth",
        )
        meters = tk.Frame(panel, bg=LIGHT_PANEL)
        meters.pack(side="left", padx=(14, 0))
        self.program_light_meters = meters
        self.program_light_meter_bars = {}
        self._build_light_meters()

        status = tk.Frame(strip, bg=COLOR_BG)
        self.show_status = status
        status.pack(side="left", padx=(16, 0))
        self.settings_warning_status = tk.Label(
            status, text="", font=FONT_SMALL, bg=COLOR_BG, fg=COLOR_WARNING,
        )
        self._refresh_light_buttons()
        self._refresh_idle_status()
        self._apply_program_light_block()

    def _build_program_block(self, parent):
        group = self._group_frame(parent)
        group.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        group.columnconfigure(0, weight=1)
        self.program_group = group

        body = tk.Frame(group, bg=COLOR_PANEL)
        body.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=6)
        body.columnconfigure(0, weight=1)

        progress = tk.Frame(body, bg=COLOR_PANEL)
        progress.grid(row=0, column=0, sticky="ew")
        progress.columnconfigure(0, weight=1)

        self.program_progress = progress
        self.main_progress = RangeProgressBar(
            progress, on_seek=self._on_main_seek, can_seek=self.program_seek_allowed,
            height=32, bg=COLOR_PANEL,
        )
        self.main_progress.grid(row=0, column=0, sticky="ew")
        self.program_video_bitrate = self._bitrate_readout(progress, "video_bitrate")
        self.program_video_bitrate.grid(row=0, column=1, sticky="e", padx=(8, 8))

        self.program_envelope = EnvelopeCanvas(
            progress, on_seek=self._on_main_seek, can_seek=self.program_seek_allowed,
            bg=COLOR_PANEL,
        )
        self.program_envelope.grid(row=1, column=0, sticky="ew")

        volume = self._build_volume_row(
            progress, self.program_volume, self._on_program_volume, COLOR_PANEL,
        )
        self.program_volume_row = volume
        volume.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 0))
        self.program_audio_bitrate = self._bitrate_readout(progress, "audio_bitrate")
        self.program_audio_bitrate.grid(row=2, column=1, sticky="e", padx=(8, 8), pady=(4, 0))
        self._pin_bitrate_column(progress, self.program_video_bitrate)

        self.audiosync_frame = tk.Frame(progress, bg=COLOR_PANEL)
        delay_row = tk.Frame(self.audiosync_frame, bg=COLOR_PANEL)
        delay_row.pack(fill="x")
        tk.Label(
            delay_row, text=t("audiosync_delay"), bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_SMALL,
        ).pack(side="left")
        self.audiosync_delay_bar = DelayBar(delay_row, on_change=self._on_audiosync_delay, bg=COLOR_PANEL)
        self.audiosync_delay_bar.pack(side="left", fill="x", expand=True, padx=8)
        self.audiosync_delay_label = tk.Label(
            delay_row, text=format_delay_ms(0), width=8, anchor="e",
            bg=COLOR_PANEL, fg=COLOR_VOLUME, font=FONT_UI_BOLD,
        )
        self.audiosync_delay_label.pack(side="left")
        tk.Button(
            delay_row, text="−", font=FONT_UI, width=2,
            command=lambda: self._nudge_audiosync_delay(-AUDIO_DELAY_STEP_MS),
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            delay_row, text="+", font=FONT_UI, width=2,
            command=lambda: self._nudge_audiosync_delay(AUDIO_DELAY_STEP_MS),
        ).pack(side="left", padx=(4, 0))
        buttons = tk.Frame(self.audiosync_frame, bg=COLOR_PANEL)
        buttons.pack(fill="x", pady=(4, 0))
        tk.Button(
            buttons, text=t("audiosync_list"), font=FONT_SMALL, command=self.show_audiosync_delays,
        ).pack(side="left")
        tk.Button(
            buttons, text=t("audiosync_load"), font=FONT_SMALL, command=self.load_audiosync_delays,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("audiosync_save"), font=FONT_SMALL, command=self.save_audiosync_delays,
        ).pack(side="left", padx=(8, 0))

        marks = tk.Frame(progress, bg=COLOR_PANEL)
        marks.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8)
        for col in range(3):
            marks.columnconfigure(col, weight=1)
        self.main_in = tk.Label(marks, text=t("in_value", value="--:--"), bg=COLOR_PANEL, font=FONT_SMALL)
        self.main_in.grid(row=0, column=0, sticky="w")
        self.main_time = tk.Label(marks, text=t("time_value", value="--:--"), bg=COLOR_PANEL, font=FONT_SMALL)
        self.main_time.grid(row=0, column=1)
        self.main_out = tk.Label(marks, text=t("out_value", value="--:--"), bg=COLOR_PANEL, font=FONT_SMALL)
        self.main_out.grid(row=0, column=2, sticky="e")

        bottom = tk.Frame(body, bg=COLOR_PANEL)
        bottom.grid(row=1, column=0, sticky="ew", pady=(8, 2))
        bottom.columnconfigure(1, weight=1)
        self._build_transport(bottom)

        times = tk.Frame(bottom, bg=COLOR_PANEL)
        self.program_clocks = times
        times.grid(row=0, column=1, sticky="ew")
        for col in range(4):
            times.columnconfigure(col, weight=1)
        self.time_total = self._time_box(times, t("total"), 0)
        self.time_elapsed = self._time_box(times, t("elapsed"), 1)
        self.time_remaining = self._time_box(times, t("remaining"), 2, primary=True)
        self.time_end = self._time_box(times, t("end"), 3, primary=True)

        self.program_meter = LevelMeter(group, bg=COLOR_PANEL, height=1)
        self.program_meter.grid(row=0, column=1, sticky="ns", padx=(8, 8), pady=6)

    def _time_box(self, parent, title, column, primary=False):
        """Remaining and end stay larger than total and elapsed."""
        box = tk.Frame(parent, bg=COLOR_PANEL)
        box.grid(row=0, column=column, sticky="ew")
        tk.Label(
            box, text=title,
            font=FONT_UI_BOLD if primary else FONT_SMALL,
            bg=COLOR_PANEL, fg=COLOR_TEXT if primary else COLOR_MUTED,
        ).pack()
        value = tk.Label(
            box, text="--:--",
            font=FONT_CLOCK if primary else FONT_UI,
            bg=COLOR_PANEL, fg=COLOR_TEXT,
        )
        value.pack()
        return value

    def _bitrate_readout(self, parent, tooltip_key):
        label = tk.Label(
            parent,
            text="--",
            width=10,
            anchor="e",
            bg=COLOR_PANEL,
            fg=COLOR_MUTED,
            font=FONT_SMALL,
        )
        label.tooltip = IconTooltip(label, t(tooltip_key))
        return label

    @staticmethod
    def _pin_bitrate_column(frame, label):
        """Keep the readout column, so the bar beside it does not change length."""
        try:
            frame.columnconfigure(1, minsize=label.winfo_reqwidth() + 16)
        except tk.TclError:
            pass

    def _build_volume_row(self, parent, variable, on_change, bg, save=False, accent=None):
        accent = COLOR_VOLUME if accent is None else accent
        row = tk.Frame(parent, bg=bg)
        tk.Label(row, text=t("volume"), bg=bg, fg=COLOR_TEXT, font=FONT_SMALL).pack(side="left")
        bar = VolumeBar(row, on_change=on_change, bg=bg, fill=accent)
        bar.pack(side="left", fill="x", expand=True, padx=8)
        bar.set_volume(variable.get())
        label = tk.Label(
            row, text=str(clamp_volume(variable.get())), width=3, anchor="e",
            bg=bg, fg=accent, font=FONT_UI_BOLD,
        )
        label.accent = accent
        label.pack(side="left")
        tk.Label(row, text="%", bg=bg, fg=accent, font=FONT_SMALL).pack(side="left", padx=(2, 0))
        if save:
            self.preview_volume_bar = bar
            self.preview_volume_label = label
            mute = tk.Button(
                row, text=t("preview_mute"), font=FONT_SMALL, width=8,
                command=self._toggle_preview_mute, cursor="hand2",
            )
            mute.pack(side="left", padx=(8, 0))
            mute.tooltip = IconTooltip(mute, t("preview_mute_tip"))
            self.preview_mute_button = mute
            self._paint_preview_mute()
            tk.Button(
                row, text=t("save_volume"), font=FONT_SMALL, command=self.save_preview_volume,
            ).pack(side="left", padx=(8, 0))
        else:
            self.program_volume_bar = bar
            self.program_volume_label = label
            save_program = tk.Button(
                row, text=t("save_volume"), font=FONT_SMALL,
                command=self.save_program_volume, cursor="hand2",
            )
            self.program_save_volume = save_program
            save_program.pack(side="left", padx=(8, 0))
            self.program_delay_readout = tk.Label(
                row, text="", width=9, anchor="e",
                bg=bg, fg=COLOR_MUTED, font=FONT_SMALL,
            )
        return row

    def _set_volume_label(self, label, volume):
        if label is not None:
            label.config(text=str(clamp_volume(volume)), fg=getattr(label, "accent", COLOR_VOLUME))

    def _on_program_volume(self, value):
        volume = clamp_volume(value)
        self.program_volume.set(volume)
        self._set_volume_label(self.program_volume_label, volume)
        # The fader stays under the finger. Only the program output eases.
        self._glide_program_volume(volume, move_fader=False)

    def _cancel_program_volume_glide(self):
        """Stop the ramp timer. The last level sent stays remembered."""
        after_id = getattr(self, "_program_volume_glide_after", None)
        self._program_volume_glide_after = None
        self._program_volume_glide = None
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass

    def _remember_program_output(self, level):
        try:
            value = float(level)
        except (TypeError, ValueError):
            value = float(clamp_volume(level))
        if not math.isfinite(value):
            value = float(clamp_volume(None))
        self._program_volume_output = max(0.0, min(100.0, value))

    def _paint_program_fader(self, volume):
        shown = clamp_volume(volume)
        self.program_volume.set(shown)
        self._set_volume_label(getattr(self, "program_volume_label", None), shown)
        bar = getattr(self, "program_volume_bar", None)
        if bar is not None:
            bar.set_volume(shown)

    def _send_program_output_volume(self, mpv=None):
        """Write the live output level. A file reload must not jump to the target."""
        player = self.main_mpv if mpv is None else mpv
        if not getattr(player, "process", None) or getattr(self, "idle_showing", False):
            return
        level = getattr(self, "_program_volume_output", None)
        if level is None:
            level = self.program_volume.get()
        player.set_volume(level)

    def _glide_program_volume(self, target, move_fader=False):
        """Ease the program output to target over about one second.

        Returns True while a ramp is running. The first clip, a stopped
        player, and a level that is already there snap instead, so a show
        does not fade up from silence. A new target restarts the second from
        the level that is playing now.
        """
        target = float(clamp_volume(target))
        audible = (
            bool(getattr(self.main_mpv, "process", None))
            and not getattr(self, "idle_showing", False)
        )
        rolling = audible and getattr(self, "program_state", "PLAYING") == "PLAYING"
        current = getattr(self, "_program_volume_output", None)
        if not rolling or current is None or abs(float(current) - target) < 0.05:
            self._cancel_program_volume_glide()
            # Remember this film's level even before the player is audible, so
            # the next file does not inherit the previous clip's output.
            self._remember_program_output(target)
            if audible:
                self._send_program_output_volume()
            if move_fader:
                self._paint_program_fader(target)
            return False
        self._cancel_program_volume_glide()
        self._program_volume_glide = {
            "start": float(current),
            "target": target,
            "begun": time.monotonic(),
            "duration": PROGRAM_VOLUME_GLIDE_SECONDS,
            "move_fader": bool(move_fader),
        }
        self._step_program_volume_glide()
        return self._program_volume_glide is not None

    def _step_program_volume_glide(self):
        glide = getattr(self, "_program_volume_glide", None)
        self._program_volume_glide_after = None
        if not glide:
            return
        if getattr(self, "idle_showing", False) or getattr(self, "program_state", "PLAYING") != "PLAYING":
            self._program_volume_glide = None
            return
        elapsed = time.monotonic() - glide["begun"]
        finished = elapsed >= glide["duration"]
        level = glide["target"] if finished else program_volume_glide(
            glide["start"], glide["target"], elapsed, glide["duration"],
        )
        self._remember_program_output(level)
        try:
            self._send_program_output_volume()
            if glide.get("move_fader"):
                self._paint_program_fader(level)
            if finished:
                self._program_volume_glide = None
                return
            self._program_volume_glide_after = self.root.after(
                PROGRAM_VOLUME_GLIDE_TICK_MS, self._step_program_volume_glide,
            )
        except tk.TclError:
            self._program_volume_glide = None

    def _on_preview_volume(self, value):
        volume = clamp_volume(value)
        self.preview_volume.set(volume)
        self._set_volume_label(self.preview_volume_label, volume)
        self._apply_preview_speaker()

    def _toggle_preview_mute(self):
        """Silence the preview speaker. The fader value stays where it is."""
        self.preview_muted = not bool(getattr(self, "preview_muted", False))
        self._paint_preview_mute()
        self._apply_preview_speaker()

    def _paint_preview_mute(self):
        button = getattr(self, "preview_mute_button", None)
        if button is None:
            return
        muted = bool(getattr(self, "preview_muted", False))
        if muted:
            button.config(
                text="✔ " + t("preview_mute"),
                bg=LIGHT_ACTIVE, fg=LIGHT_ACTIVE_TEXT,
                activebackground=LIGHT_ACTIVE, activeforeground=LIGHT_ACTIVE_TEXT,
            )
        else:
            button.config(
                text=t("preview_mute"),
                bg=COLOR_BUTTON, fg=COLOR_TEXT,
                activebackground=COLOR_BUTTON_ACTIVE, activeforeground=COLOR_TEXT,
            )
        tip = getattr(button, "tooltip", None)
        if tip is not None:
            tip.text = t("preview_unmute_tip" if muted else "preview_mute_tip")

    def _apply_preview_speaker(self):
        volume = clamp_volume(self.preview_volume.get())
        muted = bool(getattr(self, "preview_muted", False))
        self.preview_mpv.set_volume(volume, muted=muted)

    def save_preview_volume(self):
        entry = self.selected_entry()
        if not entry:
            return
        entry.volume = clamp_volume(self.preview_volume.get())
        if entry is self.current_entry():
            self.program_volume.set(entry.volume)
            self._set_volume_label(self.program_volume_label, entry.volume)
            if getattr(self, "program_volume_bar", None):
                self.program_volume_bar.set_volume(entry.volume)
            self._glide_program_volume(entry.volume, move_fader=False)
        self.repaint_playlist()

    def save_program_volume(self):
        """Store the program fader on the film at the program pointer.

        Other playlist films keep their own levels. Nothing is written into
        the application settings.
        """
        entry = self.current_entry()
        if not entry:
            return
        entry.volume = clamp_volume(self.program_volume.get())
        if entry is self.selected_entry() and getattr(self, "preview_volume", None) is not None:
            self.preview_volume.set(entry.volume)
            self._set_volume_label(getattr(self, "preview_volume_label", None), entry.volume)
            if getattr(self, "preview_volume_bar", None):
                self.preview_volume_bar.set_volume(entry.volume)
            self._apply_preview_speaker()
        self.repaint_playlist()

    def _apply_volume_setup_chrome(self):
        """Keep Save volume beside the program fader so the level can go into the playlist."""
        button = getattr(self, "program_save_volume", None)
        if button is None:
            return
        readout = getattr(self, "program_delay_readout", None)
        try:
            managed = bool(button.winfo_manager())
        except tk.TclError:
            return
        if not managed:
            before = None
            if readout is not None:
                try:
                    if readout.winfo_manager():
                        before = readout
                except tk.TclError:
                    before = None
            if before is not None:
                button.pack(side="left", padx=(8, 0), before=before)
            else:
                button.pack(side="left", padx=(8, 0))
        if readout is None:
            return
        has_text = bool(str(readout.cget("text") or "").strip())
        try:
            readout_managed = bool(readout.winfo_manager())
        except tk.TclError:
            return
        if has_text and not readout_managed:
            readout.pack(side="left", padx=(8, 0))
        elif not has_text and readout_managed:
            readout.pack_forget()

    def _load_preview_volume(self, entry):
        key = id(entry) if entry else None
        if key == self._volume_preview_key:
            return
        self._volume_preview_key = key
        volume = clamp_volume(entry.volume if entry else 100)
        self.preview_volume.set(volume)
        self._set_volume_label(self.preview_volume_label, volume)
        if getattr(self, "preview_volume_bar", None):
            self.preview_volume_bar.set_volume(volume)
        self._apply_preview_speaker()

    def _load_program_volume(self, entry, force=False):
        key = id(entry) if entry else None
        if not force and key == self._volume_program_key:
            return
        self._volume_program_key = key
        volume = clamp_volume(entry.volume if entry else 100)
        self.program_volume.set(volume)
        self._set_volume_label(self.program_volume_label, volume)
        if getattr(self, "program_volume_bar", None):
            self.program_volume_bar.set_volume(volume)

    def _build_transport(self, parent):
        row = tk.Frame(parent, bg=COLOR_PANEL)
        row.grid(row=0, column=0, sticky="w")
        self.btn_stop = self._icon_button(row, "stop", self.confirm_stop, t("stop"), caption=True)
        self.btn_pause = self._icon_button(row, "pause", self.confirm_pause, t("pause"), caption=True)
        self.btn_still = self._icon_button(row, "still", self.confirm_still, t("still"), caption=True)
        self.btn_play = self._icon_button(row, "start_program", self.start_or_resume, t("start"), caption=True)
        # Weiter sits apart from Stop, Pause and Still so the press is easy to find.
        self.btn_play.master.pack_configure(padx=(28, 0))
        self.btn_play.bind("<ButtonPress-1>", self._on_resume_press)

    def _icon_button(self, parent, icon_name, command, fallback_text, tip=None, caption=False):
        host = parent
        if caption:
            host = tk.Frame(parent, bg=parent.cget("bg"))
            host.pack(side="left", padx=(0, 4))
        image = self._transport_icon(icon_name)
        button = tk.Button(
            host,
            text=fallback_text,
            image=image,
            compound="none" if image is not None else "center",
            bd=0,
            highlightthickness=0,
            relief="flat",
            bg=host.cget("bg"),
            activebackground=host.cget("bg"),
            cursor="hand2",
            padx=2,
            pady=2,
        )
        button._transport_enabled = True

        def wrapped():
            if not getattr(button, "_transport_enabled", True):
                return
            command()

        button.config(command=wrapped)
        if image is None:
            button.config(font=FONT_SMALL, width=7)
        button.icon_name = icon_name
        if caption:
            button.pack(side="top")
            cap = tk.Label(
                host, text=fallback_text, font=FONT_SMALL,
                bg=host.cget("bg"), fg=COLOR_MUTED,
            )
            cap.pack(side="top")
            button.caption = cap
        else:
            button.pack(side="left", padx=(0, 6))
        button.tooltip = IconTooltip(button, tip if tip is not None else fallback_text)
        return button

    def _set_transport_active(self, button, active, variant=None, enabled=True):
        """Swap the highlight or disabled icon instead of painting a Tk ring."""
        button._transport_enabled = enabled
        name = getattr(button, "icon_name", None)
        image = None
        if name and not enabled:
            image = self._transport_icon(f"{name}-disabled")
        elif active and variant and name:
            image = self._transport_icon(f"{name}-{variant}")
        if image is None and name:
            image = self._transport_icon(name)
        idle = button.master.cget("bg")
        button.config(
            image=image or "",
            bg=idle,
            activebackground=idle,
            highlightbackground=idle,
            highlightcolor=idle,
            highlightthickness=0,
            cursor="arrow" if not enabled else "hand2",
        )
        caption = getattr(button, "caption", None)
        if caption is not None:
            try:
                caption.config(fg=COLOR_TEXT if enabled else COLOR_PLAYED)
            except tk.TclError:
                pass

    def refresh_transport(self):
        playing = self.program_state == "PLAYING"
        paused = playing and self.main_pause and self.blackout
        frozen = playing and self.main_pause and not self.blackout
        rolling = playing and not self.main_pause
        clip_rolling = rolling and not self.still_waiting and not self._program_loop_active()
        armed = self.program_state == "PROGRAM"
        self._set_transport_active(self.btn_stop, False, enabled=self.program_state != "OFF")
        self._set_transport_active(self.btn_pause, paused, "preview", enabled=playing)
        self._set_transport_active(self.btn_still, frozen, "program", enabled=playing)
        if self._resume_reaction_held():
            self._paint_resume_plate(self._resume_reaction)
            self._set_transport_active(
                self.btn_play, True, self._resume_reaction, enabled=True,
            )
        else:
            self._resume_reaction = None
            self._paint_resume_plate(None)
            self._set_transport_active(
                self.btn_play,
                (rolling or armed) and not clip_rolling,
                "playing" if rolling else "program",
                enabled=not clip_rolling,
            )
        self._paint_resume_caption()

        entry = self.selected_entry()
        preview_ok = bool(entry and not entry.missing and not entry.is_image)
        preview_playing = bool(
            preview_ok
            and self.preview_mpv.process
            and self.preview_mpv.loaded_path
            and not self.preview_paused
            and not self.preview_stopped
        )
        preview_paused = bool(
            preview_ok
            and self.preview_mpv.process
            and self.preview_mpv.loaded_path
            and self.preview_paused
            and not self.preview_stopped
        )
        buttons = getattr(self, "preview_buttons", {})
        for name in ("rev", "fwd"):
            if buttons.get(name):
                self._set_transport_active(buttons[name], False, enabled=preview_ok)
        if buttons.get("stop"):
            self._set_transport_active(
                buttons["stop"], self.preview_stopped, "off", enabled=preview_ok,
            )
        if buttons.get("pause"):
            self._set_transport_active(
                buttons["pause"], preview_paused, "preview", enabled=preview_ok,
            )
        if buttons.get("play"):
            self._set_transport_active(
                buttons["play"], preview_playing, "playing", enabled=preview_ok,
            )
        can_mark = preview_ok
        can_clear = bool(entry and (entry.in_point is not None or entry.out_point is not None))
        io = getattr(self, "preview_io_buttons", {})
        if io.get("set_in"):
            self._set_transport_active(io["set_in"], False, enabled=can_mark)
        if io.get("set_out"):
            self._set_transport_active(io["set_out"], False, enabled=can_mark)
        if io.get("clear_in_out"):
            self._set_transport_active(io["clear_in_out"], False, enabled=can_clear)

    def _build_playlist_block(self, parent):
        """Toolbar/settings and the entry list sit in separate frames with a gap."""
        controls = self._group_frame(parent)
        controls.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(0, weight=1)
        self.playlist_group = controls
        self._build_playlist_header(controls)

        entries = self._group_frame(parent)
        entries.grid(row=4, column=0, sticky="nsew")
        entries.columnconfigure(0, weight=1)
        entries.rowconfigure(0, weight=1)
        self._build_playlist(entries)

    def _build_playlist_header(self, parent):
        header = tk.Frame(parent, bg=COLOR_PANEL)
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        header.columnconfigure(1, weight=1)

        title = tk.Frame(header, bg=COLOR_PANEL)
        title.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.playlist_refresh = self._icon_button(
            title, "playlist_refresh", self.check_playlist_files, t("refresh_playlist"),
        )
        tk.Label(
            title, text=t("playlist"), font=FONT_UI_BOLD, bg=COLOR_PANEL, fg=COLOR_TEXT,
        ).pack(side="left")

        self.playlist_name = tk.Entry(header, font=FONT_UI)
        self.playlist_name.insert(0, t("playlist_untitled"))
        self.playlist_name.grid(row=0, column=1, sticky="ew")

        buttons = tk.Frame(header, bg=COLOR_PANEL)
        buttons.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self.playlist_tool_buttons = buttons
        self._icon_button(buttons, "video_import", self.import_media, t("import"), t("import_media"))
        self._icon_button(buttons, "playlist_load", self.load_playlist, t("load"), t("load_playlist"))
        self._icon_button(buttons, "playlist_save", self.save_playlist, t("save"), t("save_playlist"))

        toggle = tk.Canvas(
            header, width=28, height=28, bg=COLOR_PANEL,
            highlightthickness=0, bd=0, cursor="hand2",
        )
        toggle.grid(row=0, column=3, sticky="e", padx=(2, 0))
        toggle.grid_remove()
        self.playlist_tools_toggle = toggle
        self._playlist_tools_hover = False
        toggle.bind("<Button-1>", self._toggle_playlist_tools)
        toggle.bind("<Enter>", self._playlist_tools_enter)
        toggle.bind("<Leave>", self._playlist_tools_leave)
        toggle.bind("<Configure>", lambda _event: self._paint_playlist_tools_arrow())
        self.playlist_tools_tip = IconTooltip(toggle, t("playlist_tools_show"))

        self.playlist_header = header

    def _burger_button(self, parent, tooltip, fill_menu, side="left"):
        """Three-line menu button used in the header and playlist toolbar."""
        size = 36
        canvas = tk.Canvas(
            parent, width=size, height=size, bg=parent.cget("bg"),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        gap = 7
        y0 = size // 2 - gap
        for index in range(3):
            y = y0 + index * gap
            canvas.create_line(9, y, size - 9, y, fill=COLOR_TEXT, width=2, capstyle="round")
        menu = DropdownMenu(self.root, self)
        fill_menu(menu)

        def popup(_event=None):
            self._close_menus()
            menu.delete(0, "end")
            fill_menu(menu)
            self._posted_menu = menu
            self._menu_ignore_press = True
            menu.post_below(canvas, side=side)
            self.root.after_idle(self._allow_menu_dismiss)

        canvas.bind("<Button-1>", popup)
        padx = (8, 0) if side == "right" else (0, 6)
        canvas.pack(side=side, padx=padx)
        canvas.tooltip = IconTooltip(canvas, tooltip)
        canvas.menu = menu
        return canvas

    def _help_button(self, parent):
        """Open the operator manual; sits left of the settings menu."""
        points = int(FONT_STATUS[1]) * 2
        font = (FONT_STATUS[0], points, *FONT_STATUS[2:])
        size = points + 20
        canvas = tk.Canvas(
            parent, width=size, height=size, bg=parent.cget("bg"),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        canvas.create_text(
            size / 2, size / 2, text="?", fill=COLOR_TEXT, font=font,
        )
        canvas.bind("<Button-1>", lambda _event: self.open_manual())
        canvas.pack(side="right", padx=(0, 4))
        canvas.tooltip = IconTooltip(canvas, t("manual"))
        return canvas

    def _make_indicator_canvas(self, parent, command, tooltip):
        """36-pixel header icon. The same drawing is used in the settings windows."""
        size = 36
        canvas = tk.Canvas(
            parent, width=size, height=size, bg=parent.cget("bg"),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        canvas.bind("<Button-1>", command)
        canvas.tooltip = IconTooltip(canvas, tooltip)
        return canvas

    def _build_remote_indicator(self, parent):
        """Radio icon in the header; grey while the smartphone API is off."""
        self.remote_indicator = self._make_indicator_canvas(
            parent, lambda _event: self.show_remote_control(), t("remote_control"),
        )
        self._refresh_header_indicators()
        return self.remote_indicator

    def _paint_remote_indicator(self, canvas, color):
        if canvas is None:
            return
        try:
            if not int(canvas.winfo_exists()):
                return
            canvas.delete("all")
        except tk.TclError:
            return
        cx, cy = 18, 25.2
        canvas.create_oval(cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5, fill=color, outline="")
        for radius, start in ((8, 48), (14, 38)):
            canvas.create_arc(
                cx - radius, cy - radius - 1, cx + radius, cy + radius - 1,
                start=start, extent=180 - 2 * start, style="arc",
                outline=color, width=2,
            )

    def _build_lights_indicator(self, parent):
        """Bulb in the header; grey while house-light control is off."""
        self.lights_indicator = self._make_indicator_canvas(
            parent, lambda _event: self.show_lights(), t("lights"),
        )
        self._refresh_header_indicators()
        return self.lights_indicator

    def _paint_lights_indicator(self, canvas, color, lit=True):
        if canvas is None:
            return
        try:
            if not int(canvas.winfo_exists()):
                return
            canvas.delete("all")
        except tk.TclError:
            return
        canvas.create_oval(11, 4, 25, 21, outline=color, width=2)
        if lit:
            canvas.create_oval(14, 8, 22, 16, outline="", fill=color)
        canvas.create_polygon(14, 19, 22, 19, 21, 24, 15, 24, fill=color, outline=color)
        canvas.create_line(15, 26, 21, 26, fill=color, width=2)
        canvas.create_line(16, 29, 20, 29, fill=color, width=2)
        canvas.create_line(17, 32, 19, 32, fill=color, width=2)

    def _place_window_indicator(self, window, kind):
        """Pin the header icon at the top right; a click switches that function."""
        bar = tk.Frame(window, bg=COLOR_BG)
        bar.pack(side="top", fill="x", padx=10, pady=(8, 0))
        if kind == "remote":
            canvas = self._make_indicator_canvas(
                bar, self._toggle_remote_window, t("remote_control"),
            )
            self.remote_window_indicator = canvas
        else:
            canvas = self._make_indicator_canvas(
                bar, self._toggle_lights_window, t("lights"),
            )
            self.lights_window_indicator = canvas
        canvas.pack(side="right")
        self._refresh_header_indicators()
        return canvas

    def _toggle_remote_window(self, _event=None):
        enabled = getattr(self, "remote_api_enabled", None)
        if enabled is None:
            return "break"
        enabled.set(not bool(enabled.get()))
        self._apply_remote_api_settings()
        return "break"

    def _toggle_lights_window(self, _event=None):
        control = getattr(self, "lights_control", None)
        if control is None or not self._dmx_ready():
            return "break"
        control.set(not bool(control.get()))
        self._on_lights_control()
        return "break"

    def _refresh_header_indicators(self):
        """Keep radio and bulb visible; grey when the function is off."""
        remote = getattr(self, "remote_indicator", None)
        lights = getattr(self, "lights_indicator", None)
        running = bool(getattr(self, "remote_api", None) and self.remote_api.running)
        lights_on = bool(self.lights_control.get()) if getattr(self, "lights_control", None) else False
        remote_color = COLOR_VOLUME if running else COLOR_PLAYED
        lights_color = COLOR_PREVIEW if lights_on else COLOR_PLAYED
        self._paint_remote_indicator(remote, remote_color)
        self._paint_remote_indicator(getattr(self, "remote_window_indicator", None), remote_color)
        self._paint_lights_indicator(lights, lights_color, lit=lights_on)
        window_lights = getattr(self, "lights_window_indicator", None)
        self._paint_lights_indicator(window_lights, lights_color, lit=lights_on)
        if window_lights is not None:
            try:
                window_lights.configure(cursor="hand2" if self._dmx_ready() else "arrow")
            except tk.TclError:
                self.lights_window_indicator = None
        for canvas in (remote, lights):
            if canvas is None:
                continue
            try:
                canvas.pack_forget()
            except tk.TclError:
                pass
        try:
            if remote is not None:
                remote.pack(side="right", padx=(0, 4))
            if lights is not None:
                lights.pack(side="right", padx=(0, 4))
        except tk.TclError:
            pass

    def _refresh_remote_indicator(self):
        self._refresh_header_indicators()

    def _refresh_lights_indicator(self):
        self._refresh_header_indicators()

    def open_manual(self):
        path = os.path.join(ROOT_DIR, "manual", "index.html")
        if not os.path.isfile(path):
            messagebox.showerror(t("manual"), t("manual_missing"))
            return
        url = Path(path).resolve().as_uri()
        lang = self.language if self.language in ("de", "en") else "en"
        webbrowser.open(f"{url}?lang={lang}")

    def _arm_menu_dismiss_binds(self):
        if self._menu_binds_armed:
            return
        self.root.bind_all("<ButtonPress>", self._on_global_press_while_menu, add="+")
        self.root.bind_all("<Escape>", self._on_escape_while_menu, add="+")
        self._menu_binds_armed = True

    def _post_dropdown(self, menu, x_root, y_root):
        """Place an in-window dropdown at a screen position (row context menu)."""
        self._close_menus()
        self._posted_menu = menu
        self._menu_ignore_press = True
        self.root.update_idletasks()
        x = int(x_root) - self.root.winfo_rootx()
        y = int(y_root) - self.root.winfo_rooty()
        menu.place(x=x, y=y, anchor="nw")
        menu.lift()
        self.root.after_idle(self._allow_menu_dismiss)

    def _popup_menu(self, menu, x, y):
        """Post a context menu that closes on an outside click."""
        self._close_menus()
        self._posted_menu = menu
        self._menu_ignore_press = True
        menu.bind("<Unmap>", self._on_menu_unmap)
        system = str(self.root.tk.call("tk", "windowingsystem"))
        try:
            menu.tk_popup(x, y)
        finally:
            # On Win/macOS tk_popup is modal and would leave a stuck grab.
            if system != "x11":
                try:
                    menu.grab_release()
                except tk.TclError:
                    pass
        if system == "x11" and self._posted_menu is menu:
            try:
                menu.grab_set()
            except tk.TclError:
                pass
        self.root.after_idle(self._allow_menu_dismiss)

    def _allow_menu_dismiss(self):
        self._menu_ignore_press = False

    def _on_escape_while_menu(self, _event):
        if self._posted_menu is not None:
            self._close_menus()
            return "break"
        if self.window_fullscreen.get():
            self.window_fullscreen.set(False)
            self._on_window_fullscreen()
            return "break"

    def _on_global_press_while_menu(self, event):
        if self._posted_menu is None or self._menu_ignore_press:
            return
        if self._pointer_in_posted_menus(event.x_root, event.y_root):
            return
        self._close_menus()

    def _pointer_in_posted_menus(self, x, y):
        for item in self._iter_posted_menus():
            try:
                if not item.winfo_ismapped():
                    continue
                mx, my = item.winfo_rootx(), item.winfo_rooty()
                mw, mh = item.winfo_width(), item.winfo_height()
                if mx <= x < mx + mw and my <= y < my + mh:
                    return True
            except tk.TclError:
                continue
        return False

    def _iter_posted_menus(self):
        menu = self._posted_menu
        if menu is None:
            return []
        found = []
        stack = [menu]
        seen = set()
        while stack:
            item = stack.pop()
            ident = id(item)
            if ident in seen:
                continue
            seen.add(ident)
            found.append(item)
            try:
                if isinstance(item, DropdownMenu):
                    stack.extend(child for child in item._cascades if child is not None)
                else:
                    stack.extend(
                        child for child in item.winfo_children() if isinstance(child, tk.Menu)
                    )
            except tk.TclError:
                pass
        return found

    def _on_menu_unmap(self, event):
        if self._posted_menu is event.widget:
            self._posted_menu = None
            try:
                event.widget.grab_release()
            except tk.TclError:
                pass
        if self.row_menu is event.widget:
            self.row_menu = None

    def _close_menus(self):
        menu = self._posted_menu
        self._posted_menu = None
        extra = self.row_menu
        self.row_menu = None
        self._menu_ignore_press = False
        for item in (menu, extra):
            if item is None:
                continue
            try:
                item.unpost()
            except tk.TclError:
                pass
            try:
                item.grab_release()
            except tk.TclError:
                pass

    def _tcl_tk_version(self):
        try:
            tcl = self.root.tk.call("info", "patchlevel")
            toolkit = self.root.tk.call("package", "require", "Tk")
        except tk.TclError:
            return ""
        return f"Tk {toolkit}, Tcl {tcl}"

    def _about_version_line(self):
        return header_version_text(
            APP_VERSION,
            read_mpv_version(getattr(self, "mpv_path", "") or ""),
            session_display_name(),
        )

    def show_about(self):
        window = getattr(self, "about_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.deiconify()
                    self._present_popup(window)
                    return
            except tk.TclError:
                self.about_window = None
        window = tk.Toplevel(self.root)
        window.title(t("about_app"))
        window.configure(bg=COLOR_BG)
        window.minsize(420, 360)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_about_window)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        tk.Button(
            buttons, text=t("remote_control_close"), font=FONT_UI, command=self._close_about_window,
        ).pack(side="right")
        body = self._install_popup_scroll(window, COLOR_BG, padx=16, pady=(12, 8))
        logo = self._load_image(LOGO_ABOUT_FILE)
        window._about_logo_source = logo
        self.about_logo = logo
        logo_label = tk.Label(body, bg=COLOR_BG, bd=0)
        window._about_logo_label = logo_label
        if logo is not None:
            logo_label.configure(image=logo)
            logo_label.pack(pady=(4, 10))
        window._popup_canvas.bind(
            "<Configure>", lambda _event, window=window: self._fit_about_logo(window), add="+",
        )
        tk.Label(
            body, text=self._about_version_line(), bg=COLOR_BG, fg=COLOR_TEXT,
            font=FONT_UI_BOLD, justify="center",
        ).pack(pady=(0, 8))
        copyright_info = read_copyright()
        if copyright_info["notice"]:
            tk.Label(
                body, text=copyright_info["notice"], bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_UI,
            ).pack()
        if copyright_info["email"]:
            self._about_link(body, copyright_info["email"], f"mailto:{copyright_info['email']}")
        if copyright_info["url"]:
            self._about_link(body, copyright_info["url"], copyright_info["url"])
        tk.Frame(body, bg=COLOR_BORDER, height=1).pack(fill="x", pady=(12, 8))
        tk.Label(
            body, text=t("about_components"), bg=COLOR_BG, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(anchor="w", pady=(0, 4))
        table = tk.Frame(body, bg=COLOR_BG)
        table.pack(fill="x")
        rows = about_package_rows(
            getattr(self, "mpv_path", "") or "",
            platform.python_version(),
            self._tcl_tk_version(),
        )
        for index, (name, version) in enumerate(rows):
            tk.Label(
                table, text=name, bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_UI, anchor="w",
            ).grid(row=index, column=0, sticky="w", pady=1)
            tk.Label(
                table, text=self._about_version_value(version), bg=COLOR_BG, fg=COLOR_MUTED,
                font=FONT_UI, anchor="w",
            ).grid(row=index, column=1, sticky="w", padx=(18, 0), pady=1)
        self.about_window = window
        self._bind_popup_wheel(window, body)
        self._open_popup(window, 520, 560)
        self._fit_about_logo(window)

    def _fit_about_logo(self, window):
        """Shrink the about logo so both sides stay inside the popup."""
        if getattr(window, "_about_logo_guard", False):
            return
        source = getattr(window, "_about_logo_source", None)
        label = getattr(window, "_about_logo_label", None)
        canvas = getattr(window, "_popup_canvas", None)
        if source is None or label is None or canvas is None:
            return
        window._about_logo_guard = True
        try:
            if not window.winfo_exists() or not canvas.winfo_exists():
                return
            self._fit_popup_scroll(window)
            available = canvas.winfo_width() - 8
            if available <= 1:
                return
            factor = max(1, math.ceil(source.width() / available))
            if getattr(window, "_about_logo_factor", None) == factor:
                return
            scaled = source if factor == 1 else source.subsample(factor, factor)
            window._about_logo_factor = factor
            window._about_logo_scaled = scaled
            self.about_logo = scaled
            label.configure(image=scaled)
        except tk.TclError:
            pass
        finally:
            window._about_logo_guard = False

    def _about_version_value(self, version):
        if version is None:
            return t("about_missing")
        text = str(version).strip()
        return text or "—"

    def _about_link(self, parent, text, url):
        label = tk.Label(
            parent, text=text, bg=COLOR_BG, fg=COLOR_VOLUME, font=FONT_UI, cursor="hand2",
        )
        label.pack()
        label.bind("<Button-1>", lambda _event, target=url: webbrowser.open(target))
        return label

    def _close_about_window(self):
        window = getattr(self, "about_window", None)
        self.about_window = None
        self.about_logo = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _fill_app_menu(self, menu):
        menu.add_command(label=t("about_app"), command=self.show_about)
        menu.add_separator()
        menu.add_checkbutton(
            label=t("window_fullscreen"),
            variable=self.window_fullscreen,
            command=self._on_window_fullscreen,
            accelerator="F11",
        )
        menu.add_separator()
        menu.add_command(
            label=t("media_directories"),
            command=self.show_media_directories,
        )
        menu.add_separator()

        program = self._menu(menu)
        self._fill_program_menu(program)
        menu.add_cascade(label=t("program_menu"), menu=program)

        playlist = self._menu(menu)
        self._fill_playlist_menu(playlist)
        menu.add_cascade(label=t("playlist"), menu=playlist)
        menu.add_separator()

        menu.add_command(
            label=t("remote_control"),
            command=self.show_remote_control,
        )
        menu.add_command(
            label=t("lights"),
            command=self.show_lights,
        )
        menu.add_separator()

        system = self._menu(menu)
        system.add_command(
            label=t("theme_to_light") if self.theme == "dark" else t("theme_to_dark"),
            command=self.toggle_theme,
        )
        languages = self._menu(system)
        for code, name in LANGUAGES.items():
            mark = "✔  " if code == self.language else "    "
            languages.add_command(
                label=f"{mark}{name}",
                command=lambda chosen=code: self.change_language(chosen),
                foreground=self._menu_check_fg() if code == self.language else COLOR_TEXT,
            )
        system.add_cascade(label=t("language"), menu=languages)
        sizes = self._menu(system)
        current = current_text_size()
        for delta in TEXT_SIZE_DELTAS:
            mark = "✔  " if delta == current else "    "
            sizes.add_command(
                label=f"{mark}{TEXT_SIZE_LABELS[delta]}",
                command=lambda chosen=delta: self.change_text_size(chosen),
                foreground=self._menu_check_fg() if delta == current else COLOR_TEXT,
            )
        system.add_cascade(label=t("text_size"), menu=sizes)
        system.add_separator()
        beamer = self._menu(system)
        outputs = self._menu(beamer)
        self._fill_beamer_output_menu(outputs)
        beamer.add_cascade(label=t("output"), menu=outputs)
        beamer.add_checkbutton(
            label=t("pad_16x9"),
            variable=self.pad_16x9,
            command=self._on_pad_16x9,
        )
        system.add_cascade(label=t("beamer_menu"), menu=beamer)
        system.add_command(
            label=t("patch"),
            command=self.show_patch,
        )
        menu.add_cascade(label=t("system_settings"), menu=system)

        extras = self._menu(menu)
        extras.add_command(
            label=t("beamer_test"),
            command=self.show_beamer_test,
            state="normal" if self.program_state == "OFF" and not self.calibration_mode else "disabled",
        )
        video = self._menu(extras)
        self._fill_calibration_kind_menu(video, "video")
        extras.add_cascade(label=t("calibration_video"), menu=video)
        audio = self._menu(extras)
        self._fill_calibration_kind_menu(audio, "audio")
        extras.add_cascade(label=t("calibration_audio"), menu=audio)
        menu.add_cascade(
            label=t("calibration"),
            menu=extras,
            state="normal" if self.program_state == "OFF" or self.calibration_mode else "disabled",
        )
        menu.add_separator()
        menu.add_command(
            label=t("quit"),
            command=self.close,
            state="normal" if self.program_state == "OFF" else "disabled",
        )

    def _fill_beamer_output_menu(self, menu):
        try:
            names = list(self.output_manager.get_outputs())
        except Exception:
            names = []
        current = self.output_manager.video_output or self.beamer_output.get().strip()
        if current and current not in names:
            names = [current, *names]
        busy = self.program_state == "PLAYING"
        if not names:
            menu.add_command(label="--", state="disabled")
        else:
            for name in names:
                mark = "✔  " if name == current else "    "
                menu.add_command(
                    label=f"{mark}{name}",
                    command=lambda chosen=name: self.apply_beamer_output(chosen),
                    state="disabled" if busy else "normal",
                    foreground=self._menu_check_fg() if name == current else COLOR_TEXT,
                )
        menu.add_separator()
        menu.add_command(label=t("edid"), command=self.show_edid)

    def show_patch(self):
        """Route Beamer and Preview to a picture output and a sound device."""
        window = getattr(self, "patch_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.deiconify()
                    self._present_popup(window)
                    self._fill_patch_form()
                    return
            except tk.TclError:
                self.patch_window = None
        window = tk.Toplevel(self.root)
        window.title(t("patch"))
        window.configure(bg=COLOR_BG)
        window.minsize(720, 320)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_patch_window)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        body = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=(10, 0))
        tk.Label(
            body, text=t("patch_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=680, justify="left",
        ).pack(fill="x", pady=(0, 6))
        holder = tk.Frame(body, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, pady=(0, 10))
        table = tk.Frame(holder, bg=COLOR_PANEL)
        table.pack(fill="x", padx=8, pady=(8, 4))
        table.columnconfigure(1, weight=1)
        table.columnconfigure(2, weight=1)
        for column, key in ((1, "patch_picture"), (2, "patch_sound")):
            tk.Label(
                table, text=t(key), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
            ).grid(row=0, column=column, sticky="w", padx=(0, 12), pady=(0, 4))
        tk.Label(
            table, text=t("patch_beamer"), bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_UI,
        ).grid(row=1, column=0, sticky="w", padx=(0, 12), pady=4)
        tk.Label(
            table, text=t("patch_preview"), bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_UI,
        ).grid(row=2, column=0, sticky="w", padx=(0, 12), pady=4)
        self.patch_video_var = tk.StringVar(value="")
        self.patch_beamer_audio_var = tk.StringVar(value="")
        self.patch_preview_audio_var = tk.StringVar(value="")
        self.patch_video_combo = ttk.Combobox(
            table, textvariable=self.patch_video_var, state="readonly", width=36,
        )
        self.patch_video_combo.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=4)
        self.patch_beamer_audio_combo = ttk.Combobox(
            table, textvariable=self.patch_beamer_audio_var, state="readonly", width=36,
        )
        self.patch_beamer_audio_combo.grid(row=1, column=2, sticky="ew", pady=4)
        tk.Label(
            table, text=t("patch_control_window"), bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_UI,
            anchor="w",
        ).grid(row=2, column=1, sticky="w", padx=(0, 12), pady=4)
        self.patch_preview_audio_combo = ttk.Combobox(
            table, textvariable=self.patch_preview_audio_var, state="readonly", width=36,
        )
        self.patch_preview_audio_combo.grid(row=2, column=2, sticky="ew", pady=4)
        self.patch_picture_hint = tk.Label(
            holder, text="", bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL, anchor="w",
        )
        self.patch_picture_hint.pack(fill="x", padx=8)
        hints = tk.Frame(holder, bg=COLOR_PANEL)
        hints.pack(fill="x", padx=8, pady=(2, 4))
        hints.columnconfigure(1, weight=1)
        tk.Label(
            hints, text=t("patch_beamer"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.patch_beamer_hint = tk.Label(
            hints, text="", bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL, anchor="w",
        )
        self.patch_beamer_hint.grid(row=0, column=1, sticky="ew")
        tk.Label(
            hints, text=t("patch_preview"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).grid(row=1, column=0, sticky="w", padx=(0, 8))
        self.patch_preview_hint = tk.Label(
            hints, text="", bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL, anchor="w",
        )
        self.patch_preview_hint.grid(row=1, column=1, sticky="ew")
        tk.Button(
            buttons, text=t("patch_close"), font=FONT_UI, command=self._close_patch_window,
        ).pack(side="right")
        tk.Button(
            buttons, text=t("remote_control_apply"), font=FONT_UI, command=self._commit_patch,
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            buttons, text=t("patch_refresh"), font=FONT_UI, command=self._fill_patch_form,
        ).pack(side="left")
        self.patch_window = window
        self._patch_video_ids = {}
        self._patch_beamer_audio_ids = {}
        self._patch_preview_audio_ids = {}
        self._fill_patch_form()
        self._bind_popup_wheel(window, body)
        self._open_popup(window, 760, 460)

    def _close_patch_window(self):
        window = getattr(self, "patch_window", None)
        self.patch_window = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _fill_patch_form(self):
        window = getattr(self, "patch_window", None)
        if window is None:
            return
        try:
            if not window.winfo_exists():
                self.patch_window = None
                return
        except tk.TclError:
            self.patch_window = None
            return
        try:
            names = list(self.output_manager.get_outputs())
        except Exception:
            names = []
        current = self.output_manager.video_output or self.beamer_output.get().strip()
        if current and current not in names:
            names = [current, *names]
        video_rows = []
        for name in names:
            try:
                device_name = self.output_manager.get_output_device_name(name)
            except Exception:
                device_name = ""
            video_rows.append((video_output_menu_label(name, device_name), name))
        if not video_rows:
            video_rows = [("--", "")]
        self._patch_video_ids = self._set_patch_combo(
            self.patch_video_combo, self.patch_video_var, video_rows, current,
        )
        picture_state = "disabled" if self.program_state == "PLAYING" else "readonly"
        try:
            self.patch_video_combo.configure(state=picture_state)
        except tk.TclError:
            return
        self.patch_picture_hint.config(
            text=t("beamer_output_busy") if self.program_state == "PLAYING" else "",
        )
        try:
            devices, beamer_auto, preview_auto = self.output_manager.describe_automatic_audio(
                self.mpv_path,
            )
        except Exception:
            devices, beamer_auto, preview_auto = [], None, None
        audio_rows = self._patch_audio_rows(devices)
        patch = self.output_manager.audio_patch
        self._patch_beamer_audio_ids = self._set_patch_combo(
            self.patch_beamer_audio_combo,
            self.patch_beamer_audio_var,
            audio_rows,
            normalize_audio_patch_choice(patch.get("beamer")),
        )
        self._patch_preview_audio_ids = self._set_patch_combo(
            self.patch_preview_audio_combo,
            self.patch_preview_audio_var,
            list(audio_rows),
            normalize_audio_patch_choice(patch.get("preview")),
        )
        self.patch_beamer_hint.config(text=self._patch_auto_text(beamer_auto, devices))
        self.patch_preview_hint.config(text=self._patch_auto_text(preview_auto, devices))

    @staticmethod
    def _patch_audio_rows(devices):
        rows = [(t("patch_automatic"), ""), (t("patch_none"), AUDIO_PATCH_NONE)]
        used = {label for label, _ident in rows}
        for label, device_id in unique_audio_device_labels(devices):
            shown = label
            if shown in used:
                shown = f"{label} ({device_id})"
            extra = 2
            while shown in used:
                shown = f"{label} ({device_id}) {extra}"
                extra += 1
            used.add(shown)
            rows.append((shown, device_id))
        return rows

    @staticmethod
    def _set_patch_combo(combo, variable, rows, current_id):
        labels = []
        mapping = {}
        chosen = ""
        current_id = "" if current_id is None else str(current_id)
        for label, ident in rows:
            label = str(label)
            if label in mapping:
                continue
            labels.append(label)
            mapping[label] = ident
            if ident == current_id and not chosen:
                chosen = label
        if not chosen and current_id and current_id != AUDIO_PATCH_NONE:
            missing = t("patch_missing", device=current_id)
            labels.append(missing)
            mapping[missing] = current_id
            chosen = missing
        if not chosen and labels:
            chosen = labels[0]
        try:
            combo.configure(values=labels)
        except tk.TclError:
            return mapping
        variable.set(chosen)
        return mapping

    @staticmethod
    def _patch_auto_text(device_id, devices):
        if not device_id:
            return t("patch_auto_none")
        label = device_id
        for ident, description in devices or ():
            if ident == device_id:
                label = audio_device_menu_label(ident, description) or device_id
                break
        return t("patch_auto_using", device=label)

    def _commit_patch(self):
        if getattr(self, "patch_window", None) is None:
            return
        beamer_audio = normalize_audio_patch_choice(
            self._patch_beamer_audio_ids.get(self.patch_beamer_audio_var.get(), "")
        )
        preview_audio = normalize_audio_patch_choice(
            self._patch_preview_audio_ids.get(self.patch_preview_audio_var.get(), "")
        )
        video = self._patch_video_ids.get(self.patch_video_var.get(), "")
        self.output_manager.set_audio_patch({
            "beamer": beamer_audio,
            "preview": preview_audio,
        })
        self.settings["audio_patch"] = dict(self.output_manager.audio_patch)
        try:
            save_settings(self.settings)
        except OSError:
            pass
        video_changed = bool(video) and video != (self.output_manager.video_output or "")
        if video_changed and self.program_state == "PLAYING":
            messagebox.showinfo(t("beamer_status"), t("beamer_output_busy"))
        elif video_changed:
            before = self.output_manager.video_output
            self.apply_beamer_output(video)
            if self.output_manager.video_output != before:
                self._fill_patch_form()
                return
        self._apply_main_audio_device()
        self._apply_preview_audio_device()
        self._fill_patch_form()

    def _fill_calibration_kind_menu(self, menu, kind):
        menu.add_command(
            label=t("calibration_load_all"),
            command=lambda: self._start_calibration_mode(kind),
        )
        playlists = self._calibration_playlist_paths(self._calibration_spec(kind).get("folder", ""))
        if not playlists:
            return
        menu.add_separator()
        for path in playlists:
            menu.add_command(
                label=os.path.splitext(os.path.basename(path))[0],
                command=lambda chosen=path: self._start_calibration_mode(kind, playlist_path=chosen),
            )

    @staticmethod
    def _calibration_playlist_paths(folder):
        if not folder or not os.path.isdir(folder):
            return []
        return [
            os.path.join(folder, name)
            for name in sorted(os.listdir(folder), key=str.casefold)
            if name.lower().endswith(".pls") and os.path.isfile(os.path.join(folder, name))
        ]

    def _fill_program_menu(self, menu):
        """Idle media sits above the default; volume setup is last."""
        pause = self._menu(menu)
        if self.idle_media_path:
            pause.add_command(
                label=os.path.basename(self.idle_media_path),
                command=self.choose_idle_media,
            )
            pause.add_command(label=t("idle_none"), command=self.clear_idle_media)
        else:
            pause.add_command(label=t("idle_media_choose"), command=self.choose_idle_media)
        pause.add_separator()
        pause.add_entry(
            label=t("autoplay_delay"),
            variable=self.autoplay_delay,
            suffix=t("seconds_short"),
        )
        menu.add_cascade(label=t("idle_media_menu"), menu=pause)
        menu.add_checkbutton(
            label=t("default_idle_media"),
            variable=self.use_default_idle_media,
            command=self._on_use_default_idle_media,
        )
        menu.add_separator()
        menu.add_checkbutton(
            label=t("projection_zoom"),
            variable=self.projection_zoom,
            command=self.refresh_playlist,
        )
        menu.add_separator()
        menu.add_command(
            label=t("volume_setup"),
            command=self.start_volume_setup,
            state="disabled" if self.program_state == "PLAYING" else "normal",
        )

    def _fill_playlist_menu(self, menu):
        menu.add_command(label=t("refresh_playlist"), command=self.check_playlist_files)
        menu.add_command(label=t("reset_played"), command=self.reset_played)
        menu.add_separator()
        menu.add_checkbutton(
            label=t("autosave_program_change"),
            variable=self.autosave_on_program_change,
            command=self._on_autosave_program_change,
        )
        menu.add_checkbutton(
            label=t("load_last_playlist_at_start"),
            variable=self.load_last_playlist_at_start,
            command=self._on_load_last_playlist_at_start,
        )
        menu.add_separator()
        menu.add_command(
            label=t("analyze_loudness"),
            command=self.analyze_playlist_loudness,
            state="normal" if self.program_state == "OFF" else "disabled",
        )

    def _fill_playlist_column_header(self, parent):
        """Column titles sit in the same column as the list, above the scrollbar."""
        header = tk.Frame(
            parent, bg=COLOR_PANEL, padx=6, pady=2,
            highlightthickness=2, highlightbackground=COLOR_PANEL,
        )
        header.grid(row=0, column=0, sticky="ew", padx=2, pady=(4, 0))
        header.columnconfigure(1, weight=1, minsize=140)
        tk.Label(header, text="", width=2, bg=COLOR_PANEL).grid(row=0, column=0)
        tk.Label(header, text="", bg=COLOR_PANEL).grid(row=0, column=1, sticky="ew")
        for offset, (_key, label_key, width) in enumerate(PLAYLIST_META_COLUMNS):
            tk.Label(
                header, text=t(label_key), width=width, anchor="e",
                bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
            ).grid(row=0, column=2 + offset, sticky="e", padx=(6, 0))
        self.playlist_column_header = header

    def _build_playlist(self, parent):
        holder = tk.Frame(parent, bg=COLOR_PANEL)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.rowconfigure(1, weight=1)
        holder.columnconfigure(0, weight=1)
        self._fill_playlist_column_header(holder)

        self.playlist_canvas = tk.Canvas(holder, bg=COLOR_PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.playlist_canvas.yview)
        self.playlist_inner = tk.Frame(self.playlist_canvas, bg=COLOR_PANEL)
        self.playlist_inner.bind(
            "<Configure>",
            lambda e: self.playlist_canvas.configure(scrollregion=self.playlist_canvas.bbox("all")),
        )
        self.playlist_window = self.playlist_canvas.create_window((0, 0), window=self.playlist_inner, anchor="nw")
        self.playlist_canvas.configure(yscrollcommand=scroll.set)
        self.playlist_canvas.bind("<Configure>", self._on_playlist_canvas_configure)
        self.playlist_canvas.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, rowspan=2, sticky="ns")
        self.playlist_canvas.bind("<Enter>", lambda e: self.playlist_canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.playlist_canvas.bind("<Leave>", lambda e: self.playlist_canvas.unbind_all("<MouseWheel>"))
        self._bind_playlist_wheel(self.playlist_canvas)
        self._bind_playlist_wheel(self.playlist_inner)

    def _on_playlist_canvas_configure(self, event):
        self.playlist_canvas.itemconfigure(self.playlist_window, width=event.width)
        self._apply_playlist_name_wrap(event.width)

    def _playlist_name_wrap(self, width=None):
        """Width left for the file name and folder once the metadata columns fit."""
        if width is None:
            try:
                width = self.playlist_canvas.winfo_width()
            except tk.TclError:
                width = 0
        try:
            width = int(width)
        except (TypeError, ValueError):
            width = 0
        if width <= 1:
            width = 900
        return max(140, width - 720)

    def _apply_playlist_name_wrap(self, width=None):
        wrap = self._playlist_name_wrap(width)
        for widgets in self.row_widgets:
            for key in ("filename", "detail"):
                label = widgets.get(key)
                if label is None:
                    continue
                try:
                    label.configure(wraplength=wrap)
                except tk.TclError:
                    return

    def _bind_playlist_wheel(self, widget):
        """The wheel hits the row under the pointer, not the canvas behind it."""
        try:
            widget.bind("<Button-4>", self._on_mousewheel, add="+")
            widget.bind("<Button-5>", self._on_mousewheel, add="+")
            widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        except tk.TclError:
            pass

    def _on_mousewheel(self, event):
        canvas = getattr(self, "playlist_canvas", None)
        if canvas is None:
            return
        try:
            if event.num == 5 or event.delta < 0:
                canvas.yview_scroll(3, "units")
            else:
                canvas.yview_scroll(-3, "units")
        except tk.TclError:
            pass
        return "break"

    def _build_beamer(self, parent):
        panel = self._group_frame(parent)
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        panel.columnconfigure(0, weight=1)

        header = tk.Frame(panel, bg=COLOR_PANEL)
        header.pack(fill="x", padx=8, pady=(6, 4))
        tk.Label(
            header, text=t("beamer_status"), font=FONT_UI_BOLD, bg=COLOR_PANEL, fg=COLOR_TEXT,
        ).pack(side="left")
        self.beamer_ok = tk.Label(
            header, text="--", font=FONT_STATUS, bg=COLOR_BADGE_IDLE, fg=COLOR_WHITE, width=10, pady=3,
        )
        self.beamer_ok.pack(side="right")

        self.beamer_summary = tk.Frame(panel, bg=COLOR_PANEL)
        chosen = tk.Frame(self.beamer_summary, bg=COLOR_PANEL)
        chosen.pack(fill="x", padx=8, pady=(0, 4))
        self.beamer_resolution = self._beamer_inline_value(chosen, "beamer_resolution")
        self.beamer_rate = self._beamer_inline_value(chosen, "beamer_rate")
        self.beamer_colorspace_value = self._beamer_inline_value(chosen, "beamer_colorspace")
        self.beamer_drop_summary = tk.Label(
            self.beamer_summary, text="", font=FONT_SMALL, bg=COLOR_PANEL,
            fg=COLOR_OFF, anchor="w",
        )

        details = tk.Frame(panel, bg=COLOR_PANEL)
        self.beamer_details = details
        legend = tk.Frame(details, bg=COLOR_PANEL)
        legend.pack(fill="x", padx=8, pady=(0, 6))
        for color, key in (
            (ACCENT, "beamer_legend_program"),
            (COLOR_PREVIEW, "beamer_legend_preview"),
        ):
            tk.Label(
                legend, text="●", fg=color, bg=COLOR_PANEL, font=FONT_SMALL,
            ).pack(side="left")
            tk.Label(
                legend, text=t(key), fg=COLOR_TEXT, bg=COLOR_PANEL, font=FONT_SMALL,
            ).pack(side="left", padx=(2, 10))
        tk.Label(
            legend, text=t("beamer_legend_set"), fg=COLOR_MUTED, bg=COLOR_PANEL, font=FONT_SMALL,
        ).pack(side="left")
        self.beamer_legend = legend
        self.beamer_gpu = self._beamer_value_row(details, "beamer_gpu")
        device = tk.Frame(details, bg=COLOR_PANEL)
        device.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(
            device, text=t("beamer_device"), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left")
        self.beamer_device = tk.Label(
            device, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        )
        self.beamer_device.pack(side="left", padx=(8, 0), fill="x", expand=True)

        info = tk.Frame(details, bg=COLOR_PANEL)
        info.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(
            info, text=t("beamer_aspect"), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left")
        self.beamer_aspect = tk.Label(
            info, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT,
        )
        self.beamer_aspect.pack(side="left", padx=(8, 0))
        self.beamer_clip_aspect = tk.Label(
            info, text="", font=FONT_STATUS, bg=COLOR_PANEL, fg=ACCENT,
        )
        self.beamer_clip_aspect.pack(side="left", padx=(12, 0))

        decode = tk.Frame(details, bg=COLOR_PANEL)
        decode.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(
            decode, text=t("beamer_hwdec"), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left")
        self.beamer_hwdec = tk.Label(
            decode, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        )
        self.beamer_hwdec.pack(side="left", padx=(8, 0))
        tk.Label(
            decode, text=t("beamer_dropframes"), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left", padx=(16, 0))
        tk.Label(
            decode, text=t("beamer_drops_mpv"), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left", padx=(8, 0))
        self.beamer_drops_mpv = tk.Label(
            decode, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        )
        self.beamer_drops_mpv.pack(side="left", padx=(4, 0))
        tk.Label(
            decode, text=t("beamer_drops_decoder"), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left", padx=(12, 0))
        self.beamer_drops_decoder = tk.Label(
            decode, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        )
        self.beamer_drops_decoder.pack(side="left", padx=(4, 0))
        self.beamer_rates = BeamerChoiceLine(details)
        self.beamer_rates.pack(fill="x", padx=8, pady=(0, 4))
        self.beamer_resolutions = BeamerChoiceLine(details)
        self.beamer_resolutions.pack(fill="x", padx=8, pady=(0, 4))
        self.beamer_colorspaces = BeamerChoiceLine(details)
        self.beamer_colorspaces.pack(fill="x", padx=8, pady=(0, 4))

        fold = tk.Frame(panel, bg=COLOR_PANEL, cursor="hand2")
        self.beamer_fold = fold
        self._beamer_fold_hover = False
        self.beamer_fold_arrow = tk.Canvas(
            fold, height=22, highlightthickness=0, bd=0, bg=COLOR_PANEL, cursor="hand2",
        )
        self.beamer_fold_arrow.pack(fill="x", pady=(0, 2))
        fold.pack(fill="x")
        for widget in (fold, self.beamer_fold_arrow):
            widget.bind("<Button-1>", self._toggle_beamer_details)
            widget.bind("<Enter>", self._beamer_fold_enter)
            widget.bind("<Leave>", self._beamer_fold_leave)
        self.beamer_fold_arrow.bind("<Configure>", lambda _event: self._paint_beamer_fold_arrow())
        self.beamer_fold_tip = IconTooltip(self.beamer_fold_arrow, t("beamer_show_details"))
        self._apply_beamer_fold()
        self._beamer_caps_cache = None

    def _beamer_value_row(self, parent, key):
        row = tk.Frame(parent, bg=COLOR_PANEL)
        row.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(
            row, text=t(key), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left")
        value = tk.Label(
            row, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        )
        value.pack(side="left", padx=(8, 0), fill="x", expand=True)
        return value

    def _beamer_inline_value(self, parent, key):
        """Label and value packed left, so several set values share one row."""
        group = tk.Frame(parent, bg=COLOR_PANEL)
        group.pack(side="left", padx=(0, 16))
        tk.Label(
            group, text=t(key), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left")
        value = tk.Label(
            group, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        )
        value.pack(side="left", padx=(8, 0))
        return value

    def _toggle_beamer_details(self, _event=None):
        self.beamer_details_open = not bool(getattr(self, "beamer_details_open", False))
        self._apply_beamer_fold()
        return "break"

    def _apply_beamer_fold(self):
        open_details = bool(getattr(self, "beamer_details_open", False))
        summary = getattr(self, "beamer_summary", None)
        details = getattr(self, "beamer_details", None)
        fold = getattr(self, "beamer_fold", None)
        if summary is None or details is None or fold is None:
            return
        summary.pack_forget()
        details.pack_forget()
        if open_details:
            details.pack(fill="x", before=fold)
            tip = t("beamer_hide_details")
        else:
            summary.pack(fill="x", before=fold)
            tip = t("beamer_show_details")
        if getattr(self, "beamer_fold_tip", None):
            self.beamer_fold_tip.text = tip
        self._paint_beamer_fold_arrow()
        if open_details:
            for line in (self.beamer_rates, self.beamer_resolutions, self.beamer_colorspaces):
                line._laid_width = 0
                line._reflow()

    def _beamer_fold_enter(self, _event=None):
        self._beamer_fold_hover = True
        self._paint_beamer_fold_arrow()

    def _beamer_fold_leave(self, _event=None):
        self._beamer_fold_hover = False
        self._paint_beamer_fold_arrow()

    def _paint_beamer_fold_arrow(self):
        canvas = getattr(self, "beamer_fold_arrow", None)
        if canvas is None:
            return
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        cx = width / 2
        cy = height / 2
        color = ACCENT if getattr(self, "_beamer_fold_hover", False) else COLOR_TEXT
        if getattr(self, "beamer_details_open", False):
            points = [cx, cy - 5, cx - 7, cy + 4, cx + 7, cy + 4]
        else:
            points = [cx - 7, cy - 4, cx + 7, cy - 4, cx, cy + 5]
        canvas.create_polygon(points, fill=color, outline=color)

    def _set_beamer_summary(self, resolution, rate, space, res_fg=None, rate_fg=None, space_fg=None):
        labels = (
            (getattr(self, "beamer_resolution", None), resolution, res_fg),
            (getattr(self, "beamer_rate", None), rate, rate_fg),
            (getattr(self, "beamer_colorspace_value", None), space, space_fg),
        )
        for widget, text, fg in labels:
            if widget is None:
                continue
            widget.config(text=text or "--", fg=fg or COLOR_TEXT)

    @staticmethod
    def _marked_value_fg(token, program, preview):
        def as_set(value):
            if not value:
                return set()
            if isinstance(value, (set, frozenset, list, tuple)):
                return {item for item in value if item}
            return {value}

        if token and token in as_set(program):
            return ACCENT
        if token and token in as_set(preview):
            return COLOR_PREVIEW
        return COLOR_TEXT

    def _build_preview(self, parent):
        self.preview_column = parent
        header = self._group_frame(parent)
        header.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        header.columnconfigure(0, weight=1)

        title_row = tk.Frame(header, bg=COLOR_PANEL)
        title_row.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        title_row.columnconfigure(0, weight=1)
        self.preview_title = tk.Label(
            title_row, text=t("no_clip"), font=FONT_UI_BOLD, bg=COLOR_READOUT,
            fg=COLOR_TEXT, anchor="w", padx=8, pady=4,
        )
        self.preview_title.grid(row=0, column=0, sticky="ew")
        self.preview_mode_btn = tk.Button(
            title_row, text=t("live"), font=FONT_STATUS, width=10,
            command=self.toggle_preview_mode, pady=3,
        )
        self.preview_mode_btn.grid(row=0, column=1, padx=(8, 0))

        self.preview_meta = tk.Label(
            header, text=t("length_empty"), font=FONT_SMALL, bg=COLOR_PANEL, anchor="w",
        )
        self.preview_meta.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        settings = self._group_frame(parent)
        settings.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        settings.columnconfigure(0, weight=1)
        self.preview_settings = settings
        footer = tk.Frame(settings, bg=COLOR_PANEL)
        footer.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 6))

        flow = tk.Frame(footer, bg=COLOR_PANEL)
        flow.pack(side="left")
        self.autoplay_check = CheckLabel(
            flow, t("autoplay"), self.autoplay_var, self.apply_entry_settings, COLOR_PANEL,
        )
        self.autoplay_check.pack(side="left")
        clip_settings = tk.Frame(flow, bg=COLOR_PANEL)
        clip_settings.pack(side="left")
        self.preview_clip_settings = clip_settings
        CheckLabel(
            clip_settings, t("loop"), self.loop_var, self.apply_entry_settings, COLOR_PANEL,
        ).pack(side="left", padx=(8, 0))

        safety = tk.Frame(footer, bg=COLOR_PANEL)
        safety.pack(side="left", padx=(16, 0))
        self.preview_safety = safety
        tk.Label(
            safety, text=t("group_safety"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(side="left", padx=(0, 6))
        self.clip_settings_warning_check = CheckLabel(
            safety, t("clip_settings_warning"), self.clip_settings_warning_var,
            self.apply_entry_settings, COLOR_PANEL,
        )
        played = tk.Frame(safety, bg=COLOR_PANEL)
        played.pack(side="left")
        self.preview_played_box = played
        CheckLabel(
            played, t("played"), self.played_var, self.apply_entry_settings, COLOR_PANEL,
        ).pack(side="left", padx=(8, 0))
        self._sync_clip_settings_warning_option()

        image_settings = tk.Frame(footer, bg=COLOR_PANEL)
        self.preview_image_settings = image_settings
        tk.Label(image_settings, text=t("display_time"), bg=COLOR_PANEL, font=FONT_UI).pack(
            side="left", padx=(12, 4)
        )
        entry_box = tk.Entry(image_settings, textvariable=self.display_time, width=5, font=FONT_UI)
        entry_box.pack(side="left")
        entry_box.bind("<Return>", lambda e: self.apply_entry_settings())
        entry_box.bind("<FocusOut>", lambda e: self.apply_entry_settings())
        tk.Label(
            image_settings, text=t("display_time_hint"), bg=COLOR_PANEL, font=FONT_UI,
            fg=COLOR_MUTED,
        ).pack(side="left", padx=(4, 0))
        self._build_still_dim(image_settings)

        video_group = self._group_frame(parent)
        video_group.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        video_group.columnconfigure(0, weight=1)
        video_group.rowconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)
        video_row = tk.Frame(video_group, bg=COLOR_PANEL)
        video_row.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        video_row.columnconfigure(0, weight=1)
        video_row.rowconfigure(0, weight=1)
        self.preview_video = tk.Frame(video_row, bg=COLOR_VIDEO, width=480, height=270)
        self.preview_video.grid(row=0, column=0, sticky="nsew")
        meter_col = tk.Frame(video_row, bg=COLOR_PANEL)
        self.preview_meter_col = meter_col
        meter_col.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        meter_col.rowconfigure(1, weight=1)
        self.preview_lufs = tk.Label(
            meter_col,
            text=format_loudness(None),
            font=FONT_SMALL,
            bg=COLOR_PANEL,
            fg=COLOR_VOLUME,
            justify="center",
            wraplength=58,
        )
        self.preview_lufs.grid(row=0, column=0, pady=(0, 2))
        self.preview_meter = LevelMeter(meter_col)
        self.preview_meter.grid(row=1, column=0, sticky="ns")
        self.preview_placeholder = tk.Label(
            self.preview_video, text=t("video_preview"), bg=COLOR_VIDEO,
            fg=COLOR_MUTED, font=FONT_PLACEHOLDER,
        )
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        controls = self._group_frame(parent)
        controls.grid(row=4, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)
        self.preview_controls = controls

        self.preview_progress = RangeProgressBar(
            controls, on_seek=self._on_preview_seek, height=32,
        )
        self.preview_progress.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=(6, 0))
        self.preview_video_bitrate = self._bitrate_readout(controls, "video_bitrate")
        self.preview_video_bitrate.grid(row=0, column=1, sticky="e", padx=(8, 8), pady=(6, 0))

        self.preview_envelope = EnvelopeCanvas(
            controls, on_seek=self._on_preview_seek, bg=COLOR_PANEL,
        )
        self.preview_envelope.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 0))

        self.preview_volume_row = self._build_volume_row(
            controls, self.preview_volume, self._on_preview_volume, COLOR_PANEL,
            save=True, accent=COLOR_PREVIEW,
        )
        self.preview_volume_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 0))
        self.preview_audio_bitrate = self._bitrate_readout(controls, "audio_bitrate")
        self.preview_audio_bitrate.grid(row=2, column=1, sticky="e", padx=(8, 8), pady=(4, 0))
        self._pin_bitrate_column(controls, self.preview_video_bitrate)

        marks = tk.Frame(controls, bg=COLOR_PANEL)
        marks.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 4))
        self.preview_marks = marks
        for col in range(3):
            marks.columnconfigure(col, weight=1)
        self.preview_in = tk.Label(marks, text=t("in_value", value="--:--"), bg=COLOR_PANEL, font=FONT_SMALL)
        self.preview_in.grid(row=0, column=0, sticky="w")
        self.preview_time = tk.Label(marks, text=t("time_value", value="--:--"), bg=COLOR_PANEL, font=FONT_SMALL)
        self.preview_time.grid(row=0, column=1)
        self.preview_out = tk.Label(marks, text=t("out_value", value="--:--"), bg=COLOR_PANEL, font=FONT_SMALL)
        self.preview_out.grid(row=0, column=2, sticky="e")

        buttons = tk.Frame(controls, bg=COLOR_PANEL)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 4))

        transport = tk.Frame(buttons, bg=COLOR_PANEL)
        self.preview_transport = transport
        transport.pack(side="left")
        self.preview_buttons = {}
        for name, cmd, label in (
            ("rev", lambda: self.preview_seek(-5), t("rev")),
            ("stop", self.preview_stop, t("stop")),
            ("pause", self.preview_pause, t("pause")),
            ("play", self.preview_play, t("play")),
            ("fwd", lambda: self.preview_seek(5), t("fwd")),
        ):
            self.preview_buttons[name] = self._icon_button(transport, name, cmd, label)

        io = tk.Frame(buttons, bg=COLOR_PANEL)
        self.preview_io = io
        io.pack(side="left", padx=(32, 0))
        self.preview_io_buttons = {
            "set_in": self._icon_button(io, "set_in", self.set_in_point, t("set_in")),
            "set_out": self._icon_button(io, "set_out", self.set_out_point, t("set_out")),
            "clear_in_out": self._icon_button(io, "clear_in_out", self.clear_in_out, t("clear_in_out")),
        }

        tracks = tk.Frame(controls, bg=COLOR_PANEL)
        self.preview_track_settings = tracks
        tracks.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))
        tk.Label(tracks, text=t("audio_track"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left", padx=(0, 4))
        self.audio_combo = ttk.Combobox(tracks, textvariable=self.audio_var, width=16, state="readonly")
        self.audio_combo.pack(side="left")
        self.audio_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_entry_settings())
        tk.Label(tracks, text=t("subtitle"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left", padx=(12, 4))
        self.subtitle_combo = ttk.Combobox(tracks, textvariable=self.subtitle_var, width=12, state="readonly")
        self.subtitle_combo.pack(side="left")
        self.subtitle_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_entry_settings())
        self._build_light_dimmer(tracks)

    def state_color(self):
        if self.calibration_mode or getattr(self, "volume_setup", False):
            return COLOR_CALIBRATION
        return {"OFF": COLOR_OFF, "PROGRAM": COLOR_PROGRAM, "PLAYING": COLOR_PLAYING}[self.program_state]

    def selected_entry(self):
        if self.preview_index is not None and 0 <= self.preview_index < len(self.playlist):
            return self.playlist[self.preview_index]
        if self.playlist and 0 <= self.program_index < len(self.playlist):
            return self.playlist[self.program_index]
        return None

    def current_entry(self):
        if self.playlist and 0 <= self.program_index < len(self.playlist):
            return self.playlist[self.program_index]
        return None

    def _preview_clip(self):
        """The clip shown in the preview pane, if the operator picked one."""
        if self.preview_live or self.preview_index is None:
            return None
        if not 0 <= self.preview_index < len(self.playlist):
            return None
        entry = self.playlist[self.preview_index]
        if entry.missing:
            return None
        return entry

    def refresh_all(self):
        self.refresh_status()
        self.refresh_playlist()
        self.refresh_preview_meta()
        self.refresh_beamer()

    def _program_end_clock(self, now=None):
        """Finish time from the playhead. A stopped show is measured from the start."""
        moment = datetime.now() if now is None else now
        stopped = self.program_state == "OFF"
        playing = (
            self.program_state == "PLAYING"
            and not stopped
            and not getattr(self, "idle_showing", False)
        )
        return program_end_clock(
            self.playlist,
            0 if stopped else self.program_index,
            0 if stopped else self.position,
            playing,
            moment,
            self.autoplay_seconds(),
        )

    def refresh_status(self):
        if getattr(self, "volume_setup", False):
            state_key = "state_volume_setup"
        else:
            state_key = self._calibration_state_key()
        if not state_key:
            state_key = {"OFF": "state_off", "PROGRAM": "state_program", "PLAYING": "state_playing"}[self.program_state]
        self.state_label.config(text=t(state_key), bg=self.state_color())
        stopped = self.program_state == "OFF"
        entry = None if stopped else self.current_entry()
        end_clock = self._program_end_clock()
        if stopped:
            self.now_playing.config(text=t("no_program"), bg=COLOR_READOUT, fg=COLOR_TEXT)
            self.program_times.config(text=program_times_text("-", "--:--", self.playlist, end_clock))
        else:
            name = entry.filename if entry else t("no_program")
            self.now_playing.config(text=name, bg=self.state_color(), fg=COLOR_WHITE)
            index = f"{self.program_index + 1}" if self.playlist else "-"
            file_duration = (entry.duration if entry and entry.duration else 0) or self.duration or 0
            in_point = out_point = None
            if entry and not entry.is_image:
                in_point = entry.in_point
                out_point = entry.out_point
            times = clip_times(self.program_state, file_duration, self.position, in_point, out_point)
            self.program_times.config(
                text=program_times_text(index, times["total"], self.playlist, end_clock),
            )
        self._refresh_next_clip()
        if stopped:
            self.btn_play.icon_name = "start_program"
            self.btn_play.config(text=t("start"))
            self.btn_play.tooltip.text = t("start")
            if getattr(self.btn_play, "caption", None) is not None:
                self.btn_play.caption.config(text=t("start"))
        else:
            self.btn_play.icon_name = "play"
            self.btn_play.config(text=t("resume"))
            self.btn_play.tooltip.text = t("resume")
            if getattr(self.btn_play, "caption", None) is not None:
                self.btn_play.caption.config(text=t("resume"))
        self._refresh_idle_status()
        self.refresh_transport()
        if stopped:
            blank = format_clock(None)
            self.time_total.config(text=blank)
            self.time_elapsed.config(text=blank)
            self.time_remaining.config(text=blank)
            self.time_end.config(text=blank)
        else:
            self.time_total.config(text=times["total"])
            self.time_elapsed.config(text=times["elapsed"])
            self.time_remaining.config(text=times["remaining"])
            self.time_end.config(text=times["end"])
        if self.program_state != "PLAYING":
            # The fader belongs to the film under the program pointer, also
            # while the show is stopped. A stopped show has no rolling entry.
            self._load_program_volume(self.current_entry())
        self._refresh_program_delay_readout(entry)
        if self.calibration_mode == "audio":
            self._sync_audiosync_slider(entry)
        if getattr(self, "lights_fading", False):
            self._refresh_light_buttons()
        self._apply_volume_setup_chrome()
        self._apply_program_stop_chrome()
        self._apply_booth_chrome()

    def _refresh_next_clip(self):
        label = getattr(self, "next_clip", None)
        if label is None:
            return
        text = next_program_label(
            self.playlist,
            self.program_index,
            self.program_state,
            bool(self.projection_zoom.get()) if getattr(self, "projection_zoom", None) else False,
        )
        try:
            if not text:
                label.grid_remove()
                return
            label.config(text=text)
            if not label.winfo_manager():
                label.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        except tk.TclError:
            pass

    def _apply_program_stop_chrome(self):
        """A stopped show keeps the transport buttons and hides the rest of the block."""
        visible = getattr(self, "program_state", "OFF") != "OFF"
        self._set_grid_visible(getattr(self, "program_progress", None), visible)
        self._set_grid_visible(getattr(self, "program_clocks", None), visible)
        self._apply_program_audio_chrome()

    def _apply_program_audio_chrome(self):
        """A still has no soundtrack. Drop the program fader, envelope, and meter."""
        entry = self.current_entry() if getattr(self, "playlist", None) is not None else None
        still = bool(entry and getattr(entry, "is_image", False))
        running = getattr(self, "program_state", "OFF") != "OFF"
        self._set_grid_visible(getattr(self, "program_meter", None), running and not still)
        for name in ("program_envelope", "program_volume_row", "program_audio_bitrate"):
            self._set_grid_visible(getattr(self, name, None), not still)
        if getattr(self, "calibration_mode", None) == "audio":
            self._set_grid_visible(getattr(self, "audiosync_frame", None), not still)

    def _apply_preview_audio_chrome(self, entry):
        """Hide the preview meter for a still. The control strip is already gone."""
        still = bool(entry and getattr(entry, "is_image", False))
        self._set_grid_visible(getattr(self, "preview_meter_col", None), not still)

    def _booth_show_mode(self):
        """Armed or rolling show. Calibration keeps the preparation tools."""
        if getattr(self, "calibration_mode", None):
            return False
        return self.program_state in ("PROGRAM", "PLAYING")

    def _apply_booth_chrome(self):
        """Hide the playlist buttons while a show is armed or playing.

        The arrow brings them back. Preview settings such as autoplay and loop
        stay on screen.
        """
        show = self._booth_show_mode()
        previous = getattr(self, "_booth_chrome_show", None)
        self._booth_chrome_show = show
        if show and previous is not True:
            self.playlist_tools_open = False
            if getattr(self, "beamer_details_open", False):
                self.beamer_details_open = False
                self._apply_beamer_fold()
        tools_visible = (not show) or bool(getattr(self, "playlist_tools_open", False))
        self._set_grid_visible(getattr(self, "playlist_tool_buttons", None), tools_visible)
        self._set_grid_visible(getattr(self, "playlist_tools_toggle", None), show)
        self._paint_playlist_tools_arrow()

    def _toggle_playlist_tools(self, _event=None):
        if not self._booth_show_mode():
            return "break"
        self.playlist_tools_open = not bool(getattr(self, "playlist_tools_open", False))
        self._apply_booth_chrome()
        return "break"

    def _playlist_tools_enter(self, _event=None):
        self._playlist_tools_hover = True
        self._paint_playlist_tools_arrow()

    def _playlist_tools_leave(self, _event=None):
        self._playlist_tools_hover = False
        self._paint_playlist_tools_arrow()

    def _paint_playlist_tools_arrow(self):
        canvas = getattr(self, "playlist_tools_toggle", None)
        if canvas is None:
            return
        canvas.delete("all")
        try:
            width = canvas.winfo_width()
            height = canvas.winfo_height()
        except tk.TclError:
            return
        if width <= 1:
            width = int(canvas.cget("width") or 28)
        if height <= 1:
            height = int(canvas.cget("height") or 28)
        cx = width / 2
        cy = height / 2
        color = ACCENT if getattr(self, "_playlist_tools_hover", False) else COLOR_TEXT
        shown = (not self._booth_show_mode()) or bool(getattr(self, "playlist_tools_open", False))
        if shown:
            points = [cx - 5, cy - 6, cx - 5, cy + 6, cx + 6, cy]
        else:
            points = [cx + 5, cy - 6, cx + 5, cy + 6, cx - 6, cy]
        canvas.create_polygon(points, fill=color, outline=color)
        tip = getattr(self, "playlist_tools_tip", None)
        if tip is not None:
            tip.text = t("playlist_tools_hide" if shown else "playlist_tools_show")

    @staticmethod
    def _set_grid_visible(widget, visible):
        if widget is None:
            return
        try:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()
        except tk.TclError:
            pass

    def refresh_playlist(self):
        for child in self.playlist_inner.winfo_children():
            child.destroy()
        self.row_widgets = []
        apply_playlist_warnings(self.playlist, self.projection_zoom.get())
        last_group = None
        for index, entry in enumerate(self.playlist):
            group = self._playlist_group_label(entry)
            if group and group != last_group:
                self._make_folder_header(group)
                last_group = group
            elif not group:
                last_group = None
            self._make_row(index, entry)
        self._apply_playlist_name_wrap()
        self._sync_clip_settings_warning_option()
        self._refresh_settings_warning_status()

    def _row_is_preview(self, index):
        if not self.playlist:
            return False
        if self.preview_live or self.preview_index is None:
            return index == self.program_index
        return self.preview_index == index

    def _row_colors(self, index, entry):
        bg = COLOR_ROW
        fg = COLOR_PLAYED if entry.played and index != self.program_index else COLOR_TEXT
        if entry.missing:
            fg = COLOR_WARNING
        if index == self.program_index:
            if self.program_state == "PLAYING":
                bg, fg = COLOR_PLAYING, COLOR_WHITE
            elif self.program_state == "PROGRAM":
                bg, fg = COLOR_PROGRAM, COLOR_WHITE
        return bg, fg

    def _row_duration_text(self, entry):
        """Stills show their display time, or that they wait for the operator."""
        if not entry.is_image:
            return format_clock(entry.duration)
        if entry.display_time > 0:
            return format_clock(entry.display_time)
        return t("until_resume")

    def _playlist_group_label(self, entry):
        return playlist_location_short(getattr(entry, "path", ""), self.media_directories)

    def _make_folder_header(self, text):
        bar = tk.Frame(self.playlist_inner, bg=COLOR_PANEL)
        bar.playlist_index = None
        bar.pack(fill="x", padx=2, pady=(8, 0))
        tk.Label(
            bar, text=text, anchor="w", bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(side="left", padx=(8, 4))
        tk.Frame(bar, bg=COLOR_BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(4, 8))
        self._bind_playlist_wheel(bar)
        for child in bar.winfo_children():
            self._bind_playlist_wheel(child)

    def _meta_column(self, row, column, width, bg, fg):
        label = tk.Label(
            row, text="", width=width, anchor="e", bg=bg, fg=fg, font=FONT_SMALL,
        )
        label.grid(row=0, column=column, rowspan=2, sticky="e", padx=(6, 0))
        return label

    def _make_row(self, index, entry):
        bg, fg = self._row_colors(index, entry)
        border = COLOR_PREVIEW if self._row_is_preview(index) else COLOR_PANEL

        row = tk.Frame(
            self.playlist_inner, bg=bg, padx=6, pady=4,
            highlightthickness=2, highlightbackground=border, highlightcolor=border,
        )
        row.playlist_index = index
        row.pack(fill="x", pady=1, padx=2)
        row.columnconfigure(1, weight=1, minsize=140)

        cursor = tk.Label(row, text="", width=2, bg=bg, fg=fg, font=FONT_ROW_BOLD)
        cursor.grid(row=0, column=0, rowspan=2)

        name = tk.Frame(row, bg=bg)
        name.grid(row=0, column=1, rowspan=2, sticky="nsew")
        name.columnconfigure(1, weight=1)
        still_icon = tk.Label(name, bg=bg, bd=0, highlightthickness=0)
        still_icon.tooltip = IconTooltip(still_icon, t("still"))
        wrap = self._playlist_name_wrap()
        filename = tk.Label(
            name, text=entry.filename, anchor="w", justify="left",
            bg=bg, fg=fg, font=FONT_ROW_BOLD, wraplength=wrap,
        )
        detail = tk.Label(
            name, text="", anchor="w", justify="left",
            bg=bg, fg=self._location_fg(fg), font=FONT_SMALL, wraplength=wrap,
        )
        filename.grid(row=0, column=1, sticky="ew")
        detail.grid(row=1, column=1, sticky="ew", pady=(1, 0))
        filename.tooltip = IconTooltip(filename, getattr(entry, "path", "") or "")

        columns = {}
        for offset, (key, _label_key, width) in enumerate(PLAYLIST_META_COLUMNS):
            columns[key] = self._meta_column(row, 2 + offset, width, bg, fg)
        plain = [filename, *columns.values()]

        self.row_widgets.append({
            "row": row,
            "cursor": cursor,
            "name": name,
            "still_icon": still_icon,
            "plain": plain,
            "filename": filename,
            "detail": detail,
            **columns,
        })
        self._paint_row(index, entry)

        bind_targets = []
        pending = [row]
        while pending:
            widget = pending.pop()
            bind_targets.append(widget)
            pending.extend(widget.winfo_children())
        for widget in bind_targets:
            widget.bind("<ButtonPress-1>", lambda e, i=index: self.on_row_press(i, e))
            widget.bind("<B1-Motion>", lambda e: self.on_row_drag(e))
            widget.bind("<ButtonRelease-1>", lambda e: self.on_row_release(e))
            widget.bind("<Button-3>", lambda e, i=index: self.on_row_menu(i, e))
            self._bind_playlist_wheel(widget)

    def _row_detail_text(self, entry):
        codecs = " / ".join(part for part in (entry.video_codec, entry.audio_codec) if part)
        technical = " ".join(part for part in (entry.container, codecs) if part)
        parts = [part for part in (entry.resolution_label, technical) if part]
        return " · ".join(parts)

    def _paint_row(self, index, entry):
        widgets = self.row_widgets[index]
        bg, fg = self._row_colors(index, entry)
        border = COLOR_PREVIEW if self._row_is_preview(index) else COLOR_PANEL
        widgets["row"].config(
            bg=bg, highlightbackground=border, highlightcolor=border,
        )
        for label in widgets["plain"]:
            label.config(bg=bg, fg=fg)
        detail = self._row_detail_text(entry)
        widgets["detail"].config(text=detail, bg=bg, fg=self._location_fg(fg))
        try:
            if detail:
                if not widgets["detail"].winfo_manager():
                    widgets["detail"].grid(row=1, column=1, sticky="ew", pady=(1, 0))
            else:
                widgets["detail"].grid_remove()
        except tk.TclError:
            pass
        path = getattr(entry, "path", "") or ""
        tip = getattr(widgets["filename"], "tooltip", None)
        if tip is not None:
            tip.text = path
        widgets["cursor"].config(
            text=">" if index == self.program_index else " ", bg=bg, fg=fg
        )
        widgets["name"].config(bg=bg)
        still_icon = widgets["still_icon"]
        if getattr(entry, "is_image", False):
            photo = still_icon_photo(fg)
            still_icon.config(image=photo, bg=bg)
            still_icon.image = photo
            if not still_icon.winfo_manager():
                still_icon.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 6))
        else:
            still_icon.config(image="")
            still_icon.image = None
            if still_icon.winfo_manager():
                still_icon.grid_remove()
        warnings = set(playlist_warning_keys(entry))
        widgets["duration"].config(text=self._row_duration_text(entry), bg=bg, fg=fg)
        if getattr(entry, "is_image", False):
            volume_text = ""
            loudness_text = ""
        else:
            volume_text = f"{clamp_volume(entry.volume)}%"
            loudness_text = format_loudness(entry.loudness_lufs)
        widgets["volume"].config(text=volume_text, bg=bg, fg=COLOR_VOLUME)
        widgets["loudness"].config(text=loudness_text, bg=bg, fg=COLOR_VOLUME)
        rate_bad = "rate" in warnings
        widgets["fps"].config(
            text=warned_meta_text(format_fps_label(entry.fps), rate_bad, t("warn_rate")),
            bg=bg, fg=COLOR_WARNING if rate_bad else fg,
        )
        pad_16x9 = self._pad_16x9_enabled()
        widgets["aspect"].config(
            text=playlist_aspect_text(entry, pad_16x9=pad_16x9),
            bg=bg, fg=COLOR_WARNING if entry.aspect_warning else fg,
        )
        widgets["par"].config(
            text=playlist_par_text(entry, pad_16x9=pad_16x9),
            bg=bg, fg=COLOR_WARNING if entry.par_warning else fg,
        )
        widgets["colorspace"].config(
            text=playlist_color_text(entry),
            justify="right",
            bg=bg, fg=COLOR_WARNING if entry.colorspace_warning else fg,
        )
        notes = playlist_note_text(entry, self.projection_zoom.get())
        if not getattr(entry, "missing", False):
            scene = dmx.find_cue(
                getattr(entry, "light_start", ""),
                self.lights_scenes,
                getattr(self, "lights_sequences", None),
            )
            if scene is not None and getattr(scene, "id", "") != dmx.SCENE_DARK:
                badge = self._scene_badge(scene)
                if badge and badge not in notes.split():
                    notes = f"{notes} {badge}".strip()
        warning_tokens = {t("warn_color"), t("setting_badge"), t("missing_badge")}
        note_warning = any(token in notes.split() for token in warning_tokens)
        widgets["notes"].config(
            text=notes,
            bg=bg,
            fg=COLOR_WARNING if note_warning else (fg if fg == COLOR_WHITE else ACCENT),
        )

    def _sync_clip_settings_warning_option(self):
        """Preview force-warning is only offered while playlist-menu warnings are on."""
        box = getattr(self, "clip_settings_warning_check", None)
        if box is None:
            return
        try:
            if bool(self.projection_zoom.get()):
                if not box.winfo_manager():
                    played = getattr(self, "preview_played_box", None)
                    options = {"side": "left", "padx": (8, 0)}
                    if played is not None:
                        options["before"] = played
                    box.pack(**options)
            else:
                box.pack_forget()
        except tk.TclError:
            pass
        self._refresh_safety_group()

    def _refresh_safety_group(self):
        """Hide the safety heading when neither warning nor played is on screen."""
        safety = getattr(self, "preview_safety", None)
        if safety is None:
            return
        visible = False
        for widget in (
            getattr(self, "clip_settings_warning_check", None),
            getattr(self, "preview_played_box", None),
        ):
            if widget is None:
                continue
            try:
                if widget.winfo_manager():
                    visible = True
            except tk.TclError:
                pass
        try:
            if visible:
                if not safety.winfo_manager():
                    safety.pack(side="left", padx=(16, 0))
            else:
                safety.pack_forget()
        except tk.TclError:
            pass

    def _build_still_dim(self, parent):
        """Global fade switch and duration for every still."""
        self.still_dim_check = CheckLabel(
            parent, t("still_dim"), self.still_dim, self.apply_still_dim_settings, COLOR_PANEL,
        )
        self.still_dim_check.pack(side="left", padx=(16, 0))
        self.still_dim_label = tk.Label(
            parent, text=t("still_dim_time"), bg=COLOR_PANEL, font=FONT_UI,
        )
        self.still_dim_label.pack(side="left", padx=(8, 4))
        self.still_dim_seconds_entry = tk.Entry(
            parent, textvariable=self.still_dim_seconds, width=5, font=FONT_UI,
        )
        self.still_dim_seconds_entry.pack(side="left")
        self.still_dim_seconds_entry.bind("<Return>", lambda _event: self.apply_still_dim_settings())
        self.still_dim_seconds_entry.bind("<FocusOut>", lambda _event: self.apply_still_dim_settings())
        tk.Label(parent, text="s", bg=COLOR_PANEL, font=FONT_UI, fg=COLOR_MUTED).pack(
            side="left", padx=(4, 0)
        )

    def apply_still_dim_settings(self):
        seconds = self._still_dim_seconds()
        self.still_dim_seconds.set(format_seconds(seconds))
        self.settings["still_dim"] = bool(self.still_dim.get())
        self.settings["still_dim_seconds"] = seconds
        save_settings(self.settings)

    def _still_dim_seconds(self):
        raw = self.still_dim_seconds.get() if getattr(self, "still_dim_seconds", None) else 1
        try:
            value = float(str(raw).replace(",", "."))
        except (TypeError, ValueError):
            value = 1.0
        return max(0.0, value)

    def _still_dim_active(self):
        enabled = bool(self.still_dim.get()) if getattr(self, "still_dim", None) else False
        return enabled and self._still_dim_seconds() > 0

    def apply_preview_layout(self, entry):
        """Stills keep Autoplay, display time, fade, and the dimmer. Loop stays hidden."""
        image = bool(entry and entry.is_image)
        if image:
            self.preview_controls.grid_remove()
            self.preview_clip_settings.pack_forget()
            self.preview_played_box.pack_forget()
            if not self.preview_image_settings.winfo_manager():
                self.preview_image_settings.pack(side="left", padx=(16, 0))
        else:
            self.preview_controls.grid()
            self.preview_image_settings.pack_forget()
            if not self.preview_clip_settings.winfo_manager():
                self.preview_clip_settings.pack(side="left")
            if not self.preview_played_box.winfo_manager():
                self.preview_played_box.pack(side="left")
        self._place_light_dimmer(image)
        self._apply_preview_audio_chrome(entry)
        self._refresh_safety_group()

    def repaint_playlist(self):
        """Update row colours and marks in place, keeping the widgets alive."""
        if len(self.row_widgets) != len(self.playlist):
            self.refresh_playlist()
            return
        for index, entry in enumerate(self.playlist):
            self._paint_row(index, entry)

    def _set_preview_lufs(self, entry):
        label = self.preview_lufs
        if entry and getattr(entry, "is_image", False):
            label.config(text="")
            if label.winfo_manager():
                label.grid_remove()
            return
        if not label.winfo_manager():
            label.grid(row=0, column=0, pady=(0, 2))
        if entry and not entry.missing and not entry.is_image:
            value = format_loudness(entry.loudness_lufs)
        else:
            value = format_loudness(None)
        if value.endswith(" LUFS"):
            value = f"{value[:-5].strip()}\nLUFS"
        else:
            value = f"{value}\nLUFS"
        self.preview_lufs.config(text=value)

    def _set_preview_envelope(self, entry):
        canvas = getattr(self, "preview_envelope", None)
        if canvas is None:
            return
        peaks = None
        if entry and not entry.missing and not entry.is_image:
            peaks = entry.audio_envelope
        canvas.set_envelope(peaks)
        canvas.set_playhead(self._clip_duration(), self.preview_position)

    def refresh_preview_meta(self):
        entry = self.selected_entry()
        live = self.preview_live or self.preview_index is None
        mode = t("live") if live else t("preview_mode")
        color = self.state_color() if live else COLOR_PREVIEW
        self.preview_mode_btn.config(text=mode, bg=color, fg=COLOR_WHITE, activebackground=color)
        if live:
            self.preview_title.config(text=entry.filename if entry else t("live"), bg=color, fg=COLOR_WHITE)
        else:
            self.preview_title.config(
                text=entry.filename if entry else t("preview_mode"), bg=COLOR_PREVIEW, fg=COLOR_WHITE
            )
        self.apply_preview_layout(entry)
        self._load_preview_volume(entry)
        self._set_preview_lufs(entry)
        self._set_preview_envelope(entry)
        self.refresh_transport()
        if not entry:
            self.preview_meta.config(text=t("length_empty"))
            self.audio_combo["values"] = ["--"]
            self.subtitle_combo["values"] = ["--"]
            self.autoplay_var.set(False)
            self.clip_settings_warning_var.set(False)
            self.loop_var.set(False)
            self.played_var.set(False)
            self._set_play_light_combo("")
            self._update_preview_bar()
            return
        if entry.missing:
            self.preview_meta.config(text=t("missing_file", path=entry.path))
            self.autoplay_var.set(entry.autoplay)
            self.clip_settings_warning_var.set(bool(entry.force_settings_warning))
            self.loop_var.set(bool(entry.loop) and not entry.is_image)
            self.played_var.set(entry.played)
            self._set_play_light_combo(entry.light_start)
            self._update_preview_bar()
            return
        if entry.is_image:
            self.display_time.set(format_seconds(entry.display_time))
            self.preview_meta.config(
                text=t(
                    "still_image",
                    container=entry.container,
                    width=entry.width,
                    height=entry.height,
                    aspect=entry.aspect,
                    pixel_aspect=entry.pixel_aspect,
                    colorspace=format_colorspace_label(entry) + " · " + source_color_label(entry),
                )
            )
            self.autoplay_var.set(entry.autoplay)
            self.clip_settings_warning_var.set(bool(entry.force_settings_warning))
            self.loop_var.set(False)
            self.played_var.set(entry.played)
            self._set_play_light_combo(entry.light_start)
            self._update_preview_bar()
            return
        self.preview_meta.config(
            text=t(
                "length_clip",
                duration=format_clock(entry.duration),
                container=entry.container,
                video=format_codec_rate(entry.video_codec, entry.video_bitrate),
                audio=format_codec_rate(entry.audio_codec, entry.audio_bitrate),
                aspect=entry.aspect,
                pixel_aspect=entry.pixel_aspect,
                colorspace=format_colorspace_label(entry) + " · " + source_color_label(entry),
            )
        )
        self.autoplay_var.set(entry.autoplay)
        self.clip_settings_warning_var.set(bool(entry.force_settings_warning))
        self.loop_var.set(bool(entry.loop))
        self.played_var.set(entry.played)
        self._set_play_light_combo(entry.light_start)
        tracks = entry.audio_tracks or ["--"]
        self.audio_combo["values"] = tracks
        self.audio_var.set(entry.audio_track if entry.audio_track in tracks else tracks[0])
        subs = entry.subtitle_tracks or ["--"]
        self.subtitle_combo["values"] = subs
        self.subtitle_var.set(entry.subtitle_track if entry.subtitle_track in subs else "--")
        self.preview_in.config(text=t("in_value", value=format_clock(entry.in_point)))
        self.preview_out.config(text=t("out_value", value=format_clock(entry.out_point)))
        self._update_preview_bar()

    def refresh_beamer(self):
        mode = self.output_manager.video_mode or self.output_manager.get_current_mode(
            self.output_manager.video_output or ""
        )
        if not self.output_manager.video_output:
            try:
                self.output_manager.select_video_output()
            except Exception:
                pass
            mode = mode or self.output_manager.get_current_mode(self.output_manager.video_output or "")
        if not mode:
            self.beamer_ok.config(text="--", bg=COLOR_BADGE_IDLE)
            self.beamer_aspect.config(text="--", fg=COLOR_TEXT)
            self.beamer_clip_aspect.config(text="")
            self._set_beamer_summary("--", "--", "--")
            self._refresh_beamer_decode()
            self._refresh_beamer_device_name()
            self._refresh_beamer_gpu()
            self.beamer_rates.set_choices(t("beamer_rates", rates=""), [])
            self.beamer_resolutions.set_choices(
                t("beamer_resolutions", resolutions=""), [],
            )
            self.beamer_colorspaces.set_choices(
                t("beamer_colorspaces", spaces=""), [],
            )
            self.refresh_beamer_outputs()
            return
        rates, resolutions, colorspaces = self._beamer_capability_lists()
        clip = self.current_entry()
        preview = self._preview_clip()
        focus = clip if self.program_state == "PLAYING" else (preview or clip)
        fps_ok = True
        if focus and not focus.missing and not focus.is_image and focus.fps:
            fps_ok = self._beamer_rate_supported(focus.fps, rates)
        self._refresh_beamer_ok_badge(fps_ok)
        self._refresh_beamer_decode()
        aspect_text = aspect_from_mode(mode)
        self.beamer_aspect.config(text=aspect_text, fg=COLOR_TEXT)
        self.beamer_clip_aspect.config(text="")
        if preview and preview.aspect not in ("", "--") and same_aspect_ratio(
            preview.aspect, aspect_text
        ):
            self.beamer_aspect.config(fg=COLOR_PREVIEW)
        if clip and clip.aspect not in ("", "--") and same_aspect_ratio(
            clip.aspect, aspect_text
        ):
            self.beamer_aspect.config(fg=ACCENT)
        if not self._beamer_aspect_supported(clip, resolutions):
            self.beamer_clip_aspect.config(text=clip.aspect, fg=ACCENT)
        elif not self._beamer_aspect_supported(preview, resolutions):
            self.beamer_clip_aspect.config(text=preview.aspect, fg=COLOR_PREVIEW)
        selected_rate = next(
            (
                format_fps_label(rate)
                for rate in rates
                if self.output_manager.refresh_close(rate, mode.refresh)
            ),
            None,
        )
        selected_res = next(
            (
                f"{width}x{height}"
                for width, height in resolutions
                if width == mode.width and height == mode.height
            ),
            None,
        )
        rate_tokens = [format_fps_label(rate) for rate in rates]
        res_tokens = [f"{width}x{height}" for width, height in resolutions]
        program_rates = []
        program_res = None
        preview_rates = []
        preview_res = None
        if clip and not clip.missing and not clip.is_image and clip.fps:
            program_rates = self._matching_rate_labels(clip.fps, rates)
            if not program_rates:
                program_rates = [format_fps_label(clip.fps)]
                if program_rates[0] not in rate_tokens:
                    rate_tokens.append(program_rates[0])
                    rate_tokens.sort(key=self._beamer_rate_sort_key)
        if clip and not clip.missing and clip.width and clip.height:
            wanted = f"{clip.width}x{clip.height}"
            if (clip.width, clip.height) in resolutions:
                program_res = wanted
            else:
                program_res = wanted
                if wanted not in res_tokens:
                    res_tokens.append(wanted)
                    res_tokens = [
                        f"{width}x{height}"
                        for width, height in sorted(
                            [self._parse_res_token(token) for token in res_tokens],
                            key=lambda item: (-item[0] * item[1], -item[0]),
                        )
                    ]
        if preview and not preview.is_image and preview.fps:
            preview_rates = self._matching_rate_labels(preview.fps, rates)
            if not preview_rates:
                preview_rates = [format_fps_label(preview.fps)]
                if preview_rates[0] not in rate_tokens:
                    rate_tokens.append(preview_rates[0])
                    rate_tokens.sort(key=self._beamer_rate_sort_key)
        if preview and preview.width and preview.height:
            wanted = f"{preview.width}x{preview.height}"
            if (preview.width, preview.height) in resolutions:
                preview_res = wanted
            else:
                preview_res = wanted
                if wanted not in res_tokens:
                    res_tokens.append(wanted)
                    res_tokens = [
                        f"{width}x{height}"
                        for width, height in sorted(
                            [self._parse_res_token(token) for token in res_tokens],
                            key=lambda item: (-item[0] * item[1], -item[0]),
                        )
                    ]
        self.beamer_rates.set_choices(
            t("beamer_rates", rates=""),
            rate_tokens,
            selected_rate,
            program_rates,
            preview_rates,
        )
        self.beamer_resolutions.set_choices(
            t("beamer_resolutions", resolutions=""),
            res_tokens,
            selected_res,
            program_res,
            preview_res,
        )
        selected_space = None
        try:
            selected_space = self.output_manager.color_format or None
        except Exception:
            selected_space = None
        if selected_space and selected_space not in colorspaces:
            colorspaces = list(colorspaces) + [selected_space]
        self.beamer_colorspaces.set_choices(
            t("beamer_colorspaces", spaces=""),
            colorspaces,
            selected_space if selected_space in colorspaces else None,
        )
        resolution_text = selected_res or f"{mode.width}x{mode.height}"
        rate_text = selected_rate or format_fps_label(mode.refresh)
        space_text = selected_space or "--"
        self._set_beamer_summary(
            resolution_text,
            rate_text,
            space_text,
            self._marked_value_fg(resolution_text, program_res, preview_res),
            self._marked_value_fg(rate_text, program_rates, preview_rates),
        )
        self._refresh_beamer_device_name()
        self._refresh_beamer_gpu()
        self.refresh_beamer_outputs()

    def _program_decode_active(self):
        mpv = getattr(self, "main_mpv", None)
        if mpv is None:
            return False
        keepalive = bool(getattr(self, "hdmi_audio_keepalive", False))
        is_keepalive = getattr(mpv, "is_audio_keepalive", None)
        if callable(is_keepalive):
            keepalive = bool(is_keepalive())
        return (
            self.program_state == "PLAYING"
            and bool(mpv.process)
            and bool(mpv.loaded_path)
            and not self.idle_showing
            and not self.blackout
            and not keepalive
            and not self.beamer_test_active
        )

    def _refresh_beamer_ok_badge(self, fps_ok):
        dropped = self._program_decode_active() and frames_were_dropped(
            self.program_frame_drops, self.program_decoder_drops,
        )
        if not fps_ok:
            self.beamer_ok.config(text=t("mismatch"), bg=COLOR_OFF)
        elif dropped:
            self.beamer_ok.config(text=t("dropped"), bg=COLOR_OFF)
        else:
            self.beamer_ok.config(text=t("ok"), bg=COLOR_PLAYING)

    def _refresh_beamer_decode(self):
        hwdec = getattr(self, "beamer_hwdec", None)
        mpv_drops = getattr(self, "beamer_drops_mpv", None)
        decoder_drops = getattr(self, "beamer_drops_decoder", None)
        if hwdec is None or mpv_drops is None or decoder_drops is None:
            return
        summary = getattr(self, "beamer_drop_summary", None)
        if not self._program_decode_active():
            hwdec.config(text="--", fg=COLOR_TEXT)
            mpv_drops.config(text="--", fg=COLOR_TEXT)
            decoder_drops.config(text="--", fg=COLOR_TEXT)
            self._set_drop_summary(summary, "")
            return
        name = format_hwdec_current(self.program_hwdec) or "--"
        hwdec.config(text=name, fg=COLOR_TEXT)
        vo = parse_mpv_count(self.program_frame_drops)
        decoder = parse_mpv_count(self.program_decoder_drops)
        mpv_drops.config(text=str(vo), fg=COLOR_OFF if vo else COLOR_TEXT)
        decoder_drops.config(text=str(decoder), fg=COLOR_OFF if decoder else COLOR_TEXT)
        if frames_were_dropped(self.program_frame_drops, self.program_decoder_drops):
            self._set_drop_summary(summary, t("beamer_drops_short", mpv=vo, decoder=decoder))
        else:
            self._set_drop_summary(summary, "")

    def _set_drop_summary(self, summary, text):
        """Show the drop count in the short beamer form while frames are lost."""
        if summary is None:
            return
        try:
            if not text:
                summary.pack_forget()
                return
            summary.config(text=text)
            if not summary.winfo_manager():
                summary.pack(fill="x", padx=8, pady=(0, 4))
        except tk.TclError:
            pass

    def _reset_program_decode(self):
        self.program_hwdec = ""
        self.program_frame_drops = 0
        self.program_decoder_drops = 0

    def _refresh_beamer_device_name(self):
        name = ""
        try:
            name = self.output_manager.get_output_device_name()
        except Exception:
            name = ""
        widget = getattr(self, "beamer_device", None)
        if widget is not None:
            widget.config(text=name or "--")

    def _refresh_beamer_gpu(self):
        label = ""
        try:
            label = self.output_manager.gpu_label()
        except Exception:
            label = ""
        widget = getattr(self, "beamer_gpu", None)
        if widget is not None:
            widget.config(text=label or "--")

    def _beamer_capability_lists(self):
        output = self.output_manager.video_output or ""
        cache = self._beamer_caps_cache
        if cache and cache[0] == output:
            return cache[1], cache[2], cache[3]
        try:
            modes = self.output_manager.get_modes(output) if output else []
        except Exception:
            modes = []
        rates = []
        for mode in modes:
            if any(self.output_manager.refresh_close(mode.refresh, seen) for seen in rates):
                continue
            rates.append(mode.refresh)
        rates.sort()
        seen_res = []
        for mode in sorted(modes, key=lambda item: (-item.width * item.height, -item.width)):
            key = (mode.width, mode.height)
            if key in seen_res:
                continue
            seen_res.append(key)
        try:
            colorspaces = self.output_manager.get_color_formats(output) if output else []
        except Exception:
            colorspaces = []
        if not colorspaces:
            colorspaces = ["RGB"]
        self._beamer_caps_cache = (output, rates, seen_res, colorspaces)
        return rates, seen_res, colorspaces

    def _beamer_rate_supported(self, fps, rates):
        return any(self.output_manager.refresh_matches(fps, rate) for rate in rates)

    def _matching_rate_labels(self, fps, rates):
        """Beamer rates that can play this fps (native, 2x, or 50/60→25/30)."""
        labels = []
        seen = set()
        half = self.output_manager.half_refresh_rate(fps)
        has_native = any(self.output_manager.refresh_close(rate, fps) for rate in rates)
        has_double = bool(fps) and any(
            self.output_manager.refresh_close(rate, fps * 2) for rate in rates
        )
        use_half = bool(half) and not has_native and not has_double
        for rate in rates:
            matches = self.output_manager.refresh_close(rate, fps)
            if not matches and fps and fps < 48:
                matches = self.output_manager.refresh_close(rate, fps * 2)
            if not matches and use_half:
                matches = self.output_manager.refresh_close(rate, half)
            if not matches:
                continue
            label = format_fps_label(rate)
            if label in seen:
                continue
            seen.add(label)
            labels.append(label)
        return labels

    def _beamer_aspect_supported(self, entry, resolutions):
        if not entry or entry.missing or entry.aspect in ("", "--"):
            return True
        return any(
            same_aspect_ratio(entry.aspect, aspect_from_size(width, height))
            for width, height in resolutions
        )

    @staticmethod
    def _beamer_rate_sort_key(label):
        text = str(label).rstrip("piPI").strip()
        try:
            return float(text)
        except ValueError:
            return 0.0

    @staticmethod
    def _parse_res_token(token):
        width, height = str(token).lower().split("x", 1)
        return int(width), int(height)

    def refresh_beamer_outputs(self):
        """Keep the selected output name in sync with the connected display."""
        current = self.output_manager.video_output or ""
        if current and self.beamer_output.get() != current:
            self.beamer_output.set(current)

    def apply_beamer_output(self, output=None):
        if output is None:
            output = self.beamer_output.get().strip()
        else:
            self.beamer_output.set(output)
        if not output:
            return
        if self.program_state == "PLAYING":
            messagebox.showinfo(t("beamer_status"), t("beamer_output_busy"))
            self.beamer_output.set(self.output_manager.video_output or "")
            return
        if output == self.output_manager.video_output:
            return
        try:
            self.output_manager.set_video_output(output)
        except Exception as exc:
            messagebox.showerror(t("beamer_status"), str(exc))
            self.refresh_beamer_outputs()
            return
        self.settings["video_output"] = output
        self._beamer_caps_cache = None
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self._restart_main_output()
        self.refresh_beamer()
        if self.window_fullscreen.get():
            self._apply_window_fullscreen()

    def show_edid(self):
        """Show the projector's full EDID in a window on the control monitor."""
        output = self.output_manager.video_output or self.beamer_output.get().strip()
        if not output:
            messagebox.showerror(t("edid"), t("edid_no_output"))
            return
        report = self.output_manager.edid_report(output)
        if not report:
            messagebox.showerror(t("edid"), t("edid_unavailable", output=output))
            return
        blocks = max(1, len(report["data"]) // 128)
        body = "\n".join((
            t("edid_output", output=report["output"]),
            t("edid_source", source=report["source"]),
            t("edid_size", bytes=len(report["data"]), blocks=blocks),
            "",
            report["decoded"],
        ))
        if self._edid_window_alive():
            self._fill_edid_window(report["output"], body)
            self.edid_window.deiconify()
            self._present_popup(self.edid_window)
            return
        window = tk.Toplevel(self.root)
        window.title(t("edid_title", output=report["output"]))
        window.configure(bg=COLOR_BG)
        window.minsize(560, 400)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_edid_window)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        pane = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=10)
        holder = tk.Frame(pane, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        text = tk.Text(
            holder,
            wrap="none",
            font=FONT_EDID,
            bg=COLOR_FIELD,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            selectbackground=COLOR_PROGRAM,
            selectforeground=COLOR_WHITE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            padx=8,
            pady=8,
            undo=False,
        )
        yscroll = ttk.Scrollbar(holder, orient="vertical", command=text.yview)
        xscroll = ttk.Scrollbar(holder, orient="horizontal", command=text.xview)
        text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        text.bind("<Control-a>", self._select_all_text)
        text.bind("<Control-A>", self._select_all_text)

        tk.Button(
            buttons, text=t("edid_close"), command=self._close_edid_window, font=FONT_UI,
        ).pack(side="right")

        window._edid_text = text
        self.edid_window = window
        self._fill_edid_window(report["output"], body)
        self._bind_popup_wheel(window, pane)
        self._open_popup(window, 820, 700)

    def _edid_window_alive(self):
        window = getattr(self, "edid_window", None)
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            self.edid_window = None
            return False

    def _fill_edid_window(self, output, body):
        window = self.edid_window
        window.title(t("edid_title", output=output))
        text = window._edid_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", body)
        text.mark_set("insert", "1.0")
        text.configure(state="disabled")

    @staticmethod
    def _select_all_text(event):
        event.widget.tag_add("sel", "1.0", "end")
        return "break"

    def _close_edid_window(self):
        window = getattr(self, "edid_window", None)
        self.edid_window = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _place_on_control_monitor(self, window, width, height):
        """Keep secondary windows on the control screen, never on the projector."""
        geometry = self._control_fullscreen_geometry()
        if geometry:
            screen_w, screen_h, screen_x, screen_y = geometry
            x = screen_x + max(24, (screen_w - width) // 2)
            y = screen_y + max(24, (screen_h - height) // 2)
        else:
            try:
                x = self.root.winfo_rootx() + 48
                y = self.root.winfo_rooty() + 48
            except tk.TclError:
                x = y = 80
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _restart_main_output(self, blank=True):
        """Move the program window onto the newly chosen projector output."""
        if self.main_mpv.process:
            try:
                self.main_mpv.quit()
            except Exception:
                pass
            self.main_mpv = MPVController("main", self.mpv_path)
            self.main_mpv.add_callback(self.main_mpv_event)
        if not self.ensure_main_output(auto=False):
            messagebox.showerror(t("beamer_status"), t("output_failed"))
            return False
        if blank and self.program_state != "PLAYING":
            self.blank_output()
        self._apply_preview_audio_device()
        return True

    def _push_audio_route(self, controller, device, when_missing):
        """Point a running mpv instance at a sound output without restarting it."""
        if controller is None or not controller.process:
            return
        for prop, value in audio_route_commands(device, when_missing=when_missing):
            controller.command("set_property", prop, value)

    def _apply_preview_audio_device(self):
        """Point preview at its patched sound output."""
        if self.output_manager.audio_patch_is_off("preview"):
            device = AUDIO_PATCH_NONE
        else:
            device = self.output_manager.preview_audio_device(self.mpv_path)
        self._push_audio_route(self.preview_mpv, device, "null")

    def _apply_main_audio_device(self):
        """Point the Beamer player at its patched sound output."""
        if self.output_manager.audio_patch_is_off("beamer"):
            device = AUDIO_PATCH_NONE
        else:
            device = self.output_manager.program_audio_device(self.mpv_path)
        self._push_audio_route(self.main_mpv, device, "auto")

    def _pin_main_output_to_beamer(self):
        """Keep the Wayland mpv surface on the projector after a mode change."""
        output = self.output_manager.video_output
        if not output or not self.main_mpv.process:
            return
        self.main_mpv.command("set_property", "screen-name", output)
        self.main_mpv.command("set_property", "fs-screen-name", output)
        self.main_mpv.command("set_property", "fullscreen", True)

    def on_row_click(self, index):
        """Single click: show the clip in the preview window."""
        if not 0 <= index < len(self.playlist):
            return
        self.preview_index = index
        self.preview_live = False
        self.repaint_playlist()
        self.refresh_status()
        self.refresh_preview_meta()
        self.refresh_beamer()
        self.show_preview_clip(self.playlist[index])

    def on_row_menu(self, index, event):
        """Right click: act on the clicked clip."""
        if not 0 <= index < len(self.playlist):
            return
        self.on_row_click(index)
        playing = self.program_state == "PLAYING"
        missing = bool(self.playlist[index].missing)
        menu = DropdownMenu(self.root, self)
        busy = playing and index == self.program_index
        menu.add_command(
            label=t("set_program"), command=lambda: self.set_program_point(index),
            state="disabled" if playing or missing else "normal",
        )
        menu.add_separator()
        menu.add_command(label=t("autoplay"), command=lambda: self.toggle_autoplay(index))
        menu.add_command(
            label=t("loop"),
            command=lambda: self.toggle_loop(index),
            state="disabled" if self.playlist[index].is_image else "normal",
        )
        menu.add_separator()
        menu.add_command(
            label=t("refresh_playlist"), command=lambda: self.refresh_entry(index),
            state="disabled" if busy else "normal",
        )
        menu.add_command(
            label=t("relink_entry"), command=lambda: self.relink_entry(index),
            state="disabled" if busy else "normal",
        )
        in_folder = self._entry_is_in_playlist_folder(self.playlist[index])
        menu.add_command(
            label=t("copy_entry_to_import"),
            command=lambda: self.copy_entry_to_playlist_folder(index),
            state="disabled" if busy or missing or in_folder else "normal",
        )
        menu.add_separator()
        menu.add_command(
            label=t("delete_entry"), command=lambda: self.delete_entry(index),
            state="disabled" if busy else "normal",
        )
        self._post_dropdown(menu, event.x_root, event.y_root)
        self.row_menu = menu

    def _move_program_cursor(self, index):
        if self.playlist:
            index = min(max(index, 0), len(self.playlist) - 1)
        else:
            index = 0
        if index != self.program_index:
            self.zoom_confirmed_index = None
            self.program_index = index
            self._autosave_playlist()
        else:
            self.program_index = index
        self.apply_beamer_mode_for_pointer()

    def apply_beamer_mode_for_pointer(self):
        """Switch the projector refresh as soon as the program pointer sits on a film."""
        if self.program_state == "PLAYING":
            return
        entry = self.current_entry()
        if not entry or entry.missing or entry.is_image:
            return
        if not media_file_available(entry):
            return
        before = None
        output = self.output_manager.video_output
        if output:
            before = self.output_manager.get_current_mode(output)
        try:
            _video, mode, matched = self.output_manager.prepare_for_video(
                entry.path, pad_16x9=self._pad_16x9_enabled(),
            )
            entry.refresh_ok = matched
        except Exception as exc:
            print(f"Beamer-Modus nicht gesetzt: {exc}")
            return
        changed = self._projection_mode_changed(before, mode)
        if changed and session_is_wayland() and self.main_mpv.process:
            self._restart_main_output(blank=False)
            if self.program_state == "PROGRAM":
                self.blank_output()
        self.refresh_beamer()

    def _projection_mode_changed(self, before, mode):
        """True when the projector was switched to a different size or refresh."""
        if before is None or mode is None:
            return True
        return (
            before.width != mode.width
            or before.height != mode.height
            or not self.output_manager.refresh_close(before.refresh, mode.refresh)
        )

    def _skip_to_playable(self, inclusive=True):
        """Move the program cursor to the next clip whose file is still on disk."""
        if not self.playlist:
            return False
        start = self.program_index if inclusive else self.program_index + 1
        start = max(0, start)
        for index in range(start, len(self.playlist)):
            entry = self.playlist[index]
            entry.missing = not media_file_available(entry)
            if not entry.missing:
                self._move_program_cursor(index)
                return True
        return False

    def confirm_projection_zoom(self, prompt=True):
        """Ask as soon as the program cursor lands on a clip that needs a settings change."""
        if not self.playlist:
            return True
        entry = self.current_entry()
        if not entry or entry.missing or not clip_needs_settings_warning(
            entry, self.projection_zoom.get()
        ):
            return True
        if self.zoom_confirmed_index == self.program_index:
            return True
        if not prompt or self._remote_action:
            return False
        self.root.update_idletasks()
        ok = messagebox.askokcancel(
            t("projection_zoom_title"),
            t(
                "projection_zoom_message",
                filename=entry.filename,
                aspect=entry.aspect,
                pixel_aspect=entry.pixel_aspect,
                colorspace=format_colorspace_label(entry) + " · " + source_color_label(entry),
            ),
        )
        if ok:
            self.zoom_confirmed_index = self.program_index
        else:
            self.zoom_confirmed_index = None
        return ok

    def set_program_point(self, index):
        if self.program_state == "PLAYING" or not 0 <= index < len(self.playlist):
            return
        if self.playlist[index].missing:
            return
        self._move_program_cursor(index)
        self.repaint_playlist()
        self.refresh_status()
        if self.program_state == "PROGRAM":
            self.confirm_projection_zoom(prompt=not self._remote_action)

    def toggle_autoplay(self, index):
        if not 0 <= index < len(self.playlist):
            return
        entry = self.playlist[index]
        entry.autoplay = not entry.autoplay
        if self.selected_entry() is entry:
            self.autoplay_var.set(entry.autoplay)
        self.repaint_playlist()

    def toggle_loop(self, index):
        if not 0 <= index < len(self.playlist):
            return
        entry = self.playlist[index]
        if entry.is_image:
            return
        entry.loop = not entry.loop
        if self.selected_entry() is entry:
            self.loop_var.set(entry.loop)
        if self.program_state == "PLAYING" and entry is self.current_entry():
            self._apply_program_loop(entry)
            if self.preview_live:
                self._apply_program_loop(entry, self.preview_mpv)
        self.repaint_playlist()
        self.refresh_transport()

    def refresh_entry(self, index):
        """Re-read this clip's file metadata and keep its playlist settings."""
        if not 0 <= index < len(self.playlist):
            return
        if self.program_state == "PLAYING" and index == self.program_index:
            return
        entry = self.playlist[index]
        if reload_entry_metadata(entry):
            self._match_entry_refresh(entry)
        if self.preview_index == index and not self.preview_live:
            self.show_preview_clip(entry)
        self.refresh_all()

    def _match_entry_refresh(self, entry):
        """Store whether the projector can show this clip's size and rate."""
        if entry.missing or entry.is_image or not media_file_available(entry):
            return
        try:
            if not self.output_manager.video_output:
                self.output_manager.select_video_output()
            video = self.output_manager.get_video_info(entry.path)
            if video:
                _mode, matched = self.output_manager.find_best_mode(
                    video, create=False, pad_16x9=self._pad_16x9_enabled(),
                )
                entry.refresh_ok = matched
        except Exception:
            entry.refresh_ok = False

    def relink_entry(self, index):
        """Point this playlist row at a new file and keep cue/volume settings."""
        if not 0 <= index < len(self.playlist):
            return
        if self.program_state == "PLAYING" and index == self.program_index:
            return
        entry = self.playlist[index]
        dialog_options = {}
        directory = os.path.dirname(entry.path)
        if directory and os.path.isdir(directory):
            dialog_options["initialdir"] = directory
        else:
            start = self._preferred_import_dir()
            if start:
                dialog_options["initialdir"] = start
        if entry.filename:
            dialog_options["initialfile"] = entry.filename
        path = filedialog.askopenfilename(
            title=t("relink_entry"),
            filetypes=[
                (t("media_files"), " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTS | IMAGE_EXTS))),
                (t("all_files"), "*.*"),
            ],
            **dialog_options,
        )
        if not path:
            return
        try:
            probed = probe_media(path)
        except Exception as exc:
            messagebox.showerror(t("import_error"), f"{os.path.basename(path)}\n{exc}")
            return
        probed.autoplay = entry.autoplay
        probed.loop = bool(entry.loop) and not probed.is_image
        probed.played = entry.played
        probed.volume = clamp_volume(entry.volume)
        probed.display_time = entry.display_time
        probed.light_start = entry.light_start
        probed.light_end = entry.light_end
        probed.force_settings_warning = bool(entry.force_settings_warning)
        if probed.duration > 0:
            if entry.in_point is not None and 0 <= entry.in_point < probed.duration:
                probed.in_point = entry.in_point
            if entry.out_point is not None and 0 < entry.out_point <= probed.duration:
                probed.out_point = entry.out_point
            if (
                probed.in_point is not None
                and probed.out_point is not None
                and probed.in_point > probed.out_point
            ):
                probed.in_point, probed.out_point = probed.out_point, probed.in_point
        if entry.audio_track in probed.audio_tracks:
            probed.audio_track = entry.audio_track
        if entry.subtitle_track in (probed.subtitle_tracks or ["--"]):
            probed.subtitle_track = entry.subtitle_track
        probed.missing = False
        try:
            if not self.output_manager.video_output:
                self.output_manager.select_video_output()
            video = self.output_manager.get_video_info(path) if not probed.is_image else None
            if video:
                mode, matched = self.output_manager.find_best_mode(
                    video, create=False, pad_16x9=self._pad_16x9_enabled(),
                )
                probed.refresh_ok = matched
        except Exception:
            probed.refresh_ok = False
        self.playlist[index] = probed
        self.remember_import_dir(path)
        if self.zoom_confirmed_index == index:
            self.zoom_confirmed_index = None
        if self.preview_index == index:
            self.show_preview_clip(probed)
        self.refresh_all()

    def _playlist_import_folder(self):
        """Same-named folder of the current playlist under the import path."""
        if not self._ensure_import_path():
            return ""
        stem = playlist_folder_name(self._current_playlist_name())
        if not stem and getattr(self, "playlist_path", ""):
            stem = playlist_folder_name(os.path.basename(self.playlist_path))
        if not stem:
            stem = self._ask_playlist_name()
            if not stem:
                return ""
            self._set_playlist_name(f"{stem}.pls")
        folder = os.path.join(self.import_path, stem)
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(
                t("copy_entry_to_import"),
                t("copy_files_failed", path=folder, error=exc),
            )
            return ""
        return folder

    def _entry_is_in_playlist_folder(self, entry):
        if not self._import_path_ready() or entry is None:
            return False
        stem = playlist_folder_name(self._current_playlist_name())
        if not stem and getattr(self, "playlist_path", ""):
            stem = playlist_folder_name(os.path.basename(self.playlist_path))
        if not stem:
            return False
        try:
            folder = os.path.abspath(os.path.join(self.import_path, stem))
            return os.path.dirname(os.path.abspath(entry.path)) == folder
        except (OSError, ValueError):
            return False

    def copy_entry_to_playlist_folder(self, index):
        """Copy this clip into the playlist's folder in the import path."""
        if not 0 <= index < len(self.playlist):
            return
        if self.program_state == "PLAYING" and index == self.program_index:
            return
        entry = self.playlist[index]
        source = entry.path
        if not source or not os.path.isfile(source):
            messagebox.showerror(
                t("copy_entry_to_import"),
                t("copy_files_failed", path=source or "", error=t("media_directories_missing")),
            )
            return
        folder = self._playlist_import_folder()
        if not folder:
            return
        try:
            if os.path.dirname(os.path.abspath(source)) == os.path.abspath(folder):
                return
        except (OSError, ValueError):
            return
        dest, origin = self._prepare_imported_copy(source, folder)
        if origin:
            try:
                size = os.path.getsize(origin)
            except OSError:
                size = 0
            window, widgets = self._open_copy_progress(1)
            name = os.path.basename(origin)

            def cancelled():
                return bool(widgets["cancel"].get("cancel"))

            def on_progress(copied):
                self._update_copy_progress(window, widgets, 1, name, copied, size)

            try:
                outcome = self._copy_file_with_progress(
                    origin, dest, on_progress, parent=window, should_stop=cancelled,
                )
            finally:
                self._close_copy_progress(window)
            if not outcome:
                return
        entry.path = dest
        entry.filename = os.path.basename(dest)
        entry.missing = False
        if self.preview_index == index and not self.preview_live:
            self.show_preview_clip(entry)
        self.refresh_all()

    def delete_entry(self, index):
        if not 0 <= index < len(self.playlist):
            return
        if self.program_state == "PLAYING" and index == self.program_index:
            return
        del self.playlist[index]
        if self.preview_index == index:
            self.preview_index = None
            self.preview_live = True
            self.preview_mpv.stop()
            self._reset_preview_meter()
        elif self.preview_index is not None and self.preview_index > index:
            self.preview_index -= 1
        if self.program_index > index:
            self.program_index -= 1
        self.program_index = max(0, min(self.program_index, len(self.playlist) - 1))
        self.apply_beamer_mode_for_pointer()
        self.refresh_all()

    def on_row_press(self, index, event):
        self.drag_index = index
        self.drag_y = event.y_root
        self.drag_moved = False

    def on_row_drag(self, event):
        if self.drag_index is None:
            return
        if abs(event.y_root - self.drag_y) >= DRAG_THRESHOLD:
            self.drag_moved = True
        if self.drag_moved:
            self.show_drop_marker(self.drag_index, self._row_index_at(event.y_root))

    def on_row_release(self, event):
        start = self.drag_index
        moved = self.drag_moved
        self.drag_index = None
        self.drag_moved = False
        self.hide_drop_marker()
        if start is None or start >= len(self.playlist):
            return
        if not moved:
            self.on_row_click(start)
            return
        target = self._row_index_at(event.y_root)
        if target is None:
            return
        self.move_row(start, target)

    def _playlist_row_frames(self):
        """Entry rows only. Folder headings sit between them and are not slots."""
        frames = []
        inner = getattr(self, "playlist_inner", None)
        if inner is None:
            return frames
        for child in inner.winfo_children():
            index = getattr(child, "playlist_index", None)
            if isinstance(index, int):
                frames.append(child)
        return frames

    def _row_index_at(self, y_root):
        """Playlist index of the row under the given screen position."""
        rows = self._playlist_row_frames()
        if not rows:
            return None
        for row in rows:
            if y_root < row.winfo_rooty() + row.winfo_height():
                return row.playlist_index
        return rows[-1].playlist_index

    def show_drop_marker(self, start, target):
        """Draw the insert line at the slot the dragged clip would land in."""
        rows = self._playlist_row_frames()
        row = next((item for item in rows if item.playlist_index == target), None)
        if row is None:
            self.hide_drop_marker()
            return
        edge = row.winfo_rooty() + (row.winfo_height() if target > start else 0)
        y = edge - self.playlist_canvas.winfo_rooty()
        height = self.playlist_canvas.winfo_height()
        if self.drop_marker is None:
            self.drop_marker = tk.Frame(self.playlist_canvas, bg=MARKER, height=3)
        self.drop_marker.place(
            x=0, y=min(max(0, y - 1), height - 3), relwidth=1.0, height=3
        )
        self.drop_marker.lift()

    def hide_drop_marker(self):
        if self.drop_marker is not None:
            self.drop_marker.place_forget()

    def move_row(self, start, target):
        target = max(0, min(len(self.playlist) - 1, target))
        if target == start:
            return
        program_entry = self._entry_at(self.program_index)
        preview_entry = self._entry_at(self.preview_index)
        entry = self.playlist.pop(start)
        self.playlist.insert(target, entry)
        if program_entry is not None:
            self.program_index = self._index_of(program_entry)
        if preview_entry is not None:
            self.preview_index = self._index_of(preview_entry)
        self.refresh_playlist()

    def _entry_at(self, index):
        if index is None or not 0 <= index < len(self.playlist):
            return None
        return self.playlist[index]

    def _index_of(self, entry):
        for index, item in enumerate(self.playlist):
            if item is entry:
                return index
        return 0

    def remember_import_dir(self, path):
        directory = path if os.path.isdir(path) else os.path.dirname(path)
        if not directory or not os.path.isdir(directory):
            return
        self.last_import_dir = directory
        self.settings["last_import_dir"] = directory
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _save_media_directories(self):
        self.media_directories = normalize_media_directories(self.media_directories)
        self.settings["media_directories"] = self.media_directories
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self._refresh_playlist_locations()

    def _playlist_location_text(self, entry):
        return playlist_location_label(getattr(entry, "path", ""), self.media_directories)

    def _location_fg(self, fg):
        """Folder line stays readable on a highlighted row and quieter otherwise."""
        if fg == COLOR_TEXT:
            return COLOR_MUTED
        return fg

    def _refresh_playlist_locations(self):
        """Folder headings follow renamed media directories."""
        canvas = getattr(self, "playlist_canvas", None)
        view = None
        if canvas is not None:
            try:
                view = canvas.yview()
            except tk.TclError:
                view = None
        self.refresh_playlist()
        if canvas is not None and view:
            try:
                canvas.yview_moveto(view[0])
            except tk.TclError:
                pass

    def _existing_media_directories(self):
        return [item["path"] for item in self.media_directories if os.path.isdir(item["path"])]

    def _media_directory_index(self, path):
        if not path:
            return -1
        for index, item in enumerate(self.media_directories):
            if item["path"] == path:
                return index
        return -1

    def _media_directory_for_path(self, path):
        if not path:
            return ""
        abs_path = os.path.abspath(path)
        match = ""
        for folder in self._existing_media_directories():
            try:
                if os.path.commonpath([abs_path, folder]) == folder and len(folder) >= len(match):
                    match = folder
            except ValueError:
                continue
        return match

    def _preferred_import_dir(self):
        existing = self._existing_media_directories()
        last = self.last_import_dir
        if last and os.path.isdir(last):
            if self._media_directory_for_path(last) or not existing:
                return last
        if existing:
            return existing[0]
        return last if last and os.path.isdir(last) else ""

    def _stored_import_path(self):
        """Import directory from settings, including the older copy-destination key."""
        raw = self.settings.get("import_path") or self.settings.get("copy_imported_media_dir") or ""
        if not isinstance(raw, str) or not raw.strip():
            return ""
        try:
            return os.path.abspath(os.path.expanduser(raw.strip()))
        except (OSError, ValueError):
            return ""

    def _import_path_ready(self):
        path = getattr(self, "import_path", "") or ""
        return bool(path) and os.path.isdir(path)

    def _ensure_import_path(self):
        """Ask for the import path when none is stored yet."""
        if self._import_path_ready():
            return True
        return bool(self._choose_import_path(self.root))

    def _save_import_path(self):
        self.settings["import_path"] = self.import_path
        self.settings["copy_imported_media_dir"] = self.import_path
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _choose_import_path(self, parent=None):
        options = {"title": t("import_path_choose")}
        if parent is not None:
            options["parent"] = parent
        start = self.import_path if self._import_path_ready() else self._preferred_import_dir()
        if start:
            options["initialdir"] = start
        path = filedialog.askdirectory(**options)
        if not path:
            return False
        self.import_path = os.path.abspath(path)
        self._save_import_path()
        if self._media_dirs_window_alive():
            listbox = getattr(self.media_dirs_window, "_listbox", None)
            if listbox is not None:
                self._refresh_media_directory_list(listbox, select_import=True)
                self._load_media_directory_name_field(listbox)
        if self._playlist_library_alive():
            self._refresh_playlist_library(self.playlist_library_window)
        return True

    def _delete_import_media(self, window):
        row = self._selected_library_playlist(window)
        folder = (row or {}).get("folder") or ""
        if row is None or not folder or row.get("media", 0) <= 0:
            return
        if not messagebox.askyesno(
            t("edit_imports_delete_media_title"),
            t("edit_imports_delete_media_message", name=row["name"]),
            parent=window,
        ):
            return
        delete_import_media(folder)
        self._note_import_folder_changed(folder)
        self._refresh_playlist_library(window, select_path=row["path"])

    def _delete_import_folder(self, window):
        row = self._selected_library_playlist(window)
        folder = (row or {}).get("folder") or ""
        if row is None or not folder:
            return
        if not messagebox.askyesno(
            t("edit_imports_delete_folder_title"),
            t("edit_imports_delete_folder_message", name=row["name"]),
            parent=window,
        ):
            return
        if not delete_import_directory(folder, getattr(self, "import_path", "")):
            messagebox.showerror(
                t("playlist_library"),
                t("edit_imports_delete_failed", error=folder),
                parent=window,
            )
            return
        self._forget_playlist_inside(folder)
        self._note_import_folder_changed(folder)
        self._refresh_playlist_library(window)

    def _forget_playlist_inside(self, directory):
        path = getattr(self, "playlist_path", "") or ""
        if path and path_is_inside(path, directory):
            self.playlist_path = ""
        settings = getattr(self, "settings", None)
        if not isinstance(settings, dict):
            return
        last = settings.get("last_playlist_path") or ""
        if last and path_is_inside(last, directory):
            settings["last_playlist_path"] = ""
            try:
                save_settings(settings)
            except OSError:
                pass

    def _note_import_folder_changed(self, directory):
        playlist = getattr(self, "playlist", None) or []
        if not any(path_is_inside(getattr(entry, "path", ""), directory) for entry in playlist):
            return
        self._scan_playlist_media()
        self.refresh_all()

    def _current_playlist_name(self):
        entry = getattr(self, "playlist_name", None)
        if entry is None:
            return ""
        try:
            return entry.get().strip()
        except tk.TclError:
            return ""

    def _set_playlist_name(self, name):
        entry = getattr(self, "playlist_name", None)
        if entry is None:
            return
        try:
            entry.delete(0, "end")
            entry.insert(0, name)
        except tk.TclError:
            pass

    def _unique_copy_path(self, directory, filename):
        base, ext = os.path.splitext(filename)
        candidate = os.path.join(directory, filename)
        index = 2
        while os.path.exists(candidate):
            candidate = os.path.join(directory, f"{base} ({index}){ext}")
            index += 1
        return candidate

    @staticmethod
    def _format_copy_size(nbytes):
        value = max(0.0, float(nbytes))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{int(nbytes)} B"

    def _prepare_imported_copy(self, path, dest_dir):
        """Return (playlist_path, source_to_copy_or_None)."""
        source = os.path.abspath(path)
        if not os.path.isfile(source):
            return source, None
        if os.path.dirname(source) == dest_dir:
            return source, None
        dest = os.path.join(dest_dir, os.path.basename(source))
        if os.path.exists(dest):
            try:
                if os.path.samefile(source, dest):
                    return dest, None
            except OSError:
                pass
            dest = self._unique_copy_path(dest_dir, os.path.basename(source))
        return dest, source

    def _copy_file_with_progress(self, source, dest, on_progress, parent=None, should_stop=None):
        """Copy one file. ``None`` means the operator cancelled; ``False`` is an error."""
        copied = 0
        try:
            with open(source, "rb") as src, open(dest, "wb") as dst:
                while True:
                    if should_stop and should_stop():
                        raise _CopyCancelled
                    chunk = src.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
                    copied += len(chunk)
                    if on_progress:
                        on_progress(copied)
                    if should_stop and should_stop():
                        raise _CopyCancelled
            shutil.copystat(source, dest)
        except _CopyCancelled:
            try:
                os.remove(dest)
            except OSError:
                pass
            return None
        except OSError as exc:
            try:
                os.remove(dest)
            except OSError:
                pass
            messagebox.showerror(
                t("copy_files"),
                t("copy_files_failed", path=os.path.basename(source), error=exc),
                parent=parent,
            )
            return False
        return True

    def _open_copy_progress(self, total):
        window = tk.Toplevel(self.root)
        window.title(t("copy_files"))
        window.configure(bg=COLOR_BG)
        window.resizable(False, False)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        state = {"cancel": False}

        def request_cancel():
            state["cancel"] = True

        window.protocol("WM_DELETE_WINDOW", request_cancel)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        tk.Button(
            buttons, text=t("copy_files_cancel"), command=request_cancel, font=FONT_UI,
        ).pack(side="right")
        pane = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=(10, 0))
        body = tk.Frame(pane, bg=COLOR_PANEL)
        body.pack(fill="both", expand=True)
        status = tk.Label(
            body, text=t("copy_files_progress", current=0, total=total),
            bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_UI, anchor="w",
        )
        status.pack(fill="x")
        name = tk.Label(
            body, text="", bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
            anchor="w", wraplength=440, justify="left",
        )
        name.pack(fill="x", pady=(4, 8))
        bar = ttk.Progressbar(
            body, orient="horizontal", mode="determinate",
            style="Copy.Horizontal.TProgressbar", maximum=1000,
        )
        bar.pack(fill="x")
        size = tk.Label(
            body, text=t("copy_files_progress_size", done=self._format_copy_size(0), total=self._format_copy_size(0)),
            bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL, anchor="w",
        )
        size.pack(fill="x", pady=(6, 0))

        widgets = {
            "status": status, "name": name, "bar": bar, "size": size,
            "total": total, "cancel": state,
        }
        self._bind_popup_wheel(window, pane)
        self._open_popup(window, 480, 200)
        self._grab_popup(window)
        window.update_idletasks()
        return window, widgets

    def _update_copy_progress(self, window, widgets, current, name, done_bytes, total_bytes):
        widgets["status"].config(
            text=t("copy_files_progress", current=current, total=widgets["total"]),
        )
        widgets["name"].config(text=name)
        maximum = max(1, int(total_bytes) or 1)
        widgets["bar"]["value"] = min(1000, int(1000 * min(done_bytes, total_bytes) / maximum))
        widgets["size"].config(
            text=t(
                "copy_files_progress_size",
                done=self._format_copy_size(done_bytes),
                total=self._format_copy_size(total_bytes),
            ),
        )
        try:
            window.update()
        except tk.TclError:
            pass

    def _close_copy_progress(self, window):
        if window is None:
            return
        try:
            window.grab_release()
        except tk.TclError:
            pass
        try:
            window.destroy()
        except tk.TclError:
            pass

    def _copy_imported_paths(self, paths, dest_dir):
        """Copy ``paths`` into ``dest_dir``.

        The result lines up with ``paths``. A missing destination aborts with
        an empty list. A file that could not be copied is ``None``.
        """
        if not dest_dir or not os.path.isdir(dest_dir):
            messagebox.showerror(t("copy_files"), t("copy_files_missing"))
            return []
        jobs = []
        total_bytes = 0
        for path in paths:
            dest, source = self._prepare_imported_copy(path, dest_dir)
            size = 0
            if source:
                try:
                    size = os.path.getsize(source)
                except OSError:
                    size = 0
                total_bytes += size
            jobs.append((dest, source, size))

        window = None
        widgets = None
        if any(source for _dest, source, _size in jobs):
            window, widgets = self._open_copy_progress(len(jobs))
        results = []
        done_bytes = 0

        def cancelled():
            state = widgets.get("cancel") if widgets else None
            return bool(state and state.get("cancel"))

        try:
            for index, (dest, source, size) in enumerate(jobs, 1):
                if cancelled():
                    results.extend([None] * (len(jobs) - index + 1))
                    break
                name = os.path.basename(source or dest)
                if widgets is not None:
                    self._update_copy_progress(window, widgets, index, name, done_bytes, total_bytes)
                if source:
                    def on_progress(copied, base=done_bytes):
                        if widgets is not None:
                            self._update_copy_progress(
                                window, widgets, index, name, base + copied, total_bytes,
                            )

                    outcome = self._copy_file_with_progress(
                        source, dest, on_progress, parent=window, should_stop=cancelled,
                    )
                    if outcome is None:
                        results.append(None)
                        results.extend([None] * (len(jobs) - index))
                        break
                    if not outcome:
                        results.append(None)
                        continue
                    done_bytes += size
                results.append(dest)
                if widgets is not None:
                    self._update_copy_progress(window, widgets, index, name, done_bytes, total_bytes)
        finally:
            self._close_copy_progress(window)
        return results

    def _media_filetypes(self):
        return [
            (t("media_files"), " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTS | IMAGE_EXTS))),
            (t("all_files"), "*.*"),
        ]

    def _media_paths_in_directory(self, directory):
        try:
            names = os.listdir(directory)
        except OSError:
            return []
        return [
            os.path.join(directory, name)
            for name in sorted(names)
            if os.path.splitext(name)[1].lower() in VIDEO_EXTS | IMAGE_EXTS
        ]

    def _styled_listbox(self, parent):
        return tk.Listbox(
            parent,
            font=FONT_UI,
            bg=COLOR_FIELD,
            fg=COLOR_TEXT,
            selectbackground=COLOR_PROGRAM,
            selectforeground=COLOR_WHITE,
            relief="flat",
            highlightthickness=1,
            highlightbackground=COLOR_BORDER,
            activestyle="none",
            exportselection=False,
        )

    def _remote_port_value(self):
        try:
            port = int(self.remote_api_port.get().strip() or DEFAULT_PORT)
        except (TypeError, ValueError):
            port = DEFAULT_PORT
        return max(1, min(65535, port))

    def _save_remote_api_settings(self):
        self.settings["remote_api_enabled"] = bool(self.remote_api_enabled.get())
        self.settings["remote_api_port"] = self._remote_port_value()
        self.settings["remote_api_token"] = self.remote_api_token.get().strip()
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _start_remote_api(self):
        if not self.remote_api_enabled.get() or not self.remote_api_token.get().strip():
            self._stop_remote_api()
            self._refresh_remote_indicator()
            return
        port = self._remote_port_value()
        token = self.remote_api_token.get().strip()
        if not self.remote_api.start(port=port, token=token):
            print(f"Remote API: {self.remote_api.error}")
        self._refresh_remote_indicator()

    def _stop_remote_api(self):
        if self.remote_api is not None:
            self.remote_api.stop()
        self._refresh_remote_indicator()

    def _apply_remote_api_settings(self):
        token = self.remote_api_token.get().strip()
        if self.remote_api_enabled.get() and not token:
            messagebox.showerror(t("remote_control"), t("remote_control_token_required"))
            self._stop_remote_api()
            self._fill_remote_urls()
            return
        self._save_remote_api_settings()
        self._start_remote_api()
        self._fill_remote_urls()

    def _remote_connect_urls(self):
        if not self.remote_api.running:
            return []
        lang = current_language()
        return self.remote_api.connect_urls(lang) or [
            connect_url("127.0.0.1", self.remote_api.port, self.remote_api.token, lang)
        ]

    def _fill_remote_urls(self):
        widget = getattr(self, "remote_url_box", None)
        if widget is None:
            return
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        urls = self._remote_connect_urls()
        if urls:
            widget.insert("end", "\n".join(urls))
        elif self.remote_api.error:
            widget.insert("end", self.remote_api.error)
        elif self.remote_api_enabled.get() and not self.remote_api_token.get().strip():
            widget.insert("end", t("remote_control_token_required"))
        else:
            widget.insert("end", t("remote_control_off"))
        widget.configure(state="disabled")
        self._draw_remote_qr()

    def _draw_remote_qr(self):
        canvas = getattr(self, "remote_qr_canvas", None)
        if canvas is None:
            return
        canvas.delete("all")
        urls = self._remote_connect_urls()
        if urls and qr_code.draw_on_canvas(canvas, urls[0], size=196):
            return
        canvas.configure(width=196, height=196, bg=COLOR_FIELD, highlightthickness=0)
        canvas.create_text(
            98, 98,
            text=t("remote_control_qr_off"),
            fill=COLOR_MUTED,
            font=FONT_SMALL,
            width=180,
            justify="center",
        )

    def show_remote_control(self):
        window = getattr(self, "remote_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.deiconify()
                    self._present_popup(window)
                    self._fill_remote_urls()
                    self._refresh_header_indicators()
                    return
            except tk.TclError:
                self.remote_window = None
        window = tk.Toplevel(self.root)
        window.title(t("remote_control"))
        window.configure(bg=COLOR_BG)
        window.minsize(560, 380)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_remote_window)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        self._place_window_indicator(window, "remote")
        body = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=(10, 0))
        tk.Label(
            body, text=t("remote_control_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=620, justify="left",
        ).pack(fill="x", pady=(0, 6))
        holder = tk.Frame(body, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, pady=(0, 10))
        port_row = tk.Frame(holder, bg=COLOR_PANEL)
        port_row.pack(fill="x", padx=8, pady=4)
        tk.Label(port_row, text=t("remote_control_port"), bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_UI).pack(side="left")
        tk.Entry(port_row, textvariable=self.remote_api_port, width=8, font=FONT_UI).pack(side="left", padx=(8, 0))
        token_row = tk.Frame(holder, bg=COLOR_PANEL)
        token_row.pack(fill="x", padx=8, pady=4)
        tk.Label(token_row, text=t("remote_control_token"), bg=COLOR_PANEL, fg=COLOR_TEXT, font=FONT_UI).pack(side="left")
        tk.Entry(token_row, textvariable=self.remote_api_token, font=FONT_UI, show="•").pack(
            side="left", fill="x", expand=True, padx=(8, 0),
        )
        pair = tk.Frame(holder, bg=COLOR_PANEL)
        pair.pack(fill="both", expand=True, padx=8, pady=(8, 8))
        qr_col = tk.Frame(pair, bg=COLOR_PANEL)
        qr_col.pack(side="left", anchor="n", padx=(0, 12))
        tk.Label(
            qr_col, text=t("remote_control_qr"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(anchor="w", pady=(0, 4))
        self.remote_qr_canvas = tk.Canvas(
            qr_col, width=196, height=196, bg="white", highlightthickness=0,
        )
        self.remote_qr_canvas.pack()
        urls_col = tk.Frame(pair, bg=COLOR_PANEL)
        urls_col.pack(side="left", fill="both", expand=True)
        tk.Label(
            urls_col, text=t("remote_control_urls"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(anchor="w", pady=(0, 4))
        urls = tk.Text(
            urls_col, height=8, font=FONT_SMALL, bg=COLOR_FIELD, fg=COLOR_TEXT,
            relief="flat", wrap="word",
        )
        urls.pack(fill="both", expand=True)
        self.remote_url_box = urls
        tk.Button(
            buttons, text=t("remote_control_close"), command=self._close_remote_window, font=FONT_UI,
        ).pack(side="right")
        tk.Button(
            buttons, text=t("remote_control_apply"), command=self._apply_remote_api_settings, font=FONT_UI,
        ).pack(side="right", padx=(0, 8))
        self.remote_window = window
        self._fill_remote_urls()
        self._bind_popup_wheel(window, body)
        self._open_popup(window, 640, 520)

    def _close_remote_window(self):
        window = getattr(self, "remote_window", None)
        self.remote_window = None
        self.remote_window_indicator = None
        self.remote_url_box = None
        self.remote_qr_canvas = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _default_scene_name(self, scene):
        if scene is None:
            return ""
        if scene.id == dmx.SCENE_DARK:
            return t("light_dark")
        if scene.id == dmx.SCENE_BRIGHT:
            return t("light_bright")
        if scene.id == "medium":
            return t("light_medium")
        return ""

    def _scene_label(self, scene):
        if scene is None:
            return ""
        if scene.name:
            return scene.name
        return self._default_scene_name(scene) or scene.id

    def _scene_badge(self, scene):
        label = self._scene_label(scene).upper()
        if len(label) > 12:
            return label[:11] + "…"
        return label

    def _cue_label(self, item):
        if isinstance(item, dmx.SceneSequence):
            name = (item.name or "").strip() or t("sequence_new")
            return f"{name} · {t('lights_sequence_mark')}"
        return self._scene_label(item)

    def _scene_choices(self, scenes=None):
        catalog = list(self.lights_scenes if scenes is None else scenes or [])
        if scenes is None:
            catalog.extend(getattr(self, "lights_sequences", None) or [])
        used = set()
        choices = []
        for scene in catalog:
            label = self._cue_label(scene)
            unique = label
            number = 2
            while unique.casefold() in used:
                unique = f"{label} {number}"
                number += 1
            used.add(unique.casefold())
            choices.append((scene, unique))
        return choices

    def _fresh_scene_name(self, scenes):
        base = t("scene_new")
        used = {self._scene_label(scene).casefold() for scene in scenes}
        if base.casefold() not in used:
            return base
        number = 2
        while f"{base} {number}".casefold() in used:
            number += 1
        return f"{base} {number}"

    def _fill_light_buttons(self, parent, group, command, face="plain"):
        if parent is None:
            return
        try:
            if not parent.winfo_exists():
                return
            for child in list(parent.winfo_children()):
                child.destroy()
        except tk.TclError:
            return
        group.clear()
        for index, (scene, label) in enumerate(self._scene_choices()):
            options = {
                "text": label,
                "font": FONT_SMALL,
                "command": lambda scene_id=scene.id: command(scene_id),
            }
            if face == "booth":
                options.update(
                    font=FONT_UI_BOLD,
                    relief="flat",
                    overrelief="flat",
                    bd=0,
                    padx=14,
                    pady=8,
                    highlightthickness=2,
                    cursor="hand2",
                )
            button = tk.Button(parent, **options)
            button._light_face = face
            button.pack(side="left", padx=(0 if index == 0 else 8, 0))
            group[scene.id] = button

    def _rebuild_light_buttons(self):
        self._fill_light_buttons(
            getattr(self, "program_light_scenes", None),
            self.program_light_buttons,
            self._on_light_preset,
            face="booth",
        )
        self._fill_light_buttons(
            getattr(self, "settings_light_bar", None),
            self.settings_light_buttons,
            self._test_lights,
        )
        self._fill_light_combos()
        self._build_light_meters()
        bar = getattr(self, "settings_light_bar", None)
        if bar is not None and getattr(self, "_lights_body", None) is not None:
            self._bind_lights_scroll(bar)
            self._fit_lights_body()
        if getattr(self, "light_start_var", None) is not None:
            entry = self.selected_entry() if self.playlist else None
            self._set_play_light_combo(entry.light_start if entry else "")
        self._refresh_light_buttons()

    def _configure_light_combo_style(self, widget):
        style = ttk.Style(widget)
        style.configure(
            "BoothLight.TCombobox",
            fieldbackground=LIGHT_BUTTON,
            background=LIGHT_BUTTON,
            foreground=LIGHT_BUTTON_TEXT,
            arrowcolor=LIGHT_CAPTION,
            bordercolor=LIGHT_BORDER,
            lightcolor=LIGHT_BORDER,
            darkcolor=LIGHT_BORDER,
            selectbackground=LIGHT_BUTTON,
            selectforeground=LIGHT_BUTTON_TEXT,
        )
        style.map(
            "BoothLight.TCombobox",
            fieldbackground=[("readonly", LIGHT_BUTTON), ("disabled", LIGHT_PANEL)],
            foreground=[("readonly", LIGHT_BUTTON_TEXT), ("disabled", "#8a7a66")],
            background=[("readonly", LIGHT_BUTTON), ("active", LIGHT_ACTIVE)],
            arrowcolor=[("disabled", "#8a7a66")],
            selectbackground=[("readonly", LIGHT_BUTTON)],
            selectforeground=[("readonly", LIGHT_BUTTON_TEXT)],
        )

    def _paint_light_combo_popup(self, combo):
        """Colour the open list the same warm brown and gold as the scene buttons."""
        try:
            popdown = combo.tk.call("ttk::combobox::PopdownWindow", str(combo))
            combo.tk.call(
                f"{popdown}.f.l", "configure",
                "-background", LIGHT_PANEL,
                "-foreground", LIGHT_BUTTON_TEXT,
                "-selectbackground", LIGHT_ACTIVE,
                "-selectforeground", LIGHT_ACTIVE_TEXT,
                "-relief", "flat",
                "-highlightthickness", 0,
                "-borderwidth", 0,
            )
        except tk.TclError:
            pass

    def _place_light_dimmer(self, image=None):
        """Keep the clip dimmer on screen for a video and for a still."""
        dimmer = getattr(self, "program_light_dimmer", None)
        if dimmer is None:
            return
        if image is None:
            entry = None
            if getattr(self, "playlist", None):
                entry = self.selected_entry()
            image = bool(entry and getattr(entry, "is_image", False))
        visible = bool(self.lights_control.get()) if getattr(self, "lights_control", None) else False
        target = None
        if image and getattr(self, "preview_image_settings", None) is not None:
            target = self.preview_image_settings
        elif getattr(self, "preview_track_settings", None) is not None:
            target = self.preview_track_settings
        try:
            dimmer.pack_forget()
            if not visible:
                return
            options = {"side": "left", "padx": (12, 0)}
            if target is not None:
                options["in_"] = target
            dimmer.pack(**options)
        except tk.TclError:
            pass

    def _build_light_dimmer(self, parent):
        """Clip dimmer, shown with the subtitle track and again for a still."""
        host = getattr(self, "preview_column", None) or parent
        dimmer = tk.Frame(host, bg=COLOR_PANEL)
        self.program_light_dimmer = dimmer
        tk.Label(
            dimmer, text=t("light_play"), bg=COLOR_PANEL, fg=LIGHT_CAPTION, font=FONT_SMALL,
        ).pack(side="left", padx=(0, 4))
        self._configure_light_combo_style(parent)
        self.light_start_combo = ttk.Combobox(
            dimmer, textvariable=self.light_start_var, width=18, state="readonly",
            style="BoothLight.TCombobox",
        )
        self.light_start_combo.pack(side="left")
        self.light_start_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_entry_settings())
        self._paint_light_combo_popup(self.light_start_combo)
        self._fill_light_combos()
        self._set_play_light_combo("")
        self._place_light_dimmer(False)

    def _fill_light_combos(self):
        start = getattr(self, "light_start_combo", None)
        if start is None:
            return
        try:
            start["values"] = [label for _scene, label in self._scene_choices()]
        except tk.TclError:
            self.light_start_combo = None

    def _set_play_light_combo(self, key):
        cue = dmx.find_cue(key, self.lights_scenes, getattr(self, "lights_sequences", None)) if key else None
        if cue is None:
            cue = dmx.find_scene(self.lights_scenes, dmx.SCENE_DARK)
        label = ""
        if cue is not None:
            for item, text in self._scene_choices():
                if item.id == cue.id:
                    label = text
                    break
        self.light_start_var.set(label)

    def _play_light_from_label(self, label):
        for cue, text in self._scene_choices():
            if text == label:
                return cue.id
        found = dmx.find_cue(label, self.lights_scenes, getattr(self, "lights_sequences", None))
        return found.id if found is not None else dmx.SCENE_DARK

    def _cue_fade_ms(self, scene):
        if scene is not None and scene.fade_ms is not None:
            return max(0, int(scene.fade_ms))
        return getattr(self, "lights_transition_ms", None) or dmx.DEFAULT_TRANSITION_MS

    def _apply_lights(self, preset, force=False):
        if self.calibration_mode:
            return
        if not bool(self.lights_control.get()):
            return
        cue = dmx.find_cue(preset, self.lights_scenes, getattr(self, "lights_sequences", None))
        if cue is None:
            return
        if isinstance(cue, dmx.SceneSequence):
            steps = dmx.sequence_steps(cue, self.lights_scenes)
            if not steps:
                return
            if not force and self.lights_current == cue.id and getattr(self, "_sequence_run", None):
                return
            self._sequence_run = {"id": cue.id, "index": 0}
            self.lights_current = cue.id
            self._fade_to_scene(steps[0])
            return
        self._sequence_run = None
        if not force and dmx.already_at_preset(self.lights_current, cue.id, self.lights_scenes):
            return
        self.lights_current = cue.id
        self._fade_to_scene(cue)

    def _fade_to_scene(self, scene):
        """Dim toward one scene, using that scene's own fade time."""
        start_levels = self._displayed_light_levels()
        target_levels = self._scene_levels(scene.id)
        transition = self._cue_fade_ms(scene)
        output = getattr(self, "dmx_output", None)
        scenes = [item.copy() for item in self.lights_scenes]

        def worker():
            error = dmx.apply_scene(output, scene.id, scenes, transition)
            with self._light_error_lock:
                self._light_errors.append(error)

        if output is None or not output.ready() or transition <= 0:
            self.lights_shown_levels = target_levels
            self._light_meter_fade = None
            self._stop_light_fade()
            self._refresh_light_buttons()
            if output is not None and output.ready():
                threading.Thread(target=worker, daemon=True).start()
                self._advance_sequence()
            return
        self._arm_light_meter_fade(start_levels, target_levels, transition)
        self._start_light_fade(transition)
        if self._light_meter_fade:
            self._schedule_light_meters()
        threading.Thread(target=worker, daemon=True).start()

    def _advance_sequence(self):
        """Start the next scene of a running sequence after its fade."""
        run = getattr(self, "_sequence_run", None)
        if not run:
            return False
        sequence = dmx.find_sequence(getattr(self, "lights_sequences", None), run.get("id"))
        steps = dmx.sequence_steps(sequence, self.lights_scenes) if sequence is not None else []
        nxt = int(run.get("index", 0)) + 1
        if sequence is None or nxt >= len(steps):
            self._sequence_run = None
            return False
        run["index"] = nxt
        self.lights_current = sequence.id
        self._fade_to_scene(steps[nxt])
        return True

    def _show_lights_error(self, error):
        """Report a DMX problem (missing Enttec cable, closed port) in the light window."""
        status = getattr(self, "lights_status", None)
        if status is None or getattr(self, "lights_window", None) is None:
            return
        try:
            status.set(str(error or ""))
        except tk.TclError:
            pass

    def _on_light_preset(self, preset):
        self._apply_lights(preset, force=True)

    def _dmx_ready(self):
        output = getattr(self, "dmx_output", None)
        return bool(output is not None and output.ready())

    def _sync_lights_control(self, save=True):
        ready = self._dmx_ready()
        if not ready:
            if getattr(self, "lights_control", None) is not None:
                self.lights_control.set(False)
            self._stop_light_fade()
        state = "normal" if ready else "disabled"
        box = getattr(self, "settings_lights_check", None)
        if box is not None:
            try:
                box.config(state=state)
            except tk.TclError:
                self.settings_lights_check = None
        if save:
            self._save_lights_settings()
        self._refresh_light_buttons()
        self._refresh_lights_indicator()
        self._apply_program_light_block()

    def _on_lights_control(self):
        if bool(self.lights_control.get()) and not self._dmx_ready():
            self.lights_control.set(False)
        if not bool(self.lights_control.get()):
            self._stop_light_fade()
        self._save_lights_settings()
        self._refresh_light_buttons()
        self._refresh_lights_indicator()
        self._apply_program_light_block()

    def _apply_program_light_block(self):
        """Hide the program light buttons and dimmer while light control is off."""
        visible = bool(self.lights_control.get()) if getattr(self, "lights_control", None) else False
        status = getattr(self, "show_status", None)
        bar = getattr(self, "program_light_bar", None)
        try:
            if bar is not None:
                if visible and not bar.winfo_manager():
                    options = {"side": "left"}
                    if status is not None:
                        options["before"] = status
                    bar.pack(**options)
                elif not visible:
                    bar.pack_forget()
        except tk.TclError:
            pass
        self._place_light_dimmer()
        self._sync_show_strip()

    def _sync_show_strip(self):
        """Drop the show strip when neither lights nor a status note need it."""
        strip = getattr(self, "show_strip", None)
        if strip is None:
            return
        lights = bool(self.lights_control.get()) if getattr(self, "lights_control", None) else False

        def shown(widget):
            try:
                return widget is not None and bool(widget.winfo_manager())
            except tk.TclError:
                return False

        visible = lights or shown(getattr(self, "settings_warning_status", None))
        try:
            if visible:
                if not strip.winfo_manager():
                    strip.grid(row=1, column=0, sticky="ew", pady=(0, 6))
            else:
                strip.grid_remove()
        except tk.TclError:
            pass

    def _cancel_light_after(self, name):
        handle = getattr(self, name, None)
        setattr(self, name, None)
        if handle:
            try:
                self.root.after_cancel(handle)
            except tk.TclError:
                pass

    def _start_light_fade(self, transition_ms):
        self._cancel_light_after("lights_fade_after")
        self._cancel_light_after("lights_blink_after")
        self.lights_fading = True
        self.lights_blink_on = True
        self._refresh_light_buttons()
        try:
            duration = max(0, int(transition_ms))
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0:
            duration = 400
        self.lights_fade_after = self.root.after(duration, self._finish_light_fade)
        self.lights_blink_after = self.root.after(350, self._blink_light_buttons)

    def _blink_light_buttons(self):
        self.lights_blink_after = None
        if not self.lights_fading:
            return
        self.lights_blink_on = not self.lights_blink_on
        self._refresh_light_buttons()
        try:
            self.lights_blink_after = self.root.after(350, self._blink_light_buttons)
        except tk.TclError:
            self.lights_blink_after = None

    def _finish_light_fade(self):
        self.lights_fade_after = None
        fade = getattr(self, "_light_meter_fade", None)
        if fade:
            self.lights_shown_levels = {
                channel: dmx.clamp_percent(level) for channel, level in fade["target"].items()
            }
            self._light_meter_fade = None
        self._stop_light_fade()
        if self._advance_sequence():
            return
        self._refresh_light_buttons()

    def _stop_light_fade(self):
        if self.lights_fading and getattr(self, "_light_meter_fade", None):
            self.lights_shown_levels = {
                channel: dmx.clamp_percent(level)
                for channel, level in self._displayed_light_levels().items()
            }
        self._cancel_light_after("lights_fade_after")
        self._cancel_light_after("lights_blink_after")
        self._cancel_light_after("lights_meter_after")
        self.lights_fading = False
        self.lights_blink_on = False
        self._light_meter_fade = None

    def _refresh_light_buttons(self):
        enabled = bool(self.lights_control.get()) if getattr(self, "lights_control", None) else False
        current = dmx.cue_key(
            getattr(self, "lights_current", ""),
            self.lights_scenes,
            getattr(self, "lights_sequences", None),
        ) if enabled else ""
        fading = bool(enabled and current and getattr(self, "lights_fading", False))
        blink_on = bool(getattr(self, "lights_blink_on", False))
        for key, button in self._iter_light_buttons():
            active = enabled and key == current
            lit = active and (not fading or blink_on)
            booth = getattr(button, "_light_face", "") == "booth"
            if booth:
                bg = LIGHT_ACTIVE if lit else LIGHT_BUTTON
                fg = LIGHT_ACTIVE_TEXT if lit else LIGHT_BUTTON_TEXT
                ring = COLOR_WHITE if active else bg
                disabled = "#8a7a66"
            else:
                bg = ACCENT if lit else COLOR_BUTTON
                fg = COLOR_WHITE if lit else COLOR_TEXT
                ring = bg
                disabled = COLOR_MUTED
            style = (
                "normal" if enabled else "disabled",
                bg,
                fg,
                ring,
            )
            if getattr(button, "_light_style", None) == style:
                continue
            button._light_style = style
            try:
                button.config(
                    state=style[0],
                    bg=bg,
                    fg=fg,
                    activebackground=bg,
                    activeforeground=fg,
                    disabledforeground=disabled,
                    highlightbackground=ring,
                    highlightcolor=COLOR_WHITE,
                )
            except tk.TclError:
                button._light_style = None
        self._paint_light_meters()

    def _house_channels(self):
        output = getattr(self, "dmx_output", None)
        return dmx.parse_channels(getattr(output, "channels", None) or []) or [1]

    def _scene_levels(self, scene_id):
        channels = self._house_channels()
        scene = dmx.find_scene(getattr(self, "lights_scenes", None), scene_id) if scene_id else None
        return {
            channel: dmx.clamp_percent(scene.levels.get(channel, 0) if scene else 0)
            for channel in channels
        }

    def _displayed_light_levels(self):
        """Levels on the program meters, including a fade that is still running."""
        channels = self._house_channels()
        fade = getattr(self, "_light_meter_fade", None) if getattr(self, "lights_fading", False) else None
        if fade:
            now = time.monotonic()
            return {
                channel: dmx.mixed_level(
                    fade["start"].get(channel, 0),
                    fade["target"].get(channel, 0),
                    fade["started"],
                    now,
                    fade["ms"],
                )
                for channel in channels
            }
        shown = getattr(self, "lights_shown_levels", None) or {}
        if shown:
            return {channel: dmx.clamp_percent(shown.get(channel, 0)) for channel in channels}
        return self._scene_levels(getattr(self, "lights_current", ""))

    def _build_light_meters(self):
        """Narrow channel bars beside the program light buttons."""
        parent = getattr(self, "program_light_meters", None)
        if parent is None:
            return
        try:
            if not parent.winfo_exists():
                return
            for child in list(parent.winfo_children()):
                child.destroy()
        except tk.TclError:
            return
        self.program_light_meter_bars = {}
        for index, channel in enumerate(self._house_channels()):
            column = tk.Frame(parent, bg=LIGHT_PANEL)
            column.pack(side="left", padx=(8 if index else 0, 0))
            bar = tk.Canvas(
                column, width=10, height=28, bg=LIGHT_PANEL, highlightthickness=0, bd=0,
            )
            bar.pack(side="left")
            tk.Label(
                column, text=str(channel), bg=LIGHT_PANEL, fg=LIGHT_CAPTION, font=FONT_SMALL,
            ).pack(side="left", padx=(2, 0))
            self.program_light_meter_bars[channel] = bar
        self._paint_light_meters()

    def _paint_light_meters(self):
        bars = getattr(self, "program_light_meter_bars", None) or {}
        if not bars:
            return
        levels = self._displayed_light_levels()
        for channel, canvas in bars.items():
            self._draw_light_meter(canvas, levels.get(channel, 0))

    def _draw_light_meter(self, canvas, percent):
        try:
            if not canvas.winfo_exists():
                return
            value = max(0.0, min(100.0, float(percent)))
            shown = getattr(canvas, "_meter_percent", None)
            if shown is not None and abs(shown - value) < 0.5:
                return
            width = canvas.winfo_width()
            height = canvas.winfo_height()
            if width <= 1:
                width = int(canvas.cget("width"))
            if height <= 1:
                height = int(canvas.cget("height"))
            canvas.delete("all")
            canvas.create_rectangle(
                0, 0, width - 1, height - 1, outline=LIGHT_BORDER, fill=LIGHT_BUTTON,
            )
            fill = light_meter_fill(height, value)
            if fill:
                canvas.create_rectangle(
                    1, height - 1 - fill, width - 2, height - 2,
                    outline="", fill=LIGHT_ACTIVE,
                )
            canvas._meter_percent = value
        except tk.TclError:
            pass

    def _arm_light_meter_fade(self, start, target, transition_ms):
        self._cancel_light_after("lights_meter_after")
        try:
            duration = max(0, int(transition_ms))
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0:
            self._light_meter_fade = None
            self.lights_shown_levels = {
                channel: dmx.clamp_percent(level) for channel, level in target.items()
            }
            return
        self._light_meter_fade = {
            "start": {int(channel): float(level) for channel, level in start.items()},
            "target": {int(channel): float(level) for channel, level in target.items()},
            "started": time.monotonic(),
            "ms": duration,
        }

    def _schedule_light_meters(self):
        self._paint_light_meters()
        if not getattr(self, "lights_fading", False) or not getattr(self, "_light_meter_fade", None):
            return
        try:
            self.lights_meter_after = self.root.after(40, self._schedule_light_meters)
        except tk.TclError:
            self.lights_meter_after = None

    def _iter_light_buttons(self):
        for group in (
            getattr(self, "program_light_buttons", None),
            getattr(self, "settings_light_buttons", None),
        ):
            if not group:
                continue
            for key, button in group.items():
                yield key, button

    def _save_lights_settings(self):
        enabled = bool(self.lights_control.get()) if getattr(self, "lights_control", None) else True
        self.settings["lights"] = dmx.dump_lights_config(
            getattr(self, "dmx_output", None) or dmx.DmxOutput(),
            self.lights_scenes,
            self.lights_transition_ms,
            enabled,
            self.lights_start_lead_ms,
            self.lights_end_lead_ms,
            getattr(self, "lights_sequences", None),
        )
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _build_scene_editor(self, parent):
        """Name a scene or sequence, and set each scene's fade and channel levels."""
        self._scene_draft = [scene.copy() for scene in self.lights_scenes]
        self._sequence_draft = [
            sequence.copy() for sequence in (getattr(self, "lights_sequences", None) or [])
        ]
        self._scene_edit_id = self._scene_draft[0].id if self._scene_draft else ""
        self._scene_level_vars = {}
        self._scene_fade_var = None
        editor = tk.Frame(parent, bg=COLOR_PANEL)
        editor.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        left = tk.Frame(editor, bg=COLOR_PANEL)
        left.pack(side="left", fill="y")
        tk.Label(left, text=t("lights_scenes"), bg=COLOR_PANEL, font=FONT_SMALL).pack(anchor="w")
        self._scene_listbox = self._styled_listbox(left)
        self._scene_listbox.configure(height=6, width=24)
        self._scene_listbox.pack(fill="y", expand=True, pady=(2, 4))
        self._scene_listbox.bind("<<ListboxSelect>>", self._on_scene_select)
        actions = tk.Frame(left, bg=COLOR_PANEL)
        actions.pack(fill="x")
        tk.Button(
            actions, text=t("lights_scene_add"), font=FONT_SMALL, command=self._add_edited_scene,
        ).pack(side="left")
        tk.Button(
            actions, text=t("lights_sequence_add"), font=FONT_SMALL, command=self._add_edited_sequence,
        ).pack(side="left", padx=(8, 0))
        self._scene_delete_button = tk.Button(
            actions, text=t("lights_scene_delete"), font=FONT_SMALL, command=self._delete_edited_scene,
        )
        self._scene_delete_button.pack(side="left", padx=(8, 0))
        right = tk.Frame(editor, bg=COLOR_PANEL)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))
        name_row = tk.Frame(right, bg=COLOR_PANEL)
        name_row.pack(fill="x")
        tk.Label(name_row, text=t("lights_scene_name"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        self._scene_name_var = tk.StringVar(value="")
        name_entry = tk.Entry(name_row, textvariable=self._scene_name_var, width=22, font=FONT_UI)
        name_entry.pack(side="left", padx=(4, 0))
        name_entry.bind("<FocusOut>", self._on_scene_name_changed)
        name_entry.bind("<Return>", self._on_scene_name_changed)
        self._scene_levels_frame = tk.Frame(right, bg=COLOR_PANEL)
        self._scene_levels_frame.pack(fill="x", pady=(6, 0))
        tk.Label(
            right, text=t("lights_scene_hint"), bg=COLOR_PANEL, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=360, justify="left",
        ).pack(fill="x", pady=(6, 0))
        self._refresh_scene_editor()

    def _draft_channels(self):
        text = self.lights_channels.get() if getattr(self, "lights_channels", None) else ""
        return dmx.parse_channels(text) or [1]

    def _default_fade_ms(self):
        variable = getattr(self, "lights_transition", None)
        fallback = getattr(self, "lights_transition_ms", None) or dmx.DEFAULT_TRANSITION_MS
        if variable is not None:
            try:
                text = str(variable.get()).strip()
            except tk.TclError:
                text = ""
            if text:
                return dmx.seconds_to_ms(text, fallback)
        return fallback

    def _draft_cues(self):
        return list(self._scene_draft or []) + list(getattr(self, "_sequence_draft", None) or [])

    def _find_draft_cue(self, cue_id):
        return (
            dmx.find_scene(self._scene_draft, cue_id)
            or dmx.find_sequence(getattr(self, "_sequence_draft", None), cue_id)
        )

    def _flush_scene_form(self):
        if not self._scene_draft or not self._scene_edit_id or self._scene_name_var is None:
            return
        cue = self._find_draft_cue(self._scene_edit_id)
        if cue is None:
            return
        name = self._scene_name_var.get().strip()
        if isinstance(cue, dmx.SceneSequence):
            cue.name = name[:dmx.SCENE_NAME_LIMIT]
            return
        default = self._default_scene_name(cue)
        if default and (not name or name == default):
            cue.name = ""
        elif name:
            cue.name = name[:dmx.SCENE_NAME_LIMIT]
        fade_var = getattr(self, "_scene_fade_var", None)
        if fade_var is not None:
            try:
                cue.fade_ms = dmx.seconds_to_ms(fade_var.get(), cue.fade_ms or self._default_fade_ms())
            except tk.TclError:
                pass
        channels = self._draft_channels()
        for channel, variable in list(self._scene_level_vars.items()):
            if channel not in channels:
                continue
            cue.levels[channel] = dmx.clamp_percent(variable.get(), cue.levels.get(channel, 0))
        self._scene_draft = dmx.align_scenes(self._scene_draft, channels, self._default_fade_ms())

    def _refresh_scene_editor(self):
        if self._scene_listbox is None:
            return
        if not self._scene_draft:
            return
        if self._find_draft_cue(self._scene_edit_id) is None:
            self._scene_edit_id = self._scene_draft[0].id
        self._refresh_scene_list_labels()
        self._load_scene_form(self._scene_edit_id)

    def _refresh_scene_list_labels(self):
        box = self._scene_listbox
        if box is None:
            return
        self._scene_guard = True
        try:
            cues = self._draft_cues()
            selected = 0
            for index, cue in enumerate(cues):
                if cue.id == self._scene_edit_id:
                    selected = index
            box.delete(0, "end")
            for cue in cues:
                box.insert("end", self._cue_label(cue))
            if cues:
                box.selection_set(selected)
                box.activate(selected)
                box.see(selected)
        except tk.TclError:
            self._scene_listbox = None
        finally:
            self._scene_guard = False

    def _load_scene_form(self, scene_id):
        cue = self._find_draft_cue(scene_id)
        if cue is None and self._scene_draft:
            cue = self._scene_draft[0]
        if cue is None or self._scene_levels_frame is None:
            return
        self._scene_edit_id = cue.id
        self._scene_guard = True
        try:
            if isinstance(cue, dmx.SceneSequence):
                self._scene_name_var.set(cue.name or t("sequence_new"))
                self._build_sequence_editor(cue)
            else:
                self._scene_name_var.set(self._scene_label(cue))
                self._build_scene_faders(cue)
            if self._scene_delete_button is not None:
                state = "disabled" if dmx.scene_locked(cue.id) else "normal"
                self._scene_delete_button.config(state=state)
        except tk.TclError:
            self._scene_levels_frame = None
        finally:
            self._scene_guard = False
        frame = getattr(self, "_scene_levels_frame", None)
        if frame is not None and getattr(self, "_lights_body", None) is not None:
            self._bind_lights_scroll(frame)
            self._fit_lights_body()

    def _build_scene_faders(self, scene):
        for child in list(self._scene_levels_frame.winfo_children()):
            child.destroy()
        self._scene_level_vars = {}
        fade = scene.fade_ms if scene.fade_ms is not None else self._default_fade_ms()
        fade_row = tk.Frame(self._scene_levels_frame, bg=COLOR_PANEL)
        fade_row.pack(anchor="w", pady=(0, 6))
        tk.Label(
            fade_row, text=t("lights_scene_fade"), bg=COLOR_PANEL, font=FONT_SMALL,
        ).pack(side="left")
        self._scene_fade_var = tk.StringVar(value=dmx.ms_to_seconds_text(fade))
        fade_entry = tk.Entry(
            fade_row, textvariable=self._scene_fade_var, width=6, font=FONT_UI,
        )
        fade_entry.pack(side="left", padx=(4, 0))
        fade_entry.bind("<FocusOut>", self._on_scene_name_changed)
        fade_entry.bind("<Return>", self._on_scene_name_changed)
        tk.Label(
            fade_row, text=t("seconds_short"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(side="left", padx=(4, 0))
        scroller = tk.Frame(self._scene_levels_frame, bg=COLOR_PANEL)
        scroller.pack(fill="x")
        canvas = tk.Canvas(scroller, bg=COLOR_PANEL, highlightthickness=0, height=180, bd=0)
        bar = ttk.Scrollbar(scroller, orient="horizontal", command=canvas.xview)
        canvas.configure(xscrollcommand=lambda first, last, canvas=canvas, bar=bar: self._track_fader_scroll(canvas, bar, first, last))
        desk = tk.Frame(canvas, bg=COLOR_PANEL)
        canvas.create_window((0, 0), window=desk, anchor="nw")
        canvas.pack(fill="x")
        self._fader_canvas = canvas
        self._fader_desk = desk
        self._fader_scroll = bar
        desk.bind("<Configure>", lambda _event, canvas=canvas, desk=desk: self._fit_fader_canvas(canvas, desk))
        canvas.bind("<Configure>", lambda _event, canvas=canvas, desk=desk: self._fit_fader_canvas(canvas, desk))
        for index, channel in enumerate(self._draft_channels()):
            value = dmx.clamp_percent(scene.levels.get(channel, 0))
            column = tk.Frame(desk, bg=COLOR_PANEL)
            column.pack(side="left", padx=(0 if index == 0 else 12, 0))
            percent = tk.Label(
                column, text=f"{value} %", bg=COLOR_PANEL, fg=COLOR_TEXT,
                font=FONT_SMALL, width=6, anchor="center",
            )
            percent.pack()
            variable = tk.IntVar(value=value)
            self._scene_level_vars[channel] = variable

            def on_move(raw, label=percent):
                label.config(text=f"{dmx.clamp_percent(raw)} %")

            tk.Scale(
                column,
                from_=100,
                to=0,
                orient="vertical",
                variable=variable,
                showvalue=False,
                resolution=1,
                length=140,
                width=18,
                sliderlength=16,
                command=on_move,
                bg=COLOR_PANEL,
                fg=COLOR_TEXT,
                troughcolor=COLOR_FIELD,
                activebackground=COLOR_PANEL,
                highlightthickness=0,
                bd=0,
            ).pack()
            tk.Label(
                column, text=str(channel), bg=COLOR_PANEL, fg=COLOR_MUTED,
                font=FONT_SMALL, anchor="center",
            ).pack()
        self._fit_fader_canvas(canvas, desk)

    def _track_fader_scroll(self, canvas, bar, first, last):
        try:
            bar.set(first, last)
        except tk.TclError:
            return
        self._show_fader_scroll(canvas, bar)

    def _fit_fader_canvas(self, canvas, desk):
        """Keep the fader row as tall as the sliders and scroll sideways when they do not fit."""
        try:
            if not canvas.winfo_exists():
                return
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            if not bbox:
                return
            canvas.configure(scrollregion=bbox, height=max(1, bbox[3] - bbox[1]))
            self._show_fader_scroll(canvas, getattr(self, "_fader_scroll", None), desk)
        except tk.TclError:
            pass

    def _show_fader_scroll(self, canvas, bar, desk=None):
        desk = desk or getattr(self, "_fader_desk", None)
        if bar is None or desk is None:
            return
        try:
            if not canvas.winfo_exists() or not bar.winfo_exists():
                return
            view = canvas.winfo_width()
            if view <= 1:
                return
            needed = desk.winfo_reqwidth() > view + 1
            shown = bool(bar.winfo_manager())
            if needed and not shown:
                bar.pack(fill="x", side="bottom")
            elif not needed and shown:
                bar.pack_forget()
                canvas.xview_moveto(0)
        except tk.TclError:
            pass

    def _install_popup_scroll(self, window, bg, padx=0, pady=0):
        """Scroll the popup body when it is taller than the window. Buttons stay outside."""
        scroller = tk.Frame(window, bg=bg)
        scroller.pack(fill="both", expand=True, padx=padx, pady=pady)
        scroller.rowconfigure(0, weight=1)
        scroller.columnconfigure(0, weight=1)
        canvas = tk.Canvas(scroller, bg=bg, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(scroller, orient="vertical", command=canvas.yview)
        canvas.configure(
            yscrollcommand=lambda first, last, bar=bar: self._track_popup_vscroll(bar, first, last),
        )
        canvas.grid(row=0, column=0, sticky="nsew")
        body = tk.Frame(canvas, bg=bg)
        window._popup_canvas = canvas
        window._popup_body = body
        window._popup_item = canvas.create_window((0, 0), window=body, anchor="nw")
        window._popup_bar = bar
        window._popup_fit_guard = False
        body.bind("<Configure>", lambda _event, window=window: self._fit_popup_scroll(window))
        canvas.bind("<Configure>", lambda _event, window=window: self._fit_popup_scroll(window))
        self._bind_popup_wheel(window, canvas)
        return body

    def _track_popup_vscroll(self, bar, first, last):
        try:
            bar.set(first, last)
        except tk.TclError:
            pass

    def _fit_popup_scroll(self, window):
        if window is None or getattr(window, "_popup_fit_guard", False):
            return
        canvas = getattr(window, "_popup_canvas", None)
        body = getattr(window, "_popup_body", None)
        item = getattr(window, "_popup_item", None)
        if canvas is None or body is None or item is None:
            return
        window._popup_fit_guard = True
        try:
            if not canvas.winfo_exists() or not body.winfo_exists():
                return
            width = canvas.winfo_width()
            height = canvas.winfo_height()
            if width <= 1 or height <= 1:
                return
            canvas.itemconfigure(item, width=width)
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            if not bbox:
                return
            canvas.configure(scrollregion=bbox)
            self._show_popup_vscroll(window, bbox[3] - bbox[1] > height + 1)
        except tk.TclError:
            pass
        finally:
            window._popup_fit_guard = False

    def _show_popup_vscroll(self, window, needed):
        bar = getattr(window, "_popup_bar", None)
        canvas = getattr(window, "_popup_canvas", None)
        if bar is None or canvas is None:
            return
        try:
            if not bar.winfo_exists():
                return
            shown = bool(bar.winfo_manager())
            if needed and not shown:
                bar.grid(row=0, column=1, sticky="ns")
            elif not needed and shown:
                bar.grid_remove()
                canvas.yview_moveto(0)
        except tk.TclError:
            pass

    def _bind_popup_wheel(self, window, widget):
        """Scroll the popup under the pointer. Lists and their own canvases keep the wheel."""
        popup_canvas = getattr(window, "_popup_canvas", None)
        skip_bind = isinstance(widget, (tk.Listbox, tk.Text)) or (
            isinstance(widget, tk.Canvas) and widget is not popup_canvas
        )
        if not skip_bind:
            try:
                widget.bind("<Button-4>", lambda event, window=window: self._on_popup_wheel(window, event))
                widget.bind("<Button-5>", lambda event, window=window: self._on_popup_wheel(window, event))
                widget.bind("<MouseWheel>", lambda event, window=window: self._on_popup_wheel(window, event))
            except tk.TclError:
                return
        if isinstance(widget, (tk.Listbox, tk.Text)):
            return
        for child in widget.winfo_children():
            self._bind_popup_wheel(window, child)

    def _on_popup_wheel(self, window, event):
        if window is None:
            return
        canvas = getattr(window, "_popup_canvas", None)
        bar = getattr(window, "_popup_bar", None)
        if canvas is None or bar is None or not bar.winfo_manager():
            return
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            canvas.yview_scroll(-3, "units")
        else:
            canvas.yview_scroll(3, "units")
        return "break"

    def _window_alive(self, window):
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            return False

    def _popup_open(self, window):
        if not self._window_alive(window):
            return False
        try:
            return bool(window.winfo_viewable())
        except tk.TclError:
            return False

    def _ensure_popup_stack(self):
        global _dialog_owner
        _dialog_owner = self
        self._popup_stack = [
            item for item in getattr(self, "_popup_stack", []) if self._window_alive(item)
        ]

    def _note_popup(self, window):
        """Remember open popups so the next one can be placed above them."""
        self._ensure_popup_stack()
        if window in self._popup_stack:
            self._popup_stack.remove(window)
        self._popup_stack.append(window)
        if getattr(window, "_popup_tracked", False):
            return
        window._popup_tracked = True

        def forget(event, window=window):
            if getattr(event, "widget", None) is not window:
                return
            self._forget_popup(window)

        window.bind("<Destroy>", forget, add="+")

    def _cancel_popup_jobs(self, window):
        jobs = getattr(window, "_present_jobs", ())
        window._present_jobs = ()
        for job in jobs:
            try:
                window.after_cancel(job)
            except tk.TclError:
                pass

    def _forget_popup(self, window):
        self._cancel_popup_jobs(window)
        self._popup_stack = [
            item for item in getattr(self, "_popup_stack", [])
            if item is not window and self._window_alive(item)
        ]

    def _front_popup(self, skip=None):
        """Topmost open popup, ignoring one window that is being shown."""
        self._ensure_popup_stack()
        for item in reversed(self._popup_stack):
            if item is skip or not self._popup_open(item):
                continue
            return item
        return None

    def _dialog_parent(self):
        """Parent for a dialog opened while a popup is already visible."""
        return self._front_popup() or self.root

    def _focus_inside(self, window, widget):
        while widget is not None:
            if widget is window:
                return True
            try:
                widget = widget.master
            except tk.TclError:
                return False
        return False

    def _focused_widget(self):
        """Widget with keyboard focus.

        A just-closed file dialog can still be Tk's focus name without a
        Python widget. ``focus_get`` then raises ``KeyError``.
        """
        root = getattr(self, "root", None)
        if root is None:
            return None
        try:
            return root.focus_get()
        except (tk.TclError, KeyError):
            return None

    def _present_popup(self, window):
        """Put this window in front of popups that are already open."""
        if not self._window_alive(window):
            return
        owner = self._front_popup(skip=window)
        focused = self._focused_widget()
        inside = focused is not None and self._focus_inside(window, focused)
        try:
            window.lift()
            if owner is not None:
                window.lift(owner)
            window.attributes("-topmost", True)
            window.focus_force()
            if inside:
                focused.focus_set()
        except tk.TclError:
            return
        if owner is not None:
            self._cancel_popup_jobs(window)
            return
        token = getattr(window, "_present_token", 0) + 1
        window._present_token = token
        self._cancel_popup_jobs(window)

        def settle(token=token, window=window):
            if getattr(window, "_present_token", None) != token:
                return
            try:
                if not window.winfo_exists():
                    return
                window.attributes("-topmost", False)
                stack = [
                    item for item in getattr(self, "_popup_stack", [])
                    if self._window_alive(item)
                ]
                if stack and stack[-1] is not window:
                    return
                window.lift()
            except tk.TclError:
                pass

        try:
            window._present_jobs = (
                window.after_idle(settle),
                window.after(50, settle),
            )
        except tk.TclError:
            window._present_jobs = ()

    def _grab_popup(self, window):
        """Take the modal grab and keep this popup above the one under it."""
        self._note_popup(window)
        self._present_popup(window)
        try:
            window.grab_set()
        except tk.TclError:
            return
        window._grab_hooked = True
        self._present_popup(window)
        if getattr(window, "_grab_restore_bound", False):
            return
        window._grab_restore_bound = True

        def restore(event, window=window):
            if getattr(event, "widget", None) is not window:
                return
            self._forget_popup(window)
            self._restore_popup_grab()

        window.bind("<Destroy>", restore, add="+")

    def _restore_popup_grab(self):
        """Give the grab back to the previous modal popup."""
        candidate = None
        for item in reversed(getattr(self, "_popup_stack", [])):
            if getattr(item, "_grab_hooked", False) and self._popup_open(item):
                candidate = item
                break
        if candidate is None or self._front_popup() is not candidate:
            return
        try:
            current = candidate.tk.call("grab", "current", candidate)
        except tk.TclError:
            current = ""
        if current:
            try:
                grabber = candidate.nametowidget(str(current))
            except (KeyError, tk.TclError):
                grabber = None
            if (
                grabber is not None
                and grabber is not candidate
                and self._window_alive(grabber)
            ):
                return
        try:
            candidate.grab_set()
            self._present_popup(candidate)
        except tk.TclError:
            pass

    def _open_popup(self, window, width, height):
        """Open a popup tall enough for its contents, then scroll whatever still does not fit.

        A popup opened while another popup is visible stays above that window.
        """
        try:
            window.update_idletasks()
            height = max(int(height), int(window.winfo_reqheight()))
            width = max(int(width), 1)
        except (tk.TclError, TypeError, ValueError):
            pass
        width, height = self._lights_window_size(width, height)
        owner = self._front_popup(skip=window)
        try:
            window.withdraw()
            window.transient(owner if owner is not None else self.root)
        except tk.TclError:
            pass
        self._place_on_control_monitor(window, width, height)
        self._note_popup(window)
        try:
            window.deiconify()
        except tk.TclError:
            pass
        self._present_popup(window)
        self._fit_popup_scroll(window)

    def _track_lights_vscroll(self, bar, first, last):
        self._track_popup_vscroll(bar, first, last)

    def _fit_lights_body(self, _event=None):
        """Stretch the settings form to the window and scroll it when it is taller."""
        self._fit_popup_scroll(getattr(self, "lights_window", None))

    def _show_lights_vscroll(self, needed):
        self._show_popup_vscroll(getattr(self, "lights_window", None), needed)

    def _bind_lights_scroll(self, widget):
        """Scroll the settings form with the wheel, and leave lists to scroll themselves."""
        window = getattr(self, "lights_window", None)
        if window is None:
            return
        self._bind_popup_wheel(window, widget)

    def _on_lights_wheel(self, event):
        return self._on_popup_wheel(getattr(self, "lights_window", None), event)

    def _lights_window_size(self, width, height):
        """Keep the lights window on the control screen so its buttons stay reachable."""
        geometry = None
        try:
            geometry = self._control_fullscreen_geometry()
        except Exception:
            geometry = None
        if not geometry:
            return width, height
        screen_w, screen_h = geometry[0], geometry[1]
        margin = 48
        width = min(width, max(640, screen_w - margin))
        height = min(height, max(420, screen_h - margin))
        return width, height

    def _build_sequence_editor(self, sequence):
        """Pick the scenes a sequence runs, in order."""
        for child in list(self._scene_levels_frame.winfo_children()):
            child.destroy()
        self._scene_level_vars = {}
        self._scene_fade_var = None
        tk.Label(
            self._scene_levels_frame, text=t("lights_sequence_steps"),
            bg=COLOR_PANEL, font=FONT_SMALL,
        ).pack(anchor="w")
        box = self._styled_listbox(self._scene_levels_frame)
        box.configure(height=4, width=24, exportselection=False)
        box.pack(fill="x", pady=(2, 4))
        self._sequence_steps_box = box
        for step in dmx.sequence_steps(sequence, self._scene_draft):
            box.insert("end", self._scene_label(step))
        row = tk.Frame(self._scene_levels_frame, bg=COLOR_PANEL)
        row.pack(fill="x")
        labels = [self._scene_label(scene) for scene in self._scene_draft]
        self._sequence_step_var = tk.StringVar(value=labels[0] if labels else "")
        ttk.Combobox(
            row, textvariable=self._sequence_step_var, values=labels,
            state="readonly", width=16,
        ).pack(side="left")
        tk.Button(
            row, text=t("lights_sequence_add_step"), font=FONT_SMALL,
            command=self._add_sequence_step,
        ).pack(side="left", padx=(6, 0))
        tk.Button(
            row, text=t("lights_sequence_remove_step"), font=FONT_SMALL,
            command=self._remove_sequence_step,
        ).pack(side="left", padx=(6, 0))
        tk.Button(
            row, text=t("lights_sequence_up"), font=FONT_SMALL,
            command=lambda: self._move_sequence_step(-1),
        ).pack(side="left", padx=(6, 0))
        tk.Button(
            row, text=t("lights_sequence_down"), font=FONT_SMALL,
            command=lambda: self._move_sequence_step(1),
        ).pack(side="left", padx=(6, 0))

    def _add_sequence_step(self):
        sequence = dmx.find_sequence(self._sequence_draft, self._scene_edit_id)
        if sequence is None:
            return
        label = self._sequence_step_var.get() if getattr(self, "_sequence_step_var", None) else ""
        scene = next((item for item in self._scene_draft if self._scene_label(item) == label), None)
        if scene is None:
            return
        sequence.steps.append(scene.id)
        self._load_scene_form(sequence.id)

    def _remove_sequence_step(self):
        sequence = dmx.find_sequence(self._sequence_draft, self._scene_edit_id)
        box = getattr(self, "_sequence_steps_box", None)
        if sequence is None or box is None:
            return
        try:
            selection = box.curselection()
        except tk.TclError:
            return
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(sequence.steps):
            del sequence.steps[index]
        self._load_scene_form(sequence.id)

    def _move_sequence_step(self, offset):
        sequence = dmx.find_sequence(self._sequence_draft, self._scene_edit_id)
        box = getattr(self, "_sequence_steps_box", None)
        if sequence is None or box is None:
            return
        try:
            selection = box.curselection()
        except tk.TclError:
            return
        if not selection:
            return
        index = selection[0]
        target = index + offset
        if not 0 <= index < len(sequence.steps) or not 0 <= target < len(sequence.steps):
            return
        sequence.steps[index], sequence.steps[target] = sequence.steps[target], sequence.steps[index]
        self._load_scene_form(sequence.id)

    def _on_scene_select(self, _event=None):
        if self._scene_guard or self._scene_listbox is None or not self._scene_draft:
            return
        try:
            selection = self._scene_listbox.curselection()
        except tk.TclError:
            return
        if not selection:
            return
        cues = self._draft_cues()
        index = selection[0]
        if not 0 <= index < len(cues):
            return
        scene_id = cues[index].id
        if scene_id == self._scene_edit_id:
            return
        self._flush_scene_form()
        self._scene_edit_id = scene_id
        self._load_scene_form(scene_id)

    def _on_scene_name_changed(self, _event=None):
        if self._scene_guard:
            return
        self._flush_scene_form()
        self._refresh_scene_list_labels()

    def _on_scene_channels_changed(self, _event=None):
        if self._scene_guard or self._scene_draft is None:
            return
        self._flush_scene_form()
        channels = self._draft_channels()
        self._scene_draft = dmx.align_scenes(self._scene_draft, channels, self._default_fade_ms())
        self._sequence_draft = dmx.align_sequences(self._sequence_draft, self._scene_draft)
        if getattr(self, "lights_channels", None) is not None:
            self.lights_channels.set(dmx.format_channels(channels))
        self._refresh_scene_editor()
        if _event is not None and getattr(_event, "keysym", "") == "Return":
            return "break"

    def _add_edited_scene(self):
        if self._scene_draft is None:
            return
        self._flush_scene_form()
        channels = self._draft_channels()
        name = self._fresh_scene_name(self._scene_draft)
        self._scene_draft = dmx.add_scene(
            self._scene_draft, channels, name, fade_ms=self._default_fade_ms(),
        )
        self._scene_edit_id = self._scene_draft[-1].id
        self._refresh_scene_editor()

    def _add_edited_sequence(self):
        if self._scene_draft is None:
            return
        self._flush_scene_form()
        name = t("sequence_new")
        self._sequence_draft = dmx.add_sequence(self._sequence_draft, self._scene_draft, name)
        self._scene_edit_id = self._sequence_draft[-1].id
        self._refresh_scene_editor()

    def _delete_edited_scene(self):
        cue = self._find_draft_cue(self._scene_edit_id)
        if cue is None or dmx.scene_locked(getattr(cue, "id", "")):
            return
        if isinstance(cue, dmx.SceneSequence):
            self._sequence_draft = dmx.delete_sequence(self._sequence_draft, cue.id, self._scene_draft)
        else:
            channels = self._draft_channels()
            self._scene_draft = dmx.delete_scene(self._scene_draft, cue.id, channels)
            for sequence in self._sequence_draft or []:
                sequence.steps = [step for step in sequence.steps if step != cue.id]
            self._sequence_draft = dmx.align_sequences(self._sequence_draft, self._scene_draft)
        self._scene_edit_id = self._scene_draft[0].id
        self._refresh_scene_editor()

    def show_lights(self):
        """Configure DMX house lights over Enttec, Open DMX, or Art-Net."""
        window = getattr(self, "lights_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.deiconify()
                    self._present_popup(window)
                    self._refresh_light_buttons()
                    self._refresh_header_indicators()
                    return
            except tk.TclError:
                self.lights_window = None
        window = tk.Toplevel(self.root)
        window.title(t("lights"))
        window.configure(bg=COLOR_BG)
        window.minsize(680, 420)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_lights_window)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        tk.Button(buttons, text=t("lights_close"), font=FONT_UI, command=self._close_lights_window).pack(side="right")
        tk.Button(buttons, text=t("remote_control_apply"), font=FONT_UI, command=self._commit_lights_settings).pack(
            side="right", padx=(0, 8),
        )
        self.lights_window = window
        self._place_window_indicator(window, "lights")
        holder = self._install_popup_scroll(window, COLOR_PANEL, padx=10, pady=(10, 10))
        self._lights_body = window._popup_canvas
        self._lights_body_frame = holder
        self._lights_body_window = window._popup_item
        self._lights_vscroll = window._popup_bar
        self._lights_fit_guard = False
        tk.Label(
            holder, text=t("lights_hint"), bg=COLOR_PANEL, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=620, justify="left",
        ).pack(fill="x", padx=8, pady=(8, 6))
        output = getattr(self, "dmx_output", None) or dmx.DmxOutput()
        self.lights_mode = tk.StringVar(value=self._lights_mode_label(output.mode))
        self.lights_host = tk.StringVar(value=output.host or dmx.DEFAULT_HOST)
        self.lights_universe = tk.StringVar(value=str(output.universe))
        self.lights_device = tk.StringVar(value=output.device)
        self.lights_channels = tk.StringVar(value=dmx.format_channels(output.channels) or "1")
        node = tk.Frame(holder, bg=COLOR_PANEL)
        node.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(node, text=t("lights_mode"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        mode_combo = ttk.Combobox(
            node,
            textvariable=self.lights_mode,
            width=22,
            state="readonly",
            values=[
                t("lights_mode_enttec"),
                t("lights_mode_opendmx"),
                t("lights_mode_artnet"),
            ],
        )
        mode_combo.pack(side="left", padx=(4, 12))
        mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_lights_mode())
        tk.Label(node, text=t("lights_host"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        self.lights_host_entry = tk.Entry(node, textvariable=self.lights_host, width=18, font=FONT_UI)
        self.lights_host_entry.pack(side="left", padx=(4, 12))
        tk.Label(node, text=t("lights_universe"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        self.lights_universe_entry = tk.Entry(node, textvariable=self.lights_universe, width=5, font=FONT_UI)
        self.lights_universe_entry.pack(side="left", padx=4)
        cable = tk.Frame(holder, bg=COLOR_PANEL)
        cable.pack(fill="x", padx=8, pady=(0, 2))
        tk.Label(cable, text=t("lights_device"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        self.lights_device_combo = ttk.Combobox(
            cable,
            textvariable=self.lights_device,
            width=30,
            postcommand=self._fill_lights_devices,
        )
        self.lights_device_combo.pack(side="left", padx=(4, 12))
        self._fill_lights_devices()
        tk.Label(cable, text=t("lights_channels"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        self.lights_channels_entry = tk.Entry(
            cable, textvariable=self.lights_channels, width=16, font=FONT_UI,
        )
        self.lights_channels_entry.pack(side="left", padx=4)
        self.lights_channels_entry.bind("<FocusOut>", self._on_scene_channels_changed)
        self.lights_channels_entry.bind("<Return>", self._on_scene_channels_changed)
        self.lights_device_hint = tk.Label(
            holder, text=t("lights_device_hint"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL, anchor="w",
            wraplength=620, justify="left",
        )
        self.lights_device_hint.pack(fill="x", padx=8)
        tk.Label(
            holder, text=t("lights_channels_hint"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL, anchor="w",
        ).pack(fill="x", padx=8, pady=(0, 2))
        self._update_lights_mode_fields()
        self.lights_status = tk.StringVar(value="")
        tk.Label(
            holder, textvariable=self.lights_status, bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL, anchor="w",
        ).pack(fill="x", padx=8)
        self._sync_lights_control(save=False)
        self._build_scene_editor(holder)
        fade = tk.Frame(holder, bg=COLOR_PANEL)
        fade.pack(fill="x", padx=8, pady=(8, 4))
        self.lights_transition = tk.StringVar(value=self._lights_transition_text())
        tk.Label(fade, text=t("lights_transition"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        tk.Entry(fade, textvariable=self.lights_transition, width=4, font=FONT_UI).pack(side="left", padx=4)
        tk.Label(fade, text=t("seconds_short"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL).pack(side="left")
        timing = tk.Frame(holder, bg=COLOR_PANEL)
        timing.pack(fill="x", padx=8, pady=(0, 4))
        self.lights_start_lead = tk.StringVar(value=dmx.ms_to_seconds_text(self.lights_start_lead_ms))
        self.lights_end_lead = tk.StringVar(value=dmx.ms_to_seconds_text(self.lights_end_lead_ms))
        tk.Label(timing, text=t("lights_start_lead"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        tk.Entry(timing, textvariable=self.lights_start_lead, width=4, font=FONT_UI).pack(side="left", padx=4)
        tk.Label(
            timing, text=t("lights_start_lead_hint"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(side="left", padx=(0, 16))
        tk.Label(timing, text=t("lights_end_lead"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left")
        tk.Entry(timing, textvariable=self.lights_end_lead, width=4, font=FONT_UI).pack(side="left", padx=4)
        tk.Label(
            timing, text=t("lights_end_lead_hint"), bg=COLOR_PANEL, fg=COLOR_MUTED, font=FONT_SMALL,
        ).pack(side="left")
        tests = tk.Frame(holder, bg=COLOR_PANEL)
        tests.pack(fill="x", padx=8, pady=(0, 4))
        self.settings_light_bar = tk.Frame(tests, bg=COLOR_PANEL)
        self.settings_light_bar.pack(side="left")
        self.settings_light_buttons = {}
        self._fill_light_buttons(self.settings_light_bar, self.settings_light_buttons, self._test_lights)
        self._refresh_light_buttons()
        self._bind_lights_scroll(holder)
        self._open_popup(window, 820, 640)

    def _lights_mode_label(self, key):
        mode = dmx.normalize_mode(key)
        if mode == dmx.MODE_ARTNET:
            return t("lights_mode_artnet")
        if mode == dmx.MODE_OPENDMX:
            return t("lights_mode_opendmx")
        return t("lights_mode_enttec")

    def _lights_mode_key(self):
        variable = getattr(self, "lights_mode", None)
        if variable is None:
            output = getattr(self, "dmx_output", None)
            return dmx.normalize_mode(output.mode if output else dmx.DEFAULT_MODE)
        label = variable.get()
        if label == t("lights_mode_artnet"):
            return dmx.MODE_ARTNET
        if label == t("lights_mode_opendmx"):
            return dmx.MODE_OPENDMX
        return dmx.MODE_ENTTEC

    def _fill_lights_devices(self):
        combo = getattr(self, "lights_device_combo", None)
        if combo is None:
            return
        devices = dmx.list_serial_devices()
        current = self.lights_device.get().strip()
        if current and current not in devices:
            devices.insert(0, current)
        try:
            combo.configure(values=devices)
        except tk.TclError:
            self.lights_device_combo = None

    def _update_lights_mode_fields(self):
        mode = self._lights_mode_key()
        serial = mode in dmx.SERIAL_MODES
        widgets = (
            (getattr(self, "lights_host_entry", None), not serial),
            (getattr(self, "lights_universe_entry", None), not serial),
            (getattr(self, "lights_device_combo", None), serial),
        )
        for widget, active in widgets:
            if widget is None:
                continue
            try:
                widget.config(state="normal" if active else "disabled")
            except tk.TclError:
                pass
        hint = getattr(self, "lights_device_hint", None)
        if hint is not None:
            key = "lights_device_hint_opendmx" if mode == dmx.MODE_OPENDMX else "lights_device_hint"
            try:
                hint.config(text=t(key))
            except tk.TclError:
                self.lights_device_hint = None

    def _on_lights_mode(self):
        self._update_lights_mode_fields()
        self._commit_lights_settings()

    def _close_lights_window(self):
        self._commit_lights_settings()
        window = getattr(self, "lights_window", None)
        self.lights_window = None
        self.settings_light_buttons = {}
        self.settings_light_bar = None
        self.settings_lights_check = None
        self.lights_window_indicator = None
        self.lights_host_entry = None
        self.lights_universe_entry = None
        self.lights_device_combo = None
        self.lights_device_hint = None
        self.lights_channels_entry = None
        self._scene_draft = None
        self._sequence_draft = None
        self._scene_listbox = None
        self._scene_name_var = None
        self._scene_level_vars = {}
        self._scene_fade_var = None
        self._scene_levels_frame = None
        self._scene_delete_button = None
        self._lights_body = None
        self._lights_body_frame = None
        self._lights_body_window = None
        self._lights_vscroll = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _lights_transition_text(self):
        return dmx.ms_to_seconds_text(self.lights_transition_ms)

    def _commit_lights_settings(self):
        if getattr(self, "lights_host", None) is not None:
            self.dmx_output = dmx.DmxOutput(
                host=self.lights_host.get(),
                universe=self.lights_universe.get(),
                channels=self.lights_channels.get(),
                mode=self._lights_mode_key(),
                device=self.lights_device.get(),
            )
            self.lights_mode.set(self._lights_mode_label(self.dmx_output.mode))
            self.lights_host.set(self.dmx_output.host or dmx.DEFAULT_HOST)
            self.lights_universe.set(str(self.dmx_output.universe))
            self.lights_device.set(self.dmx_output.device)
            self.lights_channels.set(dmx.format_channels(self.dmx_output.channels) or "1")
        if self._scene_draft is not None:
            self._flush_scene_form()
            channels = self.dmx_output.channels if getattr(self, "dmx_output", None) else [1]
            self.lights_scenes = dmx.align_scenes(
                self._scene_draft, channels, self._default_fade_ms(),
            )
            self._scene_draft = [scene.copy() for scene in self.lights_scenes]
            if self._sequence_draft is not None:
                self.lights_sequences = dmx.align_sequences(self._sequence_draft, self.lights_scenes)
                self._sequence_draft = [sequence.copy() for sequence in self.lights_sequences]
            self._refresh_scene_editor()
            self._rebuild_light_buttons()
        if getattr(self, "lights_transition", None) is not None:
            try:
                seconds = float(self.lights_transition.get())
            except (TypeError, ValueError):
                seconds = dmx.DEFAULT_TRANSITION_MS / 1000.0
            self.lights_transition_ms = max(0, int(round(seconds * 1000)))
            self.lights_start_lead_ms = dmx.seconds_to_ms(
                self.lights_start_lead.get(), self.lights_start_lead_ms,
            )
            self.lights_end_lead_ms = dmx.seconds_to_ms(
                self.lights_end_lead.get(), self.lights_end_lead_ms,
            )
            self.lights_transition.set(self._lights_transition_text())
            self.lights_start_lead.set(dmx.ms_to_seconds_text(self.lights_start_lead_ms))
            self.lights_end_lead.set(dmx.ms_to_seconds_text(self.lights_end_lead_ms))
        self._sync_lights_control()

    def _test_lights(self, preset):
        self._commit_lights_settings()
        if not bool(self.lights_control.get()):
            status = getattr(self, "lights_status", None)
            if status is not None:
                status.set(t("lights_control_off"))
            return
        if not self._dmx_ready():
            status = getattr(self, "lights_status", None)
            if status is not None:
                mode = self._lights_mode_key()
                if mode == dmx.MODE_OPENDMX:
                    status.set(t("lights_none_ready_opendmx"))
                elif mode == dmx.MODE_ENTTEC:
                    status.set(t("lights_none_ready_enttec"))
                else:
                    status.set(t("lights_none_ready"))
            return
        self._apply_lights(preset, force=True)

    def _remote_result(self, ok=True, error=None):
        payload = self.remote_status()
        payload["ok"] = ok
        if error:
            payload["error"] = error
        elif "error" in payload:
            del payload["error"]
        return payload

    def remote_status(self):
        stopped = self.program_state == "OFF"
        entry = self.current_entry() if self.playlist else None
        duration = 0.0 if stopped else (
            (entry.duration if entry and entry.duration else 0) or self.duration or 0
        )
        in_point = out_point = None
        if entry and not stopped and not entry.is_image:
            in_point = entry.in_point
            out_point = entry.out_point
        times = clip_times(self.program_state, duration, self.position, in_point, out_point)
        paused = self.program_state == "PLAYING" and self.main_pause and self.blackout
        frozen = self.program_state == "PLAYING" and self.main_pause and not self.blackout
        rolling = self.program_state == "PLAYING" and not self.main_pause
        clip_rolling = rolling and not self.still_waiting and not self._program_loop_active()
        volume_setup = bool(getattr(self, "volume_setup", False))
        still_clip = bool(entry and getattr(entry, "is_image", False))
        if volume_setup:
            state_key = "state_volume_setup"
        else:
            state_key = self._calibration_state_key()
        if not state_key:
            state_key = {
                "OFF": "state_off",
                "PROGRAM": "state_program",
                "PLAYING": "state_playing",
            }[self.program_state]
        playlist = []
        for index, item in enumerate(self.playlist):
            playlist.append({
                "index": index,
                "filename": item.filename,
                "duration": item.duration,
                "duration_label": self._row_duration_text(item),
                "played": bool(item.played),
                "missing": bool(item.missing),
                "autoplay": bool(item.autoplay),
                "loop": bool(item.loop),
                "is_image": bool(item.is_image),
                "current": index == self.program_index,
            })
        clip = None
        if entry is not None:
            clip = {
                "filename": entry.filename,
                "index": self.program_index,
                "duration": duration if not stopped else (entry.duration or 0),
                "position": self.position if self.program_state == "PLAYING" else 0.0,
                "in_point": entry.in_point,
                "out_point": entry.out_point,
                "is_image": bool(entry.is_image),
            }
            envelope = remote_clip_envelope(
                entry, volume_setup or self.program_seek_allowed(),
            )
            if envelope:
                clip["envelope"] = envelope
        return {
            "ok": True,
            "version": APP_VERSION,
            "language": current_language(),
            "state": self.program_state,
            "state_label": t(state_key),
            "calibration": self.calibration_mode,
            "volume_setup": volume_setup,
            "paused": paused,
            "still": frozen,
            "idle": bool(self.idle_showing),
            "loop": bool(self._program_loop_active()),
            "volume": clamp_volume(self.program_volume.get()),
            "lights": {
                "enabled": bool(self.lights_control.get()),
                "preset": dmx.cue_key(
                    self.lights_current, self.lights_scenes, getattr(self, "lights_sequences", None),
                ) if self.lights_current else "",
                "scenes": [
                    {"id": cue.id, "name": self._cue_label(cue)}
                    for cue in list(self.lights_scenes) + list(getattr(self, "lights_sequences", None) or [])
                ],
                "fading": bool(self.lights_fading),
                "output": self.dmx_output.mode if getattr(self, "dmx_output", None) else "",
                "connected": dmx.connected(),
            },
            "program_index": self.program_index if self.playlist else 0,
            "playlist_name": self.playlist_name.get().strip() if getattr(self, "playlist_name", None) else "",
            "playlist": playlist,
            "clip": clip,
            "times": times,
            "actions": {
                "resume": bool(self.playlist) and not clip_rolling,
                "pause": self.program_state == "PLAYING",
                "still": self.program_state == "PLAYING",
                "stop": self.program_state == "PLAYING",
                "confirm_transport": not volume_setup,
                "volume": not still_clip,
                "save_volume": not still_clip,
                "seek": self.program_seek_allowed(),
                "set_program": bool(self.playlist) and self.program_state != "PLAYING",
                "lights": bool(self.lights_control.get()),
            },
        }

    def remote_resume(self):
        ready_at = getattr(self, "_remote_ready_at", 0) or 0
        if time.monotonic() < ready_at:
            return self._remote_result(True)
        self._remote_action = True
        try:
            if not self.playlist:
                return self._remote_result(False, "no_playlist")
            if self.program_state == "PROGRAM" and not self.confirm_projection_zoom(prompt=False):
                return self._remote_result(False, "projection_zoom_required")
            self.start_or_resume()
            return self._remote_result(True)
        finally:
            self._remote_action = False

    def remote_pause(self):
        if not self._apply_pause():
            return self._remote_result(False, "not_playing")
        return self._remote_result(True)

    def remote_still(self):
        if not self._apply_still():
            return self._remote_result(False, "not_playing")
        return self._remote_result(True)

    def remote_stop(self):
        self._remote_action = True
        try:
            if not self._apply_stop_clip():
                return self._remote_result(False, "not_playing")
            return self._remote_result(True)
        finally:
            self._remote_action = False

    def remote_save_volume(self):
        """Write the program fader into the playlist entry on the program pointer."""
        if not self.current_entry():
            return self._remote_result(False, "no_clip")
        self.save_program_volume()
        return self._remote_result(True)

    def remote_seek(self, position):
        if not self.program_seek_allowed():
            return self._remote_result(False, "seek_unavailable")
        try:
            position = float(position)
        except (TypeError, ValueError):
            return self._remote_result(False, "position_required")
        if position < 0:
            position = 0.0
        entry = self.current_entry()
        duration = (entry.duration if entry and entry.duration else 0) or getattr(self, "duration", 0) or 0
        if duration:
            position = min(position, float(duration))
        self._on_main_seek(position)
        return self._remote_result(True)

    def remote_set_volume(self, value):
        volume = clamp_volume(value)
        self._on_program_volume(volume)
        if getattr(self, "program_volume_bar", None):
            self.program_volume_bar.set_volume(volume)
        return self._remote_result(True)

    def remote_set_program(self, index):
        try:
            index = int(index)
        except (TypeError, ValueError):
            return self._remote_result(False, "invalid_index")
        if not self.playlist:
            return self._remote_result(False, "no_playlist")
        if self.program_state == "PLAYING":
            return self._remote_result(False, "playing")
        if not 0 <= index < len(self.playlist):
            return self._remote_result(False, "invalid_index")
        if self.playlist[index].missing:
            return self._remote_result(False, "missing")
        self._remote_action = True
        try:
            self.set_program_point(index)
        finally:
            self._remote_action = False
        return self._remote_result(True)

    def remote_set_lights(self, preset=None, enabled=None):
        if enabled is not None:
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() not in ("0", "false", "off", "no", "")
            self.lights_control.set(bool(enabled))
            self._on_lights_control()
            if enabled and not bool(self.lights_control.get()):
                return self._remote_result(False, "lights_disabled")
        if preset is not None and str(preset).strip() != "":
            key = dmx.cue_key(preset, self.lights_scenes, getattr(self, "lights_sequences", None))
            if not key or dmx.find_cue(key, self.lights_scenes, getattr(self, "lights_sequences", None)) is None:
                return self._remote_result(False, "invalid_preset")
            if not bool(self.lights_control.get()):
                return self._remote_result(False, "lights_disabled")
            self._apply_lights(key, force=True)
        return self._remote_result(True)

    def show_media_directories(self):
        """Edit the saved media folders used when importing into the playlist."""
        if self._media_dirs_window_alive():
            self.media_dirs_window.deiconify()
            self._present_popup(self.media_dirs_window)
            return
        window = tk.Toplevel(self.root)
        window.title(t("media_directories"))
        window.configure(bg=COLOR_BG)
        window.minsize(560, 340)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_media_dirs_window)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        body = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=(10, 0))

        tk.Label(
            body, text=t("media_directories_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=620, justify="left",
        ).pack(fill="x", pady=(0, 2))
        tk.Label(
            body, text=t("import_path_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=620, justify="left",
        ).pack(fill="x", pady=(0, 6))

        holder = tk.Frame(body, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, pady=(0, 10))
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        listbox = self._styled_listbox(holder)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        name_row = tk.Frame(body, bg=COLOR_BG)
        name_row.pack(fill="x", padx=10, pady=(0, 2))
        tk.Label(
            name_row, text=t("media_directories_name"), bg=COLOR_BG, fg=COLOR_TEXT,
            font=FONT_UI,
        ).pack(side="left")
        self._media_dir_name_var = tk.StringVar()
        self._media_dir_name_index = None
        self._media_dir_name_guard = False
        name_entry = tk.Entry(name_row, textvariable=self._media_dir_name_var, font=FONT_UI)
        name_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        name_entry.configure(state="disabled")
        self._media_dir_name_entry = name_entry
        name_entry.bind("<Return>", self._commit_media_directory_name)
        name_entry.bind("<FocusOut>", self._commit_media_directory_name)
        tk.Label(
            body, text=t("media_directories_name_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=640, justify="left",
        ).pack(fill="x", pady=(0, 8))

        tk.Button(
            buttons, text=t("media_directories_close"),
            command=self._close_media_dirs_window, font=FONT_UI,
        ).pack(side="right")
        tk.Button(
            buttons, text=t("media_directories_remove"),
            command=lambda: self._remove_media_directory(listbox), font=FONT_UI,
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            buttons, text=t("media_directories_add"),
            command=lambda: self._add_media_directory(window, listbox), font=FONT_UI,
        ).pack(side="right", padx=(0, 8))
        tk.Button(
            buttons, text=t("import_path_choose"),
            command=lambda: self._choose_import_path(window), font=FONT_UI,
        ).pack(side="left")

        window._listbox = listbox
        self.media_dirs_window = window
        listbox.bind("<<ListboxSelect>>", self._on_media_directory_select)
        listbox.bind("<Double-Button-1>", lambda _event: self._focus_media_directory_name())
        self._refresh_media_directory_list(listbox, select_import=True)
        self._load_media_directory_name_field(listbox)
        self._bind_popup_wheel(window, body)
        self._open_popup(window, 720, 560)

    def _media_dirs_window_alive(self):
        window = getattr(self, "media_dirs_window", None)
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            self.media_dirs_window = None
            return False

    def _media_directory_label(self, item):
        path = item["path"]
        name = item.get("name") or ""
        text = f"{name}  —  {path}" if name else path
        if not os.path.isdir(path):
            text = f"{text}  ({t('media_directories_missing')})"
        return text

    def _free_space_on_path(self, path):
        """Free bytes on the volume that holds path, or None when it cannot be read."""
        if not path or not os.path.isdir(path):
            return None
        try:
            return shutil.disk_usage(path).free
        except OSError:
            return None

    def _import_path_label(self):
        mark = t("import_path_mark")
        path = getattr(self, "import_path", "") or ""
        if not path:
            return f"{mark}  —  {t('import_path_missing')}"
        text = f"{mark}  —  {path}"
        if not os.path.isdir(path):
            return f"{text}  ({t('media_directories_missing')})"
        free = self._free_space_on_path(path)
        if free is None:
            return text
        return f"{text}  —  {t('import_path_free', size=self._format_copy_size(free))}"

    def _mark_import_path_row(self, listbox):
        """Keep the import path visibly distinct, including while it is selected."""
        try:
            if listbox.size() > 0:
                listbox.itemconfig(
                    0,
                    foreground=ACCENT,
                    selectforeground=COLOR_WHITE,
                    selectbackground=ACCENT,
                )
        except tk.TclError:
            pass

    def _media_directory_choice_label(self, path):
        index = self._media_directory_index(path)
        if index < 0:
            return path
        return self._media_directory_label(self.media_directories[index])

    def _refresh_media_directory_list(self, listbox, select_path=None, select_import=False):
        """Redraw the list. Row 0 is always the import path."""
        current = select_path
        keep_import = select_import
        if current is None and not keep_import:
            selection = listbox.curselection()
            if selection:
                if selection[0] == 0:
                    keep_import = True
                else:
                    media_index = selection[0] - 1
                    if 0 <= media_index < len(self.media_directories):
                        current = self.media_directories[media_index]["path"]
        listbox.delete(0, "end")
        listbox.insert("end", self._import_path_label())
        for item in self.media_directories:
            listbox.insert("end", self._media_directory_label(item))
        self._mark_import_path_row(listbox)
        if keep_import or not current:
            listbox.selection_set(0)
            listbox.activate(0)
            listbox.see(0)
            return
        index = self._media_directory_index(current)
        row = index + 1 if index >= 0 else 0
        listbox.selection_set(row)
        listbox.activate(row)
        listbox.see(row)

    def _load_media_directory_name_field(self, listbox):
        entry = getattr(self, "_media_dir_name_entry", None)
        var = getattr(self, "_media_dir_name_var", None)
        if entry is None or var is None:
            return
        selection = listbox.curselection()
        self._media_dir_name_guard = True
        try:
            if not selection:
                self._media_dir_name_index = None
                var.set("")
                entry.configure(state="disabled")
                return
            index = selection[0]
            media_index = index - 1
            if index < 1 or not 0 <= media_index < len(self.media_directories):
                self._media_dir_name_index = None
                var.set("")
                entry.configure(state="disabled")
                return
            self._media_dir_name_index = index
            entry.configure(state="normal")
            var.set(self.media_directories[media_index]["name"])
        finally:
            self._media_dir_name_guard = False

    def _focus_media_directory_name(self):
        window = getattr(self, "media_dirs_window", None)
        listbox = getattr(window, "_listbox", None) if window is not None else None
        if listbox is not None:
            try:
                selection = listbox.curselection()
            except tk.TclError:
                selection = ()
            if selection and selection[0] == 0:
                self._choose_import_path(window)
                return
        entry = getattr(self, "_media_dir_name_entry", None)
        if entry is None:
            return
        try:
            if str(entry.cget("state")) == "disabled":
                return
            entry.focus_set()
            entry.icursor("end")
            entry.selection_range(0, "end")
        except tk.TclError:
            pass

    def _on_media_directory_select(self, _event=None):
        if getattr(self, "_media_dir_name_guard", False):
            return
        window = getattr(self, "media_dirs_window", None)
        listbox = getattr(window, "_listbox", None) if window is not None else None
        if listbox is None:
            return
        selection = listbox.curselection()
        new_index = selection[0] if selection else None
        if new_index == self._media_dir_name_index:
            return
        self._commit_media_directory_name()
        self._load_media_directory_name_field(listbox)

    def _replace_media_directory_row(self, listbox, index):
        """Update one media-folder row without moving the current selection.

        ``index`` is the listbox row. Row 0 is the import path.
        """
        media_index = (index or 0) - 1
        if listbox is None or index < 1 or not 0 <= media_index < len(self.media_directories):
            return
        try:
            if index >= listbox.size():
                return
            selected = list(listbox.curselection())
        except tk.TclError:
            return
        self._media_dir_name_guard = True
        try:
            listbox.delete(index)
            listbox.insert(index, self._media_directory_label(self.media_directories[media_index]))
            self._mark_import_path_row(listbox)
            listbox.selection_clear(0, "end")
            for item in selected:
                if 0 <= item < listbox.size():
                    listbox.selection_set(item)
            if selected and 0 <= selected[0] < listbox.size():
                listbox.activate(selected[0])
        except tk.TclError:
            pass
        finally:
            self._media_dir_name_guard = False

    def _commit_media_directory_name(self, _event=None):
        if getattr(self, "_media_dir_name_guard", False):
            return "break"
        index = getattr(self, "_media_dir_name_index", None)
        var = getattr(self, "_media_dir_name_var", None)
        media_index = (index if isinstance(index, int) else 0) - 1
        if index is None or var is None or index < 1:
            return "break"
        if not 0 <= media_index < len(self.media_directories):
            return "break"
        name = var.get().strip()
        if name == self.media_directories[media_index]["name"]:
            if var.get() != name:
                self._media_dir_name_guard = True
                try:
                    var.set(name)
                finally:
                    self._media_dir_name_guard = False
            return "break"
        self.media_directories[media_index]["name"] = name
        self._save_media_directories()
        if var is not None and 0 <= media_index < len(self.media_directories):
            stored = self.media_directories[media_index]["name"]
            if var.get() != stored:
                self._media_dir_name_guard = True
                try:
                    var.set(stored)
                finally:
                    self._media_dir_name_guard = False
        window = getattr(self, "media_dirs_window", None)
        listbox = getattr(window, "_listbox", None) if self._media_dirs_window_alive() else None
        self._replace_media_directory_row(listbox, index)
        return "break"

    def _add_media_directory(self, window, listbox):
        self._commit_media_directory_name()
        options = {"parent": window, "title": t("media_directories_add")}
        start = self._preferred_import_dir()
        if start:
            options["initialdir"] = start
        path = filedialog.askdirectory(**options)
        if not path:
            return
        path = os.path.abspath(path)
        if self._media_directory_index(path) < 0:
            self.media_directories.append({"path": path, "name": ""})
            self._save_media_directories()
        self._refresh_media_directory_list(listbox, select_path=path)
        self._load_media_directory_name_field(listbox)
        self._focus_media_directory_name()

    def _remove_media_directory(self, listbox):
        selection = listbox.curselection()
        if not selection or selection[0] < 1:
            return
        media_index = selection[0] - 1
        self._media_dir_name_index = None
        del self.media_directories[media_index]
        self._save_media_directories()
        next_path = ""
        if self.media_directories:
            next_path = self.media_directories[min(media_index, len(self.media_directories) - 1)]["path"]
        self._refresh_media_directory_list(listbox, select_path=next_path or None, select_import=not next_path)
        self._load_media_directory_name_field(listbox)

    def _close_media_dirs_window(self):
        self._commit_media_directory_name()
        window = getattr(self, "media_dirs_window", None)
        self.media_dirs_window = None
        self._media_dir_name_var = None
        self._media_dir_name_entry = None
        self._media_dir_name_index = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def remember_playlist_dir(self, path):
        directory = path if os.path.isdir(path) else os.path.dirname(path)
        if not directory or not os.path.isdir(directory):
            return
        self.last_playlist_dir = directory
        self.settings["last_playlist_dir"] = directory
        if os.path.isfile(path):
            self.last_playlist_path = os.path.abspath(path)
            self.settings["last_playlist_path"] = self.last_playlist_path
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def playlist_dialog_options(self):
        """Open playlist dialogs in the last used playlist folder."""
        options = {}
        directory = ""
        if self.playlist_path:
            directory = os.path.dirname(self.playlist_path)
        if not directory or not os.path.isdir(directory):
            directory = self.last_playlist_dir
        if not directory or not os.path.isdir(directory):
            directory = self.last_import_dir
        if directory and os.path.isdir(directory):
            options["initialdir"] = directory
        return options

    def _import_folder_choices(self):
        """Saved folders that exist, plus mounted drives that are not saved yet."""
        saved = [item for item in self.media_directories if os.path.isdir(item["path"])]
        try:
            volumes = list_removable_volumes()
        except OSError:
            volumes = []
        return merge_import_directories(saved, volumes)

    def _import_choice_text(self, row):
        index = self._media_directory_index(row["path"])
        if index >= 0:
            return self._media_directory_label(self.media_directories[index])
        name = (row.get("name") or "").strip()
        if name:
            return f"{name}  —  {row['path']}"
        return row["path"]

    def _import_window_items(self, choices):
        """Import path first, then saved folders and drives without that duplicate."""
        pinned = ""
        if self._import_path_ready():
            try:
                pinned = os.path.abspath(self.import_path)
            except (OSError, ValueError):
                pinned = self.import_path or ""
        items = [{
            "path": pinned,
            "text": self._import_path_label(),
            "removable": False,
            "pinned": True,
        }]
        for row in choices:
            folder = row["path"]
            try:
                key = os.path.abspath(folder)
            except (OSError, ValueError):
                key = folder
            if pinned and key == pinned:
                continue
            items.append({
                "path": folder,
                "text": self._import_choice_text(row),
                "removable": row["removable"],
            })
        return items

    def _import_choice_index(self, items):
        """Row whose folder contains the last import, or the import path."""
        last = getattr(self, "last_import_dir", "") or ""
        if last and os.path.isdir(last):
            try:
                abs_last = os.path.abspath(last)
            except (OSError, ValueError):
                abs_last = last
            best = -1
            best_len = -1
            for index, item in enumerate(items):
                folder = item.get("path") or ""
                if not folder:
                    continue
                try:
                    if os.path.commonpath([abs_last, folder]) == folder and len(folder) > best_len:
                        best = index
                        best_len = len(folder)
                except ValueError:
                    continue
            if best >= 0:
                return best
        return 0

    def import_media(self):
        choices = self._import_folder_choices()
        if not choices:
            self._import_files_or_directory(self._preferred_import_dir())
            return
        choice = self._choose_import_action(choices)
        if not choice:
            return
        mode, directory, removable = choice
        copy_stem = ""
        if mode != "other" and removable:
            action = self._ask_link_or_copy()
            if not action:
                return
            if action == "copy":
                copy_stem = self._prompt_playlist_folder_name()
                if not copy_stem:
                    return
        if mode == "folder":
            options = {"title": t("import_directory")}
            if directory and os.path.isdir(directory):
                options["initialdir"] = directory
            chosen = filedialog.askdirectory(**options)
            if chosen:
                self._import_directory(chosen, copy_stem=copy_stem)
            return
        if mode == "other":
            self._import_files_or_directory(self.last_import_dir)
            return
        self._import_files_or_directory(directory, folder_fallback=False, copy_stem=copy_stem)

    def _choose_import_action(self, choices):
        """Let the operator pick a saved folder or a plugged-in drive."""
        result = {"choice": None}
        window = tk.Toplevel(self.root)
        window.title(t("media_directories_choose"))
        window.configure(bg=COLOR_BG)
        window.minsize(520, 280)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        body = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=(10, 0))

        tk.Label(
            body,
            text=t("media_directories_hint") + "\n" + t("media_directories_drives"),
            bg=COLOR_BG, fg=COLOR_MUTED, font=FONT_SMALL, wraplength=600, justify="left",
        ).pack(fill="x", pady=(0, 6))

        holder = tk.Frame(body, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, pady=(0, 8))
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        folder_list = ImportFolderList(holder)
        folder_list.grid(row=0, column=0, sticky="nsew")
        items = self._import_window_items(choices)
        folder_list.set_items(items)
        folder_list.select(self._import_choice_index(items))
        window._import_list = folder_list

        def finish(mode, directory="", removable=False):
            result["choice"] = (mode, directory, bool(removable))
            window.destroy()

        def selected_directory():
            return folder_list.selected_path()

        def import_files(_event=None):
            directory = selected_directory()
            if directory:
                finish("files", directory, folder_list.selected_removable())

        def import_folder():
            directory = selected_directory()
            if not directory:
                return
            finish("folder", directory, folder_list.selected_removable())

        def cancel():
            result["choice"] = None
            window.destroy()

        def activate_row(_index):
            import_files()

        folder_list.on_activate = activate_row
        window.bind("<Escape>", lambda _event: cancel())
        window.bind("<Up>", lambda _event: folder_list._move(-1))
        window.bind("<Down>", lambda _event: folder_list._move(1))
        window.bind("<Return>", import_files)
        window.protocol("WM_DELETE_WINDOW", cancel)

        tk.Button(
            buttons, text=t("media_directories_import_files"),
            command=import_files, font=FONT_UI,
        ).pack(side="left")
        tk.Button(
            buttons, text=t("media_directories_import_folder"),
            command=import_folder, font=FONT_UI,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("media_directories_other"),
            command=lambda: finish("other"), font=FONT_UI,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("media_directories_close"),
            command=cancel, font=FONT_UI,
        ).pack(side="right")

        self._bind_popup_wheel(window, body)
        self._open_popup(window, 680, 560)
        folder_list.focus_set()
        self._grab_popup(window)
        self.root.wait_window(window)
        return result["choice"]

    def _ask_link_or_copy(self):
        """Ask whether a removable drive is linked or copied.

        Returns ``"link"``, ``"copy"``, or ``None`` when the dialog is closed.
        Copy stays unavailable until an import path exists.
        """
        result = {"action": None}
        window = tk.Toplevel(self.root)
        window.title(t("import_link_or_copy_title"))
        window.configure(bg=COLOR_BG)
        window.minsize(460, 180)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        body = tk.Frame(window, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        tk.Label(
            body, text=t("import_link_or_copy"), bg=COLOR_BG, fg=COLOR_TEXT,
            font=FONT_UI, wraplength=480, justify="left",
        ).pack(fill="x")
        warning = tk.Label(
            body, text=t("import_path_required"), bg=COLOR_BG, fg=COLOR_WARNING,
            font=FONT_SMALL, wraplength=480, justify="left",
        )
        if not self._import_path_ready():
            warning.pack(fill="x", pady=(10, 0))

        def show_warning():
            if not warning.winfo_manager():
                warning.pack(fill="x", pady=(10, 0))
            try:
                window.update_idletasks()
            except tk.TclError:
                pass

        def choose_copy():
            if not self._import_path_ready():
                show_warning()
                return
            result["action"] = "copy"
            window.destroy()

        def choose_link():
            result["action"] = "link"
            window.destroy()

        def cancel():
            result["action"] = None
            window.destroy()

        tk.Button(buttons, text=t("import_link"), command=choose_link, font=FONT_UI).pack(side="left")
        tk.Button(buttons, text=t("import_copy"), command=choose_copy, font=FONT_UI).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("media_directories_close"), command=cancel, font=FONT_UI,
        ).pack(side="right")
        window.bind("<Escape>", lambda _event: cancel())
        window.protocol("WM_DELETE_WINDOW", cancel)
        self._open_popup(window, 520, 220)
        self._grab_popup(window)
        self.root.wait_window(window)
        return result["action"]

    def _prompt_playlist_folder_name(self):
        """Return a folder stem, asking when the playlist field is still a placeholder."""
        stem = playlist_folder_name(self._current_playlist_name())
        if stem:
            return stem
        stem = self._ask_playlist_name()
        if not stem:
            return ""
        self._set_playlist_name(f"{stem}.pls")
        return stem

    def _ask_playlist_name(self):
        """Dark prompt for a playlist folder name. None means the operator cancelled."""
        result = {"name": None}
        window = tk.Toplevel(self.root)
        window.title(t("import_playlist_name_title"))
        window.configure(bg=COLOR_BG)
        window.minsize(460, 160)
        if getattr(self, "icon_image", None) is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        body = tk.Frame(window, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        tk.Label(
            body, text=t("import_playlist_name_prompt"),
            bg=COLOR_BG, fg=COLOR_TEXT, font=FONT_UI,
            wraplength=460, justify="left",
        ).pack(fill="x")
        entry = tk.Entry(
            body, font=FONT_UI, bg=COLOR_FIELD, fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT, relief="flat",
            highlightthickness=1, highlightbackground=COLOR_BORDER, highlightcolor=ACCENT,
        )
        entry.pack(fill="x", pady=(10, 0))
        warning = tk.Label(
            body, text=t("import_playlist_name_invalid"),
            bg=COLOR_BG, fg=COLOR_WARNING, font=FONT_SMALL,
            wraplength=460, justify="left",
        )

        def show_invalid():
            if not warning.winfo_manager():
                warning.pack(fill="x", pady=(8, 0))

        def accept(_event=None):
            stem = playlist_folder_name(entry.get())
            if not stem:
                show_invalid()
                return "break"
            result["name"] = stem
            window.destroy()
            return "break"

        def cancel(_event=None):
            window.destroy()
            return "break"

        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        def styled(text, command):
            return tk.Button(
                buttons, text=text, command=command, font=FONT_UI,
                bg=COLOR_BUTTON, fg=COLOR_TEXT,
                activebackground=COLOR_BUTTON_ACTIVE, activeforeground=COLOR_TEXT,
                highlightthickness=0, bd=0, padx=12, pady=4, cursor="hand2",
            )

        styled(t("ok"), accept).pack(side="left")
        styled(t("quit_cancel"), cancel).pack(side="left", padx=(8, 0))
        entry.bind("<Return>", accept)
        window.bind("<Escape>", cancel)
        window.protocol("WM_DELETE_WINDOW", cancel)
        self._open_popup(window, 520, 200)
        self._grab_popup(window)
        entry.focus_set()
        self.root.wait_window(window)
        return result["name"]

    def _import_dialog_options(self, directory):
        options = {"parent": self.root}
        if directory and os.path.isdir(directory):
            options["initialdir"] = directory
        return options

    def _import_files_or_directory(self, directory, folder_fallback=True, copy_stem=""):
        dialog_options = self._import_dialog_options(directory)
        paths = filedialog.askopenfilenames(
            title=t("import_media"),
            filetypes=self._media_filetypes(),
            **dialog_options,
        )
        if paths:
            self.remember_import_dir(paths[0])
            self._add_imported_paths(paths, copy_stem=copy_stem)
            return
        if not folder_fallback:
            return
        folder = filedialog.askdirectory(
            title=t("import_directory"),
            **dialog_options,
        )
        if folder:
            self._import_directory(folder, copy_stem=copy_stem)

    def _import_directory(self, directory, copy_stem=""):
        if not directory or not os.path.isdir(directory):
            return
        self.remember_import_dir(directory)
        self._add_imported_paths(self._media_paths_in_directory(directory), copy_stem=copy_stem)

    def _add_imported_paths(self, paths, copy_stem=""):
        playlist_paths = list(paths)
        copied_dir = ""
        if copy_stem:
            playlist_paths, copied_dir = self._copy_removable_imports(paths, copy_stem)
            if playlist_paths is None:
                return
        for path in playlist_paths:
            self.add_media(path)
        if self.playlist and self.preview_index is None:
            self.program_index = 0
            self.apply_beamer_mode_for_pointer()
        self.refresh_all()
        if copied_dir:
            self._save_playlist_into(copied_dir, copy_stem)

    def _copy_removable_imports(self, paths, copy_stem):
        """Copy files that sit on a removable volume into the playlist folder.

        Internal files stay linked. Returns ``(playlist_paths, copied_dir)``.
        ``playlist_paths`` is ``None`` when the import folder cannot be created.
        ``copied_dir`` is set only after at least one file was copied.
        """
        try:
            volumes = list_removable_volumes()
        except OSError:
            volumes = []
        removable = []
        linked = []
        for path in paths:
            if path_is_on_removable_volume(path, volumes):
                removable.append(path)
            else:
                linked.append(path)
        if not removable:
            return list(paths), ""
        if not self._import_path_ready():
            messagebox.showerror(t("copy_files"), t("import_path_required"))
            return None, ""
        dest_dir = os.path.join(self.import_path, copy_stem)
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(t("copy_files"), t("import_folder_failed", error=exc))
            return None, ""
        copied = self._copy_imported_paths(removable, dest_dir)
        if len(copied) != len(removable):
            return None, ""
        playlist_paths = []
        copied_any = False
        copy_index = 0
        for path in paths:
            if path_is_on_removable_volume(path, volumes):
                dest = copied[copy_index]
                copy_index += 1
                if dest:
                    playlist_paths.append(dest)
                    copied_any = True
            else:
                playlist_paths.append(path)
        return playlist_paths, dest_dir if copied_any else ""

    def _save_playlist_into(self, directory, stem):
        path = os.path.join(directory, f"{stem}.pls")
        try:
            self._write_playlist(path)
        except OSError as exc:
            messagebox.showerror(t("save_playlist"), t("import_playlist_save_failed", error=exc))
            return
        self.playlist_path = path
        self._set_playlist_name(os.path.basename(path))
        self.remember_playlist_dir(path)

    def add_media(self, path):
        try:
            entry = probe_media(path)
        except Exception as exc:
            messagebox.showerror(t("import_error"), f"{os.path.basename(path)}\n{exc}")
            return
        try:
            if not self.output_manager.video_output:
                self.output_manager.select_video_output()
            video = self.output_manager.get_video_info(path) if not entry.is_image else None
            if video:
                mode, matched = self.output_manager.find_best_mode(
                    video, create=False, pad_16x9=self._pad_16x9_enabled(),
                )
                entry.refresh_ok = matched
        except Exception:
            entry.refresh_ok = False
        self.playlist.append(entry)

    def new_playlist(self):
        """Create an empty playlist in a new folder under the import path."""
        if self.playlist or self.playlist_path:
            if not messagebox.askyesno(t("new_playlist_title"), t("new_playlist_message")):
                return False
        if not self._ensure_import_path():
            return False
        stem = self._ask_playlist_name()
        if not stem:
            return False
        return self._install_new_playlist(stem)

    def _install_new_playlist(self, stem):
        folder = os.path.join(self.import_path, stem)
        path = os.path.join(folder, f"{stem}.pls")
        if os.path.exists(path):
            messagebox.showerror(t("new_playlist"), t("playlist_exists", name=stem))
            return False
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        self.program_state = "OFF"
        self.calibration_mode = None
        self.volume_setup = False
        self.playlist = []
        self.playlist_path = ""
        self.program_index = 0
        self.zoom_confirmed_index = None
        self.preview_index = None
        self.preview_live = True
        self.preview_mpv.stop()
        self._reset_preview_meter()
        self.main_mpv.set_audio_delay(0)
        self._show_audiosync_controls(False)
        self._close_audiosync_list_window()
        self.blank_output()
        try:
            os.makedirs(folder, exist_ok=True)
            self._write_playlist(path)
        except OSError as exc:
            messagebox.showerror(t("save_playlist"), t("import_playlist_save_failed", error=exc))
            return False
        self.playlist_path = path
        self._set_playlist_name(os.path.basename(path))
        self.remember_playlist_dir(path)
        self.refresh_all()
        self._remember_saved_playlist()
        return True

    def start_volume_setup(self):
        """Arm the current playlist so house volume can be set."""
        if self.program_state == "PLAYING":
            return False
        if not self.playlist:
            if not getattr(self, "_remote_action", False):
                messagebox.showinfo(t("volume_setup"), t("volume_setup_empty"))
            return False
        if self.volume_setup:
            return True
        self.volume_setup = True
        if self.program_state == "OFF":
            self.program_state = "PROGRAM"
            self._skip_to_playable(inclusive=True)
            self.ensure_main_output()
            self.blank_output()
        self.refresh_all()
        return True

    def _exit_volume_setup(self):
        if not getattr(self, "volume_setup", False):
            return
        if getattr(self, "autoplay_after_id", None):
            try:
                self.root.after_cancel(self.autoplay_after_id)
            except tk.TclError:
                pass
            self.autoplay_after_id = None
        self._cancel_light_after("lights_play_after")
        self.volume_setup = False
        self.program_state = "OFF"
        self.blank_output()
        self._apply_lights("bright")
        self.refresh_all()

    def start_video_calibration(self):
        self._start_calibration_mode("video")

    def start_audio_calibration(self):
        self._start_calibration_mode("audio")

    def _calibration_state_key(self, kind=None):
        kind = self.calibration_mode if kind is None else kind
        if kind == "video":
            return "state_video_calibration"
        if kind == "audio":
            return "state_audio_calibration"
        return ""

    def _calibration_spec(self, kind=None):
        kind = self.calibration_mode if kind is None else kind
        if kind == "video":
            return {
                "folder": TESTDATA_DIR,
                "warning": "calibration_video_warning",
                "missing": "calibration_video_missing",
                "empty": "calibration_video_empty",
                "stop": "calibration_video_stop",
                "playlist": "testdata.pls",
            }
        if kind == "audio":
            return {
                "folder": AUDIOSYNC_DIR,
                "warning": "calibration_audio_warning",
                "missing": "calibration_audio_missing",
                "empty": "calibration_audio_empty",
                "stop": "calibration_audio_stop",
                "playlist": "audiosync.pls",
            }
        return {}

    def _load_calibration_playlist_entries(self, path, title):
        name = os.path.basename(path)
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror(title, t("calibration_playlist_error", name=name, error=exc))
            return None
        if not isinstance(data, dict):
            messagebox.showerror(title, t("calibration_playlist_error", name=name, error=""))
            return None
        entries = playlist_entries(data.get("entries", []))
        if not entries:
            messagebox.showerror(title, t("calibration_playlist_empty", name=name))
            return None
        return entries

    def _start_calibration_mode(self, kind, playlist_path=None):
        """Replace the playlist with calibration clips and arm the program."""
        if self.program_state != "OFF" and not self.calibration_mode:
            return
        spec = self._calibration_spec(kind)
        title = t(self._calibration_state_key(kind))
        if playlist_path:
            warning = t(
                "calibration_playlist_warning",
                mode=title,
                name=os.path.basename(playlist_path),
            )
        else:
            warning = t(spec["warning"])
        if not messagebox.askyesno(title, warning):
            return
        entries = None
        paths = []
        if playlist_path:
            entries = self._load_calibration_playlist_entries(playlist_path, title)
            if not entries:
                return
            display_name = os.path.basename(playlist_path)
        else:
            folder = spec["folder"]
            if not os.path.isdir(folder):
                messagebox.showerror(title, t(spec["missing"]))
                return
            paths = [
                os.path.join(folder, name)
                for name in sorted(os.listdir(folder))
                if os.path.splitext(name)[1].lower() in VIDEO_EXTS
            ]
            if not paths:
                messagebox.showerror(title, t(spec["empty"]))
                return
            display_name = spec["playlist"]
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        if self.calibration_mode:
            self.program_state = "PROGRAM"
            self.blank_output(show_idle=False)
            if kind != "audio":
                self._close_audiosync_list_window()
        self.playlist = []
        self.playlist_path = playlist_path or ""
        self.program_index = 0
        self.zoom_confirmed_index = None
        self.preview_index = None
        self.preview_live = True
        self.preview_mpv.stop()
        self._reset_preview_meter()
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, display_name)
        if entries is not None:
            self.playlist = entries
            self._scan_playlist_media()
        else:
            for path in paths:
                self.add_media(path)
        for entry in self.playlist:
            if not entry.is_image:
                entry.loop = True
        if not self.playlist:
            messagebox.showerror(
                title,
                t("calibration_playlist_empty", name=display_name) if playlist_path else t(spec["empty"]),
            )
            return
        self.calibration_mode = kind
        self.program_state = "PROGRAM"
        self.program_index = 0
        self.apply_beamer_mode_for_pointer()
        self.ensure_main_output()
        self.blank_output()
        self._show_audiosync_controls(kind == "audio")
        if kind == "audio":
            self._sync_audiosync_slider(self.current_entry(), force=True)
        self.refresh_all()

    def _exit_calibration_mode(self):
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        self.calibration_mode = None
        self.program_state = "OFF"
        self.playlist = []
        self.playlist_path = ""
        self.program_index = 0
        self.zoom_confirmed_index = None
        self.preview_index = None
        self.preview_live = True
        self.preview_mpv.stop()
        self._reset_preview_meter()
        self.main_mpv.set_audio_delay(0)
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, t("playlist_untitled"))
        self._show_audiosync_controls(False)
        self._close_audiosync_list_window()
        self.blank_output()
        self.refresh_all()
        self._remember_saved_playlist()

    def _show_audiosync_controls(self, visible):
        frame = getattr(self, "audiosync_frame", None)
        if frame is None:
            return
        if visible:
            frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 0))
        else:
            frame.grid_forget()
        readout = getattr(self, "program_delay_readout", None)
        if readout is not None and visible:
            readout.config(text="")
            self._apply_volume_setup_chrome()

    @staticmethod
    def _normalize_audiosync_delays(raw):
        delays = {}
        items = raw.items() if isinstance(raw, dict) else []
        if isinstance(raw, dict) and "delays" in raw and isinstance(raw["delays"], dict):
            items = raw["delays"].items()
        for key, value in items:
            if key in ("delays",):
                continue
            try:
                delays[str(key)] = snap_delay_ms(value)
            except (TypeError, ValueError):
                continue
        return delays

    def _save_audiosync_delays(self):
        self.settings["audiosync_delays"] = dict(self.audiosync_delays)
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _audiosync_key_for_entry(self, entry):
        if not entry or entry.is_image:
            return ""
        return audiosync_format_key(entry.width, entry.height, entry.fps)

    def _audiosync_lookup(self, entry):
        key = self._audiosync_key_for_entry(entry)
        if not key or key not in self.audiosync_delays:
            return None
        return self.audiosync_delays[key]

    def _refresh_program_delay_readout(self, entry):
        readout = getattr(self, "program_delay_readout", None)
        if readout is None:
            return
        if self.calibration_mode == "audio":
            readout.config(text="")
        else:
            delay = self._audiosync_lookup(entry)
            readout.config(text=format_delay_ms(delay) if delay is not None else "")
        self._apply_volume_setup_chrome()

    def _sync_audiosync_slider(self, entry, force=False):
        bar = getattr(self, "audiosync_delay_bar", None)
        if bar is None or self.calibration_mode != "audio":
            return
        if bar.dragging and not force:
            return
        delay = self._audiosync_lookup(entry)
        ms = 0 if delay is None else delay
        if not force and ms == int(self.audiosync_delay_ms.get()):
            return
        self.audiosync_delay_ms.set(ms)
        bar.set_delay(ms)
        label = getattr(self, "audiosync_delay_label", None)
        if label is not None:
            label.config(text=format_delay_ms(ms))

    def _on_audiosync_delay(self, value):
        ms = snap_delay_ms(value)
        self.audiosync_delay_ms.set(ms)
        label = getattr(self, "audiosync_delay_label", None)
        if label is not None:
            label.config(text=format_delay_ms(ms))
        entry = self.current_entry()
        key = self._audiosync_key_for_entry(entry)
        if key:
            self.audiosync_delays[key] = ms
            self._save_audiosync_delays()
        if self.program_state == "PLAYING" and not self.idle_showing:
            self.main_mpv.set_audio_delay(ms / 1000.0)

    def _nudge_audiosync_delay(self, delta):
        bar = getattr(self, "audiosync_delay_bar", None)
        if bar is None:
            return
        bar.set_delay(int(self.audiosync_delay_ms.get()) + delta, notify=True)

    def _apply_program_audio_delay(self, entry):
        if self.calibration_mode == "audio":
            ms = int(self.audiosync_delay_ms.get())
        else:
            delay = self._audiosync_lookup(entry)
            ms = 0 if delay is None else delay
        self.main_mpv.set_audio_delay(ms / 1000.0)

    def _audiosync_outputs(self):
        """Projector connector and program sound device the delays were measured on."""
        manager = getattr(self, "output_manager", None)
        if manager is None:
            return {"beamer_hdmi": "", "audio_output": ""}
        video = str(getattr(manager, "video_output", "") or "")
        audio = ""
        try:
            if manager.audio_patch_is_off("beamer"):
                audio = AUDIO_PATCH_NONE
            else:
                audio = manager.program_audio_device(getattr(self, "mpv_path", "") or "") or ""
        except Exception:
            audio = normalize_audio_patch_choice(
                getattr(getattr(manager, "audio_patch", None), "get", lambda *_a: "")("beamer")
            )
        return {"beamer_hdmi": video, "audio_output": audio}

    def _audiosync_payload(self):
        payload = {"delays": dict(sorted(self.audiosync_delays.items()))}
        payload.update(self._audiosync_outputs())
        return payload

    def _apply_audiosync_outputs(self, data):
        """Restore the Beamer HDMI connector and program audio device from a delay file."""
        if not isinstance(data, dict):
            return
        manager = getattr(self, "output_manager", None)
        if manager is None:
            return
        if "audio_output" in data:
            raw = str(data.get("audio_output") or "").strip()
            if raw:
                patch = dict(getattr(manager, "audio_patch", {}) or {})
                patch["beamer"] = normalize_audio_patch_choice(raw)
                manager.set_audio_patch(patch)
                settings = getattr(self, "settings", None)
                if isinstance(settings, dict):
                    settings["audio_patch"] = dict(manager.audio_patch)
                    try:
                        save_settings(settings)
                    except OSError:
                        pass
                apply_audio = getattr(self, "_apply_main_audio_device", None)
                if callable(apply_audio):
                    apply_audio()
        video = str(data.get("beamer_hdmi") or "").strip() if "beamer_hdmi" in data else ""
        current = str(getattr(manager, "video_output", "") or "")
        if video and video != current:
            self.apply_beamer_output(video)

    def show_audiosync_delays(self):
        window = getattr(self, "audiosync_list_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    self._fill_audiosync_list(window)
                    window.deiconify()
                    self._present_popup(window)
                    return
            except tk.TclError:
                self.audiosync_list_window = None
        window = tk.Toplevel(self.root)
        window.title(t("audiosync_list_title"))
        window.configure(bg=COLOR_BG)
        window.minsize(420, 240)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_audiosync_list_window)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        body = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=10)
        holder = tk.Frame(body, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        listbox = self._styled_listbox(holder)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        tk.Button(
            buttons, text=t("media_directories_close"),
            command=self._close_audiosync_list_window, font=FONT_UI,
        ).pack(side="right")
        window._listbox = listbox
        self.audiosync_list_window = window
        self._fill_audiosync_list(window)
        self._bind_popup_wheel(window, body)
        self._open_popup(window, 520, 360)

    def _fill_audiosync_list(self, window):
        listbox = window._listbox
        listbox.delete(0, "end")
        if not self.audiosync_delays:
            listbox.insert("end", t("audiosync_list_empty"))
            return
        for key in sorted(self.audiosync_delays):
            listbox.insert(
                "end",
                t("audiosync_list_row", format=key, delay=format_delay_ms(self.audiosync_delays[key])),
            )

    def _close_audiosync_list_window(self):
        window = getattr(self, "audiosync_list_window", None)
        self.audiosync_list_window = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def load_audiosync_delays(self):
        path = filedialog.askopenfilename(
            title=t("audiosync_load_title"),
            initialdir=AUDIOSYNC_DIR,
            filetypes=[("JSON", "*.json"), (t("all_files"), "*.*")],
            parent=self.root,
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            messagebox.showerror(t("audiosync"), t("audiosync_load_error"))
            return
        self.audiosync_delays = self._normalize_audiosync_delays(data)
        self._save_audiosync_delays()
        self._apply_audiosync_outputs(data)
        self._sync_audiosync_slider(self.current_entry(), force=True)
        self._refresh_program_delay_readout(self.current_entry())
        if self.program_state == "PLAYING":
            self._apply_program_audio_delay(self.current_entry())
        window = getattr(self, "audiosync_list_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    self._fill_audiosync_list(window)
            except tk.TclError:
                pass

    def save_audiosync_delays(self):
        path = filedialog.asksaveasfilename(
            title=t("audiosync_save_title"),
            defaultextension=".json",
            initialdir=AUDIOSYNC_DIR,
            initialfile="audiosync.json",
            filetypes=[("JSON", "*.json")],
            parent=self.root,
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(self._audiosync_payload(), handle, indent=2)
        except OSError as exc:
            messagebox.showerror(t("audiosync"), t("audiosync_save_error", error=exc))

    def load_playlist(self):
        self.show_playlist_library()

    def _offer_playlist_library(self):
        """After start, offer the playlists stored in the import path."""
        if getattr(self, "playlist_path", ""):
            return
        self.show_playlist_library()

    def show_playlist_library(self):
        """List playlists in the import path so one can be opened or created."""
        if self._playlist_library_alive():
            self.playlist_library_window.deiconify()
            self._present_popup(self.playlist_library_window)
            return
        if not self._ensure_import_path():
            return
        window = tk.Toplevel(self.root)
        window.title(t("playlist_library"))
        window.configure(bg=COLOR_BG)
        window.minsize(560, 340)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        body = self._install_popup_scroll(window, COLOR_BG, padx=10, pady=(10, 0))
        path_label = tk.Label(
            body, text=self._import_path_label(), bg=COLOR_BG, fg=ACCENT,
            font=FONT_UI, wraplength=760, justify="left", anchor="w",
        )
        path_label.pack(fill="x", pady=(0, 4))
        tk.Label(
            body, text=t("playlist_library_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=640, justify="left",
        ).pack(fill="x", pady=(0, 6))
        status = tk.Label(
            body, text="", bg=COLOR_BG, fg=COLOR_WARNING,
            font=FONT_SMALL, wraplength=640, justify="left", anchor="w",
        )
        status.pack(fill="x", pady=(0, 6))
        holder = tk.Frame(body, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, pady=(0, 8))
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        listbox = self._styled_listbox(holder)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        def open_selected(_event=None):
            self._open_library_playlist(window)
            return "break"

        open_button = tk.Button(
            buttons, text=t("playlist_library_open"), command=open_selected, font=FONT_UI,
        )
        open_button.pack(side="left")
        tk.Button(
            buttons, text=t("playlist_library_new"),
            command=lambda: self._new_library_playlist(window), font=FONT_UI,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("playlist_library_import"),
            command=lambda: self._import_library_playlist(window), font=FONT_UI,
        ).pack(side="left", padx=(8, 0))
        export_button = tk.Button(
            buttons, text=t("playlist_library_export"),
            command=lambda: self._export_library_playlist(window), font=FONT_UI,
        )
        export_button.pack(side="left", padx=(8, 0))
        delete_media = tk.Button(
            buttons, text=t("edit_imports_delete_media"),
            command=lambda: self._delete_import_media(window), font=FONT_UI,
        )
        delete_media.pack(side="left", padx=(8, 0))
        delete_folder = tk.Button(
            buttons, text=t("edit_imports_delete_folder"),
            command=lambda: self._delete_import_folder(window), font=FONT_UI,
        )
        delete_folder.pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("media_directories_close"),
            command=self._close_playlist_library, font=FONT_UI,
        ).pack(side="right")

        window._path_label = path_label
        window._status = status
        window._listbox = listbox
        window._rows = []
        window._open_button = open_button
        window._export_button = export_button
        window._delete_media = delete_media
        window._delete_folder = delete_folder
        self.playlist_library_window = window
        listbox.bind("<Double-Button-1>", open_selected)
        listbox.bind("<Return>", open_selected)
        listbox.bind("<<ListboxSelect>>", lambda _event: self._sync_library_media_button(window))
        window.bind("<Escape>", lambda _event: self._close_playlist_library())
        window.protocol("WM_DELETE_WINDOW", self._close_playlist_library)
        self._refresh_playlist_library(window)
        self._bind_popup_wheel(window, body)
        self._open_popup(window, 860, 480)
        listbox.focus_set()
        self._grab_popup(window)
        self.root.wait_window(window)

    def _playlist_library_alive(self):
        window = getattr(self, "playlist_library_window", None)
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            self.playlist_library_window = None
            return False

    def _close_playlist_library(self):
        window = getattr(self, "playlist_library_window", None)
        self.playlist_library_window = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _refresh_playlist_library(self, window, select_path=None):
        rows = library_playlists(self.import_path)
        window._rows = rows
        path_label = getattr(window, "_path_label", None)
        if path_label is not None:
            try:
                path_label.configure(text=self._import_path_label())
            except tk.TclError:
                pass
        status = window._status
        status.configure(text="" if rows else t("playlist_library_empty"))
        listbox = window._listbox
        listbox.delete(0, "end")
        for row in rows:
            listbox.insert("end", self._playlist_library_line(row))
        state = "normal" if rows else "disabled"
        window._open_button.configure(state=state)
        window._export_button.configure(state=state)
        window._delete_folder.configure(state=state)
        if not rows:
            window._delete_media.configure(state="disabled")
            return
        index = 0
        if select_path:
            for position, row in enumerate(rows):
                if row["path"] == select_path:
                    index = position
                    break
        listbox.selection_set(index)
        listbox.activate(index)
        listbox.see(index)
        self._sync_library_media_button(window)

    def _sync_library_media_button(self, window):
        row = self._selected_library_playlist(window)
        state = "normal" if row and row.get("media", 0) > 0 else "disabled"
        window._delete_media.configure(state=state)

    def _playlist_library_line(self, row):
        parts = [row["name"]]
        created = row.get("created")
        if created:
            moment = datetime.fromtimestamp(created)
            pattern = "%d.%m.%Y" if current_language() == "de" else "%Y-%m-%d"
            parts.append(moment.strftime(pattern))
        count = row.get("media", 0)
        parts.append(t("edit_imports_medium" if count == 1 else "edit_imports_media", count=count))
        parts.append(self._format_copy_size(row.get("bytes", 0)))
        return "   —   ".join(parts)

    def _selected_library_playlist(self, window):
        selection = window._listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        rows = window._rows
        if 0 <= index < len(rows):
            return rows[index]
        return None

    def _open_library_playlist(self, window):
        row = self._selected_library_playlist(window)
        if row is None:
            return
        if row["path"] != getattr(self, "playlist_path", "") and self._playlist_has_unsaved_changes():
            if not self._confirm_close_playlist():
                return
        self._load_playlist_from_path(row["path"])
        self._close_playlist_library()

    def _new_library_playlist(self, window):
        if self.new_playlist():
            self._close_playlist_library()

    def _ask_playlist_media_copy(self, parent):
        """True copies media files, False keeps the original paths, None cancels."""
        result = {"choice": None}
        dialog = tk.Toplevel(parent)
        dialog.title(t("playlist_media_prompt"))
        dialog.configure(bg=COLOR_BG)
        dialog.minsize(420, 150)
        if self.icon_image is not None:
            try:
                dialog.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        dialog.transient(parent)
        body = tk.Frame(dialog, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        tk.Label(
            body, text=t("playlist_media_prompt"), bg=COLOR_BG, fg=COLOR_TEXT,
            font=FONT_UI, wraplength=440, justify="left",
        ).pack(fill="x")
        buttons = tk.Frame(dialog, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        def choose(value):
            result["choice"] = value
            dialog.destroy()

        tk.Button(
            buttons, text=t("playlist_with_media"), command=lambda: choose(True), font=FONT_UI,
        ).pack(side="left")
        tk.Button(
            buttons, text=t("playlist_without_media"), command=lambda: choose(False), font=FONT_UI,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("quit_cancel"), command=lambda: choose(None), font=FONT_UI,
        ).pack(side="right")
        dialog.bind("<Escape>", lambda _event: choose(None))
        dialog.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self._open_popup(dialog, 520, 180)
        self._grab_popup(dialog)
        self.root.wait_window(dialog)
        return result["choice"]

    def _place_playlist(self, source, dest_folder, stem, with_media):
        """Copy a playlist, storing import-directory media relative to that directory."""
        relative_to = ""
        import_path = getattr(self, "import_path", "") or ""
        if import_path and path_is_inside(dest_folder, import_path):
            relative_to = import_path
        return place_playlist(source, dest_folder, stem, with_media, relative_to=relative_to)

    def _import_library_playlist(self, window):
        path = filedialog.askopenfilename(
            title=t("playlist_import_title"),
            filetypes=[(t("playlist_files"), "*.pls *.json"), (t("all_files"), "*.*")],
            parent=window,
        )
        if not path:
            return
        stem = playlist_folder_name(os.path.basename(path))
        if not stem:
            stem = self._ask_playlist_name()
            if not stem:
                return
        folder = os.path.join(self.import_path, stem)
        dest = os.path.join(folder, f"{stem}.pls")
        if os.path.exists(dest):
            messagebox.showerror(t("playlist_import_title"), t("playlist_exists", name=stem), parent=window)
            return
        with_media = self._ask_playlist_media_copy(window)
        if with_media is None:
            return
        try:
            written = self._place_playlist(path, folder, stem, with_media)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror(
                t("playlist_import_title"),
                t("playlist_transfer_failed", error=exc),
                parent=window,
            )
            return
        self._refresh_playlist_library(window, select_path=written)
        if not getattr(self, "playlist_path", ""):
            self._load_playlist_from_path(written)
            self._close_playlist_library()

    def _export_library_playlist(self, window):
        row = self._selected_library_playlist(window)
        if row is None:
            return
        dest = filedialog.askdirectory(title=t("playlist_export_choose"), parent=window)
        if not dest:
            return
        with_media = self._ask_playlist_media_copy(window)
        if with_media is None:
            return
        stem = playlist_folder_name(row["name"]) or playlist_folder_name(os.path.basename(row["path"]))
        if not stem:
            stem = self._ask_playlist_name()
            if not stem:
                return
        try:
            self._place_playlist(row["path"], dest, stem, with_media)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            messagebox.showerror(
                t("playlist_export_title"),
                t("playlist_transfer_failed", error=exc),
                parent=window,
            )

    def _restore_last_playlist(self):
        if not self.load_last_playlist_at_start.get():
            return
        path = self.last_playlist_path
        if not path or not os.path.isfile(path):
            return
        self._load_playlist_from_path(path)

    def _load_playlist_from_path(self, path):
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror(t("load_playlist"), f"{os.path.basename(path)}\n{exc}")
            return
        if not isinstance(data, dict):
            messagebox.showerror(t("load_playlist"), os.path.basename(path))
            return
        media_root = media_root_for_playlist(path, getattr(self, "import_path", ""), data)
        self.playlist = playlist_entries(data.get("entries", []), media_root)
        missing = self._scan_playlist_media()
        self.projection_zoom.set(data.get("projection_zoom", False))
        self.autoplay_delay.set(str(data.get("autoplay_delay", 0)))
        self.idle_media_path = resolve_stored_media_path(
            data.get("idle_media_path", "") or "",
            root=media_root,
        )
        self.idle_media.set(
            os.path.basename(self.idle_media_path) if self.idle_media_path else t("idle_none")
        )
        if self.use_default_idle_media.get():
            default_path = default_idle_media_path()
            if default_path:
                self.idle_media_path = default_path
                self.idle_media.set(os.path.basename(default_path))
        self._refresh_idle_status()
        if "autosave_on_program_change" in data:
            self.autosave_on_program_change.set(bool(data["autosave_on_program_change"]))
        self.playlist_path = path
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, os.path.basename(path))
        self.remember_playlist_dir(path)
        try:
            index = int(data.get("program_index", 0))
        except (TypeError, ValueError):
            index = 0
        self.program_index = min(max(index, 0), max(len(self.playlist) - 1, 0))
        self._skip_to_playable(inclusive=True)
        self.zoom_confirmed_index = None
        self.preview_index = None
        self.preview_live = True
        if self.program_state != "PLAYING":
            self.blank_output()
        self.refresh_all()
        self._remember_saved_playlist()
        if missing:
            messagebox.showwarning(t("load_playlist"), t("missing_playlist", count=missing))

    def _scan_playlist_media(self):
        """Mark missing files and reload metadata for clips that are still on disk."""
        missing = 0
        for entry in self.playlist:
            if reload_entry_metadata(entry):
                self._match_entry_refresh(entry)
            elif entry.missing:
                missing += 1
        return missing

    def check_playlist_files(self):
        """Re-check every playlist path and reload each file's metadata."""
        missing = self._scan_playlist_media()
        if self.program_state != "PLAYING":
            self._skip_to_playable(inclusive=True)
        if self.preview_index is not None and not self.preview_live:
            self.show_preview_clip(self.selected_entry())
        self.refresh_all()
        if missing:
            messagebox.showwarning(t("refresh_playlist"), t("missing_playlist", count=missing))

    def save_playlist(self):
        """Save into a same-named folder under the import path."""
        if not self._ensure_import_path():
            return False
        stem = playlist_folder_name(self._current_playlist_name())
        if not stem:
            stem = self._ask_playlist_name()
            if not stem:
                return False
            self._set_playlist_name(f"{stem}.pls")
        folder = os.path.join(self.import_path, stem)
        path = os.path.join(folder, f"{stem}.pls")
        try:
            os.makedirs(folder, exist_ok=True)
            self._write_playlist(path)
        except OSError as exc:
            messagebox.showerror(t("save_playlist"), t("import_playlist_save_failed", error=exc))
            return False
        self.playlist_path = path
        self._set_playlist_name(os.path.basename(path))
        self.remember_playlist_dir(path)
        return True

    def _playlist_payload(self):
        return {
            "projection_zoom": self.projection_zoom.get(),
            "autoplay_delay": float(self.autoplay_delay.get() or 0),
            "idle_media": self.idle_media.get(),
            "idle_media_path": self.idle_media_path,
            "program_index": self.program_index,
            "autosave_on_program_change": bool(self.autosave_on_program_change.get()),
            "entries": [entry.__dict__ for entry in self.playlist],
        }

    def _playlist_token(self):
        return json.dumps(self._playlist_payload(), sort_keys=True, ensure_ascii=False)

    def _remember_saved_playlist(self):
        """The playlist now matches what is on disk, or there is nothing to keep."""
        self._playlist_saved_token = self._playlist_token()

    def _playlist_has_unsaved_changes(self):
        saved = getattr(self, "_playlist_saved_token", None)
        try:
            current = self._playlist_token()
        except (TypeError, ValueError):
            return True
        return current != saved

    def _write_playlist(self, path):
        payload = self._playlist_payload()
        written = playlist_for_saved_file(payload, path, getattr(self, "import_path", ""))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(written, handle, indent=2)
        self._playlist_saved_token = json.dumps(payload, sort_keys=True, ensure_ascii=False)

    def _pad_16x9_enabled(self):
        """True when 4:3 and non-square PAR should be padded to 16:9."""
        var = getattr(self, "pad_16x9", None)
        if var is None:
            return True
        try:
            return bool(var.get())
        except tk.TclError:
            return True

    def _picture_filter(self, entry):
        return mpv_picture_filter(entry, enabled=self._pad_16x9_enabled())

    def _on_pad_16x9(self):
        self.settings["pad_16x9"] = bool(self.pad_16x9.get())
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self.refresh_playlist()
        self._apply_pad_16x9_to_players()
        if self.program_state != "PLAYING":
            self.apply_beamer_mode_for_pointer()
            self.refresh_beamer()

    def _apply_pad_16x9_to_players(self):
        """Push the current pad setting onto files already in mpv."""
        extra = still_level_filter(getattr(self, "_still_level", 1.0))
        main = getattr(self, "main_mpv", None)
        if main is not None and getattr(main, "process", None):
            clip = None
            if self.program_state == "PLAYING" and not getattr(self, "idle_showing", False):
                clip = self.current_entry()
            main.output_vf = self._picture_filter(clip)
            apply = getattr(main, "apply_picture_filter", None)
            if apply:
                apply(extra if clip and getattr(clip, "is_image", False) else "")
        preview = getattr(self, "preview_mpv", None)
        if preview is not None and getattr(preview, "process", None):
            if getattr(self, "preview_live", False):
                clip = self.current_entry() if self.program_state == "PLAYING" else None
            else:
                clip = self.selected_entry()
            preview.output_vf = self._picture_filter(clip)
            apply = getattr(preview, "apply_picture_filter", None)
            if apply:
                apply(extra if clip and getattr(clip, "is_image", False) else "")

    def _on_autosave_program_change(self):
        self.settings["autosave_on_program_change"] = bool(self.autosave_on_program_change.get())
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _on_load_last_playlist_at_start(self):
        self.settings["load_last_playlist_at_start"] = bool(self.load_last_playlist_at_start.get())
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _autosave_playlist(self):
        if not self.autosave_on_program_change.get() or not self.playlist_path:
            return
        try:
            self._write_playlist(self.playlist_path)
        except OSError as exc:
            print(f"Playlist-Autosave: {exc}")

    def choose_idle_media(self):
        dialog_options = {}
        if self.last_import_dir:
            dialog_options["initialdir"] = self.last_import_dir
        path = filedialog.askopenfilename(title=t("idle_screen_media"), **dialog_options)
        if not path:
            return
        self.remember_import_dir(path)
        self._save_use_default_idle_media(False)
        self._set_idle_media(path)

    def clear_idle_media(self):
        self._save_use_default_idle_media(False)
        self._set_idle_media("")

    def _refresh_idle_status(self):
        label = getattr(self, "idle_status", None)
        if label is None:
            return
        name = os.path.basename(self.idle_media_path) if self.idle_media_path else ""
        if not name:
            try:
                label.grid_remove()
            except tk.TclError:
                pass
            self._refresh_settings_warning_status()
            return
        if self.idle_showing:
            label.config(text=name, bg=COLOR_PLAYING, fg=COLOR_WHITE)
        else:
            label.config(text=name, bg=COLOR_BG, fg=COLOR_TEXT)
        try:
            if not label.winfo_manager():
                label.grid(row=1, column=2, sticky="e", padx=(12, 0), pady=(4, 0))
        except tk.TclError:
            pass
        self._refresh_settings_warning_status()

    def _refresh_settings_warning_status(self):
        label = getattr(self, "settings_warning_status", None)
        if label is None:
            return
        if bool(self.projection_zoom.get()):
            label.config(text=t("settings_warning_active"), bg=COLOR_BG, fg=COLOR_WARNING)
            try:
                if not label.winfo_manager():
                    label.pack(side="left")
            except tk.TclError:
                pass
            self._sync_show_strip()
            return
        try:
            label.pack_forget()
        except tk.TclError:
            pass
        self._sync_show_strip()

    def _on_use_default_idle_media(self):
        enabled = bool(self.use_default_idle_media.get())
        if enabled:
            if not self._apply_default_idle_media(show_error=True):
                self._save_use_default_idle_media(False)
                return
        else:
            self._set_idle_media("")
        self._save_use_default_idle_media(enabled)

    def _save_use_default_idle_media(self, enabled):
        self.use_default_idle_media.set(bool(enabled))
        self.settings["use_default_idle_media"] = bool(enabled)
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _apply_default_idle_media(self, show_error=False):
        """Use the first video or image in the project's idle folder."""
        path = default_idle_media_path()
        if not path:
            if show_error:
                message = (
                    t("default_idle_media_missing")
                    if not os.path.isdir(IDLE_DIR)
                    else t("default_idle_media_empty")
                )
                messagebox.showerror(t("default_idle_media"), message)
            return False
        self._set_idle_media(path)
        return True

    def _set_idle_media(self, path):
        self.idle_media_path = path or ""
        self.idle_media.set(os.path.basename(path) if path else t("idle_none"))
        self._refresh_idle_status()
        if self.program_state != "PLAYING":
            self.blank_output()

    def apply_entry_settings(self):
        entry = self.selected_entry()
        if not entry:
            return
        previous_force = bool(entry.force_settings_warning)
        entry.autoplay = self.autoplay_var.get()
        entry.played = self.played_var.get()
        entry.force_settings_warning = bool(self.clip_settings_warning_var.get())
        entry.light_start = self._play_light_from_label(self.light_start_var.get())
        if entry.is_image:
            entry.loop = False
            try:
                entry.display_time = max(0.0, float(self.display_time.get() or 0))
            except ValueError:
                pass
            self.display_time.set(format_seconds(entry.display_time))
        else:
            entry.loop = self.loop_var.get()
            entry.audio_track = self.audio_var.get()
            entry.subtitle_track = self.subtitle_var.get()
            if self.preview_mpv.has_file(entry.path):
                self.apply_tracks(entry, self.preview_mpv)
            if (
                self.program_state == "PLAYING"
                and entry is self.current_entry()
                and self.main_mpv.process
            ):
                self._apply_program_loop(entry)
                if self.preview_live:
                    self._apply_program_loop(entry, self.preview_mpv)
            if (
                self.program_state == "PLAYING"
                and entry is self.current_entry()
                and self.main_mpv.has_file(entry.path)
            ):
                self.apply_tracks(entry, self.main_mpv)
        self.repaint_playlist()
        self.refresh_transport()
        if (
            not previous_force
            and entry.force_settings_warning
            and bool(self.projection_zoom.get())
            and self.program_state == "PROGRAM"
            and entry is self.current_entry()
        ):
            self.confirm_projection_zoom(prompt=not self._remote_action)

    def reset_played(self):
        if not messagebox.askyesno(t("reset_played_title"), t("reset_played_message")):
            return
        for entry in self.playlist:
            entry.played = False
        self.played_var.set(False)
        if self.playlist:
            self._move_program_cursor(0)
        self.refresh_all()

    def analyze_playlist_loudness(self):
        """Measure LUFS and a peak envelope for every playable video while the program is stopped."""
        if self.program_state != "OFF":
            messagebox.showinfo(t("analyze_loudness_title"), t("analyze_loudness_busy"))
            return
        targets = [
            entry for entry in self.playlist
            if not entry.missing and not entry.is_image and media_file_available(entry)
        ]
        if not targets:
            messagebox.showinfo(t("analyze_loudness_title"), t("analyze_loudness_none"))
            return
        if not messagebox.askyesno(t("analyze_loudness_title"), t("analyze_loudness_message")):
            return
        try:
            ffmpeg_path = find_ffmpeg()
        except RuntimeError:
            messagebox.showerror(t("analyze_loudness_title"), t("analyze_loudness_missing_ffmpeg"))
            return
        self.root.config(cursor="watch")
        self.root.update_idletasks()
        try:
            for entry in targets:
                try:
                    lufs, envelope = probe_audio(entry.path, ffmpeg_path)
                    entry.loudness_lufs = lufs
                    entry.audio_envelope = envelope
                except OSError:
                    entry.loudness_lufs = None
                    entry.audio_envelope = None
                self.repaint_playlist()
                self.refresh_preview_meta()
                self.root.update()
        except tk.TclError:
            return
        finally:
            try:
                self.root.config(cursor="")
            except tk.TclError:
                pass
        self.refresh_all()

    def toggle_preview_mode(self):
        self.preview_live = not self.preview_live
        if self.preview_live:
            self.preview_index = None
            self.live_parked = None
            self.preview_stopped = False
            entry = self.current_entry()
            rolling = (
                self.program_state == "PLAYING"
                and not self.main_pause
                and not self.blackout
            )
            self.preview_paused = not rolling
            if entry and self.program_state == "PLAYING":
                self.show_preview_clip(
                    entry,
                    follow_live=True,
                    start=self.position,
                    play=rolling,
                )
            self.sync_live_preview()
        else:
            entry = self.selected_entry()
            if entry:
                self.preview_index = self.playlist.index(entry)
                self.show_preview_clip(entry)
        self.refresh_all()

    def ensure_main_output(self, auto=False):
        """Open the output window early so the projector shows black, not the desktop."""
        if self.main_mpv.process:
            return True
        try:
            output = self.output_manager.select_video_output()
            if auto and output == self.output_manager.get_primary_output():
                # No dedicated projector display: don't cover the control screen.
                return False
            self.output_manager.ensure_operator_layout()
            arguments = self.output_manager.get_mpv_arguments(self.mpv_path)
            arguments.append(f"--af={PLAYBACK_AF}")
            self.main_mpv.start(arguments)
            self.main_mpv.observe("af-metadata/meter", 5)
        except Exception as exc:
            print(f"Videoausgang nicht verfuegbar: {exc}")
            return False
        self.blank_output()
        return True

    def idle_media_file(self):
        path = self.idle_media_path
        return path if path and os.path.exists(path) else ""

    def autoplay_seconds(self):
        try:
            return max(0.0, float(self.autoplay_delay.get() or 0))
        except ValueError:
            return 0.0

    def blank_output(self, show_idle=True):
        """Black out the output; a non-black idle background follows after the delay."""
        self._cancel_picture_fade()
        self._still_fading_out = False
        self.cancel_still_timer()
        if self.idle_after_id:
            self.root.after_cancel(self.idle_after_id)
            self.idle_after_id = None
        self._cancel_program_volume_glide()
        if not self.main_mpv.process:
            self._reset_program_meter()
            return
        # Keep HDMI PCM running. stop() closes the audio device and the
        # projector then mutes the first seconds of the next clip.
        if not self.main_mpv.load_audio_keepalive():
            self.hdmi_audio_keepalive = False
            self.main_mpv.stop()
            self.main_mpv.set_ab_loop(None, None)
            self.main_mpv.set_loop_file(False)
            self.main_mpv.set_vid(True)
        else:
            self.hdmi_audio_keepalive = True
        self._release_still_picture()
        self.current_file = None
        self._program_playback_started = False
        self.main_pause = False
        self.blackout = True
        self.idle_showing = False
        self.duration = 0.0
        self.position = 0.0
        self._reset_program_meter()
        if show_idle and self.idle_allowed() and self.idle_media_file():
            delay = int(self.autoplay_seconds() * 1000)
            self.idle_after_id = self.root.after(delay, self.show_idle_media)

    def idle_allowed(self):
        """The idle background belongs to an armed program, not to a stopped one."""
        return self.program_state == "PROGRAM" and not self.calibration_mode

    def show_idle_media(self):
        """Put the idle background on screen after the black gap."""
        self.idle_after_id = None
        path = self.idle_media_file()
        if not path or not self.idle_allowed() or not self.main_mpv.process:
            return
        if self.beamer_test_active:
            return
        self.main_mpv.set_ab_loop(None, None)
        self._cancel_program_volume_glide()
        self._remember_program_output(100)
        self.main_mpv.set_volume(100)
        self.main_mpv.load_file(path, play=True, loop=True)
        self.blackout = False
        self.idle_showing = True
        self.duration = 0.0
        self.position = 0.0

    def show_beamer_test(self):
        """Show the Cinema Player logo on the projector until the operator dismisses it."""
        if self.program_state != "OFF":
            return
        if not os.path.isfile(BEAMER_TEST_FILE):
            messagebox.showerror(t("beamer_test"), t("beamer_test_missing"))
            return
        if not self.ensure_main_output(auto=False):
            messagebox.showerror(t("beamer_status"), t("output_failed"))
            return
        if self.idle_after_id:
            self.root.after_cancel(self.idle_after_id)
            self.idle_after_id = None
        self.beamer_test_active = True
        self.idle_showing = False
        try:
            self.main_mpv.set_vid(True)
            self.main_mpv.command("set_property", "video-zoom", BEAMER_TEST_ZOOM)
            self.main_mpv.load_file(BEAMER_TEST_FILE, play=True, loop=True)
            self.blackout = False
            self.root.update_idletasks()
            messagebox.showinfo(t("beamer_test"), t("beamer_test_active"))
        finally:
            self.beamer_test_active = False
            self.main_mpv.command("set_property", "video-zoom", 0)
            self.blank_output()

    def start_preview_player(self):
        if self.preview_mpv.process:
            return
        self.preview_video.update_idletasks()
        wid = self.preview_video.winfo_id()
        arguments = [
            f"--wid={wid}",
            "--keepaspect=yes",
            f"--hwdec={hwdec_for_gpu(self.output_manager.gpu_for_output(), embed=True)}",
            "--vo=gpu-next",
            f"--gpu-context={gpu_context_for_mpv(self.mpv_path, embed=True)}",
            "--force-window=yes",
            "--osc=no",
            "--osd-level=0",
            "--image-display-duration=inf",
            "--pause",
            "--sid=no",
            "--sub-auto=no",
            f"--af={PLAYBACK_AF}",
        ]
        arguments.extend(self.output_manager.audio_launch_args("preview", self.mpv_path))
        try:
            self.preview_mpv.start(arguments)
            self.preview_mpv.observe("af-metadata/meter", 5)
            self._apply_preview_speaker()
            self.preview_placeholder.place_forget()
        except Exception as exc:
            self.preview_placeholder.config(text=t("preview_unavailable", error=exc))

    def show_preview_clip(self, entry, follow_live=False, start=None, play=None):
        if not entry or entry.missing or not media_file_available(entry):
            if entry:
                entry.missing = True
            if self.preview_mpv.process:
                self.preview_mpv.stop()
            self._reset_preview_meter()
            return
        if not self.preview_mpv.process:
            self.start_preview_player()
        if not self.preview_mpv.process:
            return
        if play is None:
            play = follow_live
        if start is None:
            start = entry.in_point
        if not follow_live and not play and self.preview_mpv.has_file(entry.path):
            self._release_preview_range()
            return
        self.preview_stopped = False
        self.preview_paused = not play
        end = entry.out_point if follow_live and not (entry.loop and not entry.is_image) else None
        if end is not None:
            self._preview_full_file = False
        self.preview_mpv.load_file(
            entry.path,
            start=start,
            end=end,
            play=play,
            vf=self._picture_filter(entry),
        )

    def _resume_reaction_held(self):
        name = getattr(self, "_resume_reaction", None)
        if not name:
            return False
        return time.monotonic() < (getattr(self, "_resume_reaction_until", 0) or 0)

    def _on_resume_press(self, _event=None):
        """Light the key on the way down, before the click releases into the action."""
        if not getattr(self.btn_play, "_transport_enabled", True):
            return
        self._show_resume_reaction()

    def _show_resume_reaction(self):
        """Fill Weiter immediately, in program blue or playing green.

        Playback can spend a while switching the projector. The light is the
        press itself and is painted before that work starts. A phone Weiter
        uses the same path, so the booth key answers at once.
        """
        button = getattr(self, "btn_play", None)
        if button is None or not getattr(button, "_transport_enabled", True):
            return
        name = resume_reaction_name(self.program_state)
        button.icon_name = "start_program" if self.program_state == "OFF" else "play"
        self._resume_reaction = name
        self._resume_reaction_until = time.monotonic() + RESUME_REACTION_SECONDS
        self._paint_resume_plate(name)
        self._set_transport_active(button, True, name, enabled=True)
        self._paint_resume_caption()
        root = getattr(self, "root", None)
        if root is None:
            return
        try:
            root.update_idletasks()
        except tk.TclError:
            pass

    def _paint_resume_plate(self, name):
        """Fill the Weiter key while the press is showing. ``None`` puts the panel back."""
        button = getattr(self, "btn_play", None)
        host = getattr(button, "master", None) if button is not None else None
        if host is None:
            return
        color = resume_reaction_color(name) if name else COLOR_PANEL
        try:
            host.configure(bg=color)
        except tk.TclError:
            pass

    def _paint_resume_caption(self):
        """Weiter stays in the program colour: blue while armed, green while it continues."""
        button = getattr(self, "btn_play", None)
        caption = getattr(button, "caption", None) if button is not None else None
        if caption is None:
            return
        held = self._resume_reaction_held()
        enabled = bool(getattr(button, "_transport_enabled", True))
        if held:
            name = self._resume_reaction
            fg = COLOR_WHITE
            bg = resume_reaction_color(name)
            font = (FONT_SMALL[0], FONT_SMALL[1], "bold")
        elif enabled and self.program_state == "PROGRAM":
            fg = COLOR_PROGRAM
            bg = COLOR_PANEL
            font = (FONT_SMALL[0], FONT_SMALL[1], "bold")
        elif enabled and self.program_state == "PLAYING":
            fg = COLOR_PLAYING
            bg = COLOR_PANEL
            font = (FONT_SMALL[0], FONT_SMALL[1], "bold")
        else:
            fg = COLOR_TEXT if enabled else COLOR_PLAYED
            bg = COLOR_PANEL
            font = FONT_SMALL
        try:
            caption.config(fg=fg, bg=bg, font=font)
        except tk.TclError:
            pass

    def start_or_resume(self):
        if not self.playlist:
            if self._remote_action:
                return
            self.import_media()
            if not self.playlist:
                return
        if self.program_state == "PLAYING" and not (
            self.still_waiting or self._program_loop_active() or self.main_pause
        ):
            return
        self._show_resume_reaction()
        if self.program_state == "OFF":
            # Start only arms the program; Resume then rolls the clip.
            self.program_state = "PROGRAM"
            self._skip_to_playable(inclusive=True)
            self.ensure_main_output()
            # Arming brings up the idle background, if one is set.
            self.blank_output()
            self.refresh_all()
            self.confirm_projection_zoom(prompt=not self._remote_action)
            return
        if self.program_state == "PLAYING" and self.still_waiting:
            # A still without display time ends when the operator resumes.
            self.on_clip_finished()
            return
        if self.program_state == "PLAYING" and self._program_loop_active():
            # A looping clip stays on air until Resume ends the loop.
            self.on_clip_finished()
            return
        if self.program_state == "PLAYING" and self.main_pause:
            self.main_mpv.set_vid(True)
            self.blackout = False
            self.main_mpv.set_pause(False)
            self.preview_mpv.set_pause(False)
            self.main_pause = False
            return
        if self.program_state == "PLAYING":
            # Resume while rolling would load the clip again from the start.
            return
        self.start_current_clip()

    def start_current_clip(self):
        if not self.playlist:
            return
        self.autoplay_after_id = None
        self._cancel_light_after("lights_play_after")
        if self.idle_after_id:
            self.root.after_cancel(self.idle_after_id)
            self.idle_after_id = None
        if self.idle_showing:
            self.blank_output(show_idle=False)
            delay = int(self.autoplay_seconds() * 1000)
            self.autoplay_after_id = self.root.after(delay, self.start_current_clip)
            return
        if not self._skip_to_playable(inclusive=True):
            self.program_state = "PROGRAM"
            self.blank_output()
            self.refresh_all()
            if not self._remote_action:
                messagebox.showinfo(t("playback"), t("missing_playback"))
            return
        if not self.confirm_projection_zoom(prompt=not self._remote_action):
            self.program_state = "PROGRAM"
            self.refresh_all()
            return
        entry = self.playlist[self.program_index]
        before = None
        output = self.output_manager.video_output
        if output:
            before = self.output_manager.get_current_mode(output)
        try:
            video, mode, matched = self.output_manager.prepare_for_video(
                entry.path, pad_16x9=self._pad_16x9_enabled(),
            )
            entry.refresh_ok = matched
        except Exception as exc:
            if not media_file_available(entry):
                entry.missing = True
                if self._skip_to_playable(inclusive=False):
                    self.start_current_clip()
                    return
                self.program_state = "PROGRAM"
                self.blank_output()
                self.refresh_all()
                if not self._remote_action:
                    messagebox.showinfo(t("playback"), t("missing_playback"))
                return
            if not self._remote_action:
                messagebox.showerror(t("playback"), str(exc))
            self.program_state = "PROGRAM"
            self.refresh_all()
            return

        mode_changed = self._projection_mode_changed(before, mode)
        if session_is_wayland() and mode_changed and self.main_mpv.process:
            if not self._restart_main_output(blank=False):
                self.program_state = "PROGRAM"
                self.refresh_all()
                return
        elif not self.ensure_main_output():
            if not self._remote_action:
                messagebox.showerror(t("playback"), t("output_failed"))
            self.program_state = "PROGRAM"
            self.refresh_all()
            return
        self.main_mpv.command("set_property", "override-display-fps", float(mode.refresh))
        if session_is_wayland():
            self._pin_main_output_to_beamer()
        else:
            self.main_mpv.command(
                "set_property", "geometry", self.output_manager.get_mpv_geometry()
            )

        self.main_mpv.set_vid(True)
        self.idle_showing = False
        self._cancel_light_after("lights_play_after")
        self.lights_end_sent = False
        self.main_pause = False
        self.blackout = False
        self.current_file = entry.path
        self.duration = entry.duration
        self.position = entry.in_point if entry.in_point is not None else 0
        self.program_state = "PLAYING"
        self._program_playback_started = False
        preset = dmx.resolve_start_preset(
            entry.light_start, self.lights_scenes, getattr(self, "lights_sequences", None),
        )
        self._apply_lights(
            preset,
            force=bool(dmx.play_preset(
                entry.light_start, self.lights_scenes, getattr(self, "lights_sequences", None),
            )),
        )
        delay = self._lights_play_delay_ms()
        if delay > 0:
            self.refresh_all()
            self._refresh_light_buttons()
            self.lights_play_after = self.root.after(delay, lambda: self._roll_current_clip(entry))
            return
        self._roll_current_clip(entry)

    def _lights_play_delay_ms(self):
        if self.calibration_mode or not bool(self.lights_control.get()):
            return 0
        if not self._dmx_ready():
            return 0
        if not self.lights_fading:
            return 0
        fade = getattr(self, "_light_meter_fade", None)
        return dmx.play_delay_ms(fade["ms"] if fade else 0, self.lights_start_lead_ms)

    def _roll_current_clip(self, entry):
        self.lights_play_after = None
        if self.program_state != "PLAYING" or entry is not self.current_entry():
            return
        self._program_playback_started = False
        looping = bool(entry.loop and not entry.is_image)
        volume = clamp_volume(entry.volume)
        aid, sid = self._entry_track_ids(entry)
        self._volume_program_key = id(entry)
        shown = clamp_volume(self.program_volume.get())
        # Ease the booth fader only when it still shows the previous clip.
        if not self._glide_program_volume(volume, move_fader=(shown != volume)):
            self._load_program_volume(entry, force=True)
        self._apply_program_audio_delay(entry)
        out_point = playback_out_point(entry, looping)
        # Arm before the load so an eof from the silent keepalive cannot
        # satisfy "this clip has reached its end".
        self._program_load_id += 1
        self._program_loaded_id = 0
        self._program_playhead = None
        self._cancel_picture_fade()
        self._still_fading_out = False
        self._still_fade_out_done = False
        # Drop a brightness value left behind by an older fade, then darken
        # only through the video filter so the still is rebuilt each step.
        self._release_still_picture()
        if entry.is_image and self._still_dim_active():
            self._apply_still_level(0.0)
        self.main_mpv.load_file(
            entry.path,
            start=entry.in_point,
            end=out_point,
            play=True,
            aid=aid,
            sid=sid,
            loop=looping,
            clear_end=out_point is None,
            vf=self._picture_filter(entry),
        )
        # Loop and Out are per-file options above. Setting them here would
        # hit the keepalive that is still on screen and end it at once.
        if session_is_wayland():
            self._pin_main_output_to_beamer()
        self.apply_tracks(entry, self.main_mpv)
        self.start_still_timer(entry)
        if self.preview_live:
            self.show_preview_clip(entry, follow_live=True)
        if entry.is_image and self._still_dim_active():
            self._restart_still_fade_in()
        self.refresh_all()
        self._refresh_light_buttons()

    def _program_loop_active(self):
        """True while a looping video is on the projector and waiting for Resume."""
        entry = self.current_entry()
        return bool(
            self.program_state == "PLAYING"
            and not self.idle_showing
            and not self.still_active()
            and entry
            and entry.loop
            and not entry.is_image
        )

    def _apply_program_loop(self, entry, controller=None):
        """Loop the current video until Resume; honour In/Out as an A-B range."""
        controller = controller or self.main_mpv
        if not controller or not controller.process:
            return
        looping = bool(entry and entry.loop and not entry.is_image)
        if controller is self.preview_mpv:
            self._preview_full_file = False
        if looping:
            start = 0.0 if entry.in_point is None else float(entry.in_point)
            controller.set_ab_loop(start, entry.out_point)
            controller.set_loop_file(True)
            controller.set_end(None)
            return
        controller.set_ab_loop(None, None)
        controller.set_loop_file(False)
        controller.set_end(playback_out_point(entry, looping=False))

    def _release_preview_range(self):
        """Independent preview plays the whole file, including after Out."""
        mpv = self.preview_mpv
        if not mpv or not mpv.process:
            return
        if self._preview_full_file:
            return
        self._preview_full_file = True
        mpv.pending_end = None
        mpv.set_ab_loop(None, None)
        mpv.set_loop_file(False)
        mpv.set_end(None)

    def start_still_timer(self, entry):
        """A still runs on a timer; without a display time it waits for Resume."""
        self.cancel_still_timer()
        self._still_fade_span = None
        if not entry.is_image:
            return
        seconds = max(0.0, float(entry.display_time or 0))
        self.duration = seconds
        self.position = 0.0
        if seconds <= 0:
            self.still_waiting = True
            return
        self.still_started = time.monotonic()
        delay, fade = still_fade_plan(seconds, self._still_dim_seconds(), self._still_dim_active())
        self._still_fade_span = fade
        self.still_after_id = self.root.after(delay, self.on_clip_finished)

    def _still_dim_players(self):
        players = []
        main = getattr(self, "main_mpv", None)
        if main is not None:
            players.append(main)
        if getattr(self, "preview_live", False):
            preview = getattr(self, "preview_mpv", None)
            if preview is not None:
                players.append(preview)
        return players

    def _still_picture_players(self, live_only=False):
        if live_only:
            return self._still_dim_players()
        return [getattr(self, "main_mpv", None), getattr(self, "preview_mpv", None)]

    def _apply_still_level(self, level, players=None):
        level = max(0.0, min(1.0, float(level)))
        self._still_level = level
        extra = still_level_filter(level)
        if players is None:
            players = self._still_dim_players()
        for player in players:
            if player is None or not getattr(player, "process", None):
                continue
            # Keep the equalizer property neutral. A stuck -100 hides the still.
            player.command("set_property", "brightness", 0)
            apply = getattr(player, "apply_picture_filter", None)
            if apply:
                apply(extra)
            else:
                player.command(
                    "set_property",
                    "vf",
                    compose_mpv_vf(getattr(player, "output_vf", ""), extra),
                )

    def _release_still_picture(self):
        self._still_level = 1.0
        for player in self._still_picture_players():
            if player is None or not getattr(player, "process", None):
                continue
            player.command("set_property", "brightness", 0)
            apply = getattr(player, "apply_picture_filter", None)
            if apply:
                apply()
            else:
                player.command(
                    "set_property",
                    "vf",
                    getattr(player, "output_vf", "") or "",
                )

    def _restart_still_fade_in(self):
        if self._still_fading_out or not self._still_dim_active():
            return
        entry = self.current_entry()
        if self.program_state != "PLAYING" or not entry or not entry.is_image:
            return
        seconds = self._still_fade_span or self._still_dim_seconds()
        self._animate_still_level(0.0, 1.0, seconds)

    def _cancel_picture_fade(self):
        self._still_fade_done = None
        after_id = getattr(self, "still_fade_after", None)
        self.still_fade_after = None
        root = getattr(self, "root", None)
        if after_id and root is not None:
            try:
                root.after_cancel(after_id)
            except Exception:
                pass

    def _animate_still_level(self, start, end, duration, done=None):
        """Fade the still between black (0) and the full picture (1)."""
        self._cancel_picture_fade()
        self._still_fade_done = done
        duration = max(0.0, float(duration or 0))
        if duration <= 0:
            self._apply_still_level(end)
            callback = self._still_fade_done
            self._still_fade_done = None
            if callback:
                callback()
            return
        begun = time.monotonic()

        def tick():
            self.still_fade_after = None
            elapsed = time.monotonic() - begun
            fraction = min(1.0, elapsed / duration)
            self._apply_still_level(start + (end - start) * fraction)
            if fraction >= 1.0:
                self._still_fading_out = False
                callback = self._still_fade_done
                self._still_fade_done = None
                if callback:
                    self._still_fade_out_done = True
                    callback()
                return
            self.still_fade_after = self.root.after(50, tick)

        tick()

    def _current_still_on_air(self):
        entry = self.current_entry()
        return bool(
            self.program_state == "PLAYING"
            and not getattr(self, "idle_showing", False)
            and entry
            and entry.is_image
        )

    def _fade_still_out(self, then, duration=None):
        """Fade the still to black, then run ``then``. A second call replaces ``then``."""
        if self._still_fading_out:
            self._still_fade_done = then
            return
        if not self._current_still_on_air() or not self._still_dim_active():
            then()
            return
        self._still_fading_out = True
        self._still_fade_span = None
        if self.still_after_id:
            self.root.after_cancel(self.still_after_id)
            self.still_after_id = None
        seconds = self._still_dim_seconds() if duration is None else max(0.0, float(duration))
        self._animate_still_level(getattr(self, "_still_level", 1.0), 0.0, seconds, then)

    def still_active(self):
        return self.still_waiting or self.still_started is not None

    def cancel_still_timer(self):
        if self.still_after_id:
            self.root.after_cancel(self.still_after_id)
        self.still_after_id = None
        self.still_started = None
        self.still_waiting = False

    def _entry_track_ids(self, entry):
        aid = None
        sid = "no"
        if entry and entry.audio_track and entry.audio_track != "--":
            try:
                aid = int(entry.audio_track.split(":", 1)[0])
            except ValueError:
                pass
        if entry and entry.subtitle_track and entry.subtitle_track != "--":
            try:
                sid = int(entry.subtitle_track.split(":", 1)[0])
            except ValueError:
                pass
        return aid, sid

    def apply_tracks(self, entry, controller):
        aid, sid = self._entry_track_ids(entry)
        if aid is not None:
            controller.command("set_property", "aid", aid)
        controller.command("set_property", "sid", sid)

    def confirm_pause(self):
        if self.program_state != "PLAYING":
            return
        if getattr(self, "volume_setup", False):
            self._apply_pause()
            return
        if messagebox.askyesno(t("pause_title"), t("pause_message")):
            self._apply_pause()

    def confirm_still(self):
        if self.program_state != "PLAYING":
            return
        if getattr(self, "volume_setup", False):
            self._apply_still()
            return
        if messagebox.askyesno(t("still_title"), t("still_message")):
            self._apply_still()

    def _apply_pause(self):
        if self.program_state != "PLAYING":
            return False
        self.main_mpv.set_pause(True)
        self.main_mpv.set_vid(False)
        self.preview_mpv.set_pause(True)
        self.main_pause = True
        self.blackout = True
        self.refresh_transport()
        return True

    def _apply_still(self):
        if self.program_state != "PLAYING":
            return False
        self.main_mpv.set_vid(True)
        self.main_mpv.set_pause(True)
        self.preview_mpv.set_pause(True)
        self.main_pause = True
        self.blackout = False
        self.refresh_transport()
        return True

    def _apply_stop_clip(self):
        """End the clip on air and return to PROGRAM. Does not stop the program."""
        if self.program_state != "PLAYING":
            return False
        if self._still_fading_out:
            self._still_fade_done = self._finish_stop_clip
            return True
        if self._current_still_on_air() and self._still_dim_active():
            self._fade_still_out(self._finish_stop_clip)
            return True
        return self._finish_stop_clip()

    def _finish_stop_clip(self):
        if self.program_state != "PLAYING":
            return False
        self._still_fade_out_done = False
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        self._cancel_light_after("lights_play_after")
        ended = self.current_entry()
        if ended:
            ended.played = True
        self.program_state = "PROGRAM"
        self.blank_output()
        self.preview_mpv.stop()
        self._reset_preview_meter()
        self._skip_to_playable(inclusive=False)
        self.lights_end_sent = False
        self._apply_lights(dmx.resolve_end_preset("", False, self.lights_scenes))
        self.refresh_all()
        self.confirm_projection_zoom(prompt=not self._remote_action)
        return True

    def confirm_stop(self):
        if self.program_state == "OFF":
            return
        if getattr(self, "volume_setup", False):
            if self.program_state == "PLAYING":
                self._apply_stop_clip()
                return
            self._exit_volume_setup()
            return
        playing = self.program_state == "PLAYING"
        if self.calibration_mode and not playing:
            spec = self._calibration_spec()
            if not messagebox.askyesno(t(self._calibration_state_key()), t(spec["stop"])):
                return
            self._exit_calibration_mode()
            return
        question = t("stop_clip") if playing else t("stop_program")
        if not messagebox.askyesno(t("stop_title"), question):
            return
        if playing:
            self._apply_stop_clip()
            return
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        self._cancel_light_after("lights_play_after")
        # A stopped program means a dark screen, so no idle background either.
        self.program_state = "OFF"
        self.blank_output()
        self._apply_lights("bright")
        self.refresh_all()

    def on_clip_finished(self):
        if self.program_state != "PLAYING":
            return
        if self._still_fading_out:
            return
        if not self._still_fade_out_done:
            span = getattr(self, "_still_fade_span", None) or 0
            self._still_fade_span = None
            if span > 0:
                self._fade_still_out(self.on_clip_finished, duration=span)
                return
            if self._current_still_on_air() and self._still_dim_active():
                self._fade_still_out(self.on_clip_finished)
                return
        self._still_fade_out_done = False
        self._program_playback_started = False
        entry = self.current_entry()
        if entry:
            entry.played = True
        autoplay = bool(entry and entry.autoplay)
        self.program_state = "PROGRAM"
        has_next = self._skip_to_playable(inclusive=False)
        # The delay stays black; the idle background only follows when nothing is queued.
        self.blank_output(show_idle=not (autoplay and has_next))
        if not self.lights_end_sent:
            self._apply_lights(
                dmx.resolve_end_preset("", autoplay and has_next, self.lights_scenes)
            )
        self.lights_end_sent = False
        self.refresh_all()
        if not has_next:
            return
        if not self.confirm_projection_zoom():
            return
        if autoplay:
            ms = int(self.autoplay_seconds() * 1000)
            self.autoplay_after_id = self.root.after(ms, self.start_current_clip)

    def _detach_live_preview(self):
        """Leave Live mode so preview transport controls the preview clip, not the program."""
        if not self.preview_live and self.preview_index is not None:
            return
        entry = self.selected_entry()
        self.preview_live = False
        self.live_parked = None
        if entry in self.playlist:
            self.preview_index = self.playlist.index(entry)
        self._release_preview_range()
        self.refresh_preview_meta()
        self.repaint_playlist()

    def preview_play(self):
        self._detach_live_preview()
        entry = self.selected_entry()
        if not entry or entry.missing:
            return
        if not self.preview_mpv.process:
            self.start_preview_player()
        if self.preview_mpv.has_file(entry.path):
            self._release_preview_range()
            self.preview_mpv.set_pause(False)
        else:
            start = self.preview_position
            if start <= 0.05 and entry.in_point is not None:
                start = entry.in_point
            self.show_preview_clip(entry, start=start, play=True)
        self.preview_paused = False
        self.preview_stopped = False
        self.refresh_preview_meta()
        self.refresh_transport()

    def preview_pause(self):
        self._detach_live_preview()
        self.preview_mpv.set_pause(True)
        self.preview_paused = True
        self.preview_stopped = False
        self.refresh_transport()

    def preview_stop(self):
        self._detach_live_preview()
        self.preview_mpv.stop()
        self.preview_paused = True
        self.preview_stopped = True
        self._reset_preview_meter()
        self.refresh_transport()

    def preview_seek(self, seconds):
        self._detach_live_preview()
        self._release_preview_range()
        self.preview_mpv.seek(seconds)
        self.refresh_transport()

    def _focus_is_text_input(self):
        widget = self._focused_widget()
        return isinstance(widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))

    def _on_key_set_in(self, _event=None):
        if self._posted_menu is not None or self._focus_is_text_input():
            return
        self.set_in_point()
        return "break"

    def _on_key_set_out(self, _event=None):
        if self._posted_menu is not None or self._focus_is_text_input():
            return
        self.set_out_point()
        return "break"

    def set_in_point(self):
        entry = self.selected_entry()
        if not entry or entry.is_image:
            return
        entry.in_point = self.preview_position
        if entry.out_point is not None and entry.in_point > entry.out_point:
            entry.in_point, entry.out_point = entry.out_point, entry.in_point
        self.refresh_preview_meta()

    def set_out_point(self):
        entry = self.selected_entry()
        if not entry or entry.is_image:
            return
        entry.out_point = self.preview_position
        if entry.in_point is not None and entry.in_point > entry.out_point:
            entry.in_point, entry.out_point = entry.out_point, entry.in_point
        self.refresh_preview_meta()

    def clear_in_out(self):
        entry = self.selected_entry()
        if not entry:
            return
        entry.in_point = None
        entry.out_point = None
        self.refresh_preview_meta()

    def _clip_duration(self):
        entry = self.selected_entry()
        if entry and entry.duration:
            return entry.duration
        if self.preview_duration > 0:
            return self.preview_duration
        return 0.0

    def _update_preview_bar(self):
        entry = self.selected_entry()
        duration = self._clip_duration()
        self.preview_progress.set_state(
            duration=duration,
            position=self.preview_position,
            in_point=entry.in_point if entry else None,
            out_point=entry.out_point if entry else None,
        )
        if getattr(self, "preview_envelope", None):
            self.preview_envelope.set_playhead(duration, self.preview_position)

    def _update_main_bar(self):
        if self.program_state == "OFF":
            self.main_progress.set_state(duration=0, position=0, in_point=None, out_point=None)
            self._set_program_envelope(None, 0, 0)
            blank = format_clock(None)
            self.main_in.config(text=t("in_value", value=blank))
            self.main_out.config(text=t("out_value", value=blank))
            self.main_time.config(text=t("time_value", value=blank))
            return
        entry = self.current_entry()
        if self.idle_showing:
            # The background is not a program clip: no In/Out marks, no highlight.
            duration = self.duration
            in_point = out_point = None
        else:
            # Use the playlist duration so In/Out stay on the full clip, not an
            # idle-video clock or an mpv start/end segment length.
            duration = (entry.duration if entry and entry.duration else 0) or self.duration
            in_point = entry.in_point if entry else None
            out_point = entry.out_point if entry else None
        self.main_progress.set_state(
            duration=duration,
            position=self.position,
            in_point=in_point,
            out_point=out_point,
        )
        self._set_program_envelope(None if self.idle_showing else entry, duration, self.position)
        self.main_in.config(text=t("in_value", value=format_clock(in_point)))
        self.main_out.config(text=t("out_value", value=format_clock(out_point)))
        self.main_time.config(text=t("time_value", value=format_clock(self.position)))

    def _set_program_envelope(self, entry, duration, position):
        canvas = getattr(self, "program_envelope", None)
        if canvas is None:
            return
        peaks = None
        if entry and not entry.missing and not entry.is_image:
            peaks = entry.audio_envelope
        canvas.set_envelope(peaks)
        canvas.set_playhead(duration, position)

    def sync_live_preview(self):
        """Live mode mirrors the program, also before it rolls and while frozen."""
        if not self.preview_live or not self.preview_mpv.process:
            return
        entry = self.current_entry()
        if not entry:
            return
        if self.program_state == "PLAYING":
            self.live_parked = None
            rolling = not self.main_pause and not self.blackout
            if not self.preview_mpv.has_file(entry.path):
                self.show_preview_clip(
                    entry,
                    follow_live=True,
                    start=self.position,
                    play=rolling,
                )
                return
            want_pause = not rolling
            if self.preview_paused != want_pause:
                self.preview_mpv.set_pause(want_pause)
                self.preview_paused = want_pause
            self.preview_stopped = False
            if want_pause and abs(self.preview_position - self.position) > 0.5:
                self.preview_mpv.set_position(self.position)
            return
        # Nothing on air yet: park the preview on the frame the program will start with.
        start = entry.in_point or 0.0
        parked = (entry.path, start)
        if self.live_parked != parked or not self.preview_mpv.has_file(entry.path):
            self.show_preview_clip(entry, follow_live=True, start=start, play=False)
            self.live_parked = parked

    def program_seek_allowed(self):
        """Scrubbing the program is only safe while the Still button holds a frame.

        Volume setup may scrub whenever a clip is on air.
        """
        entry = self.current_entry()
        if entry is not None and entry.is_image:
            return False
        if getattr(self, "volume_setup", False) and self.program_state == "PLAYING":
            return True
        return self.program_state == "PLAYING" and self.main_pause and not self.blackout

    def _on_main_seek(self, position, dragging=False):
        self.position = position
        self.main_time.config(text=t("time_value", value=format_clock(position)))
        self.main_mpv.set_position(position)
        if self.preview_live:
            self.preview_mpv.set_position(position)

    def _on_preview_seek(self, position, dragging=False):
        self.preview_position = position
        self.preview_time.config(text=t("time_value", value=format_clock(position)))
        if getattr(self, "preview_envelope", None):
            self.preview_envelope.set_playhead(self._clip_duration(), position)
        if not self.preview_live:
            self._release_preview_range()
        self.preview_mpv.set_position(position)

    def _apply_program_clock(self, mpv):
        """Keep silent clips at speed 1 when HDMI audio has to be fed at speed 2."""
        entry = self.current_entry()
        on_program = (
            self.program_state == "PLAYING"
            and not self.idle_showing
            and entry
            and mpv.has_file(entry.path)
        )
        if not on_program:
            has_audio = None
        elif entry.audio_codec or entry.audio_tracks:
            has_audio = True
        elif entry.video_codec or entry.container:
            has_audio = False
        else:
            has_audio = None
        for prop, value in self.output_manager.program_clock_properties(has_audio):
            mpv.command("set_property", prop, value)

    def _program_eof_should_advance(self):
        """eof ends the clip only after this file itself has reached its end."""
        if self.hdmi_audio_keepalive or self.main_mpv.is_audio_keepalive():
            return False
        if getattr(self, "lights_play_after", None):
            return False
        if self.beamer_test_active or self.idle_showing or self.still_active():
            return False
        if self._program_loop_active() or self.program_state != "PLAYING":
            return False
        if self._program_loaded_id != self._program_load_id or not self._program_load_id:
            return False
        entry = self.current_entry()
        if not entry or not self.main_mpv.has_file(entry.path):
            return False
        duration = entry.duration or self.duration
        return program_end_signal_is_real(
            self._program_playhead, duration, playback_out_point(entry),
        )

    def main_mpv_event(self, mpv, message):
        event = message.get("event")
        if event == "file-loaded":
            mpv.mark_file_loaded()
            keepalive = mpv.is_audio_keepalive()
            if not keepalive:
                self._apply_program_clock(mpv)
            mpv.apply_pending_range()
            self.program_video_bps = 0
            self.program_audio_bps = 0
            if keepalive:
                self._reset_program_decode()
                self.hdmi_audio_keepalive = True
                self.main_pause = False
                return
            self.hdmi_audio_keepalive = False
            self.program_frame_drops = 0
            self.program_decoder_drops = 0
            entry = self.current_entry()
            if entry and mpv.has_file(entry.path):
                self._program_loaded_id = self._program_load_id
                self._program_playhead = None
                self.apply_tracks(entry, mpv)
                if entry.is_image and self._still_dim_active() and not self._still_fading_out:
                    # The still exists now. Restart the fade so it is not baked
                    # into a single black frame from before the file opened.
                    self.root.after(0, self._restart_still_fade_in)
                self._apply_program_loop(entry, mpv)
                if program_file_loaded_starts_clip(
                    self.program_state == "PLAYING", keepalive, True,
                ):
                    self._send_program_output_volume(mpv)
            self.main_pause = False
            return
        if event == "playback-restart":
            keepalive = bool(self.hdmi_audio_keepalive or mpv.is_audio_keepalive())
            if keepalive or self.idle_showing:
                return
            entry = self.current_entry()
            if program_playback_restart_starts_clip(
                self.program_state == "PLAYING",
                keepalive,
                bool(self.idle_showing),
                bool(entry and mpv.has_file(entry.path)),
            ):
                self._program_playback_started = True
                self._send_program_output_volume(mpv)
            return
        if event == "end-file" and message.get("reason") in (None, "eof", "stop"):
            if message.get("reason") == "eof" and self._program_eof_should_advance():
                self.root.after(0, self.on_clip_finished)
            return
        if event != "property-change":
            return
        name = message.get("name")
        value = message.get("data")
        if self.still_active() and name in ("time-pos", "duration", "eof-reached"):
            # A still has no useful clock of its own; the display timer drives it.
            return
        if name == "time-pos" and value is not None:
            try:
                position = float(value)
            except (TypeError, ValueError):
                return
            if not math.isfinite(position):
                return
            if self.program_state != "PLAYING" and not self.idle_showing:
                return
            entry = self.current_entry()
            if not program_clock_drives_playhead(
                bool(getattr(self, "lights_play_after", None)),
                self.program_state == "PLAYING",
                bool(self.idle_showing),
                bool(entry and mpv.has_file(entry.path)),
            ):
                return
            if (
                self.program_state == "PLAYING"
                and not self.idle_showing
                and self._program_loaded_id != self._program_load_id
            ):
                # The keepalive clock is still running until this file confirms.
                return
            self.position = position
            if self.program_state == "PLAYING" and not self.idle_showing:
                self._program_playhead = position
            end = playback_out_point(entry)
            if (
                self.program_state == "PLAYING"
                and end is not None
                and self.position >= end - 0.04
            ):
                if self._program_loop_active():
                    start = 0.0 if entry.in_point is None else entry.in_point
                    mpv.set_position(start)
                    if self.preview_live:
                        self.preview_mpv.set_position(start)
                else:
                    self.root.after(0, self.on_clip_finished)
        elif name == "duration" and value is not None:
            try:
                duration = float(value)
            except (TypeError, ValueError):
                return
            if math.isfinite(duration) and duration > 0 and self.idle_showing:
                self.duration = duration
        elif name == "pause" and value is not None:
            self.main_pause = bool(value)
        elif name == "eof-reached" and value:
            if self._program_eof_should_advance():
                self.root.after(0, self.on_clip_finished)
        elif name == "af-metadata/meter":
            self.program_levels = parse_preview_levels(value)[:2]
            self.program_levels_at = time.monotonic()
        elif name == "video-bitrate":
            self.program_video_bps = parse_bitrate_bps(value)
        elif name == "audio-bitrate":
            self.program_audio_bps = parse_bitrate_bps(value)
        elif name == "hwdec-current":
            self.program_hwdec = format_hwdec_current(value)
        elif name == "frame-drop-count":
            self.program_frame_drops = parse_mpv_count(value)
        elif name == "decoder-frame-drop-count":
            self.program_decoder_drops = parse_mpv_count(value)
        elif name == "path":
            text = str(value).strip() if value else ""
            mpv.active_path = os.path.abspath(text) if text else None

    def preview_mpv_event(self, mpv, message):
        event = message.get("event")
        if event == "file-loaded":
            mpv.apply_pending_range()
            self.preview_video_bps = 0
            self.preview_audio_bps = 0
            self._apply_preview_speaker()
            entry = self.selected_entry()
            if entry and mpv.has_file(entry.path):
                self.apply_tracks(entry, mpv)
                if self.preview_live and self.program_state == "PLAYING":
                    self._apply_program_loop(entry, mpv)
                else:
                    self._release_preview_range()
            return
        if event != "property-change":
            return
        name = message.get("name")
        value = message.get("data")
        if name == "time-pos" and value is not None:
            try:
                position = float(value)
            except (TypeError, ValueError):
                return
            if math.isfinite(position):
                self.preview_position = position
        elif name == "duration" and value is not None:
            try:
                duration = float(value)
            except (TypeError, ValueError):
                return
            if math.isfinite(duration) and duration > 0:
                self.preview_duration = duration
        elif name == "pause" and value is not None:
            self.preview_paused = bool(value)
        elif name == "af-metadata/meter":
            self.preview_levels = parse_preview_levels(value)[:2]
            self.preview_levels_at = time.monotonic()
        elif name == "video-bitrate":
            self.preview_video_bps = parse_bitrate_bps(value)
        elif name == "audio-bitrate":
            self.preview_audio_bps = parse_bitrate_bps(value)

    def _reset_preview_meter(self):
        self.preview_levels = []
        self.preview_levels_at = 0.0
        self._meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        self.preview_video_bps = 0
        self.preview_audio_bps = 0
        self._refresh_live_bitrates()
        try:
            self.preview_meter.reset()
        except (tk.TclError, AttributeError):
            pass

    def _reset_program_meter(self):
        self.program_levels = []
        self.program_levels_at = 0.0
        self._program_meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        self.program_video_bps = 0
        self.program_audio_bps = 0
        self._reset_program_decode()
        self._refresh_live_bitrates()
        try:
            self.program_meter.reset()
        except (tk.TclError, AttributeError):
            pass

    def _program_bitrate_active(self):
        return (
            self.program_state == "PLAYING"
            and bool(self.main_mpv.loaded_path)
            and not self.idle_showing
            and not self.beamer_test_active
        )

    def _preview_bitrate_active(self):
        return (
            bool(self.preview_mpv.process)
            and bool(self.preview_mpv.loaded_path)
            and not self.preview_stopped
        )

    @staticmethod
    def _live_bitrate_text(bps, active):
        if not active:
            return "--"
        return format_bitrate(bps) or "--"

    def _apply_bitrate_text(self, label, text):
        """Replace the readout text. The label stays in the grid at a fixed width."""
        if label is None:
            return
        if getattr(label, "_shown_bitrate", None) == text:
            return
        label._shown_bitrate = text
        try:
            label.config(text=text)
        except (tk.TclError, AttributeError):
            pass

    def _refresh_live_bitrates(self):
        program_on = self._program_bitrate_active()
        preview_on = self._preview_bitrate_active()
        self._apply_bitrate_text(
            getattr(self, "program_video_bitrate", None),
            self._live_bitrate_text(self.program_video_bps, program_on),
        )
        self._apply_bitrate_text(
            getattr(self, "program_audio_bitrate", None),
            self._live_bitrate_text(self.program_audio_bps, program_on),
        )
        self._apply_bitrate_text(
            getattr(self, "preview_video_bitrate", None),
            self._live_bitrate_text(self.preview_video_bps, preview_on),
        )
        self._apply_bitrate_text(
            getattr(self, "preview_audio_bitrate", None),
            self._live_bitrate_text(self.preview_audio_bps, preview_on),
        )

    @staticmethod
    def _meter_target(playing, levels, levels_at):
        age = time.monotonic() - levels_at if levels_at else 1e9
        if playing and age < 0.2 and levels:
            target = list(levels[:2])
            if len(target) == 1:
                target = [target[0], target[0]]
            return target
        return [METER_FLOOR_DB, METER_FLOOR_DB]

    @staticmethod
    def _meter_ballistics(shown, target, dt=0.05):
        if len(shown) != 2:
            shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        next_shown = []
        for index in range(2):
            current = shown[index]
            goal = target[index]
            if goal > current:
                current = goal
            else:
                current = max(goal, current - 28.0 * dt)
            next_shown.append(current)
        return next_shown

    @staticmethod
    def _meter_post_fader(shown, volume):
        gain = volume_gain_db(volume)
        if gain is None:
            return [METER_FLOOR_DB, METER_FLOOR_DB]
        return [
            max(METER_FLOOR_DB, min(METER_CEILING_DB, db + gain))
            for db in shown
        ]

    def _tick_meters(self):
        preview_playing = (
            bool(self.preview_mpv.process)
            and bool(self.preview_mpv.loaded_path)
            and not self.preview_paused
            and not self.preview_stopped
        )
        self._meter_shown = self._meter_ballistics(
            self._meter_shown,
            self._meter_target(preview_playing, self.preview_levels, self.preview_levels_at),
        )
        program_playing = (
            self.program_state == "PLAYING"
            and bool(self.main_mpv.process)
            and bool(self.main_mpv.loaded_path)
            and not self.main_pause
            and not self.blackout
            and not self.idle_showing
            and not self.beamer_test_active
        )
        self._program_meter_shown = self._meter_ballistics(
            self._program_meter_shown,
            self._meter_target(program_playing, self.program_levels, self.program_levels_at),
        )
        try:
            self.preview_meter.set_levels(
                self._meter_post_fader(self._meter_shown, self.preview_volume.get())
            )
            output = getattr(self, "_program_volume_output", None)
            if output is None:
                output = self.program_volume.get()
            self.program_meter.set_levels(
                self._meter_post_fader(self._program_meter_shown, output)
            )
            self._meter_after_id = self.root.after(50, self._tick_meters)
        except (tk.TclError, AttributeError):
            self._meter_after_id = None

    def _has_playable_after(self, index):
        if not self.playlist:
            return False
        for item in self.playlist[index + 1:]:
            if not item.missing and media_file_available(item):
                return True
        return False

    def _maybe_lights_before_end(self):
        if self.lights_end_sent or getattr(self, "lights_play_after", None):
            return
        if self.calibration_mode or not bool(self.lights_control.get()):
            return
        lead = max(0, int(self.lights_end_lead_ms or 0)) / 1000.0
        if lead <= 0:
            return
        if self.program_state != "PLAYING" or self.idle_showing or self.main_pause:
            return
        if self._program_loop_active() or self.still_waiting:
            return
        entry = self.current_entry()
        file_duration = (entry.duration if entry and entry.duration else 0) or self.duration or 0
        in_point = out_point = None
        if entry and not entry.is_image:
            in_point = entry.in_point
            out_point = entry.out_point
        try:
            position = float(self.position or 0)
        except (TypeError, ValueError):
            return
        if not math.isfinite(file_duration) or not math.isfinite(position):
            return
        _start, _end, total, _elapsed, remaining = clip_span(
            file_duration, position, in_point, out_point, playing=True,
        )
        if total <= 0:
            return
        if remaining > lead:
            return
        autoplay_continues = bool(
            entry and entry.autoplay and self._has_playable_after(self.program_index)
        )
        self.lights_end_sent = True
        preset = dmx.resolve_end_preset("", autoplay_continues, self.lights_scenes)
        if autoplay_continues and preset == "dark":
            return
        self._apply_lights(preset)

    def _drain_light_errors(self):
        lock = getattr(self, "_light_error_lock", None)
        if lock is None:
            return
        with lock:
            pending = list(self._light_errors)
            self._light_errors.clear()
        for error in pending:
            self._show_lights_error(error)

    def update_gui(self):
        try:
            self._drain_light_errors()
            if self.still_started is not None and self.program_state == "PLAYING":
                self.position = min(self.duration, time.monotonic() - self.still_started)
            if not self.main_progress.dragging:
                self._update_main_bar()
            if not self.preview_progress.dragging:
                self._update_preview_bar()
            self._refresh_live_bitrates()
            self.preview_time.config(text=t("time_value", value=format_clock(self.preview_position)))
            self.sync_live_preview()
            self.refresh_status()
            self.refresh_beamer()
            self._maybe_lights_before_end()
        except Exception as exc:
            print(f"GUI-Aktualisierung: {exc}")
        self.root.after(250, self.update_gui)

    def _ask_unsaved_playlist(self):
        """Ask whether to cancel, save, or quit. Closing the window cancels."""
        result = {"choice": "cancel"}
        window = tk.Toplevel(self.root)
        window.title(t("quit"))
        window.configure(bg=COLOR_BG)
        window.minsize(420, 140)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        body = tk.Frame(window, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        tk.Label(
            body, text=t("quit_unsaved"), bg=COLOR_BG, fg=COLOR_TEXT,
            font=FONT_UI, wraplength=440, justify="left",
        ).pack(fill="x")
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        def choose(choice):
            result["choice"] = choice
            window.destroy()

        tk.Button(
            buttons, text=t("quit_cancel"), command=lambda: choose("cancel"), font=FONT_UI,
        ).pack(side="left")
        tk.Button(
            buttons, text=t("quit_save"), command=lambda: choose("save"), font=FONT_UI,
        ).pack(side="left", padx=(8, 0))
        tk.Button(
            buttons, text=t("quit"), command=lambda: choose("quit"), font=FONT_UI,
        ).pack(side="left", padx=(8, 0))
        window.bind("<Escape>", lambda _event: choose("cancel"))
        window.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        self._open_popup(window, 480, 160)
        self._grab_popup(window)
        self.root.wait_window(window)
        return result["choice"]

    def _save_playlist_for_quit(self):
        """Write the current playlist. A new file asks for a path."""
        if self.playlist_path:
            try:
                self._write_playlist(self.playlist_path)
            except OSError as exc:
                messagebox.showerror(
                    t("save_playlist"), t("import_playlist_save_failed", error=exc),
                )
                return False
            return True
        return bool(self.save_playlist())

    def _confirm_close_playlist(self):
        """True when the window may close."""
        if not self._playlist_has_unsaved_changes():
            return True
        choice = self._ask_unsaved_playlist()
        if choice == "save":
            return self._save_playlist_for_quit()
        return choice == "quit"

    def close(self, _event=None):
        if self.program_state != "OFF":
            messagebox.showinfo(t("quit"), t("quit_busy"))
            return "break"
        if not self._confirm_close_playlist():
            return "break"
        self._close_menus()
        self._stop_remote_api()
        self._cancel_program_volume_glide()
        self._cancel_header_clock()
        for after_id in (
            self.autoplay_after_id, self.idle_after_id, self.still_after_id, self._meter_after_id,
            self.lights_fade_after, self.lights_blink_after, self.lights_play_after,
        ):
            if after_id:
                self.root.after_cancel(after_id)
        try:
            self.preview_mpv.quit()
            self.main_mpv.quit()
        finally:
            dmx.shutdown()
            self.output_manager.restore_original_mode()
            self.root.destroy()


def aspect_from_mode(mode):
    if not mode or not mode.height:
        return "--"
    return aspect_from_size(mode.width, mode.height)


def aspect_from_size(width, height):
    if not height:
        return "--"
    ratio = width / height
    if abs(ratio - 16 / 9) < 0.05:
        return "16:9"
    if abs(ratio - 2.39) < 0.08:
        return "21:9"
    if abs(ratio - 4 / 3) < 0.05:
        return "4:3"
    return f"{width}:{height}"
