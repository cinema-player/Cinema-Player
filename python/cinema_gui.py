"""Cinema Player control GUI matching the layout mockup."""

from __future__ import annotations

import json
import os
import time
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, ttk

from cinema_player import (
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
    find_mpv,
    format_clock,
    format_fps_label,
    probe_media,
)

LOGO_BG = "#000000"
LOGO_ACCENT = "#4d9be6"
FONT_LOGO = ("DejaVu Sans", 17, "bold")
FONT_LOGO_LIGHT = ("DejaVu Sans", 17)
LOGO_HEADER_FILE = os.path.join(ROOT_DIR, "assets", "cinema-player-logo-header.png")
LOGO_ICON_FILE = os.path.join(ROOT_DIR, "assets", "cinema-player-icon.png")
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
    },
}

DEFAULT_THEME = "dark"
THEME = DEFAULT_THEME


def apply_theme(name):
    """Rebind the palette names so widgets built afterwards use the chosen design."""
    global THEME, COLOR_BG, COLOR_PANEL, COLOR_ROW, COLOR_TEXT, COLOR_MUTED, COLOR_PLAYED
    global COLOR_BORDER, COLOR_READOUT, COLOR_BADGE_IDLE, COLOR_BUTTON, COLOR_BUTTON_ACTIVE
    global COLOR_FIELD, COLOR_VIDEO, TRACK_BG, TRACK_EDGE, RANGE_FILL, PLAYHEAD, MARKER, ACCENT

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
        self.duration = max(0.0, float(duration or 0))
        if not self.dragging:
            self.position = max(0.0, float(position or 0))
        self.in_point = in_point
        self.out_point = out_point
        self.redraw()

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
                self.create_text(rx0 + 3, 1, text="In", anchor="nw", fill=MARKER, font=FONT_SMALL)
                self.create_text(rx1 - 3, 1, text="Out", anchor="ne", fill=MARKER, font=FONT_SMALL)
            else:
                self.create_text(rx0, 1, text="In", anchor="n", fill=MARKER, font=FONT_SMALL)
                self.create_text(rx1, 1, text="Out", anchor="n", fill=MARKER, font=FONT_SMALL)
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
        self.root.title("Cinema Player")
        self.icon_image = self._load_image(LOGO_ICON_FILE)
        if self.icon_image is not None:
            self.root.iconphoto(True, self.icon_image)
        self.root.minsize(1280, 720)
        self.root.geometry("1600x900")

        self.settings = load_settings()
        self.theme = apply_theme(self.settings.get("theme", DEFAULT_THEME))
        self.root.configure(bg=COLOR_BG)
        self.apply_widget_defaults()

        self.output_manager = VideoOutputManager(VIDEO_OUTPUT)
        self.mpv_path = find_mpv()
        self.main_mpv = MPVController("main", self.mpv_path)
        self.preview_mpv = MPVController("preview", self.mpv_path)

        self.playlist = []
        self.playlist_path = ""
        self.program_state = "OFF"
        self.program_index = 0
        self.preview_index = None
        self.preview_live = True
        self.live_parked = None
        self.current_file = None
        self.duration = 0.0
        self.position = 0.0
        self.preview_duration = 0.0
        self.preview_position = 0.0
        self.main_pause = False
        self.blackout = False
        self.idle_media_path = ""
        self.idle_showing = False
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
        self.last_import_dir = self.settings.get("last_import_dir") or ""
        if self.last_import_dir and not os.path.isdir(self.last_import_dir):
            self.last_import_dir = ""

        self.projection_zoom = tk.BooleanVar(value=False)
        self.autoplay_delay = tk.StringVar(value="0")
        self.idle_media = tk.StringVar(value="none")
        self.autoplay_var = tk.BooleanVar(value=False)
        self.played_var = tk.BooleanVar(value=False)
        self.display_time = tk.StringVar(value="0")
        self.audio_var = tk.StringVar(value="--")
        self.subtitle_var = tk.StringVar(value="--")

        self.create_gui()
        self.main_mpv.add_callback(self.main_mpv_event)
        self.preview_mpv.add_callback(self.preview_mpv_event)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(200, self.start_preview_player)
        self.root.after(400, lambda: self.ensure_main_output(auto=True))
        self.update_gui()
        self.refresh_all()

    def create_gui(self):
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(1, weight=1)

        self._build_logo()

        left = tk.Frame(self.root, bg=COLOR_BG)
        left.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(6, weight=1)

        right = tk.Frame(self.root, bg=COLOR_BG)
        right.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self._build_program_status(left)
        self._build_transport(left)
        self._build_playlist_header(left)
        self._build_playlist_settings(left)
        self._build_playlist(left)
        self._build_beamer(right)
        self._build_preview(right)

    def _build_logo(self):
        header = tk.Frame(self.root, bg=COLOR_BG)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6))

        self.theme_button = tk.Button(
            header, text=f"{'light' if self.theme == 'dark' else 'dark'} design",
            font=FONT_SMALL, command=self.toggle_theme,
        )
        self.theme_button.pack(side="right")

        self.logo_image = self._load_image(LOGO_HEADER_FILE)
        if self.logo_image is not None:
            tk.Label(header, image=self.logo_image, bg=LOGO_BG, bd=0).pack(side="left")
            return

        plate = tk.Frame(header, bg=LOGO_BG)
        plate.pack(side="left")
        tk.Label(
            plate, text="CINEMA", bg=LOGO_BG, fg=COLOR_WHITE, font=FONT_LOGO,
        ).pack(side="left", padx=(10, 0), pady=4)
        tk.Label(
            plate, text="PLAYER", bg=LOGO_BG, fg=LOGO_ACCENT, font=FONT_LOGO_LIGHT,
        ).pack(side="left", padx=(7, 10), pady=4)

    def _load_image(self, path):
        try:
            return tk.PhotoImage(file=path)
        except tk.TclError:
            return None

    def apply_widget_defaults(self):
        """Colour the widget classes that are built without explicit colours."""
        for pattern, value in (
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

    def rebuild_gui(self):
        """Rebuild the window for the current design and re-embed the preview player."""
        self.preview_mpv.quit()
        for child in self.root.winfo_children():
            child.destroy()
        self.row_widgets = []
        self.drop_marker = None
        self.drag_index = None
        self.drag_moved = False
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

    def _panel(self, parent, **kwargs):
        return tk.Frame(parent, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER,
                        highlightthickness=1, **kwargs)

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
            bar, text="OFF", font=FONT_STATUS, bg=COLOR_OFF, fg=COLOR_WHITE,
            width=12, pady=6,
        )
        self.state_label.grid(row=0, column=0, sticky="nsw")

        self.now_playing = tk.Label(
            bar, text="No program", font=FONT_UI_BOLD, bg=COLOR_READOUT,
            fg=COLOR_TEXT, anchor="w", padx=10,
        )
        self.now_playing.grid(row=0, column=1, sticky="nsew")

        self.program_times = tk.Label(
            bar, text="-- / --:--", font=FONT_STATUS, bg=COLOR_READOUT,
            fg=COLOR_TEXT, padx=10,
        )
        self.program_times.grid(row=0, column=2, sticky="nse")

        progress = tk.Frame(parent, bg=COLOR_BG)
        progress.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        progress.columnconfigure(0, weight=1)

        self.main_progress = RangeProgressBar(
            progress, on_seek=self._on_main_seek, can_seek=self.program_seek_allowed,
            height=32, bg=COLOR_BG,
        )
        self.main_progress.grid(row=0, column=0, sticky="ew")

        marks = tk.Frame(progress, bg=COLOR_BG)
        marks.grid(row=1, column=0, sticky="ew", padx=8)
        for col in range(3):
            marks.columnconfigure(col, weight=1)
        self.main_in = tk.Label(marks, text="In: --:--", bg=COLOR_BG, font=FONT_SMALL)
        self.main_in.grid(row=0, column=0, sticky="w")
        self.main_time = tk.Label(marks, text="Time: --:--", bg=COLOR_BG, font=FONT_SMALL)
        self.main_time.grid(row=0, column=1)
        self.main_out = tk.Label(marks, text="Out: --:--", bg=COLOR_BG, font=FONT_SMALL)
        self.main_out.grid(row=0, column=2, sticky="e")

        times = tk.Frame(parent, bg=COLOR_BG)
        times.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        for col in range(4):
            times.columnconfigure(col, weight=1)
        self.time_total = self._time_box(times, "Total", 0)
        self.time_elapsed = self._time_box(times, "Elapsed", 1)
        self.time_remaining = self._time_box(times, "Remaining", 2)
        self.time_end = self._time_box(times, "End", 3)

    def _time_box(self, parent, title, column):
        box = tk.Frame(parent, bg=COLOR_BG)
        box.grid(row=0, column=column, sticky="ew")
        tk.Label(box, text=title, font=FONT_SMALL, bg=COLOR_BG, fg=COLOR_MUTED).pack()
        value = tk.Label(box, text="--:--", font=FONT_UI_BOLD, bg=COLOR_BG, fg=COLOR_TEXT)
        value.pack()
        return value

    def _build_transport(self, parent):
        row = tk.Frame(parent, bg=COLOR_BG)
        row.grid(row=3, column=0, sticky="w", pady=(0, 10))
        self.btn_stop = self._transport_button(row, "Stop", self.confirm_stop)
        self.btn_pause = self._transport_button(row, "Pause", self.confirm_pause)
        self.btn_still = self._transport_button(row, "Still", self.confirm_still)
        self.btn_play = self._transport_button(row, "Start", self.start_or_resume, primary=True)

    def _transport_button(self, parent, text, command, primary=False):
        button = tk.Button(
            parent, text=text, command=command, font=FONT_UI_BOLD if primary else FONT_UI,
            width=10, pady=4,
        )
        button.pack(side="left", padx=(0, 8))
        return button

    def _build_playlist_header(self, parent):
        header = tk.Frame(parent, bg=COLOR_BG)
        header.grid(row=4, column=0, sticky="new")
        header.columnconfigure(1, weight=1)

        tk.Label(
            header, text="Playlist", font=FONT_UI_BOLD, bg=COLOR_BG, fg=COLOR_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.playlist_name = tk.Entry(header, font=FONT_UI)
        self.playlist_name.insert(0, "untitled.pls")
        self.playlist_name.grid(row=0, column=1, sticky="ew")

        buttons = tk.Frame(header, bg=COLOR_BG)
        buttons.grid(row=0, column=2, sticky="e", padx=(8, 0))
        tk.Button(buttons, text="import", font=FONT_SMALL, command=self.import_media).pack(side="left", padx=2)
        tk.Button(buttons, text="load", font=FONT_SMALL, command=self.load_playlist).pack(side="left", padx=2)
        tk.Button(buttons, text="save", font=FONT_SMALL, command=self.save_playlist).pack(side="left", padx=2)
        tk.Button(
            buttons, text="reset played", font=FONT_SMALL, command=self.reset_played,
        ).pack(side="left", padx=2)

        self.playlist_header = header

    def _build_playlist_settings(self, parent):
        settings = tk.Frame(parent, bg=COLOR_BG)
        settings.grid(row=5, column=0, sticky="ew", pady=(6, 6))

        self._checkbutton(
            settings, "Projection zoom", self.projection_zoom, self.refresh_playlist, COLOR_BG,
        ).pack(side="left")

        tk.Label(settings, text="Autoplay delay:", bg=COLOR_BG, font=FONT_UI).pack(side="left", padx=(16, 4))
        tk.Entry(settings, textvariable=self.autoplay_delay, width=5, font=FONT_UI).pack(side="left")
        tk.Label(settings, text="s", bg=COLOR_BG, font=FONT_UI).pack(side="left")

        tk.Label(settings, text="Idle media:", bg=COLOR_BG, font=FONT_UI).pack(side="left", padx=(16, 4))
        self.idle_button = tk.Button(
            settings, textvariable=self.idle_media, font=FONT_SMALL,
            command=self.choose_idle_media,
        )
        self.idle_button.pack(side="left")

        # Placeholder so playlist grid row 4 can grow; settings sit above list
        self.playlist_settings = settings

    def _build_playlist(self, parent):
        holder = tk.Frame(parent, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1)
        holder.grid(row=6, column=0, sticky="nsew")
        parent.rowconfigure(6, weight=1)
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
        panel = self._panel(parent)
        panel.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        panel.columnconfigure(0, weight=1)

        header = tk.Frame(panel, bg=COLOR_PANEL)
        header.pack(fill="x", padx=8, pady=(6, 4))
        tk.Label(
            header, text="Beamer status", font=FONT_UI_BOLD, bg=COLOR_PANEL, fg=COLOR_TEXT,
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

    def _build_preview(self, parent):
        panel = self._panel(parent)
        panel.grid(row=1, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)

        header = tk.Frame(panel, bg=COLOR_PANEL)
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 4))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="Preview", font=FONT_UI_BOLD, bg=COLOR_PANEL).grid(row=0, column=0, sticky="w")

        title_row = tk.Frame(panel, bg=COLOR_PANEL)
        title_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        title_row.columnconfigure(0, weight=1)
        self.preview_title = tk.Label(
            title_row, text="No clip", font=FONT_UI_BOLD, bg=COLOR_READOUT,
            fg=COLOR_TEXT, anchor="w", padx=8, pady=4,
        )
        self.preview_title.grid(row=0, column=0, sticky="ew")
        self.preview_mode_btn = tk.Button(
            title_row, text="Live", font=FONT_STATUS, width=10,
            command=self.toggle_preview_mode, pady=3,
        )
        self.preview_mode_btn.grid(row=0, column=1, padx=(8, 0))

        self.preview_meta = tk.Label(
            panel, text="Length: --:--", font=FONT_SMALL, bg=COLOR_PANEL, anchor="w",
        )
        self.preview_meta.grid(row=2, column=0, sticky="ew", padx=8)

        self.preview_video = tk.Frame(panel, bg=COLOR_VIDEO, width=480, height=270)
        self.preview_video.grid(row=3, column=0, sticky="nsew", padx=8, pady=6)
        panel.rowconfigure(3, weight=1)
        self.preview_placeholder = tk.Label(
            self.preview_video, text="video preview", bg=COLOR_VIDEO,
            fg=COLOR_MUTED, font=("DejaVu Sans", 16),
        )
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self.preview_progress = RangeProgressBar(
            panel, on_seek=self._on_preview_seek, height=32,
        )
        self.preview_progress.grid(row=4, column=0, sticky="ew", padx=8)

        marks = tk.Frame(panel, bg=COLOR_PANEL)
        marks.grid(row=5, column=0, sticky="ew", padx=8, pady=(2, 4))
        self.preview_marks = marks
        for col in range(3):
            marks.columnconfigure(col, weight=1)
        self.preview_in = tk.Label(marks, text="In: --:--", bg=COLOR_PANEL, font=FONT_SMALL)
        self.preview_in.grid(row=0, column=0, sticky="w")
        self.preview_time = tk.Label(marks, text="Time: --:--", bg=COLOR_PANEL, font=FONT_SMALL)
        self.preview_time.grid(row=0, column=1)
        self.preview_out = tk.Label(marks, text="Out: --:--", bg=COLOR_PANEL, font=FONT_SMALL)
        self.preview_out.grid(row=0, column=2, sticky="e")

        io = tk.Frame(panel, bg=COLOR_PANEL)
        io.grid(row=6, column=0, sticky="w", padx=8, pady=(0, 4))
        self.preview_io = io
        tk.Button(io, text="Set In", font=FONT_SMALL, command=self.set_in_point).pack(side="left", padx=(0, 4))
        tk.Button(io, text="Set Out", font=FONT_SMALL, command=self.set_out_point).pack(side="left", padx=4)
        tk.Button(io, text="Clear In/Out", font=FONT_SMALL, command=self.clear_in_out).pack(side="left", padx=4)

        transport = tk.Frame(panel, bg=COLOR_PANEL)
        self.preview_transport = transport
        transport.grid(row=7, column=0, sticky="w", padx=8, pady=(0, 6))
        for text, cmd in (
            ("rev", lambda: self.preview_seek(-5)),
            ("stop", self.preview_stop),
            ("pause", self.preview_pause),
            ("play", self.preview_play),
            ("fwd", lambda: self.preview_seek(5)),
        ):
            tk.Button(transport, text=text, font=FONT_SMALL, width=7, command=cmd).pack(side="left", padx=2)

        footer = tk.Frame(panel, bg=COLOR_PANEL)
        footer.grid(row=8, column=0, sticky="ew", padx=8, pady=(0, 8))
        self._checkbutton(
            footer, "Autoplay", self.autoplay_var, self.apply_entry_settings, COLOR_PANEL,
        ).pack(side="left")

        # Everything that only makes sense for a moving clip.
        clip_settings = tk.Frame(footer, bg=COLOR_PANEL)
        clip_settings.pack(side="left")
        self.preview_clip_settings = clip_settings
        self._checkbutton(
            clip_settings, "Played", self.played_var, self.apply_entry_settings, COLOR_PANEL,
        ).pack(side="left", padx=(8, 0))
        tk.Label(clip_settings, text="Audio track:", bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left", padx=(12, 4))
        self.audio_combo = ttk.Combobox(clip_settings, textvariable=self.audio_var, width=16, state="readonly")
        self.audio_combo.pack(side="left")
        self.audio_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_entry_settings())
        tk.Label(clip_settings, text="Subtitle:", bg=COLOR_PANEL, font=FONT_SMALL).pack(side="left", padx=(12, 4))
        self.subtitle_combo = ttk.Combobox(clip_settings, textvariable=self.subtitle_var, width=12, state="readonly")
        self.subtitle_combo.pack(side="left")
        self.subtitle_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_entry_settings())

        # Only for stills: how long the image stays on the projector.
        image_settings = tk.Frame(footer, bg=COLOR_PANEL)
        self.preview_image_settings = image_settings
        tk.Label(image_settings, text="Display time:", bg=COLOR_PANEL, font=FONT_SMALL).pack(
            side="left", padx=(12, 4)
        )
        entry_box = tk.Entry(image_settings, textvariable=self.display_time, width=5, font=FONT_UI)
        entry_box.pack(side="left")
        entry_box.bind("<Return>", lambda e: self.apply_entry_settings())
        entry_box.bind("<FocusOut>", lambda e: self.apply_entry_settings())
        tk.Label(
            image_settings, text="s   (0 = until resume)", bg=COLOR_PANEL, font=FONT_SMALL,
            fg=COLOR_MUTED,
        ).pack(side="left", padx=(4, 0))

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
        self.state_label.config(text=self.program_state, bg=self.state_color())
        entry = self.current_entry() if self.program_state != "OFF" else self.selected_entry()
        name = entry.filename if entry else "No program"
        self.now_playing.config(text=name, bg=self.state_color() if self.program_state != "OFF" else COLOR_READOUT,
                                fg=COLOR_WHITE if self.program_state != "OFF" else COLOR_TEXT)
        index = f"{self.program_index + 1}" if self.playlist else "-"
        self.program_times.config(
            text=f"{index} / {format_clock(self.duration if self.duration else (entry.duration if entry else 0))}"
        )
        self.btn_play.config(text="Resume" if self.program_state != "OFF" else "Start")
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
        self.time_total.config(text=format_clock(self.duration or (entry.duration if entry else None)))
        self.time_elapsed.config(text=format_clock(self.position if self.program_state == "PLAYING" else 0))
        remaining = None
        if self.duration:
            remaining = max(0, self.duration - self.position)
        self.time_remaining.config(text=format_clock(remaining))
        end_text = "--:--"
        if remaining is not None:
            end_text = (datetime.now() + timedelta(seconds=remaining)).strftime("%H:%M:%S")
        self.time_end.config(text=end_text)

    def refresh_playlist(self):
        for child in self.playlist_inner.winfo_children():
            child.destroy()
        self.row_widgets = []
        previous_aspect = None
        for index, entry in enumerate(self.playlist):
            if self.projection_zoom.get() and previous_aspect and entry.aspect != previous_aspect:
                entry.aspect_warning = True
            else:
                entry.aspect_warning = False
            if entry.aspect != "--":
                previous_aspect = entry.aspect
            self._make_row(index, entry)

    def _row_colors(self, index, entry):
        bg = COLOR_ROW
        fg = COLOR_PLAYED if entry.played and index != self.program_index else COLOR_TEXT
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
        return "resume"

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

        fps = tk.Label(row, text="", bg=bg, fg=fg, font=FONT_SMALL)
        fps.grid(row=1, column=3, sticky="e")

        autoplay = tk.Label(row, text="", width=5, bg=bg, fg=fg, font=FONT_SMALL)
        autoplay.grid(row=0, column=4, rowspan=2, sticky="e", padx=(8, 0))

        self.row_widgets.append({
            "row": row,
            "cursor": cursor,
            "plain": plain,
            "duration": duration,
            "fps": fps,
            "autoplay": autoplay,
        })
        self._paint_row(index, entry)

        for widget in row.winfo_children() + [row]:
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
        warn = (not entry.refresh_ok) or entry.aspect_warning
        widgets["fps"].config(
            text=f"{'> ' if warn else ''}{format_fps_label(entry.fps)} / {entry.aspect}",
            bg=bg, fg=COLOR_WARNING if warn and fg != COLOR_WHITE else fg,
        )
        widgets["autoplay"].config(
            text="AUTO" if entry.autoplay else "",
            bg=bg, fg=fg if fg == COLOR_WHITE else ACCENT,
        )

    def apply_preview_layout(self, entry):
        """Stills only need Autoplay and their display time; hide the clip controls."""
        image = bool(entry and entry.is_image)
        for widget in (
            self.preview_progress, self.preview_marks,
            self.preview_io, self.preview_transport,
        ):
            if image:
                widget.grid_remove()
            else:
                widget.grid()
        if image:
            self.preview_clip_settings.pack_forget()
            self.preview_image_settings.pack(side="left")
        else:
            self.preview_image_settings.pack_forget()
            self.preview_clip_settings.pack(side="left")

    def repaint_playlist(self):
        """Update row colours and marks in place, keeping the widgets alive."""
        if len(self.row_widgets) != len(self.playlist):
            self.refresh_playlist()
            return
        for index, entry in enumerate(self.playlist):
            self._paint_row(index, entry)

    def refresh_preview_meta(self):
        entry = self.selected_entry()
        live = self.preview_live or self.preview_index is None
        mode = "Live" if live else "Preview"
        color = self.state_color() if live else COLOR_PREVIEW
        self.preview_mode_btn.config(text=mode, bg=color, fg=COLOR_WHITE, activebackground=color)
        if live:
            self.preview_title.config(text=entry.filename if entry else "Live", bg=color, fg=COLOR_WHITE)
        else:
            self.preview_title.config(
                text=entry.filename if entry else "Preview", bg=COLOR_PREVIEW, fg=COLOR_WHITE
            )
        self.apply_preview_layout(entry)
        if not entry:
            self.preview_meta.config(text="Length: --:--")
            self.audio_combo["values"] = ["--"]
            self.subtitle_combo["values"] = ["--"]
            self._update_preview_bar()
            return
        if entry.is_image:
            self.display_time.set(format_seconds(entry.display_time))
            self.preview_meta.config(
                text=f"Still image   {entry.container} - {entry.width}x{entry.height} - {entry.aspect}"
            )
            self.autoplay_var.set(entry.autoplay)
            self.played_var.set(entry.played)
            self._update_preview_bar()
            return
        self.preview_meta.config(
            text=(
                f"Length: {format_clock(entry.duration)}   "
                f"{entry.container} - {entry.video_codec} / {entry.audio_codec} - {entry.aspect}"
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
        self.preview_in.config(text=f"In: {format_clock(entry.in_point)}")
        self.preview_out.config(text=f"Out: {format_clock(entry.out_point)}")
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
            return
        entry = self.current_entry() if self.program_state == "PLAYING" else self.selected_entry()
        fps = entry.fps if entry else 0
        matched = (
            self.output_manager.refresh_matches(fps, mode.refresh)
            if fps else True
        )
        self.beamer_ok.config(
            text="OK" if matched else "Mismatch",
            bg=COLOR_PLAYING if matched else COLOR_OFF,
        )
        self.beamer_res.config(text=f"{mode.width} x {mode.height}")
        self.beamer_fps.config(text=format_fps_label(mode.refresh))
        self.beamer_aspect.config(text=aspect_from_mode(mode))

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
        menu = tk.Menu(
            self.root, tearoff=0, bg=COLOR_PANEL, fg=COLOR_TEXT,
            activebackground=COLOR_PROGRAM, activeforeground=COLOR_WHITE,
            disabledforeground=COLOR_PLAYED,
        )
        menu.add_command(
            label="Set program", command=lambda: self.set_program_point(index),
            state="disabled" if playing else "normal",
        )
        menu.add_command(label="Toggle autoplay", command=lambda: self.toggle_autoplay(index))
        menu.add_separator()
        menu.add_command(
            label="Delete entry", command=lambda: self.delete_entry(index),
            state="disabled" if playing and index == self.program_index else "normal",
        )
        self.row_menu = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def set_program_point(self, index):
        if self.program_state == "PLAYING" or not 0 <= index < len(self.playlist):
            return
        self.program_index = index
        self.repaint_playlist()
        self.refresh_status()

    def toggle_autoplay(self, index):
        if not 0 <= index < len(self.playlist):
            return
        entry = self.playlist[index]
        entry.autoplay = not entry.autoplay
        if index == self.preview_index:
            self.autoplay_var.set(entry.autoplay)
        self.repaint_playlist()

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

    def import_media(self):
        dialog_options = {}
        if self.last_import_dir:
            dialog_options["initialdir"] = self.last_import_dir
        paths = filedialog.askopenfilenames(
            title="Import media",
            filetypes=[
                ("Media", " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTS | IMAGE_EXTS))),
                ("All files", "*.*"),
            ],
            **dialog_options,
        )
        if not paths:
            directory = filedialog.askdirectory(
                title="Import directory",
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
            messagebox.showerror("Import", f"{os.path.basename(path)}\n{exc}")
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

    def load_playlist(self):
        path = filedialog.askopenfilename(
            title="Load playlist",
            filetypes=[("Playlist", "*.pls *.json"), ("All files", "*.*")],
        )
        if not path:
            return
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.playlist = [PlaylistEntry.from_dict(item) for item in data.get("entries", [])]
        self.projection_zoom.set(data.get("projection_zoom", False))
        self.autoplay_delay.set(str(data.get("autoplay_delay", 0)))
        self.idle_media_path = data.get("idle_media_path", "")
        self.idle_media.set(
            os.path.basename(self.idle_media_path) if self.idle_media_path else "none"
        )
        self.playlist_path = path
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, os.path.basename(path))
        # Pick up the saved program cue, clamped to the entries we actually loaded.
        try:
            index = int(data.get("program_index", 0))
        except (TypeError, ValueError):
            index = 0
        self.program_index = min(max(index, 0), max(len(self.playlist) - 1, 0))
        self.preview_index = None
        self.preview_live = True
        if self.program_state != "PLAYING":
            self.blank_output()
        self.refresh_all()

    def save_playlist(self):
        suggested = self.playlist_name.get().strip() or "playlist.pls"
        path = filedialog.asksaveasfilename(
            title="Save playlist",
            defaultextension=".pls",
            initialfile=suggested,
            filetypes=[("Playlist", "*.pls"), ("JSON", "*.json")],
        )
        if not path:
            return
        payload = {
            "projection_zoom": self.projection_zoom.get(),
            "autoplay_delay": float(self.autoplay_delay.get() or 0),
            "idle_media": self.idle_media.get(),
            "idle_media_path": self.idle_media_path,
            "program_index": self.program_index,
            "entries": [entry.__dict__ for entry in self.playlist],
        }
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        self.playlist_path = path
        self.playlist_name.delete(0, "end")
        self.playlist_name.insert(0, os.path.basename(path))

    def choose_idle_media(self):
        dialog_options = {}
        if self.last_import_dir:
            dialog_options["initialdir"] = self.last_import_dir
        path = filedialog.askopenfilename(title="Idle screen media", **dialog_options)
        self.idle_media.set(os.path.basename(path) if path else "none")
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
        self.repaint_playlist()

    def reset_played(self):
        for entry in self.playlist:
            entry.played = False
        self.played_var.set(False)
        self.repaint_playlist()

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
            self.main_mpv.start(self.output_manager.get_mpv_arguments())
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
            return
        self.main_mpv.stop()
        self.main_mpv.set_loop_file(False)
        self.main_mpv.set_vid(True)
        self.current_file = None
        self.main_pause = False
        self.blackout = True
        self.idle_showing = False
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
        self.main_mpv.set_loop_file(True)
        self.main_mpv.load_file(path, play=True)
        self.blackout = False
        self.idle_showing = True
        self.duration = 0.0
        self.position = 0.0

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
        ]
        try:
            self.preview_mpv.start(arguments)
            self.preview_mpv.set_volume(0)
            self.preview_placeholder.place_forget()
        except Exception as exc:
            self.preview_placeholder.config(text=f"Preview unavailable\n{exc}")

    def show_preview_clip(self, entry, follow_live=False, start=None, play=None):
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
            self.ensure_main_output()
            # Arming brings up the idle background, if one is set.
            self.blank_output()
            self.refresh_all()
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
        if self.idle_showing:
            # Fade the non-black background out to black before the clip comes up.
            self.blank_output(show_idle=False)
            delay = int(self.autoplay_seconds() * 1000)
            self.autoplay_after_id = self.root.after(delay, self.start_current_clip)
            return
        self.program_index = min(self.program_index, len(self.playlist) - 1)
        entry = self.playlist[self.program_index]
        if self.projection_zoom.get() and entry.aspect_warning:
            if not messagebox.askokcancel(
                "Projection zoom",
                f"{entry.filename} needs a zoom / aspect change ({entry.aspect}).\n"
                "Confirm after the projector zoom has been set.",
            ):
                self.program_state = "PROGRAM"
                self.refresh_all()
                return
        try:
            video, mode, matched = self.output_manager.prepare_for_video(entry.path)
            entry.refresh_ok = matched
        except Exception as exc:
            messagebox.showerror("Playback", str(exc))
            self.program_state = "PROGRAM"
            self.refresh_all()
            return

        if not self.ensure_main_output():
            messagebox.showerror("Playback", "Der Videoausgang konnte nicht geoeffnet werden.")
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
        if messagebox.askyesno("Pause", "Pause playback? The projector output will go black."):
            self.main_mpv.set_pause(True)
            self.main_mpv.set_vid(False)
            self.preview_mpv.set_pause(True)
            self.main_pause = True
            self.blackout = True

    def confirm_still(self):
        if self.program_state != "PLAYING":
            return
        if messagebox.askyesno("Still", "Freeze the current frame on the projector?"):
            self.main_mpv.set_vid(True)
            self.main_mpv.set_pause(True)
            self.preview_mpv.set_pause(True)
            self.main_pause = True
            self.blackout = False

    def confirm_stop(self):
        if self.program_state == "OFF":
            return
        playing = self.program_state == "PLAYING"
        question = "Stop the current clip?" if playing else "Stop the program?"
        if not messagebox.askyesno("Stop", question):
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
            if self.program_index < len(self.playlist) - 1:
                self.program_index += 1
        else:
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
        has_next = self.program_index < len(self.playlist) - 1
        autoplay = bool(entry and entry.autoplay and has_next)
        self.program_state = "PROGRAM"
        # The delay stays black; the idle background only follows when nothing is queued.
        self.blank_output(show_idle=not autoplay)
        if has_next:
            self.program_index += 1
        self.refresh_all()
        if autoplay:
            ms = int(self.autoplay_seconds() * 1000)
            self.autoplay_after_id = self.root.after(ms, self.start_current_clip)

    def preview_play(self):
        self.preview_live = False
        entry = self.selected_entry()
        if not entry:
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
        self.refresh_preview_meta()

    def preview_pause(self):
        self.preview_mpv.set_pause(True)

    def preview_stop(self):
        self.preview_mpv.stop()

    def preview_seek(self, seconds):
        self.preview_mpv.seek(seconds)

    def set_in_point(self):
        entry = self.selected_entry()
        if not entry:
            return
        entry.in_point = self.preview_position
        if entry.out_point is not None and entry.in_point > entry.out_point:
            entry.in_point, entry.out_point = entry.out_point, entry.in_point
        self.refresh_preview_meta()

    def set_out_point(self):
        entry = self.selected_entry()
        if not entry:
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
        if self.preview_duration > 0:
            return self.preview_duration
        entry = self.selected_entry()
        return entry.duration if entry else 0.0

    def _update_preview_bar(self):
        entry = self.selected_entry()
        self.preview_progress.set_state(
            duration=self._clip_duration(),
            position=self.preview_position,
            in_point=entry.in_point if entry else None,
            out_point=entry.out_point if entry else None,
        )

    def _update_main_bar(self):
        entry = self.current_entry()
        if self.idle_showing:
            # The background is not a program clip: no In/Out marks, no highlight.
            duration = self.duration
            in_point = out_point = None
        else:
            duration = self.duration or (entry.duration if entry else 0)
            in_point = entry.in_point if entry else None
            out_point = entry.out_point if entry else None
        self.main_progress.set_state(
            duration=duration,
            position=self.position,
            in_point=in_point,
            out_point=out_point,
        )
        self.main_in.config(text=f"In: {format_clock(in_point)}")
        self.main_out.config(text=f"Out: {format_clock(out_point)}")
        self.main_time.config(text=f"Time: {format_clock(self.position)}")

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
        self.main_time.config(text=f"Time: {format_clock(position)}")
        self.main_mpv.set_position(position)
        if self.preview_live:
            self.preview_mpv.set_position(position)

    def _on_preview_seek(self, position, dragging=False):
        self.preview_position = position
        self.preview_time.config(text=f"Time: {format_clock(position)}")
        self.preview_mpv.set_position(position)

    def main_mpv_event(self, mpv, message):
        event = message.get("event")
        if event == "file-loaded":
            mpv.apply_pending_range()
            entry = self.current_entry()
            if entry and mpv.has_file(entry.path):
                self.apply_tracks(entry, mpv)
            self.main_pause = False
            return
        if event == "end-file" and message.get("reason") in (None, "eof", "stop"):
            if message.get("reason") == "eof" and not self.still_active():
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
            self.position = float(value)
            entry = self.current_entry()
            if (
                self.program_state == "PLAYING"
                and entry
                and entry.out_point is not None
                and self.position >= entry.out_point - 0.04
            ):
                self.root.after(0, self.on_clip_finished)
        elif name == "duration" and value is not None:
            self.duration = float(value)
        elif name == "pause" and value is not None:
            self.main_pause = bool(value)
        elif name == "eof-reached" and value:
            self.root.after(0, self.on_clip_finished)

    def preview_mpv_event(self, mpv, message):
        event = message.get("event")
        if event == "file-loaded":
            mpv.apply_pending_range()
            return
        if event != "property-change":
            return
        name = message.get("name")
        value = message.get("data")
        if name == "time-pos" and value is not None:
            self.preview_position = float(value)
        elif name == "duration" and value is not None:
            self.preview_duration = float(value)

    def update_gui(self):
        if self.still_started is not None and self.program_state == "PLAYING":
            self.position = min(self.duration, time.monotonic() - self.still_started)
        if not self.main_progress.dragging:
            self._update_main_bar()
        if not self.preview_progress.dragging:
            self._update_preview_bar()
        self.preview_time.config(text=f"Time: {format_clock(self.preview_position)}")
        self.sync_live_preview()
        self.refresh_status()
        self.refresh_beamer()
        self.root.after(250, self.update_gui)

    def close(self):
        for after_id in (self.autoplay_after_id, self.idle_after_id, self.still_after_id):
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
