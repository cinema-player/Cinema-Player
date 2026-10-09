#!/usr/bin/env python3
"""Booth layout: playlist columns, show chrome, beamer short form, clocks."""

import os
import sys
import unittest
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

import cinema_gui
from cinema_player import PlaylistEntry, reload_entry_metadata
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

    def test_program_menu_holds_idle_media_above_the_default(self):
        self.app.root = self.root
        self.app._close_menus = lambda: None
        self.app.idle_media_path = ""
        self.app.program_state = "OFF"
        self.app.use_default_idle_media = tk.BooleanVar(master=self.root, value=False)
        self.app.autoplay_delay = tk.StringVar(master=self.root, value="0")
        self.app.autosave_on_program_change = tk.BooleanVar(master=self.root, value=False)
        self.app.load_last_playlist_at_start = tk.BooleanVar(master=self.root, value=False)
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
            ["Pausenmedium  >", "Standard-Pausenmedium verwenden", "Einstellungswarnung"],
        )
        children = program.winfo_children()
        self.assertIsInstance(children[-2], tk.Frame)
        self.assertEqual(children[-1].cget("text"), "Einstellungswarnung")
        playlist = cinema_gui.DropdownMenu(self.root, self.app)
        cinema_gui.VideoPlayerGUI._fill_playlist_menu(self.app, playlist)
        playlist_text = " ".join(
            child.cget("text")
            for child in playlist.winfo_children()
            if isinstance(child, tk.Label)
        )
        self.assertNotIn("Pausenmedium", playlist_text)
        self.assertNotIn("Einstellungswarnung", playlist_text)

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
        self.assertEqual(self.app.show_strip.winfo_manager(), "")
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "")
        self.app.lights_control.set(True)
        cinema_gui.VideoPlayerGUI._apply_program_light_block(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_light_bar.winfo_manager(), "pack")
        self.assertEqual(self.app.program_light_dimmer.winfo_manager(), "pack")

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
