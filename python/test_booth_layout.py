#!/usr/bin/env python3
"""Booth layout: playlist columns, show chrome, beamer short form, clocks."""

import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))


def _ensure_real_tkinter():
    """Undo the MagicMock some earlier test modules install for headless runs."""
    current = sys.modules.get("tkinter")
    if current is not None and type(current).__module__ == "unittest.mock":
        for name in list(sys.modules):
            if name == "tkinter" or name.startswith("tkinter."):
                del sys.modules[name]
        sys.modules.pop("cinema_gui", None)


_ensure_real_tkinter()

import tkinter as tk
import tkinter.font as tkfont

import cinema_gui
from cinema_player import PlaylistEntry, folder_created, reload_entry_metadata
from language import set_language, t


def _entry(**kwargs):
    path = kwargs.pop("path", "/media/films/day/clip.mp4")
    entry = PlaylistEntry(path=path, filename=os.path.basename(path))
    for key, value in kwargs.items():
        setattr(entry, key, value)
    return entry


class PlaylistMarkTests(unittest.TestCase):
    def setUp(self):
        set_language("de")

    def tearDown(self):
        set_language("en")

    def test_rate_and_zoom_sit_on_the_value(self):
        entry = _entry(fps=25, aspect="21:9", refresh_ok=False, aspect_warning=True)
        self.assertEqual(
            cinema_gui.warned_meta_text("25p", True, t("warn_rate")),
            "25p Rate",
        )
        self.assertIn("rate", cinema_gui.playlist_warning_keys(entry))
        self.assertIn("zoom", cinema_gui.playlist_warning_keys(entry))
        notes = cinema_gui.playlist_note_text(entry, True)
        self.assertNotIn("Rate", notes)
        self.assertNotIn("Zoom", notes)

    def test_narrow_format_and_par_show_16x9_conversion(self):
        four_three = _entry(aspect="4:3", pixel_aspect="1:1", width=1440, height=1080)
        self.assertEqual(cinema_gui.playlist_aspect_text(four_three), "4:3 →16:9")
        self.assertEqual(cinema_gui.playlist_par_text(four_three), "1:1")
        anamorphic = _entry(aspect="16:9", pixel_aspect="64:45", width=720, height=576)
        self.assertEqual(cinema_gui.playlist_aspect_text(anamorphic), "16:9")
        self.assertEqual(cinema_gui.playlist_par_text(anamorphic), "64:45 →16:9")
        pal = _entry(
            aspect="4:3", pixel_aspect="16:15", width=720, height=576,
            aspect_warning=True, par_warning=True,
        )
        self.assertEqual(cinema_gui.playlist_aspect_text(pal), "4:3 →16:9 Zoom")
        self.assertEqual(cinema_gui.playlist_par_text(pal), "16:15 →16:9 PAR")
        wide = _entry(aspect="21:9", pixel_aspect="1:1", width=2560, height=1080)
        self.assertEqual(cinema_gui.playlist_aspect_text(wide), "21:9")
        self.assertEqual(cinema_gui.playlist_par_text(wide), "1:1")
        self.assertEqual(cinema_gui.playlist_aspect_text(four_three, pad_16x9=False), "4:3")
        self.assertEqual(cinema_gui.playlist_par_text(anamorphic, pad_16x9=False), "64:45")

    def test_reload_replaces_picture_metadata_and_keeps_cues(self):
        entry = _entry(
            hdr_status="Unknown", colorspace="--", autoplay=True, volume=80,
            loop=True, in_point=1.0, out_point=5.0, light_start="bright",
            played=True, loudness_lufs=-23.0, audio_track="1: AAC",
            subtitle_track="1: SRT",
        )
        probed = _entry(
            hdr_status="SDR", colorspace="Rec.709", color_range="TV",
            width=1280, height=720, fps=25, duration=10,
            video_codec="H264", audio_codec="AAC",
            audio_tracks=["1: AAC"], subtitle_tracks=["--", "1: SRT"],
            aspect="16:9", pixel_aspect="1:1", resolution_label="HD",
            container="MP4",
        )
        with (
            patch("cinema_player.media_file_available", return_value=True),
            patch("cinema_player.probe_media", return_value=probed),
        ):
            self.assertTrue(reload_entry_metadata(entry))
        self.assertEqual(entry.hdr_status, "SDR")
        self.assertEqual(entry.colorspace, "Rec.709")
        self.assertEqual(entry.fps, 25)
        self.assertEqual(entry.video_codec, "H264")
        self.assertTrue(entry.autoplay)
        self.assertTrue(entry.loop)
        self.assertTrue(entry.played)
        self.assertEqual(entry.volume, 80)
        self.assertEqual(entry.in_point, 1.0)
        self.assertEqual(entry.out_point, 5.0)
        self.assertEqual(entry.light_start, "bright")
        self.assertEqual(entry.loudness_lufs, -23.0)
        self.assertFalse(entry.missing)

    def test_reload_flags_a_missing_file_without_wiping_metadata(self):
        entry = _entry(hdr_status="SDR", colorspace="Rec.709", autoplay=True)
        with patch("cinema_player.media_file_available", return_value=False):
            self.assertFalse(reload_entry_metadata(entry))
        self.assertTrue(entry.missing)
        self.assertEqual(entry.hdr_status, "SDR")
        self.assertTrue(entry.autoplay)

    def test_row_menu_order(self):
        root = tk.Tk()
        try:
            app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
            app.root = root
            app.playlist = [_entry()]
            app.program_state = "OFF"
            app.program_index = 0
            app.on_row_click = lambda index: None
            posted = {}
            app._post_dropdown = lambda menu, x, y: posted.update(menu=menu)
            event = type("E", (), {"x_root": 0, "y_root": 0})()
            cinema_gui.VideoPlayerGUI.on_row_menu(app, 0, event)
            labels = [
                child.cget("text") if isinstance(child, tk.Label) else "---"
                for child in posted["menu"].winfo_children()
            ]
            self.assertEqual(
                labels,
                [
                    "Programmzeiger setzen",
                    "---",
                    "Autoplay",
                    "Loop",
                    "---",
                    "Aktualisieren",
                    "Neu verknüpfen",
                    "In den Playlistordner kopieren",
                    "---",
                    "Eintrag löschen",
                ],
            )
        finally:
            root.destroy()

    def test_playlist_color_stacks_status_above_the_space(self):
        entry = _entry(colorspace="Rec.709", color_range="", hdr_status="SDR")
        self.assertEqual(cinema_gui.playlist_color_text(entry), "Native SDR\nRec.709")
        entry.hdr_status = "HDR"
        entry.colorspace = "Rec.2020 PQ"
        self.assertEqual(
            cinema_gui.playlist_color_text(entry),
            "HDR (output unverified)\nRec.2020 PQ",
        )

    def test_color_warning_is_a_note(self):
        entry = _entry(colorspace_warning=True, colorspace="Rec.2020")
        notes = cinema_gui.playlist_note_text(entry, True)
        self.assertIn("Farbe", notes)
        self.assertNotIn("setting!", notes)

    def test_forced_warning_keeps_the_setting_badge(self):
        entry = _entry(force_settings_warning=True)
        self.assertIn("setting!", cinema_gui.playlist_note_text(entry, True))

    def test_program_status_shows_the_runtime_of_every_video(self):
        videos = [
            _entry(duration=60, in_point=10, out_point=40),
            _entry(duration=90),
            _entry(path="/media/films/day/still.png", is_image=True, duration=0, display_time=15),
        ]
        self.assertEqual(cinema_gui.playlist_video_seconds(videos), 120)
        self.assertEqual(cinema_gui.program_times_text("-", "--:--", videos), "- / --:--   02:00")
        self.assertEqual(cinema_gui.program_times_text("2", "01:30", videos), "2 / 01:30   02:00")
        self.assertEqual(cinema_gui.program_times_text("-", "--:--", []), "- / --:--   00:00")
        self.assertEqual(
            cinema_gui.program_times_text("2", "01:30", videos, "20:02:15"),
            "2 / 01:30   02:00   Ende 20:02:15",
        )

    def test_program_end_runs_from_the_playhead_to_the_last_clip(self):
        now = datetime(2026, 10, 13, 20, 0, 0)
        first = _entry(duration=60, in_point=10, out_point=40)
        second = _entry(duration=90)
        still = _entry(path="/media/films/day/still.png", is_image=True, display_time=15)
        playlist = [first, second, still]
        self.assertEqual(cinema_gui.program_remaining_seconds(playlist, 0, 0, False), 135)
        self.assertEqual(
            cinema_gui.program_end_clock(playlist, 0, 0, False, now),
            "20:02:15",
        )
        self.assertEqual(cinema_gui.program_remaining_seconds(playlist, 0, 20, True), 125)
        self.assertEqual(cinema_gui.program_remaining_seconds(playlist, 1, 30, True), 75)
        self.assertEqual(cinema_gui.program_remaining_seconds(playlist, 0, 0, True), 135)
        self.assertEqual(cinema_gui.program_remaining_seconds(playlist, 0, 50, True), 105)

    def test_program_end_includes_the_autoplay_gap_and_skips_missing_clips(self):
        now = datetime(2026, 10, 13, 20, 0, 0)
        first = _entry(duration=30, autoplay=True)
        missing = _entry(path="/media/films/gone.mp4", duration=100, missing=True, autoplay=True)
        second = _entry(duration=20)
        playlist = [first, missing, second]
        self.assertEqual(
            cinema_gui.program_remaining_seconds(playlist, 0, 0, False, autoplay_delay=5),
            55,
        )
        self.assertEqual(
            cinema_gui.program_end_clock(playlist, 0, 0, False, now, autoplay_delay=5),
            "20:00:55",
        )

    def test_program_end_is_open_while_a_clip_waits_for_the_operator(self):
        now = datetime(2026, 10, 13, 20, 0, 0)
        film = _entry(duration=30)
        looping = _entry(duration=10, loop=True)
        holding = _entry(path="/media/films/hold.png", is_image=True, display_time=0)
        self.assertIsNone(cinema_gui.program_remaining_seconds([film, looping], 0, 0, False))
        self.assertEqual(
            cinema_gui.program_end_clock([film, looping], 0, 5, True, now),
            "--:--",
        )
        self.assertIsNone(cinema_gui.program_remaining_seconds([film, holding], 0, 0, True))
        self.assertEqual(cinema_gui.program_remaining_seconds([looping], 0, 3, False), None)

    def test_stopped_show_ends_from_the_start_even_if_the_pointer_moved(self):
        root = tk.Tk()
        try:
            app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
            app.playlist = [_entry(duration=60), _entry(duration=30)]
            app.program_state = "OFF"
            app.program_index = 1
            app.position = 10
            app.idle_showing = False
            app.autoplay_delay = tk.StringVar(master=root, value="0")
            now = datetime(2026, 10, 13, 20, 0, 0)
            self.assertEqual(cinema_gui.VideoPlayerGUI._program_end_clock(app, now), "20:01:30")
            app.program_state = "PLAYING"
            self.assertEqual(cinema_gui.VideoPlayerGUI._program_end_clock(app, now), "20:00:20")
            app.program_state = "PROGRAM"
            self.assertEqual(cinema_gui.VideoPlayerGUI._program_end_clock(app, now), "20:00:30")
        finally:
            root.destroy()

    def test_next_clip_names_the_following_title_and_zoom(self):
        first = _entry(path="/media/films/a.mp4")
        second = _entry(path="/media/films/wide.mp4", aspect="21:9", aspect_warning=True)
        label = cinema_gui.next_program_label([first, second], 0, "PLAYING", True)
        self.assertEqual(label, "als Nächstes: wide.mp4 · Zoom 21:9")
        self.assertEqual(cinema_gui.next_program_label([first], 0, "OFF", True), "")


class BoothChromeTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.root.geometry("900x600+20+20")
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.media_directories = []
        self.app.program_state = "OFF"
        self.app.program_index = 0
        self.app.preview_index = None
        self.app.preview_live = True
        self.app.calibration_mode = None
        self.app.projection_zoom = tk.BooleanVar(master=self.root, value=True)
        self.app.playlist = []
        self.app.row_widgets = []
        self.app.lights_scenes = []
        self.app.lights_sequences = []
        self.app.transport_icons = {}
        self.app.beamer_details_open = False

    def tearDown(self):
        self.root.destroy()
        set_language("en")

    def test_playlist_groups_a_shared_folder_and_warns_in_the_row(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="both", expand=True)
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        cinema_gui.VideoPlayerGUI._build_playlist(self.app, parent)
        self.app.playlist = [
            _entry(path="/media/films/day/one.mp4", fps=25, refresh_ok=False, resolution_label="HD"),
            _entry(path="/media/films/day/two.mp4", fps=24, aspect="16:9"),
            _entry(path="/media/stills/night/three.mp4", fps=30),
        ]
        cinema_gui.VideoPlayerGUI.refresh_playlist(self.app)
        self.root.update_idletasks()
        self.assertEqual(len(self.app.row_widgets), 3)
        headers = [
            child for child in self.app.playlist_inner.winfo_children()
            if getattr(child, "playlist_index", None) is None
        ]
        header_text = " ".join(child.winfo_children()[0].cget("text") for child in headers)
        self.assertIn("day", header_text)
        self.assertIn("night", header_text)
        self.assertEqual(self.app.row_widgets[0]["fps"].cget("text"), "25p Rate")
        self.assertEqual(self.app.row_widgets[0]["filename"].cget("text"), "one.mp4")
        self.assertIn("HD", self.app.row_widgets[0]["detail"].cget("text"))
        header = self.app.playlist_column_header
        texts = [
            child.cget("text")
            for child in header.winfo_children()
            if isinstance(child, tk.Label) and child.cget("text")
        ]
        self.assertEqual(
            texts,
            ["Dauer", "fps", "Format", "PAR", "Farbe", "Laut", "LUFS", "Hinweise"],
        )

    def test_playlist_row_shows_16x9_conversion_on_format_and_par(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="both", expand=True)
        cinema_gui.VideoPlayerGUI._build_playlist(self.app, parent)
        self.app.projection_zoom.set(False)
        self.app.playlist = [
            _entry(
                path="/media/films/day/pal.avi", aspect="4:3", pixel_aspect="16:15",
                width=720, height=576, fps=25,
            ),
            _entry(
                path="/media/films/day/hd.mp4", aspect="16:9", pixel_aspect="1:1",
                width=1920, height=1080, fps=24,
            ),
        ]
        cinema_gui.VideoPlayerGUI.refresh_playlist(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.row_widgets[0]["aspect"].cget("text"), "4:3 →16:9")
        self.assertEqual(self.app.row_widgets[0]["par"].cget("text"), "16:15 →16:9")
        self.assertEqual(self.app.row_widgets[1]["aspect"].cget("text"), "16:9")
        self.assertEqual(self.app.row_widgets[1]["par"].cget("text"), "1:1")
        self.app.pad_16x9 = tk.BooleanVar(master=self.root, value=False)
        cinema_gui.VideoPlayerGUI.refresh_playlist(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.row_widgets[0]["aspect"].cget("text"), "4:3")
        self.assertEqual(self.app.row_widgets[0]["par"].cget("text"), "16:15")

    def test_mouse_wheel_scrolls_the_playlist_from_a_row(self):
        parent = tk.Frame(self.root, height=180)
        parent.pack(fill="both", expand=True)
        parent.pack_propagate(False)
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        cinema_gui.VideoPlayerGUI._build_playlist(self.app, parent)
        self.app.playlist = [
            _entry(path=f"/media/films/day/clip-{index:02d}.mp4")
            for index in range(40)
        ]
        cinema_gui.VideoPlayerGUI.refresh_playlist(self.app)
        self.root.geometry("900x220+20+20")
        self.root.update()
        label = self.app.row_widgets[0]["filename"]
        before = self.app.playlist_canvas.yview()[0]
        label.event_generate("<Button-5>")
        self.root.update()
        self.assertGreater(self.app.playlist_canvas.yview()[0], before)

    def test_show_mode_hides_preparation_tools(self):
        tools = tk.Frame(self.root)
        tools.grid(row=0, column=0)
        settings = tk.Frame(self.root)
        settings.grid(row=1, column=0)
        arrow = tk.Canvas(self.root, width=28, height=28, bg="black")
        arrow.grid(row=0, column=1)
        arrow.grid_remove()
        self.app.playlist_tool_buttons = tools
        self.app.preview_settings = settings
        self.app.playlist_tools_toggle = arrow
        self.app.playlist_tools_open = False
        self.app.playlist_tools_tip = None
        self.app._playlist_tools_hover = False
        self.app.program_state = "PLAYING"
        self.app.calibration_mode = None
        cinema_gui.VideoPlayerGUI._apply_booth_chrome(self.app)
        self.root.update()
        self.assertEqual(tools.winfo_manager(), "")
        self.assertEqual(settings.winfo_manager(), "grid")
        self.assertEqual(arrow.winfo_manager(), "grid")
        self.assertEqual(len(arrow.find_all()), 1)
        cinema_gui.VideoPlayerGUI._toggle_playlist_tools(self.app)
        self.assertTrue(self.app.playlist_tools_open)
        self.assertEqual(tools.winfo_manager(), "grid")
        cinema_gui.VideoPlayerGUI._toggle_playlist_tools(self.app)
        self.assertFalse(self.app.playlist_tools_open)
        self.assertEqual(tools.winfo_manager(), "")
        self.assertEqual(settings.winfo_manager(), "grid")
        self.app.calibration_mode = "video"
        cinema_gui.VideoPlayerGUI._apply_booth_chrome(self.app)
        self.assertEqual(tools.winfo_manager(), "grid")
        self.assertEqual(settings.winfo_manager(), "grid")
        self.assertEqual(arrow.winfo_manager(), "")

    def test_remaining_clock_is_larger_than_elapsed(self):
        parent = tk.Frame(self.root)
        parent.pack()
        for column in range(2):
            parent.columnconfigure(column, weight=1)
        elapsed = cinema_gui.VideoPlayerGUI._time_box(self.app, parent, "Gelaufen", 0)
        remaining = cinema_gui.VideoPlayerGUI._time_box(self.app, parent, "Rest", 1, primary=True)
        self.assertNotEqual(elapsed.cget("font"), remaining.cget("font"))

    def test_transport_captions(self):
        row = tk.Frame(self.root)
        row.pack()
        button = cinema_gui.VideoPlayerGUI._icon_button(
            self.app, row, "pause", lambda: None, "Pause", caption=True,
        )
        self.assertEqual(button.caption.cget("text"), "Pause")

    def test_resume_reaction_is_blue_to_arm_and_green_to_roll(self):
        self.assertEqual(cinema_gui.resume_reaction_name("OFF"), "program")
        self.assertEqual(cinema_gui.resume_reaction_color("program"), cinema_gui.COLOR_PROGRAM)
        self.assertEqual(cinema_gui.resume_reaction_name("PROGRAM"), "playing")
        self.assertEqual(cinema_gui.resume_reaction_name("PLAYING"), "playing")
        self.assertEqual(cinema_gui.resume_reaction_color("playing"), cinema_gui.COLOR_PLAYING)

    def _build_program_transport(self):
        self.app.root = self.root
        parent = tk.Frame(self.root, bg=cinema_gui.COLOR_PANEL)
        parent.pack()
        cinema_gui.VideoPlayerGUI._build_transport(self.app, parent)
        self.app.main_pause = False
        self.app.blackout = False
        self.app.still_waiting = False
        self.app._program_loop_active = lambda: False
        return parent

    def test_weiter_sits_apart_and_an_armed_show_uses_the_blue_icon(self):
        self._build_program_transport()
        padx = self.app.btn_play.master.pack_info()["padx"]
        self.assertIn("28", str(padx))
        self.app.program_state = "PROGRAM"
        self.app.btn_play.icon_name = "play"
        cinema_gui.VideoPlayerGUI.refresh_transport(self.app)
        self.assertEqual(
            str(self.app.btn_play.cget("image")),
            str(self.app._transport_icon("play-program")),
        )
        self.assertEqual(
            str(self.app.btn_play.caption.cget("fg")).lower(),
            cinema_gui.COLOR_PROGRAM.lower(),
        )

    def test_weiter_press_lights_before_the_clip_starts(self):
        self._build_program_transport()
        self.app.program_state = "PROGRAM"
        self.app.playlist = [_entry()]
        self.app._remote_action = False
        seen = {}

        def start_current_clip():
            seen["reaction"] = self.app._resume_reaction
            seen["image"] = str(self.app.btn_play.cget("image"))
            seen["caption"] = str(self.app.btn_play.caption.cget("fg")).lower()

        self.app.start_current_clip = start_current_clip
        cinema_gui.VideoPlayerGUI.start_or_resume(self.app)
        self.assertEqual(seen["reaction"], "playing")
        self.assertEqual(seen["image"], str(self.app._transport_icon("play-playing")))
        self.assertEqual(seen["caption"], cinema_gui.COLOR_WHITE.lower())
        self.assertEqual(
            str(self.app.btn_play.master.cget("bg")).lower(),
            cinema_gui.COLOR_PLAYING.lower(),
        )

    def test_stopped_press_lights_program_blue_and_a_rolling_clip_ignores_it(self):
        self._build_program_transport()
        self.app.program_state = "OFF"
        cinema_gui.VideoPlayerGUI._show_resume_reaction(self.app)
        self.assertEqual(self.app._resume_reaction, "program")
        self.assertEqual(
            str(self.app.btn_play.cget("image")),
            str(self.app._transport_icon("start_program-program")),
        )
        self.assertEqual(
            str(self.app.btn_play.master.cget("bg")).lower(),
            cinema_gui.COLOR_PROGRAM.lower(),
        )
        self.app.program_state = "PLAYING"
        self.app.playlist = [_entry()]
        self.app._remote_action = False
        self.app._resume_reaction = None
        self.app._resume_reaction_until = 0
        called = []
        self.app.start_current_clip = lambda: called.append("start")
        cinema_gui.VideoPlayerGUI.start_or_resume(self.app)
        self.assertEqual(called, [])
        self.assertFalse(cinema_gui.VideoPlayerGUI._resume_reaction_held(self.app))

    def test_idle_media_shares_the_next_clip_line(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="x")
        parent.columnconfigure(0, weight=1)
        self.app.playlist = [
            _entry(path="/media/films/day/one.mp4"),
            _entry(path="/media/films/day/two.mp4"),
        ]
        self.app.program_state = "PROGRAM"
        self.app.program_index = 0
        self.app.idle_media_path = "/media/idle/pause.mp4"
        self.app.idle_showing = False
        cinema_gui.VideoPlayerGUI._build_program_status(self.app, parent)
        cinema_gui.VideoPlayerGUI._refresh_next_clip(self.app)
        cinema_gui.VideoPlayerGUI._refresh_idle_status(self.app)
        self.root.update()
        self.assertEqual(self.app.idle_status.cget("text"), "pause.mp4")
        self.assertEqual(self.app.next_clip.grid_info()["row"], self.app.idle_status.grid_info()["row"])
        self.assertLess(
            abs(self.app.idle_status.winfo_rooty() - self.app.next_clip.winfo_rooty()),
            8,
        )

    def test_media_folder_window_keeps_its_buttons_on_screen(self):
        self.app.root = self.root
        self.app.icon_image = None
        self.app.media_directories = [{"path": "/tmp", "name": "Filme"}]
        self.app.last_import_dir = ""
        self.app.settings = {}
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+20+20"
        )
        held = {}

        def capture(window):
            held["window"] = window

        self.root.wait_window = capture
        cinema_gui.VideoPlayerGUI._choose_import_action(
            self.app, [{"path": "/tmp", "name": "Filme", "removable": False}],
        )
        window = held["window"]
        window.update()
        rows = window._import_list._rows
        self.assertTrue(rows[0]["pinned"])
        self.assertIn("Importpfad", rows[0]["label"].cget("text"))
        self.assertIn("nicht gesetzt", rows[0]["label"].cget("text"))
        self.assertEqual(window._import_list.selected_path(), "")
        self.assertIn("Filme", rows[1]["label"].cget("text"))
        window._import_list.select(1)
        self.assertEqual(window._import_list.selected_path(), "/tmp")
        window._import_list.select(0)
        self.assertEqual(window._import_list.selected_removable(), False)
        self.app.import_path = "/tmp"
        listed = self.app._import_window_items([
            {"path": "/tmp", "name": "Filme", "removable": False},
            {"path": "/data/stills", "name": "Stills", "removable": False},
        ])
        self.assertEqual(listed[0]["path"], "/tmp")
        self.assertTrue(listed[0]["pinned"])
        self.assertEqual([item["path"] for item in listed], ["/tmp", "/data/stills"])
        self.assertGreaterEqual(window.winfo_height(), 560)
        bottom = window.winfo_rooty() + window.winfo_height()
        labels = {
            child.cget("text"): child
            for child in window.winfo_children()
            if isinstance(child, tk.Frame)
            for child in child.winfo_children()
            if isinstance(child, tk.Button)
        }
        for text in ("Dateien importieren", "Ordner importieren", "Anderer Speicherort…", "Schließen"):
            button = labels[text]
            self.assertTrue(button.winfo_viewable())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)
        self.assertNotIn("Files kopieren", labels)
        window.geometry("680x320+20+20")
        window.update()
        self.assertEqual(window._popup_bar.winfo_manager(), "grid")
        self.assertEqual(str(window._popup_bar.cget("orient")), "vertical")
        close = labels["Schließen"]
        self.assertTrue(close.winfo_viewable())
        self.assertLessEqual(close.winfo_rooty() + close.winfo_height(), window.winfo_rooty() + window.winfo_height())
        window.destroy()

    def test_edit_imports_lists_folders_and_deletes_videos_or_the_folder(self):
        root = tempfile.mkdtemp()
        try:
            evening = os.path.join(root, "Abend")
            os.makedirs(evening)
            for name, data in (
                ("one.mp4", b"1234"),
                ("two.mkv", b"12345678"),
                ("still.jpg", b"ab"),
                ("Abend.pls", b"[]"),
            ):
                with open(os.path.join(evening, name), "wb") as handle:
                    handle.write(data)
            other = os.path.join(root, "Matinee")
            os.makedirs(other)
            with open(os.path.join(other, "clip.mov"), "wb") as handle:
                handle.write(b"xyz")
            playlist = os.path.join(other, "Matinee.pls")
            with open(playlist, "wb") as handle:
                handle.write(b"{}")
            self.app.root = self.root
            self.app.icon_image = None
            self.app.import_path = root
            self.app.playlist_library_window = None
            self.app.settings = {"last_playlist_path": playlist}
            self.app.playlist_path = playlist
            self.app.playlist = []
            self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
                f"{width}x{height}+20+20"
            )
            self.root.wait_window = lambda window: None
            self.app.show_playlist_library()
            window = self.app.playlist_library_window
            window.update()
            lines = list(window._listbox.get(0, "end"))
            self.assertEqual(len(lines), 2)
            self.assertIn("Abend", lines[0])
            self.assertIn("3 Medien", lines[0])
            self.assertIn("16 B", lines[0])
            self.assertIn("Matinee", lines[1])
            self.assertIn("1 Medium", lines[1])
            self.assertIn("Importpfad", window._path_label.cget("text"))
            self.assertIn(root, window._path_label.cget("text"))
            window._listbox.selection_clear(0, "end")
            window._listbox.selection_set(0)
            self.assertEqual(window._delete_media.cget("text"), "Mediendateien löschen")
            with patch("cinema_gui.messagebox.askyesno", return_value=True):
                self.app._delete_import_media(window)
            self.assertFalse(os.path.exists(os.path.join(evening, "one.mp4")))
            self.assertFalse(os.path.exists(os.path.join(evening, "two.mkv")))
            self.assertFalse(os.path.exists(os.path.join(evening, "still.jpg")))
            self.assertTrue(os.path.isfile(os.path.join(evening, "Abend.pls")))
            self.assertIn("0 Medien", window._listbox.get(0))
            window._listbox.selection_clear(0, "end")
            window._listbox.selection_set(1)
            with (
                patch("cinema_gui.messagebox.askyesno", return_value=True),
                patch("cinema_gui.save_settings") as saved,
            ):
                self.app._delete_import_folder(window)
            self.assertFalse(os.path.exists(other))
            self.assertTrue(os.path.isdir(evening))
            self.assertEqual(self.app.playlist_path, "")
            self.assertEqual(self.app.settings["last_playlist_path"], "")
            saved.assert_called_once()
            self.assertEqual(window._listbox.size(), 1)
            window.destroy()
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_context_copy_puts_the_file_in_the_playlist_folder(self):
        root = tempfile.mkdtemp()
        try:
            source = os.path.join(root, "clip.mp4")
            with open(source, "wb") as handle:
                handle.write(b"film-data")
            imports = os.path.join(root, "imports")
            os.makedirs(imports)
            self.app.root = self.root
            self.app.icon_image = None
            self.app.import_path = imports
            self.app.playlist_path = ""
            self.app.program_state = "OFF"
            self.app.program_index = 0
            self.app.preview_index = None
            self.app.preview_live = True
            self.app.playlist = [_entry(path=source)]
            self.app._current_playlist_name = lambda: "Abend.pls"
            self.app.refresh_all = lambda: None
            self.app.show_preview_clip = lambda _entry: None
            cinema_gui.VideoPlayerGUI.copy_entry_to_playlist_folder(self.app, 0)
            dest = os.path.join(imports, "Abend", "clip.mp4")
            self.assertTrue(os.path.isfile(dest))
            self.assertEqual(self.app.playlist[0].path, dest)
            self.assertEqual(self.app.playlist[0].filename, "clip.mp4")
            with open(dest, "rb") as handle:
                self.assertEqual(handle.read(), b"film-data")
            self.assertTrue(os.path.isfile(source))
            cinema_gui.VideoPlayerGUI.copy_entry_to_playlist_folder(self.app, 0)
            self.assertFalse(os.path.exists(os.path.join(imports, "Abend", "clip (2).mp4")))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_cancel_stops_the_playlist_folder_copy(self):
        root = tempfile.mkdtemp()
        try:
            source = os.path.join(root, "clip.mp4")
            with open(source, "wb") as handle:
                handle.write(b"film-data")
            imports = os.path.join(root, "imports")
            os.makedirs(imports)
            self.app.root = self.root
            self.app.icon_image = None
            self.app.import_path = imports
            self.app.playlist_path = ""
            self.app.program_state = "OFF"
            self.app.program_index = 0
            self.app.preview_index = None
            self.app.preview_live = True
            self.app.playlist = [_entry(path=source)]
            self.app._current_playlist_name = lambda: "Abend.pls"
            self.app.refresh_all = lambda: None
            self.app.show_preview_clip = lambda _entry: None
            real_update = cinema_gui.VideoPlayerGUI._update_copy_progress

            def update(progress, widgets, current, name, done, total):
                real_update(self.app, progress, widgets, current, name, done, total)
                widgets["cancel"]["cancel"] = True

            self.app._update_copy_progress = update
            cinema_gui.VideoPlayerGUI.copy_entry_to_playlist_folder(self.app, 0)
            self.assertEqual(self.app.playlist[0].path, source)
            self.assertFalse(os.path.exists(os.path.join(imports, "Abend", "clip.mp4")))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_playlist_library_lists_saved_playlists_and_save_creates_the_folder(self):
        root = tempfile.mkdtemp()
        try:
            evening = os.path.join(root, "Abend")
            os.makedirs(evening)
            with open(os.path.join(evening, "Abend.pls"), "w", encoding="utf-8") as handle:
                handle.write("{}")
            self.app.root = self.root
            self.app.icon_image = None
            self.app.import_path = root
            self.app.playlist_path = ""
            self.app.playlist_library_window = None
            self.app.settings = {}
            self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
                f"{width}x{height}+20+20"
            )
            held = {}
            self.root.wait_window = lambda window: held.setdefault("window", window)
            self.app.show_playlist_library()
            window = held["window"]
            window.update()
            created = datetime.fromtimestamp(folder_created(evening))
            line = window._listbox.get(0)
            self.assertTrue(line.startswith("Abend"))
            self.assertIn(created.strftime("%d.%m.%Y"), line)
            labels = {
                child.cget("text")
                for child in window.winfo_children()
                if isinstance(child, tk.Frame)
                for child in child.winfo_children()
                if isinstance(child, tk.Button)
            }
            for text in (
                "Öffnen", "Neue Playlist", "Importieren", "Exportieren",
                "Mediendateien löschen", "Verzeichnis löschen", "Schließen",
            ):
                self.assertIn(text, labels)
            window.destroy()
            def write_playlist(path):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("saved")

            self.app._current_playlist_name = lambda: "Matinee.pls"
            self.app._write_playlist = write_playlist
            self.app._set_playlist_name = lambda _name: None
            self.app.remember_playlist_dir = lambda _path: None
            self.assertTrue(self.app.save_playlist())
            saved = os.path.join(root, "Matinee", "Matinee.pls")
            self.assertEqual(self.app.playlist_path, saved)
            with open(saved, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "saved")
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_media_directories_pin_the_import_path(self):
        self.app.root = self.root
        self.app.icon_image = None
        self.app.media_dirs_window = None
        self.app.import_path = ""
        self.app.media_directories = [{"path": "/tmp", "name": "Filme"}]
        self.app.settings = {"media_directories": self.app.media_directories}
        self.app.refresh_playlist = lambda: None
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+20+20"
        )
        cinema_gui.VideoPlayerGUI.show_media_directories(self.app)
        window = self.app.media_dirs_window
        window.update()
        box = window._listbox
        self.assertTrue(box.get(0).startswith("Importpfad"))
        self.assertIn("nicht gesetzt", box.get(0))
        self.assertEqual(box.get(1), "Filme  —  /tmp")
        self.assertEqual(str(box.itemcget(0, "foreground")).lower(), cinema_gui.ACCENT.lower())
        self.assertEqual(str(box.itemcget(0, "selectbackground")).lower(), cinema_gui.ACCENT.lower())
        self.assertEqual(str(self.app._media_dir_name_entry.cget("state")), "disabled")
        labels = [
            child.cget("text")
            for child in window.winfo_children()
            if isinstance(child, tk.Frame)
            for child in child.winfo_children()
            if isinstance(child, tk.Button)
        ]
        self.assertIn("Importpfad festlegen", labels)
        cinema_gui.VideoPlayerGUI._remove_media_directory(self.app, box)
        self.assertEqual(self.app.media_directories, [{"path": "/tmp", "name": "Filme"}])
        box.selection_clear(0, "end")
        box.selection_set(1)
        box.event_generate("<<ListboxSelect>>")
        window.update()
        self.assertEqual(str(self.app._media_dir_name_entry.cget("state")), "normal")
        self.assertEqual(self.app._media_dir_name_var.get(), "Filme")
        with patch.object(cinema_gui, "save_settings"):
            cinema_gui.VideoPlayerGUI._remove_media_directory(self.app, box)
        self.assertEqual(self.app.media_directories, [])
        self.assertEqual(box.get(0).startswith("Importpfad"), True)
        self.assertEqual(box.size(), 1)
        window.destroy()

    def test_copy_from_a_drive_needs_an_import_path_and_a_playlist_name(self):
        self.app.root = self.root
        self.app.icon_image = None
        self.app.import_path = ""
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+20+20"
        )
        held = {}
        self.root.wait_window = lambda window: held.update(window=window)
        action = cinema_gui.VideoPlayerGUI._ask_link_or_copy(self.app)
        self.assertIsNone(action)
        window = held["window"]
        window.update()
        labels = {
            child.cget("text"): child
            for child in window.winfo_children()
            if isinstance(child, tk.Frame)
            for child in child.winfo_children()
            if isinstance(child, tk.Button)
        }
        warning = [
            child for child in window.winfo_children()
            if isinstance(child, tk.Frame)
            for child in child.winfo_children()
            if isinstance(child, tk.Label)
            and str(child.cget("fg")).lower() == cinema_gui.COLOR_WARNING.lower()
        ]
        self.assertTrue(warning)
        self.assertTrue(warning[0].winfo_viewable())
        labels["Kopieren"].invoke()
        window.update()
        self.assertTrue(window.winfo_exists())
        labels["Verlinken"].invoke()
        window.update()
        self.assertFalse(window.winfo_exists())

        del self.root.wait_window
        self.app.playlist_name = tk.Entry(self.root)
        self.app.playlist_name.insert(0, "unbekannt.pls")

        def answer_playlist_name():
            windows = [child for child in self.root.winfo_children() if isinstance(child, tk.Toplevel)]
            window = windows[-1]
            window.update()
            self.assertEqual(str(window.cget("bg")).lower(), cinema_gui.COLOR_BG.lower())
            entries = [
                child for frame in window.winfo_children() if isinstance(frame, tk.Frame)
                for child in frame.winfo_children() if isinstance(child, tk.Entry)
            ]
            entry = entries[0]
            self.assertEqual(str(entry.cget("bg")).lower(), cinema_gui.COLOR_FIELD.lower())
            self.assertEqual(str(entry.cget("fg")).lower(), cinema_gui.COLOR_TEXT.lower())
            buttons = {
                child.cget("text"): child
                for frame in window.winfo_children() if isinstance(frame, tk.Frame)
                for child in frame.winfo_children() if isinstance(child, tk.Button)
            }
            self.assertEqual(str(buttons["OK"].cget("bg")).lower(), cinema_gui.COLOR_BUTTON.lower())
            entry.insert(0, "unbekannt")
            buttons["OK"].invoke()
            window.update()
            self.assertTrue(window.winfo_exists())
            warning = [
                child for frame in window.winfo_children() if isinstance(frame, tk.Frame)
                for child in frame.winfo_children() if isinstance(child, tk.Label)
                and str(child.cget("fg")).lower() == cinema_gui.COLOR_WARNING.lower()
            ]
            self.assertTrue(warning[0].winfo_viewable())
            entry.delete(0, "end")
            entry.insert(0, "Abend")
            buttons["OK"].invoke()

        self.root.after(30, answer_playlist_name)
        stem = cinema_gui.VideoPlayerGUI._prompt_playlist_folder_name(self.app)
        self.assertEqual(stem, "Abend")
        self.assertEqual(self.app.playlist_name.get(), "Abend.pls")
        self.assertEqual(
            cinema_gui.VideoPlayerGUI._prompt_playlist_folder_name(self.app),
            "Abend",
        )

    def test_copied_drive_files_share_the_playlist_folder(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        stick = os.path.join(root, "stick")
        internal = os.path.join(root, "internal")
        dest = os.path.join(root, "import")
        os.makedirs(stick)
        os.makedirs(internal)
        os.makedirs(dest)
        stick_file = os.path.join(stick, "clip.mp4")
        internal_file = os.path.join(internal, "still.jpg")
        with open(stick_file, "wb") as handle:
            handle.write(b"video-bytes")
        with open(internal_file, "wb") as handle:
            handle.write(b"still-bytes")
        added = []
        written = {}

        def write_playlist(path):
            written["path"] = path
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{}")

        self.app.root = self.root
        self.app.icon_image = None
        self.app.import_path = dest
        self.app.add_media = lambda path: added.append(path)
        self.app.playlist = []
        self.app.preview_index = None
        self.app.refresh_all = lambda: None
        self.app._write_playlist = write_playlist
        self.app.playlist_path = ""
        self.app.playlist_name = tk.Entry(self.root)
        self.app.playlist_name.insert(0, "Abend.pls")
        self.app.remember_playlist_dir = lambda path: None
        self.app._open_copy_progress = lambda total: (None, None)
        self.app._close_copy_progress = lambda window: None
        self.app._update_copy_progress = lambda *args, **kwargs: None
        volumes = [{"path": stick, "name": "Stick"}]
        with patch.object(cinema_gui, "list_removable_volumes", return_value=volumes):
            cinema_gui.VideoPlayerGUI._add_imported_paths(
                self.app, [internal_file, stick_file], copy_stem="Abend",
            )
        copied = os.path.join(dest, "Abend", "clip.mp4")
        self.assertEqual(added, [internal_file, copied])
        with open(copied, "rb") as handle:
            self.assertEqual(handle.read(), b"video-bytes")
        self.assertFalse(os.path.exists(os.path.join(dest, "Abend", "still.jpg")))
        self.assertEqual(written["path"], os.path.join(dest, "Abend", "Abend.pls"))
        self.assertTrue(os.path.isfile(written["path"]))
        added.clear()
        with patch.object(cinema_gui, "list_removable_volumes", return_value=volumes):
            cinema_gui.VideoPlayerGUI._add_imported_paths(self.app, [stick_file], copy_stem="")
        self.assertEqual(added, [stick_file])
        before = dict(written)
        added.clear()
        with patch.object(cinema_gui, "list_removable_volumes", return_value=volumes):
            cinema_gui.VideoPlayerGUI._add_imported_paths(
                self.app, [internal_file], copy_stem="Abend",
            )
        self.assertEqual(added, [internal_file])
        self.assertEqual(written, before)
        self.assertFalse(os.path.exists(os.path.join(dest, "Abend", "still.jpg")))

    def test_cancel_stops_the_copy_and_keeps_finished_files(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        source = os.path.join(root, "source")
        dest = os.path.join(root, "dest")
        os.makedirs(source)
        os.makedirs(dest)
        names = ("one.mp4", "two.mp4", "three.mp4")
        paths = []
        for name in names:
            path = os.path.join(source, name)
            with open(path, "wb") as handle:
                handle.write(b"x" * (64 * 1024))
            paths.append(path)
        self.app.root = self.root
        self.app.icon_image = None
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+20+20"
        )
        window, widgets = cinema_gui.VideoPlayerGUI._open_copy_progress(self.app, 3)
        window.update()
        buttons = {
            child.cget("text"): child
            for child in window.winfo_children()
            if isinstance(child, tk.Frame)
            for child in child.winfo_children()
            if isinstance(child, tk.Button)
        }
        cancel = buttons["Abbrechen"]
        self.assertTrue(cancel.winfo_viewable())
        self.assertFalse(widgets["cancel"]["cancel"])
        cancel.invoke()
        self.assertTrue(widgets["cancel"]["cancel"])
        self.assertTrue(window.winfo_exists())
        cinema_gui.VideoPlayerGUI._close_copy_progress(self.app, window)

        real_update = cinema_gui.VideoPlayerGUI._update_copy_progress

        def update(progress, widgets, current, name, done, total):
            real_update(self.app, progress, widgets, current, name, done, total)
            if name == "two.mp4" and done:
                widgets["cancel"]["cancel"] = True

        self.app._update_copy_progress = update
        results = cinema_gui.VideoPlayerGUI._copy_imported_paths(self.app, paths, dest)
        self.assertEqual(
            results,
            [os.path.join(dest, "one.mp4"), None, None],
        )
        with open(results[0], "rb") as handle:
            self.assertEqual(handle.read(), b"x" * (64 * 1024))
        self.assertFalse(os.path.exists(os.path.join(dest, "two.mp4")))
        self.assertFalse(os.path.exists(os.path.join(dest, "three.mp4")))

    def test_refresh_icon_sits_before_the_playlist_name(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="x")
        parent.columnconfigure(0, weight=1)
        called = []
        self.app.root = self.root
        self.app.check_playlist_files = lambda: called.append("refresh")
        cinema_gui.VideoPlayerGUI._build_playlist_header(self.app, parent)
        self.root.update()
        icon = self.app.playlist_refresh
        name = self.app.playlist_name
        label = next(
            child for child in icon.master.winfo_children() if isinstance(child, tk.Label)
        )
        self.assertEqual(label.cget("text"), "Playlist")
        self.assertLess(icon.winfo_rootx() + icon.winfo_width(), label.winfo_rootx() + 2)
        self.assertLess(label.winfo_rootx(), name.winfo_rootx())
        self.assertLess(
            abs((icon.winfo_rooty() + icon.winfo_height() / 2) - (label.winfo_rooty() + label.winfo_height() / 2)),
            max(icon.winfo_height(), label.winfo_height()),
        )
        self.assertEqual(icon.tooltip.text, "Aktualisieren")
        self.assertNotEqual(icon.master, self.app.playlist_tool_buttons)
        icon.invoke()
        self.assertEqual(called, ["refresh"])

    def test_file_dialog_creates_a_folder_in_the_open_directory(self):
        cinema_gui.install_file_dialog_new_folder(self.root)
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        parent = str(self.root)
        window = ".__tk_choosedir" if parent == "." else f"{parent}.__tk_choosedir"
        self.root.tk.call(
            "::tk::dialog::file::chooseDir::Config",
            "__tk_choosedir",
            ["-parent", parent, "-initialdir", directory, "-title", "test"],
        )
        if self.root.tk.call("winfo", "exists", window):
            self.root.tk.call("destroy", window)
        self.root.tk.call("::tk::dialog::file::Create", window, "TkChooseDir")
        button = window + ".contents.f2.newfolder"
        self.assertIn("Verzeichnis", str(self.root.tk.call(button, "cget", "-text")))
        with patch.object(cinema_gui.simpledialog, "askstring", return_value="Abend"):
            self.root.tk.call(button, "invoke")
        self.root.update()
        created = os.path.join(directory, "Abend")
        self.assertTrue(os.path.isdir(created))
        current = str(self.root.tk.call("set", "::tk::dialog::file::__tk_choosedir(selectPath)"))
        self.assertEqual(os.path.realpath(current), os.path.realpath(created))
        with patch.object(cinema_gui.simpledialog, "askstring", return_value="a/b"), \
                patch.object(cinema_gui.messagebox, "showerror") as error:
            self.root.tk.call(button, "invoke")
        self.assertFalse(os.path.exists(os.path.join(directory, "a")))
        error.assert_called_once()
        self.root.tk.call("destroy", window)

    def test_program_menu_holds_idle_media_above_the_default(self):
        self.app.root = self.root
        self.app._close_menus = lambda: None
        self.app.idle_media_path = ""
        self.app.program_state = "OFF"
        self.app.use_default_idle_media = tk.BooleanVar(master=self.root, value=False)
        self.app.autoplay_delay = tk.StringVar(master=self.root, value="0")
        self.app.autosave_on_program_change = tk.BooleanVar(master=self.root, value=False)
        self.app.load_last_playlist_at_start = tk.BooleanVar(master=self.root, value=False)
        self.app.pad_16x9 = tk.BooleanVar(master=self.root, value=True)
        self.app.projection_zoom.set(False)
        program = cinema_gui.DropdownMenu(self.root, self.app)
        cinema_gui.VideoPlayerGUI._fill_program_menu(self.app, program)
        labels = [
            child.cget("text")
            for child in program.winfo_children()
            if isinstance(child, tk.Label)
        ]
        self.assertEqual(
            labels,
            [
                "Pausenmedium  >",
                "Standard-Pausenmedium verwenden",
                "Einstellungswarnung",
                "Lautstärke einstellen",
            ],
        )
        children = program.winfo_children()
        self.assertIsInstance(children[-2], tk.Frame)
        self.assertEqual(children[-1].cget("text"), "Lautstärke einstellen")
        playlist = cinema_gui.DropdownMenu(self.root, self.app)
        cinema_gui.VideoPlayerGUI._fill_playlist_menu(self.app, playlist)
        playlist_text = " ".join(
            child.cget("text")
            for child in playlist.winfo_children()
            if isinstance(child, tk.Label)
        )
        self.assertNotIn("Pausenmedium", playlist_text)
        self.assertNotIn("Einstellungswarnung", playlist_text)
        self.assertNotIn("Lautstärke einstellen", playlist_text)
        self.assertIn("4:3 auf 16:9 umrechnen", playlist_text)

    def test_pad_16x9_toggle_is_remembered(self):
        self.app.pad_16x9 = tk.BooleanVar(master=self.root, value=False)
        self.app.settings = {}
        self.app.program_state = "OFF"
        self.app.refresh_playlist = lambda: None
        self.app._apply_pad_16x9_to_players = lambda: None
        self.app.apply_beamer_mode_for_pointer = lambda: None
        self.app.refresh_beamer = lambda: None
        with patch.object(cinema_gui, "save_settings") as saved:
            cinema_gui.VideoPlayerGUI._on_pad_16x9(self.app)
        self.assertFalse(self.app.settings["pad_16x9"])
        saved.assert_called_once_with(self.app.settings)

    def test_audiosync_save_includes_beamer_hdmi_and_audio_output(self):
        class Manager:
            def __init__(self):
                self.video_output = "HDMI-A-1"
                self.audio_patch = {"beamer": "", "preview": ""}

            def audio_patch_is_off(self, role):
                return self.audio_patch.get(role) == cinema_gui.AUDIO_PATCH_NONE

            def program_audio_device(self, _mpv_path):
                return "pipewire/alsa_output.hdmi-stereo"

            def set_audio_patch(self, patch):
                self.audio_patch = {
                    "beamer": patch.get("beamer", ""),
                    "preview": patch.get("preview", ""),
                }

        self.app.audiosync_delays = {"1920x1080@24p": -5}
        self.app.output_manager = Manager()
        self.app.mpv_path = "/usr/bin/mpv"
        self.app.settings = {}
        self.app.program_state = "OFF"
        applied = {}
        self.app._apply_main_audio_device = lambda: applied.setdefault("audio", True)
        self.app.apply_beamer_output = lambda output: applied.setdefault("video", output)
        payload = cinema_gui.VideoPlayerGUI._audiosync_payload(self.app)
        self.assertEqual(payload["delays"], {"1920x1080@24p": -5})
        self.assertEqual(payload["beamer_hdmi"], "HDMI-A-1")
        self.assertEqual(payload["audio_output"], "pipewire/alsa_output.hdmi-stereo")
        with patch.object(cinema_gui, "save_settings"):
            cinema_gui.VideoPlayerGUI._apply_audiosync_outputs(self.app, payload)
        self.assertEqual(self.app.output_manager.audio_patch["beamer"], "pipewire/alsa_output.hdmi-stereo")
        self.assertEqual(self.app.settings["audio_patch"]["beamer"], "pipewire/alsa_output.hdmi-stereo")
        self.assertTrue(applied["audio"])
        self.app.output_manager.video_output = "DP-1"
        with patch.object(cinema_gui, "save_settings"):
            cinema_gui.VideoPlayerGUI._apply_audiosync_outputs(self.app, payload)
        self.assertEqual(applied["video"], "HDMI-A-1")

    def test_tooltips_stay_inside_the_control_monitor(self):
        self.root.geometry("500x320+80+80")
        button = tk.Label(self.root, text="Einstellung")
        button.place(x=440, y=260, width=40, height=30)
        self.root.update()

        def inside(window, origin_x, origin_y, width, height):
            self.root.update()
            right = window.winfo_rootx() + window.winfo_width()
            bottom = window.winfo_rooty() + window.winfo_height()
            self.assertGreaterEqual(window.winfo_rootx(), origin_x)
            self.assertGreaterEqual(window.winfo_rooty(), origin_y)
            self.assertLessEqual(right, origin_x + width)
            self.assertLessEqual(bottom, origin_y + height)

        left = button.winfo_rootx() + button.winfo_width() - 160
        top = button.winfo_rooty() + button.winfo_height() - 100
        self.root.tooltip_screen_bounds = lambda: (160, 100, left, top)
        tip = cinema_gui.IconTooltip(button, "Einstellungen")
        tip._show()
        inside(tip._window, left, top, 160, 100)
        self.assertLess(tip._window.winfo_rooty() + tip._window.winfo_height(), button.winfo_rooty())
        self.assertLess(tip._window.winfo_rootx(), button.winfo_rootx())
        tip._hide()

        long_tip = cinema_gui.IconTooltip(
            button, "Einstellungen und Beamerausgabe bleiben auf diesem Monitor",
        )
        long_tip._show()
        inside(long_tip._window, left, top, 160, 100)
        long_tip._hide()

        corner = tk.Label(self.root, text="x")
        corner.place(x=0, y=0, width=20, height=20)
        self.root.update()
        cleft = corner.winfo_rootx() + 30
        ctop = corner.winfo_rooty()
        self.root.tooltip_screen_bounds = lambda: (120, 70, cleft, ctop)
        corner_tip = cinema_gui.IconTooltip(corner, "Kurz")
        corner_tip._show()
        inside(corner_tip._window, cleft, ctop, 120, 70)
        corner_tip._hide()

    def test_about_sits_above_fullscreen_and_lists_the_stack(self):
        self.app.root = self.root
        self.app.icon_image = None
        self.app.mpv_path = "/usr/bin/mpv"
        self.app.theme = "dark"
        self.app.language = "de"
        self.app.program_state = "OFF"
        self.app.calibration_mode = None
        self.app.window_fullscreen = tk.BooleanVar(master=self.root, value=False)
        self.app._menu = lambda _parent: cinema_gui.DropdownMenu(self.root, self.app)
        self.app._menu_check_fg = lambda: "#ffffff"
        self.app._fill_program_menu = lambda menu: None
        self.app._fill_playlist_menu = lambda menu: None
        self.app._fill_beamer_output_menu = lambda menu: None
        self.app._fill_calibration_kind_menu = lambda menu, kind: None
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+30+30"
        )
        menu = cinema_gui.DropdownMenu(self.root, self.app)
        cinema_gui.VideoPlayerGUI._fill_app_menu(self.app, menu)
        labels = [
            child.cget("text")
            for child in menu.winfo_children()
            if isinstance(child, tk.Label)
        ]
        self.assertEqual(labels[0], "Über Cinema-Player")
        self.assertIn("Vollbildmodus", labels[1])
        with patch.object(cinema_gui, "read_mpv_version", return_value="0.41.0"), \
                patch.object(cinema_gui, "about_package_rows", return_value=[
                    ("Python", "3.12.13"),
                    ("Tcl/Tk", "Tk 8.6.16, Tcl 8.6.16"),
                    ("mpv", "0.41.0"),
                    ("FFmpeg", "8.0.1"),
                    ("gdctl", None),
                ]):
            cinema_gui.VideoPlayerGUI.show_about(self.app)
        window = self.app.about_window
        window.update()
        texts = []

        def walk(widget):
            if isinstance(widget, tk.Label):
                texts.append(widget.cget("text"))
            for child in widget.winfo_children():
                walk(child)

        walk(window)
        self.assertTrue(any(text.startswith("v") and "mpv 0.41.0" in text for text in texts))
        self.assertIn("Copyright (C) 2026 Thomas Winkler", texts)
        self.assertIn("thomas.winkler@iggmp.net", texts)
        self.assertIn("http://cinema-player.github.io", texts)
        self.assertIn("FFmpeg", texts)
        self.assertIn("8.0.1", texts)
        self.assertIn("nicht gefunden", texts)
        self.assertIsNotNone(self.app.about_logo)
        canvas = window._popup_canvas
        label = window._about_logo_label
        self.assertLessEqual(label.winfo_reqwidth(), canvas.winfo_width())
        self.assertLessEqual(self.app.about_logo.width(), canvas.winfo_width())
        window.destroy()


class BeamerSummaryTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.beamer_details_open = False
        parent = tk.Frame(self.root)
        parent.pack(fill="both", expand=True)
        cinema_gui.VideoPlayerGUI._build_beamer(self.app, parent)

    def tearDown(self):
        self.root.destroy()
        set_language("en")

    def test_legend_lives_in_the_details(self):
        self.root.update_idletasks()
        self.assertEqual(self.app.beamer_details.winfo_manager(), "")
        self.assertEqual(self.app.beamer_legend.master, self.app.beamer_details)
        self.assertIn("Programm", self.app.beamer_legend.winfo_children()[1].cget("text"))

    def test_dropped_frames_show_in_the_short_form(self):
        class Player:
            process = object()
            loaded_path = "/clip.mp4"

        self.app.program_state = "PLAYING"
        self.app.main_mpv = Player()
        self.app.idle_showing = False
        self.app.blackout = False
        self.app.hdmi_audio_keepalive = False
        self.app.beamer_test_active = False
        self.app.program_hwdec = ""
        self.app.program_frame_drops = 2
        self.app.program_decoder_drops = 1
        cinema_gui.VideoPlayerGUI._refresh_beamer_decode(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.beamer_drop_summary.cget("text"), "Drops 2 / 1")
        self.assertEqual(self.app.beamer_drop_summary.winfo_manager(), "pack")
        self.assertEqual(self.app.beamer_drop_summary.master, self.app.beamer_summary)
        self.app.program_hwdec = "nvdec-copy"
        cinema_gui.VideoPlayerGUI._refresh_beamer_decode(self.app)
        self.assertEqual(self.app.beamer_hwdec.cget("text"), "nvdec-copy")
        self.assertEqual(self.app.beamer_hwdec.master.master, self.app.beamer_details)
        self.assertFalse(self.app.beamer_hwdec.winfo_ismapped())

    def test_program_light_block_hides_when_control_is_off(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="x")
        self.app.lights_control = tk.BooleanVar(master=self.root, value=True)
        self.app.lights_scenes = [cinema_gui.dmx.Scene("dark", "Dunkel", {})]
        self.app.lights_current = ""
        self.app.lights_fading = False
        self.app.light_start_var = tk.StringVar(master=self.root, value="")
        self.app.idle_media_path = ""
        self.app.projection_zoom = tk.BooleanVar(master=self.root, value=False)
        cinema_gui.VideoPlayerGUI._build_show_strip(self.app, parent)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "pack")
        self.assertEqual(self.app.program_light_bar.cget("bg"), "#241c14")
        self.assertFalse(hasattr(self.app, "program_light_caption"))
        tracks = tk.Frame(self.root, bg=cinema_gui.COLOR_PANEL)
        tracks.pack()
        cinema_gui.VideoPlayerGUI._build_light_dimmer(self.app, tracks)
        self.assertEqual(self.app.light_start_combo.cget("style"), "BoothLight.TCombobox")
        popup = self.app.light_start_combo.tk.call(
            "ttk::combobox::PopdownWindow", str(self.app.light_start_combo),
        )
        self.assertEqual(
            self.app.light_start_combo.tk.call(f"{popup}.f.l", "cget", "-background"),
            cinema_gui.LIGHT_PANEL,
        )
        scene = self.app.program_light_buttons["dark"]
        self.assertEqual(scene.cget("bg"), "#3a2a18")
        self.assertEqual(scene.cget("fg"), "#f3e2c4")
        self.app.lights_current = "dark"
        cinema_gui.VideoPlayerGUI._refresh_light_buttons(self.app)
        self.assertEqual(scene.cget("bg"), "#c9a227")
        self.assertEqual(scene.cget("fg"), "#1a1408")
        self.app.lights_current = ""
        cinema_gui.VideoPlayerGUI._refresh_light_buttons(self.app)
        self.assertEqual(self.app.program_light_dimmer.winfo_manager(), "pack")
        self.assertEqual(self.app.show_strip.winfo_manager(), "grid")
        self.app.lights_control.set(False)
        cinema_gui.VideoPlayerGUI._apply_program_light_block(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "")
        self.assertEqual(self.app.program_light_dimmer.winfo_manager(), "")
        self.assertEqual(self.app.show_strip.winfo_manager(), "")
        self.app.idle_media_path = "/media/idle.mp4"
        self.app.idle_showing = False
        cinema_gui.VideoPlayerGUI._refresh_idle_status(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.show_strip.winfo_manager(), "")
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "")
        self.app.lights_control.set(True)
        cinema_gui.VideoPlayerGUI._apply_program_light_block(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "pack")
        self.assertEqual(self.app.program_light_dimmer.winfo_manager(), "pack")

    def test_still_keeps_the_light_dimmer(self):
        column = tk.Frame(self.root, bg=cinema_gui.COLOR_PANEL)
        column.pack(fill="x")
        self.app.preview_column = column
        controls = tk.Frame(column, bg=cinema_gui.COLOR_PANEL)
        controls.grid(row=0, column=0, sticky="ew")
        self.app.preview_controls = controls
        footer = tk.Frame(column, bg=cinema_gui.COLOR_PANEL)
        footer.grid(row=1, column=0, sticky="ew")
        clip = tk.Frame(footer, bg=cinema_gui.COLOR_PANEL)
        clip.pack(side="left")
        self.app.preview_clip_settings = clip
        safety = tk.Frame(footer, bg=cinema_gui.COLOR_PANEL)
        safety.pack(side="left")
        self.app.preview_safety = safety
        played = tk.Frame(safety, bg=cinema_gui.COLOR_PANEL)
        played.pack(side="left")
        self.app.preview_played_box = played
        image_settings = tk.Frame(footer, bg=cinema_gui.COLOR_PANEL)
        self.app.preview_image_settings = image_settings
        tracks = tk.Frame(controls, bg=cinema_gui.COLOR_PANEL)
        tracks.pack(side="left")
        self.app.preview_track_settings = tracks
        self.app.lights_control = tk.BooleanVar(master=self.root, value=True)
        self.app.lights_scenes = [cinema_gui.dmx.Scene("dark", "Dunkel", {})]
        self.app.light_start_var = tk.StringVar(master=self.root, value="")
        self.app.still_dim = tk.BooleanVar(master=self.root, value=True)
        self.app.still_dim_seconds = tk.StringVar(master=self.root, value="1")
        self.app.settings = {}
        cinema_gui.VideoPlayerGUI._build_still_dim(self.app, image_settings)
        cinema_gui.VideoPlayerGUI._build_light_dimmer(self.app, tracks)
        still = _entry(path="/media/films/still.png", is_image=True, display_time=10)
        film = _entry(is_image=False)

        cinema_gui.VideoPlayerGUI.apply_preview_layout(self.app, still)
        self.root.update()
        self.assertIs(self.app.program_light_dimmer.pack_info()["in"], image_settings)
        self.assertIn("Dimmen", self.app.still_dim_check.cget("text"))
        self.assertEqual(self.app.still_dim_label.cget("text"), "Dimmzeit:")
        self.assertIs(self.app.still_dim_seconds_entry.master, image_settings)
        self.assertTrue(self.app.program_light_dimmer.winfo_ismapped())
        self.assertTrue(image_settings.winfo_ismapped())
        self.assertFalse(controls.winfo_ismapped())

        cinema_gui.VideoPlayerGUI.apply_preview_layout(self.app, film)
        self.root.update()
        self.assertIs(self.app.program_light_dimmer.pack_info()["in"], tracks)
        self.assertTrue(self.app.program_light_dimmer.winfo_ismapped())
        self.assertTrue(controls.winfo_ismapped())
        self.assertFalse(image_settings.winfo_ismapped())

    def test_program_meters_show_channel_numbers_and_follow_the_fade(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="x")
        self.app.lights_control = tk.BooleanVar(master=self.root, value=True)
        self.app.dmx_output = cinema_gui.dmx.DmxOutput(channels=[1, 2])
        self.app.lights_scenes = [
            cinema_gui.dmx.Scene("dark", "", {1: 0, 2: 0}),
            cinema_gui.dmx.Scene("bright", "", {1: 100, 2: 40}),
        ]
        self.app.lights_current = "dark"
        self.app.lights_fading = False
        self.app.lights_shown_levels = {1: 0, 2: 0}
        self.app._light_meter_fade = None
        self.app.light_start_var = tk.StringVar(master=self.root, value="")
        self.app.idle_media_path = ""
        self.app.projection_zoom = tk.BooleanVar(master=self.root, value=False)
        cinema_gui.VideoPlayerGUI._build_show_strip(self.app, parent)
        self.root.update_idletasks()
        labels = [
            child.cget("text")
            for child in self.app.program_light_meters.winfo_children()
            for child in child.winfo_children()
            if isinstance(child, tk.Label)
        ]
        self.assertEqual(labels, ["1", "2"])
        self.root.update_idletasks()
        self.assertGreater(
            self.app.program_light_meters.winfo_rootx(),
            self.app.program_light_scenes.winfo_rootx(),
        )
        self.assertLess(
            abs(self.app.program_light_meters.winfo_rooty() - self.app.program_light_scenes.winfo_rooty()),
            self.app.program_light_scenes.winfo_height(),
        )
        self.assertFalse(any("%" in text or text.isdigit() and len(text) > 3 for text in labels))
        self.app.lights_fading = True
        self.app._light_meter_fade = {
            "start": {1: 0.0, 2: 0.0},
            "target": {1: 100.0, 2: 100.0},
            "started": cinema_gui.time.monotonic() - 0.5,
            "ms": 1000,
        }
        for canvas in self.app.program_light_meter_bars.values():
            canvas._meter_percent = None
        cinema_gui.VideoPlayerGUI._paint_light_meters(self.app)
        bar = self.app.program_light_meter_bars[1]
        height = int(bar.cget("height"))
        gold = [
            bar.coords(item)
            for item in bar.find_all()
            if bar.itemcget(item, "fill") == cinema_gui.LIGHT_ACTIVE
        ]
        self.assertEqual(len(gold), 1)
        span = gold[0][3] - gold[0][1]
        self.assertAlmostEqual(span, cinema_gui.light_meter_fill(height, 50), delta=2)

    def test_scene_editor_uses_faders_with_percent_above(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="both", expand=True)
        self.app.lights_scenes = [
            cinema_gui.dmx.Scene("dark", "", {1: 0, 2: 40}),
        ]
        self.app.lights_channels = tk.StringVar(master=self.root, value="1, 2")
        self.app._scene_guard = False
        cinema_gui.VideoPlayerGUI._build_scene_editor(self.app, parent)
        self.root.update_idletasks()
        frame = self.app._scene_levels_frame

        def _walk(widget):
            yield widget
            for child in widget.winfo_children():
                yield from _walk(child)

        desk = next(
            widget for widget in _walk(frame)
            if widget.winfo_children()
            and all(
                any(isinstance(item, tk.Scale) for item in column.winfo_children())
                for column in widget.winfo_children()
            )
        )
        columns = list(desk.winfo_children())
        self.assertEqual(len(columns), 2)
        percent, scale, number = columns[1].winfo_children()
        self.assertIsInstance(scale, tk.Scale)
        self.assertEqual(scale.cget("orient"), "vertical")
        self.assertEqual(percent.cget("text"), "40 %")
        self.assertEqual(number.cget("text"), "2")
        self.assertLess(
            columns[1].pack_slaves().index(percent),
            columns[1].pack_slaves().index(scale),
        )
        scale.set(75)
        self.app._scene_fade_var.set("1.5")
        cinema_gui.VideoPlayerGUI._flush_scene_form(self.app)
        self.assertEqual(self.app._scene_draft[0].levels[2], 75)
        self.assertEqual(self.app._scene_draft[0].fade_ms, 1500)
        self.app.lights_transition_ms = 2500
        cinema_gui.VideoPlayerGUI._add_edited_scene(self.app)
        added = self.app._scene_draft[-1]
        self.assertEqual(added.fade_ms, 2500)
        cinema_gui.VideoPlayerGUI._add_edited_sequence(self.app)
        sequence = self.app._sequence_draft[-1]
        labels = [
            self.app._scene_listbox.get(index)
            for index in range(self.app._scene_listbox.size())
        ]
        self.assertIn(f"{sequence.name} · Sequenz", labels)
        self.app.lights_scenes = list(self.app._scene_draft)
        self.app.lights_sequences = list(self.app._sequence_draft)
        choices = [label for _cue, label in cinema_gui.VideoPlayerGUI._scene_choices(self.app)]
        self.assertIn(f"{sequence.name} · Sequenz", choices)
        self.assertIn("Dunkel", choices)

    def test_fader_row_scrolls_sideways_when_the_channels_do_not_fit(self):
        self.root.geometry("900x640+40+40")
        parent = tk.Frame(self.root)
        parent.pack(fill="both", expand=True)
        self.app.lights_scenes = [cinema_gui.dmx.Scene("dark", "", {channel: 0 for channel in range(1, 13)})]
        self.app.lights_channels = tk.StringVar(master=self.root, value="1-12")
        self.app.lights_sequences = []
        self.app.lights_transition_ms = 2500
        self.app._scene_guard = False
        cinema_gui.VideoPlayerGUI._build_scene_editor(self.app, parent)
        self.root.update()
        self.assertEqual(self.app._fader_scroll.winfo_manager(), "pack")
        self.assertEqual(str(self.app._fader_scroll.cget("orient")), "horizontal")

    def test_light_actions_stay_inside_the_settings_window(self):
        self.app.root = self.root
        self.app.icon_image = None
        self.app.lights_control = tk.BooleanVar(master=self.root, value=False)
        self.app.dmx_output = cinema_gui.dmx.DmxOutput(mode="artnet", host="127.0.0.1", channels=[1])
        self.app.lights_scenes = [
            cinema_gui.dmx.Scene("dark", "", {1: 0}),
            cinema_gui.dmx.Scene("bright", "", {1: 100}),
        ]
        self.app.lights_sequences = []
        self.app.lights_transition_ms = 2500
        self.app.lights_start_lead_ms = 0
        self.app.lights_end_lead_ms = 0
        self.app.lights_current = ""
        self.app.lights_fading = False
        self.app.lights_fade_after = None
        self.app.lights_blink_after = None
        self.app.lights_meter_after = None
        self.app.lights_blink_on = False
        self.app._light_meter_fade = None
        self.app._sequence_run = None
        self.app.program_light_buttons = {}
        self.app.settings_light_buttons = {}
        self.app.settings = {}
        self.app._dmx_ready = lambda: False
        self.app._refresh_header_indicators = lambda: None
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+30+30"
        )
        self.app._save_lights_settings = lambda: None
        cinema_gui.VideoPlayerGUI.show_lights(self.app)
        window = self.app.lights_window
        window.update_idletasks()
        bottom = window.winfo_rooty() + window.winfo_height()
        labels = {
            child.cget("text"): child
            for child in window.winfo_children()
            if isinstance(child, tk.Frame)
            for child in child.winfo_children()
            if isinstance(child, tk.Button)
        }
        for text in ("Übernehmen", "Schließen"):
            button = labels[text]
            self.assertTrue(button.winfo_viewable())
            self.assertGreaterEqual(button.winfo_rooty(), window.winfo_rooty())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), bottom)
        window.destroy()

    def test_light_settings_scroll_vertically_when_the_form_does_not_fit(self):
        self.app.root = self.root
        self.app.icon_image = None
        self.app.lights_control = tk.BooleanVar(master=self.root, value=False)
        self.app.dmx_output = cinema_gui.dmx.DmxOutput(mode="artnet", host="127.0.0.1", channels=[1])
        self.app.lights_scenes = [
            cinema_gui.dmx.Scene("dark", "", {1: 0}),
            cinema_gui.dmx.Scene("bright", "", {1: 100}),
        ]
        self.app.lights_sequences = []
        self.app.lights_transition_ms = 2500
        self.app.lights_start_lead_ms = 0
        self.app.lights_end_lead_ms = 0
        self.app.lights_current = ""
        self.app.lights_fading = False
        self.app.lights_fade_after = None
        self.app.lights_blink_after = None
        self.app.lights_meter_after = None
        self.app.lights_blink_on = False
        self.app._light_meter_fade = None
        self.app._sequence_run = None
        self.app.program_light_buttons = {}
        self.app.settings_light_buttons = {}
        self.app.settings = {}
        self.app._dmx_ready = lambda: False
        self.app._refresh_header_indicators = lambda: None
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+30+30"
        )
        self.app._save_lights_settings = lambda: None
        cinema_gui.VideoPlayerGUI.show_lights(self.app)
        window = self.app.lights_window
        window.geometry("820x420+30+30")
        window.update()
        bar = self.app._lights_vscroll
        self.assertEqual(bar.winfo_manager(), "grid")
        self.assertEqual(str(bar.cget("orient")), "vertical")
        canvas = self.app._lights_body
        canvas.yview_moveto(1)
        window.update()
        button = self.app.settings_light_buttons["dark"]
        top = canvas.winfo_rooty()
        bottom = top + canvas.winfo_height()
        self.assertGreaterEqual(button.winfo_rooty() + button.winfo_height(), top)
        self.assertLessEqual(button.winfo_rooty(), bottom)
        window.geometry("820x1200+30+30")
        window.update()
        self.assertEqual(bar.winfo_manager(), "")
        window.destroy()

    def _open_lights_window(self, ready):
        self.app.root = self.root
        self.app.icon_image = None
        self.app.lights_control = tk.BooleanVar(master=self.root, value=False)
        self.app.dmx_output = cinema_gui.dmx.DmxOutput(mode="artnet", host="127.0.0.1", channels=[1])
        self.app.lights_scenes = [cinema_gui.dmx.Scene("dark", "", {1: 0})]
        self.app.lights_sequences = []
        self.app.lights_transition_ms = 0
        self.app.lights_start_lead_ms = 0
        self.app.lights_end_lead_ms = 0
        self.app.lights_current = ""
        self.app.lights_fading = False
        self.app.lights_fade_after = None
        self.app.lights_blink_after = None
        self.app.lights_meter_after = None
        self.app.lights_blink_on = False
        self.app._light_meter_fade = None
        self.app._sequence_run = None
        self.app.program_light_buttons = {}
        self.app.settings_light_buttons = {}
        self.app.settings = {}
        self.app._dmx_ready = lambda: ready["value"]
        self.app._save_lights_settings = lambda: None
        self.app._place_on_control_monitor = lambda window, width, height: window.geometry(
            f"{width}x{height}+30+30"
        )
        cinema_gui.VideoPlayerGUI.show_lights(self.app)
        self.app.lights_window.update()

    def test_light_and_remote_windows_switch_with_the_header_icons(self):
        ready = {"value": False}
        self._open_lights_window(ready)
        window = self.app.lights_window
        icon = self.app.lights_window_indicator
        reference = tk.Canvas(self.root, width=36, height=36)
        cinema_gui.VideoPlayerGUI._paint_lights_indicator(self.app, reference, "#c9a227", lit=True)
        cinema_gui.VideoPlayerGUI._paint_lights_indicator(self.app, icon, "#c9a227", lit=True)

        def shapes(canvas):
            return [(canvas.type(item), canvas.coords(item)) for item in canvas.find_all()]

        self.assertEqual(shapes(icon), shapes(reference))
        self.assertLess(icon.winfo_rooty(), self.app._lights_body.winfo_rooty())
        self.assertGreater(icon.winfo_rootx(), window.winfo_rootx() + window.winfo_width() / 2)
        icon.event_generate("<Button-1>")
        window.update()
        self.assertFalse(self.app.lights_control.get())
        ready["value"] = True
        icon.event_generate("<Button-1>")
        window.update()
        self.assertTrue(self.app.lights_control.get())
        window.destroy()

        class Api:
            running = False
            error = ""
            port = 8765
            token = "secret"

            def connect_urls(self, _lang):
                return ["http://127.0.0.1/"]

            def start(self, port, token):
                self.running = True
                self.port = port
                self.token = token
                return True

            def stop(self):
                self.running = False

        self.app.remote_api = Api()
        self.app.remote_api_enabled = tk.BooleanVar(master=self.root, value=False)
        self.app.remote_api_port = tk.StringVar(master=self.root, value="8765")
        self.app.remote_api_token = tk.StringVar(master=self.root, value="secret")
        self.app.remote_window = None
        self.app.remote_window_indicator = None
        with patch.object(cinema_gui, "save_settings"):
            cinema_gui.VideoPlayerGUI.show_remote_control(self.app)
            remote = self.app.remote_window
            radio = self.app.remote_window_indicator
            remote.update()
            other = tk.Canvas(self.root, width=36, height=36)
            cinema_gui.VideoPlayerGUI._paint_remote_indicator(self.app, other, "#4477aa")
            cinema_gui.VideoPlayerGUI._paint_remote_indicator(self.app, radio, "#4477aa")
            self.assertEqual(shapes(radio), shapes(other))
            self.assertLess(radio.winfo_rooty(), self.app.remote_qr_canvas.winfo_rooty())
            self.assertGreater(radio.winfo_rootx(), remote.winfo_rootx() + remote.winfo_width() / 2)
            radio.event_generate("<Button-1>")
            remote.update()
        self.assertTrue(self.app.remote_api_enabled.get())
        self.assertTrue(self.app.remote_api.running)
        remote.destroy()


class ProgramEndTests(unittest.TestCase):
    def test_keepalive_clock_is_not_the_end_of_the_movie(self):
        self.assertFalse(cinema_gui.program_end_signal_is_real(None, 600, None))
        self.assertFalse(cinema_gui.program_end_signal_is_real(0.0, 600, None))
        self.assertFalse(cinema_gui.program_end_signal_is_real(0.9, 600, None))
        self.assertFalse(cinema_gui.program_end_signal_is_real(1.0, 90, 40))

    def test_playhead_at_the_real_end_counts(self):
        self.assertTrue(cinema_gui.program_end_signal_is_real(599.4, 600, None))
        self.assertTrue(cinema_gui.program_end_signal_is_real(39.5, 120, 40))
        self.assertFalse(cinema_gui.program_end_signal_is_real(10, 120, 40))

    def test_zero_out_point_does_not_stop_on_the_first_frame(self):
        entry = _entry(duration=30, out_point=0)
        self.assertIsNone(cinema_gui.playback_out_point(entry))
        self.assertEqual(cinema_gui.playback_out_point(_entry(duration=30, out_point=12)), 12)

    def _armed(self, entry, *, keepalive=False):
        class Player:
            def is_audio_keepalive(self):
                return keepalive

            def has_file(self, path):
                return path == entry.path

        class Root:
            def after(self, _delay, fn):
                fn()

        app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        app.program_state = "PLAYING"
        app.playlist = [entry]
        app.program_index = 0
        app.main_mpv = Player()
        app.idle_showing = False
        app.hdmi_audio_keepalive = keepalive
        app.beamer_test_active = False
        app.still_waiting = False
        app.still_started = None
        app.lights_play_after = None
        app.duration = entry.duration
        app.position = 0.0
        app._program_load_id = 1
        app._program_loaded_id = 0
        app._program_playhead = None
        app.finished = 0
        app.root = Root()
        app.on_clip_finished = lambda: setattr(app, "finished", app.finished + 1)
        return app

    def test_eof_at_the_start_does_not_finish_the_clip(self):
        entry = _entry(duration=600, out_point=None)
        app = self._armed(entry)
        app.main_mpv_event(app.main_mpv, {"event": "property-change", "name": "eof-reached", "data": True})
        app.main_mpv_event(app.main_mpv, {"event": "end-file", "reason": "eof"})
        app.main_mpv_event(app.main_mpv, {"event": "property-change", "name": "time-pos", "data": 0.95})
        self.assertEqual(app.finished, 0)
        self.assertEqual(app.position, 0.0)

    def test_eof_at_the_real_end_finishes_the_clip(self):
        entry = _entry(duration=600, out_point=None)
        app = self._armed(entry)
        app._program_loaded_id = 1
        app._program_playhead = 599.5
        app.main_mpv_event(app.main_mpv, {"event": "property-change", "name": "eof-reached", "data": True})
        self.assertEqual(app.finished, 1)

    def test_keepalive_eof_does_not_finish_even_near_its_own_end(self):
        entry = _entry(duration=1.0, out_point=None)
        app = self._armed(entry, keepalive=True)
        app._program_loaded_id = 1
        app._program_playhead = 0.99
        app.main_mpv_event(app.main_mpv, {"event": "property-change", "name": "eof-reached", "data": True})
        self.assertEqual(app.finished, 0)

    def test_out_point_waits_until_the_new_file_is_loaded(self):
        entry = _entry(duration=120, out_point=5)
        app = self._armed(entry)
        app.main_mpv_event(app.main_mpv, {"event": "property-change", "name": "time-pos", "data": 4.99})
        self.assertEqual(app.finished, 0)
        app._program_loaded_id = 1
        app.main_mpv_event(app.main_mpv, {"event": "property-change", "name": "time-pos", "data": 4.99})
        self.assertEqual(app.finished, 1)


class ProgramClockTests(unittest.TestCase):
    def test_fade_wait_ignores_the_projector_clock(self):
        self.assertFalse(cinema_gui.program_clock_drives_playhead(True, True, False, False))
        self.assertFalse(cinema_gui.program_clock_drives_playhead(True, True, False, True))

    def test_previous_file_does_not_move_the_armed_clip(self):
        self.assertFalse(cinema_gui.program_clock_drives_playhead(False, True, False, False))

    def test_loaded_program_and_idle_follow_the_clock(self):
        self.assertTrue(cinema_gui.program_clock_drives_playhead(False, True, False, True))
        self.assertTrue(cinema_gui.program_clock_drives_playhead(False, False, True, False))


class ProgressBarLayoutTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.geometry("900x160+20+20")
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)

    def tearDown(self):
        self.root.destroy()

    def test_missing_bitrate_keeps_the_bar_width(self):
        frame = tk.Frame(self.root)
        frame.pack(fill="x")
        frame.columnconfigure(0, weight=1)
        bar = cinema_gui.RangeProgressBar(frame, on_seek=lambda *_args: None, height=32)
        bar.grid(row=0, column=0, sticky="ew")
        video = cinema_gui.VideoPlayerGUI._bitrate_readout(self.app, frame, "video_bitrate")
        video.grid(row=0, column=1, sticky="e", padx=(8, 8))
        audio = cinema_gui.VideoPlayerGUI._bitrate_readout(self.app, frame, "audio_bitrate")
        audio.grid(row=1, column=1, sticky="e", padx=(8, 8))
        cinema_gui.VideoPlayerGUI._pin_bitrate_column(frame, video)
        bar.set_state(duration=100, position=40)
        self.root.update()
        width = bar.winfo_width()
        playhead = bar._x_for_time(40)
        self.assertGreater(width, 1)
        for text in ("--", "", "25 Mbps", "--"):
            cinema_gui.VideoPlayerGUI._apply_bitrate_text(self.app, video, text)
            cinema_gui.VideoPlayerGUI._apply_bitrate_text(self.app, audio, text)
            self.root.update()
            self.assertEqual(video.winfo_manager(), "grid")
            self.assertEqual(audio.winfo_manager(), "grid")
            self.assertEqual(bar.winfo_width(), width)
            self.assertEqual(bar._x_for_time(40), playhead)


class HeaderClockTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.root.geometry("1100x120+20+20")
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.root = self.root
        self.app.mpv_path = ""
        self.app.lights_control = None
        self.app.remote_api = None

    def tearDown(self):
        cinema_gui.VideoPlayerGUI._cancel_header_clock(self.app)
        self.root.destroy()
        set_language("en")

    def test_clock_is_not_a_scaled_bitmap(self):
        cinema_gui.sync_fonts()
        with patch.object(cinema_gui.VideoPlayerGUI, "_fill_app_menu", lambda self, menu: None):
            cinema_gui.VideoPlayerGUI._build_logo(self.app)
        self.root.update()
        actual = tkfont.Font(font=self.app.header_clock.cget("font")).actual()
        self.assertNotEqual(actual["family"].casefold(), "fixed")
        families = {name.casefold() for name in tkfont.families()}
        if "dejavu sans mono" in families:
            self.assertEqual(actual["family"].casefold(), "dejavu sans mono")

    def test_clock_text_is_24_hour_with_seconds(self):
        self.assertEqual(
            cinema_gui.header_clock_text(datetime(2026, 10, 13, 9, 5, 7)),
            "09:05:07",
        )

    def test_clock_sits_left_of_the_header_icons(self):
        with patch.object(cinema_gui.VideoPlayerGUI, "_fill_app_menu", lambda self, menu: None):
            cinema_gui.VideoPlayerGUI._build_logo(self.app)
        self.root.update()
        clock = self.app.header_clock
        self.assertRegex(clock.cget("text"), r"^\d{2}:\d{2}:\d{2}$")
        icons = (
            self.app.lights_indicator,
            self.app.remote_indicator,
            self.app.app_menu,
        )
        clock_right = clock.winfo_rootx() + clock.winfo_width()
        clock_mid = clock.winfo_rooty() + clock.winfo_height() / 2
        for icon in icons:
            self.assertLess(clock_right, icon.winfo_rootx())
            icon_mid = icon.winfo_rooty() + icon.winfo_height() / 2
            self.assertLess(abs(clock_mid - icon_mid), icon.winfo_height())
        cinema_gui.VideoPlayerGUI._refresh_header_indicators(self.app)
        self.root.update()
        clock_right = clock.winfo_rootx() + clock.winfo_width()
        self.assertLess(clock_right, self.app.lights_indicator.winfo_rootx())

    def test_clock_follows_the_wall_time(self):
        with patch.object(cinema_gui.VideoPlayerGUI, "_fill_app_menu", lambda self, menu: None):
            cinema_gui.VideoPlayerGUI._build_logo(self.app)
        moment = datetime(2026, 10, 13, 21, 4, 5)
        with patch("cinema_gui.datetime") as clock:
            clock.now.return_value = moment
            cinema_gui.VideoPlayerGUI._tick_header_clock(self.app)
        self.assertEqual(self.app.header_clock.cget("text"), "21:04:05")


class VolumeSetupTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.root = self.root
        self.app.program_state = "OFF"
        self.app.calibration_mode = None
        self.app.volume_setup = False
        self.app.program_index = 0
        self.app.preview_index = None
        self.app.preview_live = True
        self.app.playlist = [_entry(volume=40, duration=20, is_image=False)]
        self.app.program_volume = tk.DoubleVar(master=self.root, value=40)
        self.app.preview_volume = tk.DoubleVar(master=self.root, value=10)
        self.app.main_pause = False
        self.app.blackout = False
        self.app.position = 0
        self.app.duration = 20
        self.app.idle_showing = False
        self.app.still_waiting = False
        self.app.still_started = None
        self.app._remote_action = False
        self.app.lights_control = tk.BooleanVar(master=self.root, value=False)
        self.app.lights_current = ""
        self.app.lights_scenes = []
        self.app.lights_sequences = []
        self.app.lights_fading = False
        self.app.dmx_output = None
        self.app.playlist_name = tk.StringVar(master=self.root, value="abend.pls")
        self.app.idle_media_path = ""
        self.app.autoplay_delay = tk.StringVar(master=self.root, value="0")
        self.app.use_default_idle_media = tk.BooleanVar(master=self.root, value=False)
        self.app.projection_zoom = tk.BooleanVar(master=self.root, value=False)
        self.app._close_menus = lambda: None
        self.calls = []
        self.app._skip_to_playable = lambda inclusive=True: True
        self.app.ensure_main_output = lambda *args, **kwargs: self.calls.append("output")
        self.app.blank_output = lambda *args, **kwargs: self.calls.append("blank")
        self.app.refresh_all = lambda: self.calls.append("refresh")
        self.app._cancel_light_after = lambda name: self.calls.append(name)
        self.app._apply_lights = lambda preset, force=False: self.calls.append(preset)
        self.app.repaint_playlist = lambda: self.calls.append("repaint")
        self.sent = []
        self.app.preview_mpv = type("Speaker", (), {
            "set_volume": lambda _self, volume, muted=None: self.sent.append((volume, muted)),
        })()

    def tearDown(self):
        self.root.destroy()
        set_language("en")

    def _menu_labels(self):
        menu = cinema_gui.DropdownMenu(self.root, self.app)
        cinema_gui.VideoPlayerGUI._fill_program_menu(self.app, menu)
        return [
            child.cget("text")
            for child in menu.winfo_children()
            if isinstance(child, tk.Label)
        ]

    def test_menu_item_stays_visible_and_disables_while_playing(self):
        labels = self._menu_labels()
        self.assertIn("Lautstärke einstellen", labels)
        self.app.program_state = "PROGRAM"
        self.assertIn("Lautstärke einstellen", self._menu_labels())
        self.app.program_state = "PLAYING"
        self.assertIn("Lautstärke einstellen", self._menu_labels())
        menu = cinema_gui.DropdownMenu(self.root, self.app)
        cinema_gui.VideoPlayerGUI._fill_program_menu(self.app, menu)
        row = next(
            child for child in menu.winfo_children()
            if isinstance(child, tk.Label) and child.cget("text") == "Lautstärke einstellen"
        )
        self.assertEqual(row.cget("fg"), cinema_gui.COLOR_PLAYED)

    def test_start_arms_the_program_in_purple_and_keeps_the_playlist(self):
        self.assertTrue(cinema_gui.VideoPlayerGUI.start_volume_setup(self.app))
        self.assertTrue(self.app.volume_setup)
        self.assertEqual(self.app.program_state, "PROGRAM")
        self.assertEqual(len(self.app.playlist), 1)
        self.assertEqual(self.app.state_color(), cinema_gui.COLOR_CALIBRATION)
        self.assertIn("refresh", self.calls)

    def test_empty_playlist_stays_stopped(self):
        self.app.playlist = []
        with patch.object(cinema_gui.messagebox, "showinfo") as info:
            self.assertFalse(cinema_gui.VideoPlayerGUI.start_volume_setup(self.app))
        info.assert_called_once()
        self.assertEqual(self.app.program_state, "OFF")
        self.assertFalse(self.app.volume_setup)

    def test_transport_skips_confirmation_and_stop_leaves_the_mode(self):
        self.app.volume_setup = True
        self.app.program_state = "PLAYING"
        applied = []
        self.app._apply_pause = lambda: applied.append("pause") or True
        self.app._apply_still = lambda: applied.append("still") or True
        self.app._apply_stop_clip = lambda: applied.append("clip") or True
        with patch.object(cinema_gui.messagebox, "askyesno") as ask:
            cinema_gui.VideoPlayerGUI.confirm_pause(self.app)
            cinema_gui.VideoPlayerGUI.confirm_still(self.app)
            cinema_gui.VideoPlayerGUI.confirm_stop(self.app)
        ask.assert_not_called()
        self.assertEqual(applied, ["pause", "still", "clip"])
        self.assertTrue(self.app.volume_setup)
        self.app.program_state = "PROGRAM"
        cinema_gui.VideoPlayerGUI.confirm_stop(self.app)
        self.assertFalse(self.app.volume_setup)
        self.assertEqual(self.app.program_state, "OFF")
        self.assertIn("bright", self.calls)
        self.app.volume_setup = True
        self.app.program_state = "PROGRAM"
        del self.app._apply_stop_clip
        result = cinema_gui.VideoPlayerGUI.remote_stop(self.app)
        self.assertFalse(result["ok"])
        self.assertTrue(self.app.volume_setup)
        self.assertEqual(self.app.program_state, "PROGRAM")

    def test_program_can_be_scrubbed_and_saving_keeps_the_fader(self):
        self.app.volume_setup = True
        self.app.program_state = "PLAYING"
        self.app.main_pause = False
        self.assertTrue(cinema_gui.VideoPlayerGUI.program_seek_allowed(self.app))
        self.app.volume_setup = False
        self.assertFalse(cinema_gui.VideoPlayerGUI.program_seek_allowed(self.app))
        self.app.volume_setup = True
        self.app.program_volume.set(55)
        cinema_gui.VideoPlayerGUI.save_program_volume(self.app)
        self.assertEqual(self.app.playlist[0].volume, 55)
        self.assertEqual(self.app.program_volume.get(), 55)
        self.assertEqual(self.app.preview_volume.get(), 55)
        self.assertEqual(self.sent[-1][0], 55)
        sought = []
        self.app._on_main_seek = lambda position, dragging=False: sought.append(position)
        result = cinema_gui.VideoPlayerGUI.remote_seek(self.app, 12.5)
        self.assertTrue(result["ok"])
        self.assertEqual(sought, [12.5])
        self.app.program_state = "PROGRAM"
        status = cinema_gui.VideoPlayerGUI.remote_status(self.app)
        self.assertTrue(status["volume_setup"])
        self.assertEqual(status["state_label"], "Lautstärke einstellen")
        self.assertTrue(status["actions"]["save_volume"])
        self.assertFalse(status["actions"]["confirm_transport"])
        self.assertFalse(status["actions"]["stop"])
        self.assertFalse(status["actions"]["seek"])
        self.assertNotIn("start_volume_setup", status["actions"])
        self.assertNotIn("envelope", status["clip"])
        self.app.playlist[0].audio_envelope = [0.1, 0.8, 0.3]
        status = cinema_gui.VideoPlayerGUI.remote_status(self.app)
        self.assertEqual(status["clip"]["envelope"], [0.1, 0.8, 0.3])
        self.app.volume_setup = False
        status = cinema_gui.VideoPlayerGUI.remote_status(self.app)
        self.assertNotIn("envelope", status.get("clip") or {})

    def test_save_button_appears_only_in_the_mode(self):
        parent = tk.Frame(self.root, bg=cinema_gui.COLOR_PANEL)
        parent.pack(fill="x")
        cinema_gui.VideoPlayerGUI._build_volume_row(
            self.app, parent, self.app.program_volume, lambda value: None,
            cinema_gui.COLOR_PANEL,
        )
        self.root.update()
        button = self.app.program_save_volume
        self.assertEqual(button.cget("text"), "Lautstärke speichern")
        self.assertEqual(button.winfo_manager(), "")
        self.app.volume_setup = True
        cinema_gui.VideoPlayerGUI._apply_volume_setup_chrome(self.app)
        self.root.update()
        self.assertEqual(button.winfo_manager(), "pack")
        self.app.volume_setup = False
        cinema_gui.VideoPlayerGUI._apply_volume_setup_chrome(self.app)
        self.assertEqual(button.winfo_manager(), "")


class PreviewMuteTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.preview_volume = tk.DoubleVar(master=self.root, value=73)
        self.app.preview_muted = False
        self.sent = []

        class Speaker:
            def __init__(self, sent):
                self.sent = sent

            def set_volume(self, volume, muted=None):
                self.sent.append((volume, muted))

        self.app.preview_mpv = Speaker(self.sent)

    def tearDown(self):
        self.root.destroy()
        set_language("en")

    def test_mute_silences_the_speaker_and_keeps_the_fader(self):
        parent = tk.Frame(self.root)
        parent.pack(fill="x")
        cinema_gui.VideoPlayerGUI._build_volume_row(
            self.app, parent, self.app.preview_volume, self.app._on_preview_volume,
            cinema_gui.COLOR_PANEL, save=True,
        )
        self.root.update()
        button = self.app.preview_mute_button
        self.assertEqual(button.cget("text"), "Stumm")
        cinema_gui.VideoPlayerGUI._toggle_preview_mute(self.app)
        self.assertTrue(self.app.preview_muted)
        self.assertEqual(self.app.preview_volume.get(), 73)
        self.assertEqual(self.app.preview_volume_label.cget("text"), "73")
        self.assertEqual(self.sent[-1], (73, True))
        self.assertIn("✔", button.cget("text"))
        cinema_gui.VideoPlayerGUI._on_preview_volume(self.app, 40)
        self.assertTrue(self.app.preview_muted)
        self.assertEqual(self.app.preview_volume.get(), 40)
        self.assertEqual(self.app.preview_volume_label.cget("text"), "40")
        self.assertEqual(self.sent[-1], (40, True))
        cinema_gui.VideoPlayerGUI._toggle_preview_mute(self.app)
        self.assertFalse(self.app.preview_muted)
        self.assertEqual(self.app.preview_volume.get(), 40)
        self.assertEqual(self.sent[-1], (40, False))
        self.assertEqual(button.cget("text"), "Stumm")


class UnsavedPlaylistQuitTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.root = self.root
        self.app.icon_image = None
        self.app.output_manager = None

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def test_a_changed_playlist_is_unsaved_until_it_is_remembered(self):
        self.app._playlist_payload = lambda: {"entries": []}
        cinema_gui.VideoPlayerGUI._remember_saved_playlist(self.app)
        self.assertFalse(cinema_gui.VideoPlayerGUI._playlist_has_unsaved_changes(self.app))
        self.app._playlist_payload = lambda: {"entries": ["clip.mp4"]}
        self.assertTrue(cinema_gui.VideoPlayerGUI._playlist_has_unsaved_changes(self.app))
        cinema_gui.VideoPlayerGUI._remember_saved_playlist(self.app)
        self.assertFalse(cinema_gui.VideoPlayerGUI._playlist_has_unsaved_changes(self.app))

    def test_cancel_keeps_the_window_open(self):
        self.app.program_state = "OFF"
        self.app._playlist_has_unsaved_changes = lambda: True
        self.app._ask_unsaved_playlist = lambda: "cancel"
        self.assertEqual(cinema_gui.VideoPlayerGUI.close(self.app), "break")
        self.assertTrue(self.root.winfo_exists())

    def test_quit_discards_the_playlist(self):
        self.app._playlist_has_unsaved_changes = lambda: True
        self.app._ask_unsaved_playlist = lambda: "quit"
        self.app._save_playlist_for_quit = lambda: self.fail("save")
        self.assertTrue(cinema_gui.VideoPlayerGUI._confirm_close_playlist(self.app))

    def test_failed_save_keeps_the_program_open(self):
        self.app._playlist_has_unsaved_changes = lambda: True
        self.app._ask_unsaved_playlist = lambda: "save"
        self.app._save_playlist_for_quit = lambda: False
        self.assertFalse(cinema_gui.VideoPlayerGUI._confirm_close_playlist(self.app))

    def test_save_writes_the_known_playlist_file(self):
        written = []
        self.app.playlist_path = "/films/abend.pls"
        self.app._write_playlist = lambda path: written.append(path)
        self.assertTrue(cinema_gui.VideoPlayerGUI._save_playlist_for_quit(self.app))
        self.assertEqual(written, ["/films/abend.pls"])

    def test_save_without_a_path_uses_the_save_dialog(self):
        self.app.playlist_path = ""
        self.app.save_playlist = lambda: False
        self.assertFalse(cinema_gui.VideoPlayerGUI._save_playlist_for_quit(self.app))

    def test_dialog_offers_cancel_save_and_quit(self):
        labels = {
            t("quit_cancel"): "cancel",
            t("quit_save"): "save",
            t("quit"): "quit",
        }
        for label, expected in labels.items():
            self.root.after(80, lambda text=label: self._press(text))
            choice = cinema_gui.VideoPlayerGUI._ask_unsaved_playlist(self.app)
            self.assertEqual(choice, expected)

    def _press(self, text):
        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Button) and child.cget("text") == text:
                    child.invoke()
                    return True
                if walk(child):
                    return True
            return False

        for widget in self.root.winfo_children():
            if walk(widget):
                return
        self.fail(f"button {text!r} was not shown")


class StillFadeTests(unittest.TestCase):
    def test_full_level_clears_the_still_filter(self):
        self.assertEqual(cinema_gui.still_level_filter(1), "")
        self.assertIn("brightness=-1.000", cinema_gui.still_level_filter(0))

    def test_fade_fits_inside_the_display_time(self):
        self.assertIsNone(cinema_gui.still_fade_plan(0, 2, True))
        self.assertEqual(cinema_gui.still_fade_plan(10, 2, False), (10000, 0.0))
        self.assertEqual(cinema_gui.still_fade_plan(10, 2, True), (8000, 2.0))
        self.assertEqual(cinema_gui.still_fade_plan(1, 2, True), (500, 0.5))

    def test_dim_time_is_one_global_setting(self):
        root = tk.Tk()
        try:
            app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
            app.still_dim = tk.BooleanVar(master=root, value=True)
            app.still_dim_seconds = tk.StringVar(master=root, value="2,5")
            app.settings = {}
            with patch("cinema_gui.save_settings") as save:
                cinema_gui.VideoPlayerGUI.apply_still_dim_settings(app)
            self.assertTrue(app.settings["still_dim"])
            self.assertEqual(app.settings["still_dim_seconds"], 2.5)
            self.assertEqual(app.still_dim_seconds.get(), "2.5")
            save.assert_called_once_with(app.settings)
        finally:
            root.destroy()


class StillFadePlaybackTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.root = self.root
        self.app.still_after_id = None
        self.app.still_started = None
        self.app.still_waiting = False
        self.app.still_fade_after = None
        self.app._still_fade_done = None
        self.app._still_fade_span = None
        self.app._still_fading_out = False
        self.app._still_fade_out_done = False
        self.app._still_level = 1.0
        self.app._picture_brightness = 0
        self.app.still_dim = tk.BooleanVar(master=self.root, value=True)
        self.app.still_dim_seconds = tk.StringVar(master=self.root, value="2")
        self.app.preview_live = False
        self.app.preview_mpv = None
        self.app.idle_showing = False
        self.app.program_state = "PLAYING"
        self.player = _BrightnessPlayer()
        self.app.main_mpv = self.player

    def tearDown(self):
        self.root.destroy()
        set_language("en")

    def test_timer_starts_the_fade_before_the_still_ends(self):
        scheduled = []
        self.app.root.after = lambda ms, fn, *args: scheduled.append(ms) or "timer"
        self.app.root.after_cancel = lambda *args: None
        entry = _entry(path="/media/films/still.png", is_image=True, display_time=10)
        cinema_gui.VideoPlayerGUI.start_still_timer(self.app, entry)
        self.assertEqual(scheduled, [8000])
        self.assertEqual(self.app._still_fade_span, 2)
        self.app.still_dim.set(False)
        scheduled.clear()
        cinema_gui.VideoPlayerGUI.start_still_timer(self.app, entry)
        self.assertEqual(scheduled, [10000])
        self.assertEqual(self.app._still_fade_span, 0)

    def test_stop_fades_the_still_out_before_the_clip_ends(self):
        entry = _entry(path="/media/films/still.png", is_image=True, display_time=0)
        self.app.current_entry = lambda: entry
        self.app.still_dim_seconds.set("0.12")
        stopped = []
        self.app._finish_stop_clip = lambda: stopped.append(True) or True
        self.assertTrue(cinema_gui.VideoPlayerGUI._apply_stop_clip(self.app))
        self.assertEqual(stopped, [])
        deadline = time.monotonic() + 1
        while not stopped and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertEqual(stopped, [True])
        self.assertEqual(self.player.commands[-1], ("set_property", "vf", cinema_gui.still_level_filter(0)))

    def test_resume_on_a_waiting_still_fades_out_first(self):
        entry = _entry(path="/media/films/still.png", is_image=True, display_time=0)
        self.app.current_entry = lambda: entry
        self.app.still_waiting = True
        self.app.still_dim_seconds.set("0.12")
        finished = []

        def finish():
            if finished:
                return
            finished.append(self.app._still_level)
            self.app.program_state = "PROGRAM"

        self.app.on_clip_finished = finish
        cinema_gui.VideoPlayerGUI.on_clip_finished(self.app)
        self.assertEqual(finished, [])
        deadline = time.monotonic() + 1
        while not finished and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        self.assertEqual(finished, [0.0])
        self.assertEqual(
            self.player.commands[-1],
            ("set_property", "vf", cinema_gui.still_level_filter(0)),
        )


class _BrightnessPlayer:
    process = object()

    def __init__(self):
        self.commands = []

    def command(self, *args):
        self.commands.append(args)


class _ProgramSpeaker:
    def __init__(self, sent, process=True):
        self.sent = sent
        self.process = object() if process else None

    def set_volume(self, volume, muted=None):
        self.sent.append(volume)


class ProgramVolumeGlideTests(unittest.TestCase):
    def test_smoothstep_is_the_midpoint_at_half_a_second(self):
        self.assertEqual(cinema_gui.program_volume_glide(20, 80, 0), 20)
        self.assertEqual(cinema_gui.program_volume_glide(20, 80, -1), 20)
        self.assertEqual(cinema_gui.program_volume_glide(20, 80, 0.5), 50)
        self.assertAlmostEqual(cinema_gui.program_volume_glide(0, 100, 0.25), 15.625)
        self.assertEqual(cinema_gui.program_volume_glide(20, 80, 1.0), 80)
        self.assertEqual(cinema_gui.program_volume_glide(20, 80, 2.0), 80)
        self.assertEqual(cinema_gui.program_volume_glide(40, 40, 0.3), 40)

    def setUp(self):
        self.root = tk.Tk()
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.root = self.root
        self.app.program_state = "PLAYING"
        self.app.idle_showing = False
        self.app.program_volume = tk.DoubleVar(master=self.root, value=80)
        self.app.program_volume_label = None
        self.app.program_volume_bar = None
        self.app._program_volume_output = 20.0
        self.app._program_volume_glide = None
        self.app._program_volume_glide_after = None
        self.sent = []
        self.app.main_mpv = _ProgramSpeaker(self.sent)

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _clock(self):
        clock = {"t": 1000.0}
        scheduled = {}

        def monotonic():
            return clock["t"]

        def after(ms, fn):
            scheduled["ms"] = ms
            scheduled["fn"] = fn
            return "glide-timer"

        def after_cancel(_after_id):
            scheduled.clear()

        self.app.root.after = after
        self.app.root.after_cancel = after_cancel
        return clock, scheduled, monotonic

    def test_output_eases_while_the_fader_stays_on_the_target(self):
        clock, scheduled, monotonic = self._clock()
        with patch("cinema_gui.time.monotonic", side_effect=monotonic):
            running = cinema_gui.VideoPlayerGUI._glide_program_volume(self.app, 80, move_fader=False)
            self.assertTrue(running)
            self.assertAlmostEqual(self.sent[-1], 20)
            self.assertEqual(self.app.program_volume.get(), 80)
            clock["t"] += 0.5
            scheduled["fn"]()
            self.assertAlmostEqual(self.sent[-1], 50)
            self.assertEqual(self.app.program_volume.get(), 80)
            clock["t"] += 0.5
            scheduled["fn"]()
        self.assertEqual(self.sent[-1], 80)
        self.assertIsNone(self.app._program_volume_glide)
        self.assertIsNone(self.app._program_volume_glide_after)

    def test_clip_change_eases_the_fader_from_the_current_level(self):
        clock, scheduled, monotonic = self._clock()
        self.app.program_volume.set(80)
        with patch("cinema_gui.time.monotonic", side_effect=monotonic):
            running = cinema_gui.VideoPlayerGUI._glide_program_volume(self.app, 80, move_fader=True)
            self.assertTrue(running)
            self.assertEqual(self.app.program_volume.get(), 20)
            clock["t"] += 1.0
            scheduled["fn"]()
        self.assertEqual(self.app.program_volume.get(), 80)
        self.assertEqual(self.sent[-1], 80)
        self.assertIsNone(self.app._program_volume_glide)

    def test_first_clip_snaps_instead_of_fading_up_from_silence(self):
        self.app._program_volume_output = None
        self.app.program_volume.set(10)
        running = cinema_gui.VideoPlayerGUI._glide_program_volume(self.app, 80, move_fader=True)
        self.assertFalse(running)
        self.assertEqual(self.sent, [80.0])
        self.assertEqual(self.app.program_volume.get(), 80)
        self.assertIsNone(self.app._program_volume_glide)
        self.assertEqual(self.app._program_volume_output, 80.0)

    def test_a_new_target_restarts_from_the_level_now_playing(self):
        clock, scheduled, monotonic = self._clock()
        self.app._program_volume_output = 0.0
        with patch("cinema_gui.time.monotonic", side_effect=monotonic):
            cinema_gui.VideoPlayerGUI._glide_program_volume(self.app, 100, move_fader=False)
            clock["t"] += 0.5
            scheduled["fn"]()
            self.assertAlmostEqual(self.app._program_volume_output, 50)
            cinema_gui.VideoPlayerGUI._glide_program_volume(self.app, 80, move_fader=False)
            self.assertAlmostEqual(self.sent[-1], 50)
            clock["t"] += 1.0
            scheduled["fn"]()
        self.assertEqual(self.sent[-1], 80)
        self.assertIsNone(self.app._program_volume_glide)

    def test_file_reload_repeats_the_live_level(self):
        self.app._program_volume_output = 33.5
        self.app.program_volume.set(90)
        cinema_gui.VideoPlayerGUI._send_program_output_volume(self.app)
        self.assertEqual(self.sent, [33.5])
        self.app.idle_showing = True
        cinema_gui.VideoPlayerGUI._send_program_output_volume(self.app)
        self.assertEqual(self.sent, [33.5])

    def test_fader_move_keeps_the_command_and_eases_the_output(self):
        clock, scheduled, monotonic = self._clock()
        with patch("cinema_gui.time.monotonic", side_effect=monotonic):
            cinema_gui.VideoPlayerGUI._on_program_volume(self.app, 80)
            self.assertEqual(self.app.program_volume.get(), 80)
            self.assertAlmostEqual(self.sent[-1], 20)
            clock["t"] += 1.0
            scheduled["fn"]()
        self.assertEqual(self.sent[-1], 80)

    def test_idle_cancels_the_ramp_and_is_remembered_at_full_level(self):
        cancelled = []
        loaded = []
        self.app.root.after_cancel = lambda after_id: cancelled.append(after_id)
        self.app._program_volume_glide = {"start": 20, "target": 80}
        self.app._program_volume_glide_after = "timer"
        self.app.program_state = "PROGRAM"
        self.app.calibration_mode = None
        self.app.beamer_test_active = False
        self.app.idle_media_path = os.path.abspath(__file__)

        def load_file(*_args, **_kwargs):
            loaded.append(True)

        self.app.main_mpv.set_ab_loop = lambda *_args, **_kwargs: None
        self.app.main_mpv.load_file = load_file
        cinema_gui.VideoPlayerGUI.show_idle_media(self.app)
        self.assertEqual(cancelled, ["timer"])
        self.assertIsNone(self.app._program_volume_glide)
        self.assertEqual(self.app._program_volume_output, 100)
        self.assertEqual(self.sent[-1], 100)
        self.assertTrue(self.app.idle_showing)
        self.assertTrue(loaded)

    def test_real_timer_settles_in_about_one_second(self):
        self.app._program_volume_output = 0.0
        self.app.program_volume.set(0)
        started = time.monotonic()
        running = cinema_gui.VideoPlayerGUI._glide_program_volume(self.app, 100, move_fader=True)
        self.assertTrue(running)
        deadline = started + 1.6
        while self.app._program_volume_glide is not None and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.02)
        elapsed = time.monotonic() - started
        self.assertIsNone(self.app._program_volume_glide)
        self.assertEqual(self.sent[-1], 100)
        self.assertEqual(self.app.program_volume.get(), 100)
        self.assertGreater(elapsed, 0.85)
        self.assertLess(elapsed, 1.45)
        self.assertGreater(len(self.sent), 10)
        self.assertLess(self.sent[1], 30)
        self.assertGreater(self.sent[len(self.sent) // 2], self.sent[1])
        self.assertEqual(self.sent, sorted(self.sent))


if __name__ == "__main__":
    unittest.main()
