#!/usr/bin/env python3
"""Booth layout: playlist columns, show chrome, beamer short form, clocks."""

import os
import sys
import unittest

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

import cinema_gui
from cinema_player import PlaylistEntry
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

    def test_color_warning_is_a_note(self):
        entry = _entry(colorspace_warning=True, colorspace="Rec.2020")
        notes = cinema_gui.playlist_note_text(entry, True)
        self.assertIn("Farbe", notes)
        self.assertNotIn("setting!", notes)

    def test_forced_warning_keeps_the_setting_badge(self):
        entry = _entry(force_settings_warning=True)
        self.assertIn("setting!", cinema_gui.playlist_note_text(entry, True))

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

    def test_show_mode_hides_preparation_tools(self):
        tools = tk.Frame(self.root)
        tools.grid(row=0, column=0)
        settings = tk.Frame(self.root)
        settings.grid(row=1, column=0)
        self.app.playlist_tool_buttons = tools
        self.app.preview_settings = settings
        self.app.program_state = "PLAYING"
        cinema_gui.VideoPlayerGUI._apply_booth_chrome(self.app)
        self.assertEqual(tools.winfo_manager(), "")
        self.assertEqual(settings.winfo_manager(), "")
        self.app.calibration_mode = "video"
        cinema_gui.VideoPlayerGUI._apply_booth_chrome(self.app)
        self.assertEqual(tools.winfo_manager(), "grid")
        self.assertEqual(settings.winfo_manager(), "grid")

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
        self.assertEqual(self.app.show_strip.winfo_manager(), "grid")
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "")
        self.app.lights_control.set(True)
        cinema_gui.VideoPlayerGUI._apply_program_light_block(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "pack")
        self.assertEqual(self.app.program_light_dimmer.winfo_manager(), "pack")


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


if __name__ == "__main__":
    unittest.main()
