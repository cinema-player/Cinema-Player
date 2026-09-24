"""Cinema Player control GUI matching the layout mockup."""

from __future__ import annotations

import font_setup  # noqa: F401  — load Inter before tkinter opens fontconfig

import json
import math
import os
import re
import shutil
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from language import LANGUAGES, t, set_language, current_language
from remote_api import DEFAULT_PORT, RemoteAPIServer, clip_times, connect_url
import qr_code
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
    format_bitrate,
    format_clock,
    format_codec_rate,
    format_fps_label,
    format_colorspace_label,
    format_loudness,
    gpu_context_for_mpv,
    mark_missing_media,
    media_file_available,
    parse_bitrate_bps,
    probe_loudness,
    probe_media,
    refresh_entry_aspect,
    same_aspect_ratio,
    session_display_name,
    session_is_wayland,
)

LOGO_BG = "#000000"
LOGO_ACCENT = "#4d9be6"
FONT_LOGO = (FONT_FAMILY, 17, "bold")
FONT_LOGO_LIGHT = (FONT_FAMILY, 17)
FONT_BEAMER_PICK = (FONT_FAMILY, 13, "bold")
FONT_TOOLTIP = (FONT_FAMILY, 11)
FONT_EDID = ("DejaVu Sans Mono", 10)
LOGO_HEADER_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-logo-header.png")
LOGO_ICON_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-icon.png")
BEAMER_TEST_FILE = os.path.join(ROOT_DIR, "assets", "logo", "cinema-player-logo.png")
# mpv log2 zoom: -0.8 ≈ 57% size, so the wide logo does not fill the screen width.
BEAMER_TEST_ZOOM = -0.8
ICONS_DIR = os.path.join(ROOT_DIR, "assets", "icons")
TESTDATA_DIR = os.path.join(ROOT_DIR, "testdata", "videotestdata")
AUDIOSYNC_DIR = os.path.join(ROOT_DIR, "testdata", "audiosyncdata")
IDLE_DIR = os.path.join(ROOT_DIR, "idle")
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
COLOR_PREVIEW = "#c9a227"
COLOR_CALIBRATION = "#500070"
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
        tip.configure(bg=COLOR_TIP_BG)
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            tip, text=self.text, font=FONT_TOOLTIP, bg=COLOR_TIP_BG, fg=COLOR_TIP_FG,
            relief="flat", bd=0, padx=10, pady=6,
        ).pack()
        self._window = tip


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

    def add_cascade(self, label="", menu=None, state="normal", **_kwargs):
        self._cascades.append(menu)

        def open_cascade(event, submenu=menu):
            self._show_cascade(event.widget, submenu)

        self._add_row(f"{label}  ▸", None, state, None, on_press=open_cascade)

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


def format_seconds(value):
    seconds = max(0.0, float(value or 0))
    return str(int(seconds)) if seconds == int(seconds) else f"{seconds:g}"


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
        self.calibration_mode = None
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
        self.program_video_bps = 0
        self.program_audio_bps = 0
        self.preview_video_bps = 0
        self.preview_audio_bps = 0
        self.main_pause = False
        self.blackout = False
        self.idle_media_path = ""
        self.idle_showing = False
        self.beamer_test_active = False
        self.edid_window = None
        self.media_dirs_window = None
        self.audiosync_list_window = None
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
        self.media_directories = self._normalize_media_directories(
            self.settings.get("media_directories", [])
        )
        self.copy_imported_media = tk.BooleanVar(
            value=bool(self.settings.get("copy_imported_media", False))
        )
        self.copy_imported_media_dir = self.settings.get("copy_imported_media_dir") or ""
        if self.copy_imported_media_dir:
            self.copy_imported_media_dir = os.path.abspath(
                os.path.expanduser(self.copy_imported_media_dir)
            )
        self.copy_imported_media_label = tk.StringVar(value=self._copy_path_label_text())
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
        self.autosave_on_program_change = tk.BooleanVar(
            value=bool(self.settings.get("autosave_on_program_change", False))
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
        self._remote_action = False
        self._windowed_geometry = None
        self._fullscreen_applied = False
        self.autoplay_delay = tk.StringVar(value="0")
        self.idle_media = tk.StringVar(value=t("idle_none"))
        self.autoplay_var = tk.BooleanVar(value=False)
        self.loop_var = tk.BooleanVar(value=False)
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
        self._help_button(header)
        self._build_remote_indicator(header)

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
            header,
            text=f"v{APP_VERSION}  ·  {session_display_name()}",
            bg=COLOR_BG, fg=COLOR_MUTED, font=FONT_UI,
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
        self.edid_window = None
        self.media_dirs_window = None
        self.audiosync_list_window = None
        self.remote_window = None
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
        self.copy_imported_media_label.set(self._copy_path_label_text())
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
        self.program_video_bitrate = self._bitrate_readout(progress, "video_bitrate")
        self.program_video_bitrate.grid(row=0, column=1, sticky="e", padx=(8, 8))

        volume = self._build_volume_row(
            progress, self.program_volume, self._on_program_volume, COLOR_PANEL,
        )
        volume.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))
        self.program_audio_bitrate = self._bitrate_readout(progress, "audio_bitrate")
        self.program_audio_bitrate.grid(row=1, column=1, sticky="e", padx=(8, 8), pady=(4, 0))

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
        marks.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8)
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
            self.program_delay_readout = tk.Label(
                row, text="", width=9, anchor="e",
                bg=bg, fg=COLOR_MUTED, font=FONT_SMALL,
            )
            self.program_delay_readout.pack(side="left", padx=(8, 0))
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
        button._transport_enabled = True

        def wrapped():
            if not getattr(button, "_transport_enabled", True):
                return
            command()

        button.config(command=wrapped)
        if image is None:
            button.config(font=FONT_SMALL, width=7)
        button.icon_name = icon_name
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
        self._set_transport_active(
            self.btn_play,
            (rolling or armed) and not clip_rolling,
            "playing" if rolling else "program",
            enabled=not clip_rolling,
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
        size = 36
        canvas = tk.Canvas(
            parent, width=size, height=size, bg=parent.cget("bg"),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        canvas.create_text(
            size / 2, size / 2, text="?", fill=COLOR_TEXT, font=FONT_STATUS,
        )
        canvas.bind("<Button-1>", lambda _event: self.open_manual())
        canvas.pack(side="right", padx=(0, 4))
        canvas.tooltip = IconTooltip(canvas, t("manual"))
        return canvas

    def _build_remote_indicator(self, parent):
        """Radio icon in the header while the smartphone API is running."""
        size = 36
        canvas = tk.Canvas(
            parent, width=size, height=size, bg=parent.cget("bg"),
            highlightthickness=0, bd=0, cursor="hand2",
        )
        cx, cy = size / 2, size * 0.7
        color = COLOR_VOLUME
        canvas.create_oval(cx - 2.5, cy - 2.5, cx + 2.5, cy + 2.5, fill=color, outline="")
        for radius, start in ((8, 48), (14, 38)):
            canvas.create_arc(
                cx - radius, cy - radius - 1, cx + radius, cy + radius - 1,
                start=start, extent=180 - 2 * start, style="arc",
                outline=color, width=2,
            )
        canvas.bind("<Button-1>", lambda _event: self.show_remote_control())
        canvas.tooltip = IconTooltip(canvas, t("remote_control"))
        self.remote_indicator = canvas
        self._refresh_remote_indicator()
        return canvas

    def _refresh_remote_indicator(self):
        canvas = getattr(self, "remote_indicator", None)
        if canvas is None:
            return
        try:
            if self.remote_api and self.remote_api.running:
                canvas.pack(side="right", padx=(0, 4))
            else:
                canvas.pack_forget()
        except tk.TclError:
            pass

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
            if isinstance(menu, DropdownMenu):
                menus.extend(child for child in menu._cascades if child is not None)
            else:
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
            label=t("media_directories"),
            command=self.show_media_directories,
        )
        menu.add_command(
            label=t("remote_control"),
            command=self.show_remote_control,
        )
        menu.add_separator()
        menu.add_checkbutton(
            label=t("window_fullscreen"),
            variable=self.window_fullscreen,
            command=self._on_window_fullscreen,
            accelerator="F11",
        )
        menu.add_command(
            label=t("theme_to_light") if self.theme == "dark" else t("theme_to_dark"),
            command=self.toggle_theme,
        )
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
        menu.add_separator()
        menu.add_checkbutton(
            label=t("default_idle_media"),
            variable=self.use_default_idle_media,
            command=self._on_use_default_idle_media,
        )
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

        device = tk.Frame(panel, bg=COLOR_PANEL)
        device.pack(fill="x", padx=8, pady=(0, 4))
        tk.Label(
            device, text=t("beamer_device"), font=FONT_SMALL, bg=COLOR_PANEL, fg=COLOR_MUTED,
        ).pack(side="left")
        self.beamer_device = tk.Label(
            device, text="--", font=FONT_STATUS, bg=COLOR_PANEL, fg=COLOR_TEXT, anchor="w",
        )
        self.beamer_device.pack(side="left", padx=(8, 0), fill="x", expand=True)

        info = tk.Frame(panel, bg=COLOR_PANEL)
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
        self.beamer_rates = BeamerChoiceLine(panel)
        self.beamer_rates.pack(fill="x", padx=8, pady=(0, 4))
        self.beamer_resolutions = BeamerChoiceLine(panel)
        self.beamer_resolutions.pack(fill="x", padx=8, pady=(0, 8))
        self._beamer_caps_cache = None

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
            clip_settings, t("loop"), self.loop_var, self.apply_entry_settings, COLOR_PANEL,
        ).pack(side="left", padx=(8, 0))
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
        self.preview_progress.grid(row=0, column=0, sticky="ew", padx=(8, 0), pady=(6, 0))
        self.preview_video_bitrate = self._bitrate_readout(controls, "video_bitrate")
        self.preview_video_bitrate.grid(row=0, column=1, sticky="e", padx=(8, 8), pady=(6, 0))

        self.preview_volume_row = self._build_volume_row(
            controls, self.preview_volume, self._on_preview_volume, COLOR_PANEL,
            save=True,
        )
        self.preview_volume_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))
        self.preview_audio_bitrate = self._bitrate_readout(controls, "audio_bitrate")
        self.preview_audio_bitrate.grid(row=1, column=1, sticky="e", padx=(8, 8), pady=(4, 0))

        marks = tk.Frame(controls, bg=COLOR_PANEL)
        marks.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(2, 4))
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
        buttons.grid(row=3, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))

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
        if self.calibration_mode:
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

    def refresh_status(self):
        state_key = self._calibration_state_key()
        if not state_key:
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
        self._refresh_program_delay_readout(entry)
        if self.calibration_mode == "audio":
            self._sync_audiosync_slider(entry)

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
            badges = []
            if entry.autoplay:
                badges.append(t("auto_badge"))
            if entry.loop and not entry.is_image:
                badges.append(t("loop_badge"))
            widgets["autoplay"].config(
                text="\n".join(badges),
                bg=bg, fg=fg if fg == COLOR_WHITE else ACCENT,
            )

    def apply_preview_layout(self, entry):
        """Stills only need Autoplay and display time; Loop and clip controls stay hidden."""
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
            self.autoplay_var.set(False)
            self.loop_var.set(False)
            self.played_var.set(False)
            self._update_preview_bar()
            return
        if entry.missing:
            self.preview_meta.config(text=t("missing_file", path=entry.path))
            self.autoplay_var.set(entry.autoplay)
            self.loop_var.set(bool(entry.loop) and not entry.is_image)
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
            self.loop_var.set(False)
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
        self.loop_var.set(bool(entry.loop))
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
            self.beamer_aspect.config(text="--", fg=COLOR_TEXT)
            self.beamer_clip_aspect.config(text="")
            self._refresh_beamer_device_name()
            self.beamer_rates.set_choices(t("beamer_rates", rates=""), [])
            self.beamer_resolutions.set_choices(
                t("beamer_resolutions", resolutions=""), [],
            )
            self.refresh_beamer_outputs()
            return
        rates, resolutions = self._beamer_capability_lists()
        clip = self.current_entry()
        preview = self._preview_clip()
        focus = clip if self.program_state == "PLAYING" else (preview or clip)
        fps_ok = True
        if focus and not focus.missing and not focus.is_image and focus.fps:
            fps_ok = self._beamer_rate_supported(focus.fps, rates)
        self.beamer_ok.config(
            text=t("ok") if fps_ok else t("mismatch"),
            bg=COLOR_PLAYING if fps_ok else COLOR_OFF,
        )
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
        self._refresh_beamer_device_name()
        self.refresh_beamer_outputs()

    def _refresh_beamer_device_name(self):
        name = ""
        try:
            name = self.output_manager.get_output_device_name()
        except Exception:
            name = ""
        self.beamer_device.config(text=name or "--")

    def _beamer_capability_lists(self):
        output = self.output_manager.video_output or ""
        cache = self._beamer_caps_cache
        if cache and cache[0] == output:
            return cache[1], cache[2]
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
        self._beamer_caps_cache = (output, rates, seen_res)
        return rates, seen_res

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
            self.edid_window.lift()
            self.edid_window.focus_force()
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

        holder = tk.Frame(window, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, padx=10, pady=10)
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

        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(
            buttons, text=t("edid_close"), command=self._close_edid_window, font=FONT_UI,
        ).pack(side="right")

        window._edid_text = text
        self.edid_window = window
        self._fill_edid_window(report["output"], body)
        self._place_on_control_monitor(window, 820, 700)

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
        return True

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
        menu = self._menu(self.root)
        menu.add_command(
            label=t("set_program"), command=lambda: self.set_program_point(index),
            state="disabled" if playing or missing else "normal",
        )
        menu.add_command(label=t("toggle_autoplay"), command=lambda: self.toggle_autoplay(index))
        menu.add_command(
            label=t("toggle_loop"),
            command=lambda: self.toggle_loop(index),
            state="disabled" if self.playlist[index].is_image else "normal",
        )
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
            _video, mode, matched = self.output_manager.prepare_for_video(entry.path)
            entry.refresh_ok = matched
        except Exception as exc:
            print(f"Beamer-Modus nicht gesetzt: {exc}")
            return
        changed = (
            before is None
            or before.width != mode.width
            or before.height != mode.height
            or not self.output_manager.refresh_close(before.refresh, mode.refresh)
        )
        if changed and session_is_wayland() and self.main_mpv.process:
            self._restart_main_output(blank=False)
            if self.program_state == "PROGRAM":
                self.blank_output()
        self.refresh_beamer()

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

    @staticmethod
    def _normalize_media_directories(paths):
        seen = set()
        result = []
        if not isinstance(paths, list):
            return result
        for raw in paths:
            if not isinstance(raw, str):
                continue
            path = os.path.abspath(os.path.expanduser(raw.strip()))
            if not path or path in seen:
                continue
            seen.add(path)
            result.append(path)
        return result

    def _save_media_directories(self):
        self.media_directories = self._normalize_media_directories(self.media_directories)
        self.settings["media_directories"] = list(self.media_directories)
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _existing_media_directories(self):
        return [path for path in self.media_directories if os.path.isdir(path)]

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

    def _copy_path_label_text(self):
        path = self.copy_imported_media_dir
        if not path:
            return t("copy_files_none")
        if os.path.isdir(path):
            return path
        return f"{path}  ({t('media_directories_missing')})"

    def _copy_destination(self):
        path = self.copy_imported_media_dir
        if path and os.path.isdir(path):
            return os.path.abspath(path)
        return ""

    def _save_copy_imported_media(self):
        self.settings["copy_imported_media"] = bool(self.copy_imported_media.get())
        self.settings["copy_imported_media_dir"] = self.copy_imported_media_dir
        self.copy_imported_media_label.set(self._copy_path_label_text())
        try:
            save_settings(self.settings)
        except OSError:
            pass

    def _choose_copy_destination(self, parent=None):
        options = {"title": t("copy_files_choose")}
        if parent is not None:
            options["parent"] = parent
        start = self._copy_destination() or self._preferred_import_dir()
        if start:
            options["initialdir"] = start
        path = filedialog.askdirectory(**options)
        if not path:
            return False
        self.copy_imported_media_dir = os.path.abspath(path)
        self._save_copy_imported_media()
        return True

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

    def _copy_file_with_progress(self, source, dest, on_progress, parent=None):
        copied = 0
        try:
            with open(source, "rb") as src, open(dest, "wb") as dst:
                while True:
                    chunk = src.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
                    copied += len(chunk)
                    if on_progress:
                        on_progress(copied)
            shutil.copystat(source, dest)
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
        window.protocol("WM_DELETE_WINDOW", lambda: None)

        body = tk.Frame(window, bg=COLOR_PANEL)
        body.pack(fill="both", expand=True, padx=10, pady=10)
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

        widgets = {"status": status, "name": name, "bar": bar, "size": size, "total": total}
        self._place_on_control_monitor(window, 480, 160)
        window.grab_set()
        window.lift()
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

    def _copy_imported_paths(self, paths):
        dest_dir = self._copy_destination()
        if not dest_dir:
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
        try:
            for index, (dest, source, size) in enumerate(jobs, 1):
                name = os.path.basename(source or dest)
                if widgets is not None:
                    self._update_copy_progress(window, widgets, index, name, done_bytes, total_bytes)
                if source:
                    def on_progress(copied, base=done_bytes):
                        if widgets is not None:
                            self._update_copy_progress(
                                window, widgets, index, name, base + copied, total_bytes,
                            )

                    if not self._copy_file_with_progress(source, dest, on_progress, parent=window):
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
                    window.lift()
                    window.focus_force()
                    self._fill_remote_urls()
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
        tk.Label(
            window, text=t("remote_control_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=620, justify="left",
        ).pack(fill="x", padx=10, pady=(10, 6))
        holder = tk.Frame(window, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._checkbutton(
            holder, t("remote_control_enable"), self.remote_api_enabled,
            self._apply_remote_api_settings, COLOR_PANEL,
        ).pack(anchor="w", padx=8, pady=(8, 4))
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
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(
            buttons, text=t("remote_control_close"), command=self._close_remote_window, font=FONT_UI,
        ).pack(side="right")
        tk.Button(
            buttons, text=t("remote_control_apply"), command=self._apply_remote_api_settings, font=FONT_UI,
        ).pack(side="right", padx=(0, 8))
        self.remote_window = window
        self._fill_remote_urls()
        self._place_on_control_monitor(window, 640, 420)

    def _close_remote_window(self):
        window = getattr(self, "remote_window", None)
        self.remote_window = None
        self.remote_url_box = None
        self.remote_qr_canvas = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

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
        duration = 0.0 if stopped else (self.duration or (entry.duration if entry else 0) or 0)
        times = clip_times(self.program_state, duration, self.position)
        paused = self.program_state == "PLAYING" and self.main_pause and self.blackout
        frozen = self.program_state == "PLAYING" and self.main_pause and not self.blackout
        rolling = self.program_state == "PLAYING" and not self.main_pause
        clip_rolling = rolling and not self.still_waiting and not self._program_loop_active()
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
            }
        return {
            "ok": True,
            "version": APP_VERSION,
            "language": current_language(),
            "state": self.program_state,
            "state_label": t(state_key),
            "calibration": self.calibration_mode,
            "paused": paused,
            "still": frozen,
            "idle": bool(self.idle_showing),
            "loop": bool(self._program_loop_active()),
            "volume": clamp_volume(self.program_volume.get()),
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
                "volume": True,
                "set_program": bool(self.playlist) and self.program_state != "PLAYING",
            },
        }

    def remote_resume(self):
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

    def show_media_directories(self):
        """Edit the saved media folders used when importing into the playlist."""
        if self._media_dirs_window_alive():
            self.media_dirs_window.deiconify()
            self.media_dirs_window.lift()
            self.media_dirs_window.focus_force()
            return
        window = tk.Toplevel(self.root)
        window.title(t("media_directories"))
        window.configure(bg=COLOR_BG)
        window.minsize(520, 280)
        if self.icon_image is not None:
            try:
                window.iconphoto(True, self.icon_image)
            except tk.TclError:
                pass
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", self._close_media_dirs_window)

        tk.Label(
            window, text=t("media_directories_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=620, justify="left",
        ).pack(fill="x", padx=10, pady=(10, 6))

        holder = tk.Frame(window, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        listbox = self._styled_listbox(holder)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
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

        window._listbox = listbox
        self.media_dirs_window = window
        self._refresh_media_directory_list(listbox)
        self._place_on_control_monitor(window, 680, 360)

    def _media_dirs_window_alive(self):
        window = getattr(self, "media_dirs_window", None)
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            self.media_dirs_window = None
            return False

    def _media_directory_label(self, path):
        if os.path.isdir(path):
            return path
        return f"{path}  ({t('media_directories_missing')})"

    def _refresh_media_directory_list(self, listbox, select_path=None):
        current = select_path
        if current is None:
            selection = listbox.curselection()
            if selection:
                current = self.media_directories[selection[0]]
        listbox.delete(0, "end")
        for path in self.media_directories:
            listbox.insert("end", self._media_directory_label(path))
        if current in self.media_directories:
            index = self.media_directories.index(current)
            listbox.selection_set(index)
            listbox.see(index)

    def _add_media_directory(self, window, listbox):
        options = {"parent": window, "title": t("media_directories_add")}
        start = self._preferred_import_dir()
        if start:
            options["initialdir"] = start
        path = filedialog.askdirectory(**options)
        if not path:
            return
        path = os.path.abspath(path)
        if path not in self.media_directories:
            self.media_directories.append(path)
            self._save_media_directories()
        self._refresh_media_directory_list(listbox, select_path=path)

    def _remove_media_directory(self, listbox):
        selection = listbox.curselection()
        if not selection:
            return
        index = selection[0]
        del self.media_directories[index]
        self._save_media_directories()
        next_path = ""
        if self.media_directories:
            next_path = self.media_directories[min(index, len(self.media_directories) - 1)]
        self._refresh_media_directory_list(listbox, select_path=next_path)

    def _close_media_dirs_window(self):
        window = getattr(self, "media_dirs_window", None)
        self.media_dirs_window = None
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

    def import_media(self):
        directories = self._existing_media_directories()
        if directories:
            choice = self._choose_import_action(directories)
            if not choice:
                return
            mode, directory = choice
            if mode == "folder":
                self._import_directory(directory)
                return
            if mode == "other":
                self._import_files_or_directory(self.last_import_dir)
                return
            self._import_files_or_directory(directory, folder_fallback=False)
            return
        self._import_files_or_directory(self._preferred_import_dir())

    def _choose_import_action(self, directories):
        """Let the operator pick a saved media folder, or another location."""
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

        tk.Label(
            window, text=t("media_directories_hint"), bg=COLOR_BG, fg=COLOR_MUTED,
            font=FONT_SMALL, wraplength=600, justify="left",
        ).pack(fill="x", padx=10, pady=(10, 6))

        holder = tk.Frame(window, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)

        listbox = self._styled_listbox(holder)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        for path in directories:
            listbox.insert("end", path)
        selected = self._media_directory_for_path(self.last_import_dir)
        if selected in directories:
            index = directories.index(selected)
        else:
            index = 0
        listbox.selection_set(index)
        listbox.see(index)
        listbox.focus_set()

        copy_row = tk.Frame(window, bg=COLOR_BG)
        copy_row.pack(fill="x", padx=10, pady=(0, 8))
        path_holder = tk.Frame(copy_row, bg=COLOR_BG)
        path_button = tk.Button(
            path_holder,
            textvariable=self.copy_imported_media_label,
            command=lambda: self._choose_copy_destination(window),
            font=FONT_SMALL,
        )
        path_button.pack(side="left", fill="x", expand=True)

        def show_copy_path(visible):
            if visible:
                path_holder.pack(side="left", fill="x", expand=True, padx=(12, 0))
            else:
                path_holder.pack_forget()

        def on_copy_toggle():
            enabled = bool(self.copy_imported_media.get())
            if enabled:
                show_copy_path(True)
                if not self._copy_destination():
                    if not self._choose_copy_destination(window):
                        self.copy_imported_media.set(False)
                        show_copy_path(False)
                        self._save_copy_imported_media()
                        return
            else:
                show_copy_path(False)
            self._save_copy_imported_media()

        self._checkbutton(
            copy_row, t("copy_files"), self.copy_imported_media, on_copy_toggle, COLOR_BG,
        ).pack(side="left")
        self.copy_imported_media_label.set(self._copy_path_label_text())
        show_copy_path(bool(self.copy_imported_media.get()))

        def ready_to_copy():
            if not self.copy_imported_media.get():
                return True
            if self._copy_destination():
                return True
            if self._choose_copy_destination(window):
                return True
            messagebox.showerror(t("copy_files"), t("copy_files_missing"), parent=window)
            return False

        def finish(mode, directory=""):
            if not ready_to_copy():
                return
            result["choice"] = (mode, directory)
            window.destroy()

        def selected_directory():
            selection = listbox.curselection()
            if not selection:
                return ""
            return directories[selection[0]]

        def import_files(_event=None):
            directory = selected_directory()
            if directory:
                finish("files", directory)

        def import_folder():
            directory = selected_directory()
            if not directory:
                return
            options = {"title": t("import_directory"), "parent": window}
            if os.path.isdir(directory):
                options["initialdir"] = directory
            chosen = filedialog.askdirectory(**options)
            if chosen:
                finish("folder", chosen)

        def cancel():
            result["choice"] = None
            window.destroy()

        listbox.bind("<Double-Button-1>", import_files)
        listbox.bind("<Return>", import_files)
        window.bind("<Escape>", lambda _event: cancel())
        window.protocol("WM_DELETE_WINDOW", cancel)

        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
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

        self._place_on_control_monitor(window, 680, 380)
        window.grab_set()
        self.root.wait_window(window)
        return result["choice"]

    def _import_dialog_options(self, directory):
        options = {"parent": self.root}
        if directory and os.path.isdir(directory):
            options["initialdir"] = directory
        return options

    def _import_files_or_directory(self, directory, folder_fallback=True):
        dialog_options = self._import_dialog_options(directory)
        paths = filedialog.askopenfilenames(
            title=t("import_media"),
            filetypes=self._media_filetypes(),
            **dialog_options,
        )
        if paths:
            self.remember_import_dir(paths[0])
            self._add_imported_paths(paths)
            return
        if not folder_fallback:
            return
        folder = filedialog.askdirectory(
            title=t("import_directory"),
            **dialog_options,
        )
        if folder:
            self._import_directory(folder)

    def _import_directory(self, directory):
        if not directory or not os.path.isdir(directory):
            return
        self.remember_import_dir(directory)
        self._add_imported_paths(self._media_paths_in_directory(directory))

    def _add_imported_paths(self, paths):
        playlist_paths = []
        copy_enabled = bool(self.copy_imported_media.get())
        if copy_enabled:
            playlist_paths = self._copy_imported_paths(paths)
        else:
            playlist_paths = list(paths)
        for path in playlist_paths:
            self.add_media(path)
        if self.playlist and self.preview_index is None:
            self.program_index = 0
            self.apply_beamer_mode_for_pointer()
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
        self.calibration_mode = None
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
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, "untitled.pls")
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
        entries = [PlaylistEntry.from_dict(item) for item in data.get("entries", [])]
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
        self.playlist_name.insert(0, "untitled.pls")
        self._show_audiosync_controls(False)
        self._close_audiosync_list_window()
        self.blank_output()
        self.refresh_all()

    def _show_audiosync_controls(self, visible):
        frame = getattr(self, "audiosync_frame", None)
        if frame is None:
            return
        if visible:
            frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=8, pady=(4, 0))
        else:
            frame.grid_forget()
        readout = getattr(self, "program_delay_readout", None)
        if readout is not None and visible:
            readout.config(text="")

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
            return
        delay = self._audiosync_lookup(entry)
        readout.config(text=format_delay_ms(delay) if delay is not None else "")

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

    def _audiosync_payload(self):
        return {"delays": dict(sorted(self.audiosync_delays.items()))}

    def show_audiosync_delays(self):
        window = getattr(self, "audiosync_list_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    self._fill_audiosync_list(window)
                    window.deiconify()
                    window.lift()
                    window.focus_force()
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
        holder = tk.Frame(window, bg=COLOR_PANEL)
        holder.pack(fill="both", expand=True, padx=10, pady=10)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        listbox = self._styled_listbox(holder)
        scroll = ttk.Scrollbar(holder, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scroll.set)
        listbox.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        buttons = tk.Frame(window, bg=COLOR_BG)
        buttons.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(
            buttons, text=t("media_directories_close"),
            command=self._close_audiosync_list_window, font=FONT_UI,
        ).pack(side="right")
        window._listbox = listbox
        self.audiosync_list_window = window
        self._fill_audiosync_list(window)
        self._place_on_control_monitor(window, 520, 320)

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
        if self.use_default_idle_media.get():
            default_path = default_idle_media_path()
            if default_path:
                self.idle_media_path = default_path
                self.idle_media.set(os.path.basename(default_path))
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
        if not path:
            return
        self.remember_import_dir(path)
        self._save_use_default_idle_media(False)
        self._set_idle_media(path)

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
        if self.program_state != "PLAYING":
            self.blank_output()

    def apply_entry_settings(self):
        entry = self.selected_entry()
        if not entry:
            return
        entry.autoplay = self.autoplay_var.get()
        entry.played = self.played_var.get()
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
            self.output_manager.ensure_operator_layout()
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
        self.main_mpv.set_ab_loop(None, None)
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
            f"--gpu-context={gpu_context_for_mpv(self.mpv_path, embed=True)}",
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
        end = entry.out_point if follow_live and not (entry.loop and not entry.is_image) else None
        self.preview_mpv.load_file(
            entry.path,
            start=start,
            end=end,
            play=play,
        )
        if follow_live:
            self._apply_program_loop(entry, self.preview_mpv)
        else:
            self._apply_program_loop(None, self.preview_mpv)

    def start_or_resume(self):
        if not self.playlist:
            if self._remote_action:
                return
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
                if not self._remote_action:
                    messagebox.showinfo(t("playback"), t("missing_playback"))
                return
            if not self._remote_action:
                messagebox.showerror(t("playback"), str(exc))
            self.program_state = "PROGRAM"
            self.refresh_all()
            return

        if session_is_wayland():
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

        looping = bool(entry.loop and not entry.is_image)
        self._apply_program_loop(entry)
        self.main_mpv.set_vid(True)
        self.idle_showing = False
        self.main_mpv.load_file(
            entry.path,
            start=entry.in_point,
            end=None if looping else entry.out_point,
            play=True,
        )
        if session_is_wayland():
            self._pin_main_output_to_beamer()
        self.apply_tracks(entry, self.main_mpv)
        volume = clamp_volume(entry.volume)
        self._load_program_volume(entry, force=True)
        self.main_mpv.set_volume(volume)
        self._apply_program_audio_delay(entry)
        self.main_pause = False
        self.blackout = False
        self.current_file = entry.path
        self.duration = entry.duration
        self.position = entry.in_point if entry.in_point is not None else 0
        self.start_still_timer(entry)
        self.program_state = "PLAYING"
        if self.preview_live:
            self.show_preview_clip(entry, follow_live=True)
        self.refresh_all()

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
        if looping:
            start = 0.0 if entry.in_point is None else float(entry.in_point)
            controller.set_ab_loop(start, entry.out_point)
            controller.set_loop_file(True)
            controller.command("set_property", "end", "no")
            return
        controller.set_ab_loop(None, None)
        controller.set_loop_file(False)
        if entry and entry.out_point is not None:
            controller.command("set_property", "end", float(entry.out_point))
        else:
            controller.command("set_property", "end", "no")

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
            self._apply_pause()

    def confirm_still(self):
        if self.program_state != "PLAYING":
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
        if self.autoplay_after_id:
            self.root.after_cancel(self.autoplay_after_id)
            self.autoplay_after_id = None
        if self.current_entry():
            self.current_entry().played = True
        self.program_state = "PROGRAM"
        self.blank_output()
        self.preview_mpv.stop()
        self._reset_preview_meter()
        self._skip_to_playable(inclusive=False)
        self.refresh_all()
        self.confirm_projection_zoom(prompt=not self._remote_action)
        return True

    def confirm_stop(self):
        if self.program_state == "OFF":
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
        # A stopped program means a dark screen, so no idle background either.
        self.program_state = "OFF"
        self.blank_output()
        self.refresh_all()

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
            self.program_video_bps = 0
            self.program_audio_bps = 0
            entry = self.current_entry()
            if entry and mpv.has_file(entry.path):
                self.apply_tracks(entry, mpv)
                self._apply_program_loop(entry, mpv)
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
                and not self._program_loop_active()
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
            if (
                not self.beamer_test_active
                and not self._program_loop_active()
                and self.program_state == "PLAYING"
                and not self.idle_showing
            ):
                self.root.after(0, self.on_clip_finished)
        elif name == "af-metadata/meter":
            self.program_levels = parse_preview_levels(value)[:2]
            self.program_levels_at = time.monotonic()
        elif name == "video-bitrate":
            self.program_video_bps = parse_bitrate_bps(value)
        elif name == "audio-bitrate":
            self.program_audio_bps = parse_bitrate_bps(value)

    def preview_mpv_event(self, mpv, message):
        event = message.get("event")
        if event == "file-loaded":
            mpv.apply_pending_range()
            self.preview_video_bps = 0
            self.preview_audio_bps = 0
            entry = self.selected_entry()
            if entry and mpv.has_file(entry.path):
                self.apply_tracks(entry, mpv)
                if self.preview_live and self.program_state == "PLAYING":
                    self._apply_program_loop(entry, mpv)
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
            self._refresh_live_bitrates()
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
        self._stop_remote_api()
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
