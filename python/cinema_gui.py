"""Cinema Player control GUI matching the layout mockup."""

from __future__ import annotations

import font_setup  # noqa: F401  — load Inter before tkinter opens fontconfig

import json
import math
import os
import re
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from language import LANGUAGES, t, set_language
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
    apply_playlist_warnings,
    clamp_volume,
    find_mpv,
    find_ffmpeg,
    format_clock,
    format_codec_rate,
    format_fps_label,
    format_colorspace_label,
    format_loudness,
    mark_missing_media,
    media_file_available,
    probe_loudness,
    probe_media,
    refresh_entry_aspect,
)

LOGO_BG = "#000000"
LOGO_ACCENT = "#4d9be6"
FONT_LOGO = (FONT_FAMILY, 17, "bold")
FONT_LOGO_LIGHT = (FONT_FAMILY, 17)
LOGO_HEADER_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-logo-header.png")
LOGO_ICON_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-icon.png")
BEAMER_TEST_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-logo.png")
# mpv log2 zoom: -0.8 ≈ 57% size, so the wide logo does not fill the screen width.
BEAMER_TEST_ZOOM = -0.8
ICONS_DIR = os.path.join(ROOT_DIR, "assets", "icons")
TESTDATA_DIR = os.path.join(ROOT_DIR, "testdata")
TRANSPORT_ICON_PX = 52
DRAG_THRESHOLD = 12

# Status colours keep their meaning in every design.
COLOR_OFF = "#c62828"
COLOR_PROGRAM = "#1565c0"
COLOR_PLAYING = "#2e9d3a"
COLOR_PREVIEW = "#c9a227"
COLOR_WARNING = "#d32f2f"
COLOR_WHITE = "#ffffff"

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
    },
}

DEFAULT_THEME = "dark"
THEME = DEFAULT_THEME


def apply_theme(name):
    """Rebind the palette names so widgets built afterwards use the chosen design."""
    global THEME, COLOR_BG, COLOR_PANEL, COLOR_ROW, COLOR_TEXT, COLOR_MUTED, COLOR_PLAYED
    global COLOR_BORDER, COLOR_READOUT, COLOR_BADGE_IDLE, COLOR_BUTTON, COLOR_BUTTON_ACTIVE
    global COLOR_FIELD, COLOR_VIDEO, TRACK_BG, TRACK_EDGE, RANGE_FILL, PLAYHEAD, MARKER, ACCENT, COLOR_VOLUME

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

    def __init__(self, master, on_change, **kwargs):
        kwargs.setdefault("height", 22)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("bd", 0)
        kwargs.setdefault("bg", COLOR_PANEL)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, **kwargs)
        self.on_change = on_change
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
                fill=COLOR_VOLUME, outline="",
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


_PEAK_LEVEL_RE = re.compile(r"^lavfi\.astats\.(\d+)\.Peak_level$")
METER_FLOOR_DB = -60.0
METER_CEILING_DB = 0.0
METER_TICKS_DB = (0, -6, -12, -18, -24, -36, -48, -60)
METER_AF = "@meter:lavfi=[astats=metadata=1:reset=1]"


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
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except tk.TclError:
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tip, text=self.text, font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_TEXT,
            relief="solid", bd=1, padx=8, pady=4,
        ).pack()
        self._window = tip


def format_seconds(value):
    seconds = max(0.0, float(value or 0))
    return str(int(seconds)) if seconds == int(seconds) else f"{seconds:g}"


def settings_path():
    return os.path.join(os.path.expanduser("~"), ".config", "cinema-player", "settings.json")


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


class VideoPlayerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Cinema Player {APP_VERSION}")
        self.icon_image = self._load_image(LOGO_ICON_FILE)
        if self.icon_image is not None:
            self.root.iconphoto(True, self.icon_image)
        self.root.minsize(1280, 720)
        self.root.geometry("1600x900")

        self.settings = load_settings()
        self.language = set_language(self.settings.get("language", "en"))
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
        self.preview_levels = []
        self.preview_levels_at = 0.0
        self._meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        self.program_levels = []
        self.program_levels_at = 0.0
        self._program_meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        self._meter_after_id = None
        self.main_pause = False
        self.blackout = False
        self.idle_media_path = ""
        self.idle_showing = False
        self.beamer_test_active = False
        self.idle_after_id = None
        self.autoplay_after_id = None
        self.still_after_id = None
        self.still_started = None
        self.still_waiting = False
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
        self.last_playlist_dir = self.settings.get("last_playlist_dir") or ""
        if self.last_playlist_dir and not os.path.isdir(self.last_playlist_dir):
            self.last_playlist_dir = ""
        self.last_playlist_path = self.settings.get("last_playlist_path") or ""
        if self.last_playlist_path and not os.path.isfile(self.last_playlist_path):
            self.last_playlist_path = ""

        self.projection_zoom = tk.BooleanVar(value=False)
        self.autosave_on_program_change = tk.BooleanVar(
            value=bool(self.settings.get("autosave_on_program_change", False))
        )
        self.load_last_playlist_at_start = tk.BooleanVar(
            value=bool(self.settings.get("load_last_playlist_at_start", False))
        )
        self.window_fullscreen = tk.BooleanVar(
            value=bool(self.settings.get("window_fullscreen", False))
        )
        self._windowed_geometry = None
        self._fullscreen_applied = False
        self.autoplay_delay = tk.StringVar(value="0")
        self.idle_media = tk.StringVar(value=t("idle_none"))
        self.autoplay_var = tk.BooleanVar(value=False)
        self.played_var = tk.BooleanVar(value=False)
        self.display_time = tk.StringVar(value="0")
        self.audio_var = tk.StringVar(value="--")
        self.subtitle_var = tk.StringVar(value="--")
        self.program_volume = tk.DoubleVar(value=100)
        self.preview_volume = tk.DoubleVar(value=100)
        self.beamer_output = tk.StringVar(value=self.output_manager.video_output or "")
        self._volume_preview_key = None
        self._volume_program_key = None

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
        self.root.after(400, lambda: self.ensure_main_output(auto=not explicit_output))
        self.root.after(500, self._warn_if_no_beamer_output)
        self.update_gui()
        self._tick_meters()
        self.refresh_all()
        self._restore_last_playlist()

    def _warn_if_no_beamer_output(self):
        if self.output_manager.has_dedicated_beamer():
            return
        messagebox.showwarning(t("beamer_no_output_title"), t("beamer_no_output"))

    def create_gui(self):
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        self._build_logo()

        left = tk.Frame(self.root, bg=COLOR_BG)
        left.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(3, weight=1)

        right = tk.Frame(self.root, bg=COLOR_BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        self._build_program_status(left)
        self._build_program_block(left)
        self._build_playlist_block(left)
        self._build_beamer(right)
        self._build_preview(right)

    def _build_logo(self):
        header = tk.Frame(self.root, bg=COLOR_BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6))

        self.app_menu = self._burger_button(
            header, t("app_menu"), self._fill_app_menu, side="right",
        )

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
        tk.Label(
            header, text=f"v{APP_VERSION}", bg=COLOR_BG, fg=COLOR_MUTED, font=FONT_UI,
        ).pack(side="left", padx=(10, 0), pady=(0, 8), anchor="s")

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

    def apply_widget_defaults(self):
        """Colour the widget classes that are built without explicit colours."""
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
            "Vertical.TScrollbar", background=COLOR_BUTTON, troughcolor=COLOR_BG,
            arrowcolor=COLOR_TEXT, bordercolor=COLOR_BORDER, lightcolor=COLOR_BUTTON,
            darkcolor=COLOR_BUTTON,
        )
        style.map("Vertical.TScrollbar", background=[("active", COLOR_BUTTON_ACTIVE)])

    def toggle_theme(self):
        self.theme = apply_theme("dark" if self.theme == "light" else "light")
        self.settings["theme"] = self.theme
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self.rebuild_gui()

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

    def rebuild_gui(self):
        """Rebuild the window for the current design and re-embed the preview player."""
        self.preview_mpv.quit()
        self._close_menus()
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
        self.apply_widget_defaults()
        self.create_gui()
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

    def _build_program_block(self, parent):
        group = self._group_frame(parent)
        group.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        group.columnconfigure(0, weight=1)
        self.program_group = group

        body = tk.Frame(group, bg=COLOR_PANEL)
        body.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=6)
        body.columnconfigure(0, weight=1)

        progress = tk.Frame(body, bg=COLOR_PANEL)
        progress.grid(row=0, column=0, sticky="ew")
        progress.columnconfigure(0, weight=1)

        self.main_progress = RangeProgressBar(
            progress, on_seek=self._on_main_seek, can_seek=self.program_seek_allowed,
            height=32, bg=COLOR_PANEL,
        )
        self.main_progress.grid(row=0, column=0, sticky="ew")

        volume = self._build_volume_row(
            progress, self.program_volume, self._on_program_volume, COLOR_PANEL,
        )
        volume.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))

        marks = tk.Frame(progress, bg=COLOR_PANEL)
        marks.grid(row=2, column=0, sticky="ew", padx=8)
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
        times.grid(row=0, column=1, sticky="ew")
        for col in range(4):
            times.columnconfigure(col, weight=1)
        self.time_total = self._time_box(times, t("total"), 0)
        self.time_elapsed = self._time_box(times, t("elapsed"), 1)
        self.time_remaining = self._time_box(times, t("remaining"), 2)
        self.time_end = self._time_box(times, t("end"), 3)

        self.program_meter = LevelMeter(group, bg=COLOR_PANEL, height=1)
        self.program_meter.grid(row=0, column=1, sticky="ns", padx=(8, 8), pady=6)

    def _time_box(self, parent, title, column):
        box = tk.Frame(parent, bg=COLOR_PANEL)
        box.grid(row=0, column=column, sticky="ew")
        tk.Label(box, text=title, font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED).pack()
        value = tk.Label(box, text="--:--", font=FONT_UI_BOLD, bg=COLOR_PANEL, fg=COLOR_TEXT)
        value.pack()
        return value

    def _build_volume_row(self, parent, variable, on_change, bg, save=False):
        row = tk.Frame(parent, bg=bg)
        tk.Label(row, text=t("volume"), bg=bg, fg=COLOR_TEXT, font=FONT_SMALL).pack(side="left")
        bar = VolumeBar(row, on_change=on_change, bg=bg)
        bar.pack(side="left", fill="x", expand=True, padx=8)
        bar.set_volume(variable.get())
        label = tk.Label(
            row, text=str(clamp_volume(variable.get())), width=3, anchor="e",
            bg=bg, fg=COLOR_VOLUME, font=FONT_UI_BOLD,
        )
        label.pack(side="left")
        tk.Label(row, text="%", bg=bg, fg=COLOR_VOLUME, font=FONT_SMALL).pack(side="left", padx=(2, 0))
        if save:
            self.preview_volume_bar = bar
            self.preview_volume_label = label
            tk.Button(
                row, text=t("save_volume"), font=FONT_SMALL, command=self.save_preview_volume,
            ).pack(side="left", padx=(8, 0))
        else:
            self.program_volume_bar = bar
            self.program_volume_label = label
        return row

    def _set_volume_label(self, label, volume):
        if label is not None:
            label.config(text=str(clamp_volume(volume)), fg=COLOR_VOLUME)

    def _on_program_volume(self, value):
        volume = clamp_volume(value)
        self.program_volume.set(volume)
        self._set_volume_label(self.program_volume_label, volume)
        if self.program_state == "PLAYING" and not self.idle_showing:
            self.main_mpv.set_volume(volume)

    def _on_preview_volume(self, value):
        volume = clamp_volume(value)
        self.preview_volume.set(volume)
        self._set_volume_label(self.preview_volume_label, volume)
        self.preview_mpv.set_volume(volume)

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
            if self.program_state == "PLAYING" and not self.idle_showing:
                self.main_mpv.set_volume(entry.volume)
        self.repaint_playlist()

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
        self.preview_mpv.set_volume(volume)

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
        self.btn_stop = self._icon_button(row, "stop", self.confirm_stop, t("stop"))
        self.btn_pause = self._icon_button(row, "pause", self.confirm_pause, t("pause"))
        self.btn_still = self._icon_button(row, "still", self.confirm_still, t("still"))
        self.btn_play = self._icon_button(row, "start_program", self.start_or_resume, t("start"))

    def _icon_button(self, parent, icon_name, command, fallback_text, tip=None):
        image = self._transport_icon(icon_name)
        button = tk.Button(
            parent,
            text=fallback_text,
            command=command,
            image=image,
            compound="none" if image is not None else "center",
            bd=0,
            highlightthickness=0,
            relief="flat",
            bg=parent.cget("bg"),
            activebackground=parent.cget("bg"),
            cursor="hand2",
            padx=2,
            pady=2,
        )
        if image is None:
            button.config(font=FONT_SMALL, width=7)
        button.icon_name = icon_name
        button.pack(side="left", padx=(0, 6))
        button.tooltip = IconTooltip(button, tip if tip is not None else fallback_text)
        return button

    def _set_transport_active(self, button, active, variant=None, enabled=True):
        """Swap the highlight or disabled icon instead of painting a Tk ring."""
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

    def refresh_transport(self):
        playing = self.program_state == "PLAYING"
        paused = playing and self.main_pause and self.blackout
        frozen = playing and self.main_pause and not self.blackout
        rolling = playing and not self.main_pause
        armed = self.program_state == "PROGRAM"
        self._set_transport_active(self.btn_stop, False, enabled=self.program_state != "OFF")
        self._set_transport_active(self.btn_pause, paused, "preview", enabled=playing)
        self._set_transport_active(self.btn_still, frozen, "program", enabled=playing)
        self._set_transport_active(
            self.btn_play, rolling or armed, "playing" if rolling else "program",
        )

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
        controls.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        controls.columnconfigure(0, weight=1)
        self.playlist_group = controls
        self._build_playlist_header(controls)
        self._build_playlist_settings(controls)

        entries = self._group_frame(parent)
        entries.grid(row=3, column=0, sticky="nsew")
        entries.columnconfigure(0, weight=1)
        entries.rowconfigure(0, weight=1)
        self._build_playlist(entries)

    def _build_playlist_header(self, parent):
        header = tk.Frame(parent, bg=COLOR_PANEL)
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 2))
        header.columnconfigure(1, weight=1)

        tk.Label(
            header, text=t("playlist"), font=FONT_UI_BOLD, bg=COLOR_PANEL, fg=COLOR_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.playlist_name = tk.Entry(header, font=FONT_UI)
        self.playlist_name.insert(0, "untitled.pls")
        self.playlist_name.grid(row=0, column=1, sticky="ew")

        buttons = tk.Frame(header, bg=COLOR_PANEL)
        buttons.grid(row=0, column=2, sticky="e", padx=(8, 0))
        self._icon_button(buttons, "video_import", self.import_media, t("import"), t("import_media"))
        self._icon_button(buttons, "playlist_new", self.new_playlist, t("new"), t("new_playlist"))
        self._icon_button(buttons, "playlist_load", self.load_playlist, t("load"), t("load_playlist"))
        self._icon_button(buttons, "playlist_save", self.save_playlist, t("save"), t("save_playlist"))
        self._burger_button(buttons, t("playlist_menu"), self._fill_playlist_menu)

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
        menu = self._menu(self.root)
        fill_menu(menu)

        def popup(_event=None):
            menu.delete(0, "end")
            fill_menu(menu)
            self._popup_menu(
                menu, canvas.winfo_rootx(), canvas.winfo_rooty() + canvas.winfo_height(),
            )

        canvas.bind("<Button-1>", popup)
        padx = (8, 0) if side == "right" else (0, 6)
        canvas.pack(side=side, padx=padx)
        canvas.tooltip = IconTooltip(canvas, tooltip)
        canvas.menu = menu
        return canvas

    def _arm_menu_dismiss_binds(self):
        if self._menu_binds_armed:
            return
        self.root.bind_all("<ButtonPress>", self._on_global_press_while_menu, add="+")
        self.root.bind_all("<Escape>", self._on_escape_while_menu, add="+")
        self._menu_binds_armed = True

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
        menu = self._posted_menu
        if menu is None:
            return False
        menus = [menu]
        try:
            menus.extend(
                child for child in menu.winfo_children() if isinstance(child, tk.Menu)
            )
        except tk.TclError:
            pass
        for item in menus:
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

    def _fill_app_menu(self, menu):
        menu.add_command(
            label=t("theme_to_light") if self.theme == "dark" else t("theme_to_dark"),
            command=self.toggle_theme,
        )
        menu.add_checkbutton(
            label=t("window_fullscreen"),
            variable=self.window_fullscreen,
            command=self._on_window_fullscreen,
            accelerator="F11",
        )
        menu.add_separator()
        languages = self._menu(menu)
        for code, name in LANGUAGES.items():
            mark = "✔  " if code == self.language else "    "
            languages.add_command(
                label=f"{mark}{name}",
                command=lambda chosen=code: self.change_language(chosen),
                foreground=self._menu_check_fg() if code == self.language else COLOR_TEXT,
            )
        menu.add_cascade(label=t("language"), menu=languages)
        menu.add_separator()
        outputs = self._menu(menu)
        self._fill_beamer_output_menu(outputs)
        menu.add_cascade(label=t("beamer_output"), menu=outputs)
        menu.add_command(
            label=t("beamer_test"),
            command=self.show_beamer_test,
            state="normal" if self.program_state == "OFF" else "disabled",
        )
        menu.add_separator()
        menu.add_command(
            label=t("load_testdata"),
            command=self.load_testdata_playlist,
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
            return
        for name in names:
            mark = "✔  " if name == current else "    "
            menu.add_command(
                label=f"{mark}{name}",
                command=lambda chosen=name: self.apply_beamer_output(chosen),
                state="disabled" if busy else "normal",
                foreground=self._menu_check_fg() if name == current else COLOR_TEXT,
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

    def _build_playlist_settings(self, parent):
        settings = tk.Frame(parent, bg=COLOR_PANEL)
        settings.grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 6))

        self._checkbutton(
            settings, t("projection_zoom"), self.projection_zoom, self.refresh_playlist, COLOR_PANEL,
        ).pack(side="left")

        tk.Label(settings, text=t("autoplay_delay"), bg=COLOR_PANEL, font=FONT_UI).pack(side="left", padx=(16, 4))
        tk.Entry(settings, textvariable=self.autoplay_delay, width=5, font=FONT_UI).pack(side="left")
        tk.Label(settings, text=t("seconds_short"), bg=COLOR_PANEL, font=FONT_UI).pack(side="left")

        tk.Label(settings, text=t("idle_media"), bg=COLOR_PANEL, font=FONT_UI).pack(side="left", padx=(16, 4))
        self.idle_button = tk.Button(
            settings, textvariable=self.idle_media, font=FONT_SMALL,
            command=self.choose_idle_media,
        )
        self.idle_button.pack(side="left")

        self.playlist_settings = settings

    def _build_playlist(self, parent):
        holder = tk.Frame(parent, bg=COLOR_PANEL)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        self.playlist_canvas = tk.Canvas(holder, bg=COLOR_PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.playlist_canvas.yview)
        self.playlist_inner = tk.Frame(self.playlist_canvas, bg=COLOR_PANEL)
        self.playlist_inner.bind(
            "<Configure>",
            lambda e: self.playlist_canvas.configure(scrollregion=self.playlist_canvas.bbox("all")),
        )
        self.playlist_window = self.playlist_canvas.create_window((0, 0), window=self.playlist_inner, anchor="nw")
        self.playlist_canvas.configure(yscrollcommand=scroll.set)
        self.playlist_canvas.bind(
            "<Configure>",
            lambda e: self.playlist_canvas.itemconfigure(self.playlist_window, width=e.width),
        )
        self.playlist_canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.playlist_canvas.bind("<Enter>", lambda e: self.playlist_canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.playlist_canvas.bind("<Leave>", lambda e: self.playlist_canvas.unbind_all("<MouseWheel>"))
        self.playlist_canvas.bind("<Button-4>", self._on_mousewheel)
        self.playlist_canvas.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if event.num == 5 or event.delta < 0:
            self.playlist_canvas.yview_scroll(1, "units")
        else:
            self.playlist_canvas.yview_scroll(-1, "units")

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

        info = tk.Frame(panel, bg=COLOR_PANEL)
        info.pack(fill="x", padx=8, pady=(0, 8))
        self.beamer_res = tk.Label(info, text="---- x ----", font=FONT_UI, bg=COLOR_PANEL)
        self.beamer_res.pack(side="left")
        self.beamer_fps = tk.Label(info, text="--p", font=FONT_UI_BOLD, bg=COLOR_PANEL)
        self.beamer_fps.pack(side="left", padx=16)
        self.beamer_aspect = tk.Label(info, text="--", font=FONT_UI, bg=COLOR_PANEL)
        self.beamer_aspect.pack(side="left")
        self.beamer_rates = tk.Label(
            panel, text=t("beamer_rates", rates="--"), font=FONT_SMALL,
            bg=COLOR_PANEL, fg=COLOR_MUTED, anchor="w", justify="left", wraplength=520,
        )
        self.beamer_rates.pack(fill="x", padx=8, pady=(0, 8))
        self._beamer_rates_cache = None

    def _build_preview(self, parent):
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
        footer = tk.Frame(settings, bg=COLOR_PANEL)
        footer.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 6))
        self._checkbutton(
            footer, t("autoplay"), self.autoplay_var, self.apply_entry_settings, COLOR_PANEL,
        ).pack(side="left")

        clip_settings = tk.Frame(footer, bg=COLOR_PANEL)
        clip_settings.pack(side="left")
        self.preview_clip_settings = clip_settings
        self._checkbutton(
            clip_settings, t("played"), self.played_var, self.apply_entry_settings, COLOR_PANEL,
        ).pack(side="left", padx=(8, 0))
        tk.Label(clip_settings, text=t("audio_track"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left", padx=(12, 4))
        self.audio_combo = ttk.Combobox(clip_settings, textvariable=self.audio_var, width=16, state="readonly")
        self.audio_combo.pack(side="left")
        self.audio_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_entry_settings())
        tk.Label(clip_settings, text=t("subtitle"), bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left", padx=(12, 4))
        self.subtitle_combo = ttk.Combobox(clip_settings, textvariable=self.subtitle_var, width=12, state="readonly")
        self.subtitle_combo.pack(side="left")
        self.subtitle_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_entry_settings())

        image_settings = tk.Frame(footer, bg=COLOR_PANEL)
        self.preview_image_settings = image_settings
        tk.Label(image_settings, text=t("display_time"), bg=COLOR_PANEL, font=FONT_SMALL).pack(
            side="left", padx=(12, 4)
        )
        entry_box = tk.Entry(image_settings, textvariable=self.display_time, width=5, font=FONT_UI)
        entry_box.pack(side="left")
        entry_box.bind("<Return>", lambda e: self.apply_entry_settings())
        entry_box.bind("<FocusOut>", lambda e: self.apply_entry_settings())
        tk.Label(
            image_settings, text=t("display_time_hint"), bg=COLOR_PANEL, font=FONT_SMALL,
            fg=COLOR_MUTED,
        ).pack(side="left", padx=(4, 0))

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
            fg=COLOR_MUTED, font=(FONT_FAMILY, 16),
        )
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        controls = self._group_frame(parent)
        controls.grid(row=4, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)
        self.preview_controls = controls

        self.preview_progress = RangeProgressBar(
            controls, on_seek=self._on_preview_seek, height=32,
        )
        self.preview_progress.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))

        self.preview_volume_row = self._build_volume_row(
            controls, self.preview_volume, self._on_preview_volume, COLOR_PANEL,
            save=True,
        )
        self.preview_volume_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))

        marks = tk.Frame(controls, bg=COLOR_PANEL)
        marks.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 4))
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
        buttons.grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

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

    def state_color(self):
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

    def refresh_all(self):
        self.refresh_status()
        self.refresh_playlist()
        self.refresh_preview_meta()
        self.refresh_beamer()

    def refresh_status(self):
        state_key = {"OFF": "state_off", "PROGRAM": "state_program", "PLAYING": "state_playing"}[self.program_state]
        self.state_label.config(text=t(state_key), bg=self.state_color())
        stopped = self.program_state == "OFF"
        entry = None if stopped else self.current_entry()
        if stopped:
            self.now_playing.config(text=t("no_program"), bg=COLOR_READOUT, fg=COLOR_TEXT)
            self.program_times.config(text="- / --:--")
        else:
            name = entry.filename if entry else t("no_program")
            self.now_playing.config(text=name, bg=self.state_color(), fg=COLOR_WHITE)
            index = f"{self.program_index + 1}" if self.playlist else "-"
            self.program_times.config(
                text=f"{index} / {format_clock(self.duration if self.duration else (entry.duration if entry else 0))}"
            )
        if stopped:
            self.btn_play.icon_name = "start_program"
            self.btn_play.config(text=t("start"))
            self.btn_play.tooltip.text = t("start")
        else:
            self.btn_play.icon_name = "play"
            self.btn_play.config(text=t("resume"))
            self.btn_play.tooltip.text = t("resume")
        # The idle media button turns green while its media is on the projector.
        if self.idle_showing:
            self.idle_button.config(
                bg=COLOR_PLAYING, fg=COLOR_WHITE,
                activebackground=COLOR_PLAYING, activeforeground=COLOR_WHITE,
            )
        else:
            self.idle_button.config(
                bg=COLOR_BUTTON, fg=COLOR_TEXT,
                activebackground=COLOR_BUTTON_ACTIVE, activeforeground=COLOR_TEXT,
            )
        self.refresh_transport()
        if stopped:
            blank = format_clock(None)
            self.time_total.config(text=blank)
            self.time_elapsed.config(text=blank)
            self.time_remaining.config(text=blank)
            self.time_end.config(text=blank)
        else:
            self.time_total.config(text=format_clock(self.duration or (entry.duration if entry else None)))
            self.time_elapsed.config(text=format_clock(self.position if self.program_state == "PLAYING" else 0))
            remaining = None
            if self.duration and math.isfinite(self.duration) and math.isfinite(self.position):
                remaining = max(0, self.duration - self.position)
            self.time_remaining.config(text=format_clock(remaining))
            end_text = "--:--"
            if remaining is not None:
                end_text = (datetime.now() + timedelta(seconds=remaining)).strftime("%H:%M:%S")
            self.time_end.config(text=end_text)
        if self.program_state != "PLAYING":
            self._load_program_volume(entry)

    def refresh_playlist(self):
        for child in self.playlist_inner.winfo_children():
            child.destroy()
        self.row_widgets = []
        apply_playlist_warnings(self.playlist, self.projection_zoom.get())
        for index, entry in enumerate(self.playlist):
            self._make_row(index, entry)

    def _row_colors(self, index, entry):
        bg = COLOR_ROW
        fg = COLOR_PLAYED if entry.played and index != self.program_index else COLOR_TEXT
        if entry.missing:
            fg = COLOR_WARNING
        if self.program_state == "PLAYING" and index == self.program_index:
            bg, fg = COLOR_PLAYING, COLOR_WHITE
        elif self.preview_index == index and not self.preview_live:
            bg, fg = COLOR_PREVIEW, COLOR_WHITE
        elif self.program_state == "PROGRAM" and index == self.program_index:
            bg, fg = COLOR_PROGRAM, COLOR_WHITE
        return bg, fg

    def _row_duration_text(self, entry):
        """Stills show their display time, or that they wait for the operator."""
        if not entry.is_image:
            return format_clock(entry.duration)
        if entry.display_time > 0:
            return format_clock(entry.display_time)
        return t("until_resume")

    def _make_row(self, index, entry):
        bg, fg = self._row_colors(index, entry)

        row = tk.Frame(self.playlist_inner, bg=bg, padx=6, pady=4)
        row.pack(fill="x", pady=1, padx=2)
        row.columnconfigure(1, weight=1)

        cursor = tk.Label(row, text="", width=2, bg=bg, fg=fg, font=FONT_ROW_BOLD)
        cursor.grid(row=0, column=0, rowspan=2)

        plain = [
            tk.Label(row, text=entry.filename, anchor="w", bg=bg, fg=fg, font=FONT_ROW_BOLD),
            tk.Label(row, text=os.path.dirname(entry.path), anchor="w", bg=bg, fg=fg, font=FONT_SMALL),
            tk.Label(row, text="", bg=bg, fg=fg, font=FONT_ROW),
        ]
        plain[0].grid(row=0, column=1, sticky="w")
        plain[1].grid(row=0, column=2, sticky="w", padx=8)
        plain[2].grid(row=0, column=3, sticky="e")
        duration = plain[2]

        codecs = " / ".join(part for part in (entry.video_codec, entry.audio_codec) if part) or "--"
        plain.append(tk.Label(row, text=f"{entry.container}   {codecs}", anchor="w", bg=bg, fg=fg, font=FONT_SMALL))
        plain[-1].grid(row=1, column=1, sticky="w")
        plain.append(tk.Label(row, text=entry.resolution_label, bg=bg, fg=fg, font=FONT_SMALL))
        plain[-1].grid(row=1, column=2, sticky="w", padx=8)

        meta = tk.Frame(row, bg=bg)
        meta.grid(row=1, column=3, sticky="e")
        fps = tk.Label(meta, text="", bg=bg, fg=fg, font=FONT_SMALL)
        slash_a = tk.Label(meta, text=" / ", bg=bg, fg=fg, font=FONT_SMALL)
        aspect = tk.Label(meta, text="", bg=bg, fg=fg, font=FONT_SMALL)
        slash_p = tk.Label(meta, text=" / ", bg=bg, fg=fg, font=FONT_SMALL)
        par = tk.Label(meta, text="", bg=bg, fg=fg, font=FONT_SMALL)
        slash_c = tk.Label(meta, text=" / ", bg=bg, fg=fg, font=FONT_SMALL)
        colorspace = tk.Label(meta, text="", bg=bg, fg=fg, font=FONT_SMALL)
        for widget in (fps, slash_a, aspect, slash_p, par, slash_c, colorspace):
            widget.pack(side="left")

        autoplay = tk.Label(row, text="", width=8, bg=bg, fg=fg, font=FONT_SMALL)
        autoplay.grid(row=0, column=5, rowspan=2, sticky="e", padx=(8, 0))

        volume = tk.Label(row, text="", width=5, anchor="e", bg=bg, fg=COLOR_VOLUME, font=FONT_ROW)
        volume.grid(row=0, column=4, sticky="e", padx=(8, 0))
        loudness = tk.Label(row, text="", width=11, anchor="e", bg=bg, fg=COLOR_VOLUME, font=FONT_SMALL)
        loudness.grid(row=1, column=4, sticky="e", padx=(8, 0))

        self.row_widgets.append({
            "row": row,
            "cursor": cursor,
            "plain": plain,
            "duration": duration,
            "volume": volume,
            "loudness": loudness,
            "meta": meta,
            "fps": fps,
            "slash_a": slash_a,
            "aspect": aspect,
            "slash_p": slash_p,
            "par": par,
            "slash_c": slash_c,
            "colorspace": colorspace,
            "autoplay": autoplay,
        })
        self._paint_row(index, entry)

        bind_targets = [row, *row.winfo_children(), *meta.winfo_children()]
        for widget in bind_targets:
            widget.bind("<ButtonPress-1>", lambda e, i=index: self.on_row_press(i, e))
            widget.bind("<B1-Motion>", lambda e: self.on_row_drag(e))
            widget.bind("<ButtonRelease-1>", lambda e: self.on_row_release(e))
            widget.bind("<Button-3>", lambda e, i=index: self.on_row_menu(i, e))

    def _paint_row(self, index, entry):
        widgets = self.row_widgets[index]
        bg, fg = self._row_colors(index, entry)
        widgets["row"].config(bg=bg)
        for label in widgets["plain"]:
            label.config(bg=bg, fg=fg)
        widgets["cursor"].config(
            text=">" if index == self.program_index else " ", bg=bg, fg=fg
        )
        widgets["duration"].config(text=self._row_duration_text(entry))
        widgets["volume"].config(
            text=f"{clamp_volume(entry.volume)}%",
            bg=bg, fg=COLOR_VOLUME,
        )
        widgets["loudness"].config(
            text=format_loudness(entry.loudness_lufs),
            bg=bg, fg=COLOR_VOLUME,
        )
        widgets["meta"].config(bg=bg)
        widgets["fps"].config(
            text=format_fps_label(entry.fps),
            bg=bg, fg=COLOR_WARNING if not entry.refresh_ok else fg,
        )
        widgets["slash_a"].config(bg=bg, fg=fg)
        widgets["aspect"].config(
            text=entry.aspect,
            bg=bg, fg=COLOR_WARNING if entry.aspect_warning else fg,
        )
        widgets["slash_p"].config(bg=bg, fg=fg)
        widgets["par"].config(
            text=entry.pixel_aspect,
            bg=bg, fg=COLOR_WARNING if entry.par_warning else fg,
        )
        widgets["slash_c"].config(bg=bg, fg=fg)
        widgets["colorspace"].config(
            text=format_colorspace_label(entry),
            bg=bg, fg=COLOR_WARNING if entry.colorspace_warning else fg,
        )
        if entry.missing:
            widgets["autoplay"].config(text=t("missing_badge"), bg=bg, fg=COLOR_WARNING)
        else:
            widgets["autoplay"].config(
                text=t("auto_badge") if entry.autoplay else "",
                bg=bg, fg=fg if fg == COLOR_WHITE else ACCENT,
            )

    def apply_preview_layout(self, entry):
        """Stills only need Autoplay and their display time; hide the clip controls."""
        image = bool(entry and entry.is_image)
        if image:
            self.preview_controls.grid_remove()
            self.preview_clip_settings.pack_forget()
            self.preview_image_settings.pack(side="left")
        else:
            self.preview_controls.grid()
            self.preview_image_settings.pack_forget()
            self.preview_clip_settings.pack(side="left")

    def repaint_playlist(self):
        """Update row colours and marks in place, keeping the widgets alive."""
        if len(self.row_widgets) != len(self.playlist):
            self.refresh_playlist()
            return
        for index, entry in enumerate(self.playlist):
            self._paint_row(index, entry)

    def _set_preview_lufs(self, entry):
        if entry and not entry.missing and not entry.is_image:
            value = format_loudness(entry.loudness_lufs)
        else:
            value = format_loudness(None)
        if value.endswith(" LUFS"):
            value = f"{value[:-5].strip()}\nLUFS"
        else:
            value = f"{value}\nLUFS"
        self.preview_lufs.config(text=value)

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
        self.refresh_transport()
        if not entry:
            self.preview_meta.config(text=t("length_empty"))
            self.audio_combo["values"] = ["--"]
            self.subtitle_combo["values"] = ["--"]
            self._update_preview_bar()
            return
        if entry.missing:
            self.preview_meta.config(text=t("missing_file", path=entry.path))
            self.autoplay_var.set(entry.autoplay)
            self.played_var.set(entry.played)
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
                    colorspace=format_colorspace_label(entry),
                )
            )
            self.autoplay_var.set(entry.autoplay)
            self.played_var.set(entry.played)
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
                colorspace=format_colorspace_label(entry),
            )
        )
        self.autoplay_var.set(entry.autoplay)
        self.played_var.set(entry.played)
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
            self.beamer_res.config(text="---- x ----")
            self.beamer_fps.config(text="--p")
            self.beamer_aspect.config(text="--")
            self.beamer_rates.config(text=t("beamer_rates", rates="--"))
            self.refresh_beamer_outputs()
            return
        entry = self.current_entry() if self.program_state == "PLAYING" else self.selected_entry()
        fps = entry.fps if entry else 0
        matched = (
            self.output_manager.refresh_matches(fps, mode.refresh)
            if fps else True
        )
        self.beamer_ok.config(
            text=t("ok") if matched else t("mismatch"),
            bg=COLOR_PLAYING if matched else COLOR_OFF,
        )
        self.beamer_res.config(text=f"{mode.width} x {mode.height}")
        self.beamer_fps.config(text=format_fps_label(mode.refresh))
        self.beamer_aspect.config(text=aspect_from_mode(mode))
        self.beamer_rates.config(text=self._beamer_rate_text())
        self.refresh_beamer_outputs()

    def _beamer_rate_text(self):
        output = self.output_manager.video_output or ""
        cache = self._beamer_rates_cache
        if cache and cache[0] == output:
            return cache[1]
        rates = []
        try:
            modes = self.output_manager.get_modes(output) if output else []
        except Exception:
            modes = []
        for mode in modes:
            if any(self.output_manager.refresh_close(mode.refresh, seen) for seen in rates):
                continue
            rates.append(mode.refresh)
        rates.sort()
        labels = "  ".join(format_fps_label(rate) for rate in rates) or "--"
        text = t("beamer_rates", rates=labels)
        self._beamer_rates_cache = (output, text)
        return text

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
        try:
            save_settings(self.settings)
        except OSError:
            pass
        self._restart_main_output()
        self.refresh_beamer()
        if self.window_fullscreen.get():
            self._apply_window_fullscreen()

    def _restart_main_output(self):
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
            return
        if self.program_state != "PLAYING":
            self.blank_output()

    def on_row_click(self, index):
        """Single click: show the clip in the preview window."""
        if not 0 <= index < len(self.playlist):
            return
        self.preview_index = index
        self.preview_live = False
        self.repaint_playlist()
        self.refresh_status()
        self.refresh_preview_meta()
        self.show_preview_clip(self.playlist[index])

    def on_row_menu(self, index, event):
        """Right click: act on the clicked clip."""
        if not 0 <= index < len(self.playlist):
            return
        self.on_row_click(index)
        playing = self.program_state == "PLAYING"
        missing = bool(self.playlist[index].missing)
        menu = self._menu(self.root)
        menu.add_command(
            label=t("set_program"), command=lambda: self.set_program_point(index),
            state="disabled" if playing or missing else "normal",
        )
        menu.add_command(label=t("toggle_autoplay"), command=lambda: self.toggle_autoplay(index))
        menu.add_command(
            label=t("relink_entry"), command=lambda: self.relink_entry(index),
            state="disabled" if playing and index == self.program_index else "normal",
        )
        menu.add_separator()
        menu.add_command(
            label=t("delete_entry"), command=lambda: self.delete_entry(index),
            state="disabled" if playing and index == self.program_index else "normal",
        )
        self._popup_menu(menu, event.x_root, event.y_root)
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

    def confirm_projection_zoom(self):
        """Ask as soon as the program cursor lands on a clip that needs a zoom change."""
        if not self.projection_zoom.get() or not self.playlist:
            return True
        entry = self.current_entry()
        if not entry or entry.missing or not (
            entry.aspect_warning or entry.par_warning or entry.colorspace_warning
        ):
            return True
        if self.zoom_confirmed_index == self.program_index:
            return True
        self.root.update_idletasks()
        ok = messagebox.askokcancel(
            t("projection_zoom_title"),
            t(
                "projection_zoom_message",
                filename=entry.filename,
                aspect=entry.aspect,
                pixel_aspect=entry.pixel_aspect,
                colorspace=format_colorspace_label(entry),
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
            self.confirm_projection_zoom()

    def toggle_autoplay(self, index):
        if not 0 <= index < len(self.playlist):
            return
        entry = self.playlist[index]
        entry.autoplay = not entry.autoplay
        if index == self.preview_index:
            self.autoplay_var.set(entry.autoplay)
        self.repaint_playlist()

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
        elif self.last_import_dir:
            dialog_options["initialdir"] = self.last_import_dir
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
        probed.played = entry.played
        probed.volume = clamp_volume(entry.volume)
        probed.display_time = entry.display_time
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
                mode, matched = self.output_manager.find_best_mode(video, create=False)
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

    def _row_index_at(self, y_root):
        """Playlist index of the row under the given screen position."""
        rows = self.playlist_inner.winfo_children()
        if not rows:
            return None
        for index, row in enumerate(rows):
            if y_root < row.winfo_rooty() + row.winfo_height():
                return index
        return len(rows) - 1

    def show_drop_marker(self, start, target):
        """Draw the insert line at the slot the dragged clip would land in."""
        rows = self.playlist_inner.winfo_children()
        if target is None or not 0 <= target < len(rows):
            self.hide_drop_marker()
            return
        row = rows[target]
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

    def import_media(self):
        dialog_options = {}
        if self.last_import_dir:
            dialog_options["initialdir"] = self.last_import_dir
        paths = filedialog.askopenfilenames(
            title=t("import_media"),
            filetypes=[
                (t("media_files"), " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTS | IMAGE_EXTS))),
                (t("all_files"), "*.*"),
            ],
            **dialog_options,
        )
        if not paths:
            directory = filedialog.askdirectory(
                title=t("import_directory"),
                **dialog_options,
            )
            if directory:
                self.remember_import_dir(directory)
                paths = [
                    os.path.join(directory, name)
                    for name in sorted(os.listdir(directory))
                    if os.path.splitext(name)[1].lower() in VIDEO_EXTS | IMAGE_EXTS
                ]
        elif paths:
            self.remember_import_dir(paths[0])
        for path in paths:
            self.add_media(path)
        if self.playlist and self.preview_index is None:
            self.program_index = 0
        self.refresh_all()

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
                mode, matched = self.output_manager.find_best_mode(video, create=False)
                entry.refresh_ok = matched
        except Exception:
            entry.refresh_ok = False
        self.playlist.append(entry)

    def new_playlist(self):
        if self.playlist or self.playlist_path:
            if not messagebox.askyesno(t("new_playlist_title"), t("new_playlist_message")):
                return
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        self.program_state = "OFF"
        self.playlist = []
        self.playlist_path = ""
        self.program_index = 0
        self.zoom_confirmed_index = None
        self.preview_index = None
        self.preview_live = True
        self.preview_mpv.stop()
        self._reset_preview_meter()
        self.blank_output()
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, "untitled.pls")
        self.refresh_all()

    def load_testdata_playlist(self):
        """Replace the current playlist with every video in testdata/."""
        if not messagebox.askyesno(t("load_testdata_title"), t("load_testdata_message")):
            return
        if not os.path.isdir(TESTDATA_DIR):
            messagebox.showerror(t("load_testdata_title"), t("load_testdata_missing"))
            return
        paths = [
            os.path.join(TESTDATA_DIR, name)
            for name in sorted(os.listdir(TESTDATA_DIR))
            if os.path.splitext(name)[1].lower() in VIDEO_EXTS
        ]
        if not paths:
            messagebox.showerror(t("load_testdata_title"), t("load_testdata_empty"))
            return
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        self.program_state = "OFF"
        self.playlist = []
        self.playlist_path = ""
        self.program_index = 0
        self.zoom_confirmed_index = None
        self.preview_index = None
        self.preview_live = True
        self.preview_mpv.stop()
        self._reset_preview_meter()
        self.blank_output()
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, "testdata.pls")
        for path in paths:
            self.add_media(path)
        if self.playlist:
            self.program_index = 0
        self.refresh_all()

    def load_playlist(self):
        path = filedialog.askopenfilename(
            title=t("load_playlist"),
            filetypes=[(t("playlist_files"), "*.pls *.json"), (t("all_files"), "*.*")],
            **self.playlist_dialog_options(),
        )
        if not path:
            return
        self._load_playlist_from_path(path)

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
        self.playlist = [PlaylistEntry.from_dict(item) for item in data.get("entries", [])]
        missing = self._scan_playlist_media()
        self.projection_zoom.set(data.get("projection_zoom", False))
        self.autoplay_delay.set(str(data.get("autoplay_delay", 0)))
        self.idle_media_path = data.get("idle_media_path", "")
        self.idle_media.set(
            os.path.basename(self.idle_media_path) if self.idle_media_path else t("idle_none")
        )
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
        if missing:
            messagebox.showwarning(t("load_playlist"), t("missing_playlist", count=missing))

    def _scan_playlist_media(self):
        """Mark missing files and refresh metadata for clips that are still on disk."""
        missing = mark_missing_media(self.playlist)
        for entry in self.playlist:
            if not entry.missing:
                refresh_entry_aspect(entry)
        return missing

    def check_playlist_files(self):
        """Re-check every playlist path, as when a playlist is loaded."""
        missing = self._scan_playlist_media()
        if self.program_state != "PLAYING":
            self._skip_to_playable(inclusive=True)
        if self.preview_index is not None and not self.preview_live:
            self.show_preview_clip(self.selected_entry())
        self.refresh_all()
        if missing:
            messagebox.showwarning(t("refresh_playlist"), t("missing_playlist", count=missing))

    def save_playlist(self):
        suggested = self.playlist_name.get().strip() or "playlist.pls"
        options = self.playlist_dialog_options()
        path = filedialog.asksaveasfilename(
            title=t("save_playlist"),
            defaultextension=".pls",
            initialfile=suggested,
            filetypes=[(t("playlist_files"), "*.pls"), ("JSON", "*.json")],
            **options,
        )
        if not path:
            return
        self._write_playlist(path)
        self.playlist_path = path
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, os.path.basename(path))
        self.remember_playlist_dir(path)

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

    def _write_playlist(self, path):
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self._playlist_payload(), handle, indent=2)

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
        self.idle_media.set(os.path.basename(path) if path else t("idle_none"))
        self.idle_media_path = path or ""
        if path:
            self.remember_import_dir(path)
        if self.program_state != "PLAYING":
            self.blank_output()

    def apply_entry_settings(self):
        entry = self.selected_entry()
        if not entry:
            return
        entry.autoplay = self.autoplay_var.get()
        entry.played = self.played_var.get()
        if entry.is_image:
            try:
                entry.display_time = max(0.0, float(self.display_time.get() or 0))
            except ValueError:
                pass
            self.display_time.set(format_seconds(entry.display_time))
        else:
            entry.audio_track = self.audio_var.get()
            entry.subtitle_track = self.subtitle_var.get()
            if self.preview_mpv.has_file(entry.path):
                self.apply_tracks(entry, self.preview_mpv)
            if (
                self.program_state == "PLAYING"
                and entry is self.current_entry()
                and self.main_mpv.has_file(entry.path)
            ):
                self.apply_tracks(entry, self.main_mpv)
        self.repaint_playlist()

    def reset_played(self):
        for entry in self.playlist:
            entry.played = False
        self.played_var.set(False)
        self.repaint_playlist()

    def analyze_playlist_loudness(self):
        """Measure integrated LUFS for every playable video while the program is stopped."""
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
                    entry.loudness_lufs = probe_loudness(entry.path, ffmpeg_path)
                except OSError:
                    entry.loudness_lufs = None
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
            entry = self.current_entry()
            if entry and self.program_state == "PLAYING":
                self.show_preview_clip(entry, follow_live=True, start=self.position)
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
            arguments = self.output_manager.get_mpv_arguments(self.mpv_path)
            arguments.append(f"--af={METER_AF}")
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
        self.cancel_still_timer()
        if self.idle_after_id:
            self.root.after_cancel(self.idle_after_id)
            self.idle_after_id = None
        if not self.main_mpv.process:
            self._reset_program_meter()
            return
        self.main_mpv.stop()
        self.main_mpv.set_loop_file(False)
        self.main_mpv.set_vid(True)
        self.current_file = None
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
        return self.program_state == "PROGRAM"

    def show_idle_media(self):
        """Put the idle background on screen after the black gap."""
        self.idle_after_id = None
        path = self.idle_media_file()
        if not path or not self.idle_allowed() or not self.main_mpv.process:
            return
        if self.beamer_test_active:
            return
        self.main_mpv.set_loop_file(True)
        self.main_mpv.set_volume(100)
        self.main_mpv.load_file(path, play=True)
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
            self.main_mpv.set_loop_file(True)
            self.main_mpv.set_vid(True)
            self.main_mpv.command("set_property", "video-zoom", BEAMER_TEST_ZOOM)
            self.main_mpv.load_file(BEAMER_TEST_FILE, play=True)
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
            "--hwdec=auto-safe",
            "--vo=gpu",
            "--gpu-context=x11egl",
            "--force-window=yes",
            "--osc=no",
            "--osd-level=0",
            "--image-display-duration=inf",
            "--pause",
            "--audio-device=auto",
            "--sid=no",
            "--sub-auto=no",
            f"--af={METER_AF}",
        ]
        try:
            self.preview_mpv.start(arguments)
            self.preview_mpv.observe("af-metadata/meter", 5)
            self.preview_mpv.set_volume(clamp_volume(self.preview_volume.get()))
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
            return
        end = entry.out_point if follow_live else None
        self.preview_mpv.load_file(
            entry.path,
            start=start,
            end=end,
            play=play,
        )

    def start_or_resume(self):
        if not self.playlist:
            self.import_media()
            if not self.playlist:
                return
        if self.program_state == "OFF":
            # Start only arms the program; Resume then rolls the clip.
            self.program_state = "PROGRAM"
            self._skip_to_playable(inclusive=True)
            self.ensure_main_output()
            # Arming brings up the idle background, if one is set.
            self.blank_output()
            self.refresh_all()
            self.confirm_projection_zoom()
            return
        if self.program_state == "PLAYING" and self.still_waiting:
            # A still without display time ends when the operator resumes.
            self.on_clip_finished()
            return
        if self.program_state == "PLAYING" and self.main_pause:
            self.main_mpv.set_vid(True)
            self.blackout = False
            self.main_mpv.set_pause(False)
            self.preview_mpv.set_pause(False)
            self.main_pause = False
            return
        self.start_current_clip()

    def start_current_clip(self):
        if not self.playlist:
            return
        self.autoplay_after_id = None
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
            messagebox.showinfo(t("playback"), t("missing_playback"))
            return
        if not self.confirm_projection_zoom():
            self.program_state = "PROGRAM"
            self.refresh_all()
            return
        entry = self.playlist[self.program_index]
        try:
            video, mode, matched = self.output_manager.prepare_for_video(entry.path)
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
                messagebox.showinfo(t("playback"), t("missing_playback"))
                return
            messagebox.showerror(t("playback"), str(exc))
            self.program_state = "PROGRAM"
            self.refresh_all()
            return

        if not self.ensure_main_output():
            messagebox.showerror(t("playback"), t("output_failed"))
            self.program_state = "PROGRAM"
            self.refresh_all()
            return
        self.main_mpv.command("set_property", "override-display-fps", float(mode.refresh))
        self.main_mpv.command(
            "set_property", "geometry", self.output_manager.get_mpv_geometry()
        )

        self.main_mpv.set_loop_file(False)
        self.main_mpv.set_vid(True)
        self.idle_showing = False
        self.main_mpv.load_file(
            entry.path,
            start=entry.in_point,
            end=entry.out_point,
            play=True,
        )
        self.apply_tracks(entry, self.main_mpv)
        volume = clamp_volume(entry.volume)
        self._load_program_volume(entry, force=True)
        self.main_mpv.set_volume(volume)
        self.main_pause = False
        self.blackout = False
        self.current_file = entry.path
        self.duration = entry.duration
        self.position = entry.in_point if entry.in_point is not None else 0
        self.start_still_timer(entry)
        self.program_state = "PLAYING"
        self.preview_live = True
        self.show_preview_clip(entry, follow_live=True)
        self.refresh_all()

    def start_still_timer(self, entry):
        """A still runs on a timer; without a display time it waits for Resume."""
        self.cancel_still_timer()
        if not entry.is_image:
            return
        seconds = max(0.0, float(entry.display_time or 0))
        self.duration = seconds
        self.position = 0.0
        if seconds <= 0:
            self.still_waiting = True
            return
        self.still_started = time.monotonic()
        self.still_after_id = self.root.after(int(seconds * 1000), self.on_clip_finished)

    def still_active(self):
        return self.still_waiting or self.still_started is not None

    def cancel_still_timer(self):
        if self.still_after_id:
            self.root.after_cancel(self.still_after_id)
        self.still_after_id = None
        self.still_started = None
        self.still_waiting = False

    def apply_tracks(self, entry, controller):
        if entry.audio_track and entry.audio_track != "--":
            try:
                aid = int(entry.audio_track.split(":", 1)[0])
                controller.command("set_property", "aid", aid)
            except ValueError:
                pass
        if entry.subtitle_track and entry.subtitle_track != "--":
            try:
                sid = int(entry.subtitle_track.split(":", 1)[0])
                controller.command("set_property", "sid", sid)
            except ValueError:
                pass
        else:
            controller.command("set_property", "sid", "no")

    def confirm_pause(self):
        if self.program_state != "PLAYING":
            return
        if messagebox.askyesno(t("pause_title"), t("pause_message")):
            self.main_mpv.set_pause(True)
            self.main_mpv.set_vid(False)
            self.preview_mpv.set_pause(True)
            self.main_pause = True
            self.blackout = True

    def confirm_still(self):
        if self.program_state != "PLAYING":
            return
        if messagebox.askyesno(t("still_title"), t("still_message")):
            self.main_mpv.set_vid(True)
            self.main_mpv.set_pause(True)
            self.preview_mpv.set_pause(True)
            self.main_pause = True
            self.blackout = False

    def confirm_stop(self):
        if self.program_state == "OFF":
            return
        playing = self.program_state == "PLAYING"
        question = t("stop_clip") if playing else t("stop_program")
        if not messagebox.askyesno(t("stop_title"), question):
            return
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        if playing:
            if self.current_entry():
                self.current_entry().played = True
            self.program_state = "PROGRAM"
            self.blank_output()
            self.preview_mpv.stop()
            self._reset_preview_meter()
            self._skip_to_playable(inclusive=False)
        else:
            # A stopped program means a dark screen, so no idle background either.
            self.program_state = "OFF"
            self.blank_output()
        self.refresh_all()
        if playing:
            self.confirm_projection_zoom()

    def on_clip_finished(self):
        if self.program_state != "PLAYING":
            return
        entry = self.current_entry()
        if entry:
            entry.played = True
        autoplay = bool(entry and entry.autoplay)
        self.program_state = "PROGRAM"
        has_next = self._skip_to_playable(inclusive=False)
        # The delay stays black; the idle background only follows when nothing is queued.
        self.blank_output(show_idle=not (autoplay and has_next))
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
        self.preview_mpv.seek(seconds)
        self.refresh_transport()

    def _focus_is_text_input(self):
        widget = self.root.focus_get()
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
        self.preview_progress.set_state(
            duration=self._clip_duration(),
            position=self.preview_position,
            in_point=entry.in_point if entry else None,
            out_point=entry.out_point if entry else None,
        )

    def _update_main_bar(self):
        if self.program_state == "OFF":
            self.main_progress.set_state(duration=0, position=0, in_point=None, out_point=None)
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
        self.main_in.config(text=t("in_value", value=format_clock(in_point)))
        self.main_out.config(text=t("out_value", value=format_clock(out_point)))
        self.main_time.config(text=t("time_value", value=format_clock(self.position)))

    def sync_live_preview(self):
        """Live mode mirrors the program, also before it rolls and while frozen."""
        if not self.preview_live or not self.preview_mpv.process:
            return
        entry = self.current_entry()
        if not entry:
            return
        if self.program_state == "PLAYING":
            self.live_parked = None
            self.preview_mpv.set_pause(self.main_pause or self.blackout)
            frozen = self.main_pause and not self.blackout
            if frozen and abs(self.preview_position - self.position) > 0.5:
                self.preview_mpv.set_position(self.position)
            return
        # Nothing on air yet: park the preview on the frame the program will start with.
        start = entry.in_point or 0.0
        parked = (entry.path, start)
        if self.live_parked != parked or not self.preview_mpv.has_file(entry.path):
            self.show_preview_clip(entry, follow_live=True, start=start, play=False)
            self.live_parked = parked

    def program_seek_allowed(self):
        """Scrubbing the program is only safe while the Still button holds a frame."""
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
        self.preview_mpv.set_position(position)

    def main_mpv_event(self, mpv, message):
        event = message.get("event")
        if event == "file-loaded":
            mpv.apply_pending_range()
            entry = self.current_entry()
            if entry and mpv.has_file(entry.path):
                self.apply_tracks(entry, mpv)
                if self.program_state == "PLAYING":
                    mpv.set_volume(clamp_volume(entry.volume))
            self.main_pause = False
            return
        if event == "end-file" and message.get("reason") in (None, "eof", "stop"):
            if self.beamer_test_active:
                return
            if (
                message.get("reason") == "eof"
                and not self.still_active()
                and self.program_state == "PLAYING"
                and not self.idle_showing
            ):
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
            self.position = position
            entry = self.current_entry()
            if (
                self.program_state == "PLAYING"
                and entry
                and entry.out_point is not None
                and self.position >= entry.out_point - 0.04
            ):
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
            if (
                not self.beamer_test_active
                and self.program_state == "PLAYING"
                and not self.idle_showing
            ):
                self.root.after(0, self.on_clip_finished)
        elif name == "af-metadata/meter":
            self.program_levels = parse_preview_levels(value)[:2]
            self.program_levels_at = time.monotonic()

    def preview_mpv_event(self, mpv, message):
        event = message.get("event")
        if event == "file-loaded":
            mpv.apply_pending_range()
            entry = self.selected_entry()
            if entry and mpv.has_file(entry.path):
                self.apply_tracks(entry, mpv)
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

    def _reset_preview_meter(self):
        self.preview_levels = []
        self.preview_levels_at = 0.0
        self._meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        try:
            self.preview_meter.reset()
        except (tk.TclError, AttributeError):
            pass

    def _reset_program_meter(self):
        self.program_levels = []
        self.program_levels_at = 0.0
        self._program_meter_shown = [METER_FLOOR_DB, METER_FLOOR_DB]
        try:
            self.program_meter.reset()
        except (tk.TclError, AttributeError):
            pass

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
            self.program_meter.set_levels(
                self._meter_post_fader(self._program_meter_shown, self.program_volume.get())
            )
            self._meter_after_id = self.root.after(50, self._tick_meters)
        except (tk.TclError, AttributeError):
            self._meter_after_id = None

    def update_gui(self):
        try:
            if self.still_started is not None and self.program_state == "PLAYING":
                self.position = min(self.duration, time.monotonic() - self.still_started)
            if not self.main_progress.dragging:
                self._update_main_bar()
            if not self.preview_progress.dragging:
                self._update_preview_bar()
            self.preview_time.config(text=t("time_value", value=format_clock(self.preview_position)))
            self.sync_live_preview()
            self.refresh_status()
            self.refresh_beamer()
        except Exception as exc:
            print(f"GUI-Aktualisierung: {exc}")
        self.root.after(250, self.update_gui)

    def close(self, _event=None):
        if self.program_state != "OFF":
            messagebox.showinfo(t("quit"), t("quit_busy"))
            return "break"
        self._close_menus()
        for after_id in (
            self.autoplay_after_id, self.idle_after_id, self.still_after_id, self._meter_after_id,
        ):
            if after_id:
                self.root.after_cancel(after_id)
        try:
            self.preview_mpv.quit()
            self.main_mpv.quit()
        finally:
            self.output_manager.restore_original_mode()
            self.root.destroy()


def aspect_from_mode(mode):
    if not mode.height:
        return "--"
    ratio = mode.width / mode.height
    if abs(ratio - 16 / 9) < 0.05:
        return "16:9"
    if abs(ratio - 2.39) < 0.08:
        return "21:9"
    if abs(ratio - 4 / 3) < 0.05:
        return "4:3"
    return f"{mode.width}:{mode.height}"
