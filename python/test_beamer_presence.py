#!/usr/bin/env python3
"""Program and beamer stay dark until a projector is connected."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))


def _ensure_real_tkinter():
    current = sys.modules.get("tkinter")
    if current is not None and type(current).__module__ == "unittest.mock":
        for name in list(sys.modules):
            if name == "tkinter" or name.startswith("tkinter."):
                del sys.modules[name]
        sys.modules.pop("cinema_gui", None)


_ensure_real_tkinter()

import tkinter as tk

import cinema_gui
import cinema_player as player
from language import set_language, t


class _Manager:
    def __init__(self, outputs, primary=None):
        self._outputs = list(outputs)
        self._primary = primary if primary is not None else (outputs[0] if outputs else None)
        self.video_output = outputs[1] if len(outputs) > 1 else None
        self.video_mode = None

    def get_outputs(self):
        return list(self._outputs)

    def get_primary_output(self):
        return self._primary

    def has_dedicated_beamer(self):
        return len(self._outputs) >= 2

    def rescan_outputs(self, preferred=None):
        if len(self._outputs) < 2:
            self.video_output = None
            return None
        pick = preferred if preferred in self._outputs and preferred != self._primary else self._outputs[1]
        self.video_output = pick
        return pick

    def select_video_output(self, preferred=None):
        if preferred and preferred in self._outputs:
            self.video_output = preferred
            return preferred
        if len(self._outputs) >= 2:
            self.video_output = next(
                name for name in self._outputs if name != self._primary
            )
            return self.video_output
        self.video_output = self._outputs[0] if self._outputs else None
        return self.video_output

    def get_current_mode(self, _name):
        return None


class RescanOutputsTests(unittest.TestCase):
    def test_has_dedicated_beamer_needs_two_outputs(self):
        manager = player.VideoOutputManager()
        with mock.patch.object(manager, "get_outputs", return_value=["eDP-1"]):
            self.assertFalse(manager.has_dedicated_beamer())
        with mock.patch.object(manager, "get_outputs", return_value=["eDP-1", "HDMI-A-1"]):
            self.assertTrue(manager.has_dedicated_beamer())

    def test_clears_output_when_only_one_display(self):
        manager = player.VideoOutputManager(video_output="eDP-1")
        with (
            mock.patch.object(manager, "get_outputs", return_value=["eDP-1"]),
            mock.patch.object(manager, "get_primary_output", return_value="eDP-1"),
        ):
            self.assertIsNone(manager.rescan_outputs())
        self.assertIsNone(manager.video_output)
        self.assertIsNone(manager.video_mode)

    def test_selects_the_second_display_after_a_laptop_only_start(self):
        manager = player.VideoOutputManager(video_output="eDP-1")
        with (
            mock.patch.object(manager, "get_outputs", return_value=["eDP-1", "HDMI-A-1"]),
            mock.patch.object(manager, "get_primary_output", return_value="eDP-1"),
            mock.patch.object(manager, "_clear_audio_cache"),
        ):
            self.assertEqual(manager.rescan_outputs(), "HDMI-A-1")
        self.assertEqual(manager.video_output, "HDMI-A-1")

    def test_keeps_a_non_primary_choice(self):
        manager = player.VideoOutputManager(video_output="HDMI-A-1")
        with (
            mock.patch.object(manager, "get_outputs", return_value=["eDP-1", "HDMI-A-1"]),
            mock.patch.object(manager, "get_primary_output", return_value="eDP-1"),
            mock.patch.object(manager, "_clear_audio_cache"),
        ):
            self.assertEqual(manager.rescan_outputs(), "HDMI-A-1")
        self.assertEqual(manager.video_output, "HDMI-A-1")

    def test_preferred_output_wins(self):
        manager = player.VideoOutputManager()
        with (
            mock.patch.object(manager, "get_outputs", return_value=["eDP-1", "HDMI-A-1", "DP-2"]),
            mock.patch.object(manager, "get_primary_output", return_value="eDP-1"),
            mock.patch.object(manager, "_clear_audio_cache"),
        ):
            self.assertEqual(manager.rescan_outputs("DP-2"), "DP-2")
        self.assertEqual(manager.video_output, "DP-2")


class BeamerPresenceTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.root.geometry("900x500+20+20")
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.root = self.root
        self.app.beamer_details_open = False
        self.app.program_state = "OFF"
        self.app.program_index = 0
        self.app.playlist = []
        self.app.calibration_mode = None
        self.app.volume_setup = False
        self.app.autoplay_after_id = None
        self.app.settings = {}
        self.app.mpv_path = "/usr/bin/mpv"
        self.app.main_mpv = type("Player", (), {"process": None, "add_callback": lambda *_args: None})()
        self.app.beamer_output = tk.StringVar(master=self.root, value="")
        left = tk.Frame(self.root)
        left.pack(fill="x")
        right = tk.Frame(self.root)
        right.pack(fill="x")
        group = cinema_gui.VideoPlayerGUI._group_frame(self.app, left)
        group.pack(fill="x")
        group.columnconfigure(0, weight=1)
        self.app.program_group = group
        self.app.program_body = tk.Frame(group, bg=cinema_gui.COLOR_PANEL)
        self.app.program_body.grid(row=0, column=0, sticky="nsew")
        self.app.program_missing = tk.Label(
            group, text=t("beamer_disconnected"), bg=cinema_gui.COLOR_PANEL,
        )
        self.app.program_missing.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.app.program_missing.grid_remove()
        self.app.program_meter = tk.Frame(group, bg=cinema_gui.COLOR_PANEL)
        self.app.program_meter.grid(row=0, column=1, sticky="ns")
        cinema_gui.VideoPlayerGUI._build_beamer(self.app, right)
        self.app.output_manager = _Manager(["eDP-1"])
        self.started = []
        self.app.ensure_main_output = lambda auto=False: self.started.append(auto) or True
        self.app.refresh_all = lambda: cinema_gui.VideoPlayerGUI._apply_beamer_presence(self.app)

    def tearDown(self):
        self.root.destroy()
        set_language("en")

    def test_language_keys(self):
        self.assertEqual(t("beamer_disconnected"), "Kein Beamer angeschlossen.")
        self.assertEqual(t("beamer_rescan"), "Beamer neu einlesen")
        set_language("en")
        self.assertEqual(t("beamer_disconnected"), "No projector connected.")
        self.assertEqual(t("beamer_rescan"), "Rescan projector")

    def test_missing_projector_hides_program_and_status(self):
        cinema_gui.VideoPlayerGUI._apply_beamer_presence(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_missing.cget("text"), "Kein Beamer angeschlossen.")
        self.assertEqual(self.app.program_missing.winfo_manager(), "grid")
        self.assertEqual(self.app.program_body.winfo_manager(), "")
        self.assertEqual(self.app.program_meter.winfo_manager(), "")
        self.assertEqual(self.app.beamer_rescan.cget("text"), "Beamer neu einlesen")
        self.assertEqual(self.app.beamer_rescan.winfo_manager(), "pack")
        self.assertEqual(self.app.beamer_ok.winfo_manager(), "")
        self.assertEqual(self.app.beamer_summary.winfo_manager(), "")
        self.assertEqual(self.app.beamer_details.winfo_manager(), "")
        self.assertEqual(self.app.beamer_fold.winfo_manager(), "")

    def test_connected_projector_keeps_program_and_status(self):
        self.app.output_manager = _Manager(["eDP-1", "HDMI-A-1"])
        cinema_gui.VideoPlayerGUI._apply_beamer_presence(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_body.winfo_manager(), "grid")
        self.assertEqual(self.app.program_missing.winfo_manager(), "")
        self.assertEqual(self.app.beamer_ok.winfo_manager(), "pack")
        self.assertEqual(self.app.beamer_summary.winfo_manager(), "pack")
        self.assertEqual(self.app.beamer_fold.winfo_manager(), "pack")

    def test_start_or_resume_does_nothing_without_a_projector(self):
        called = []
        self.app.playlist = [object()]
        self.app.start_current_clip = lambda: called.append("start")
        cinema_gui.VideoPlayerGUI.start_or_resume(self.app)
        self.assertEqual(called, [])
        self.assertEqual(self.app.program_state, "OFF")

    def test_volume_setup_stays_off_without_a_projector(self):
        self.assertFalse(cinema_gui.VideoPlayerGUI.start_volume_setup(self.app))
        self.assertFalse(self.app.volume_setup)

    def test_ensure_main_output_does_not_start_mpv_without_a_projector(self):
        self.app.ensure_main_output = cinema_gui.VideoPlayerGUI.ensure_main_output.__get__(
            self.app, cinema_gui.VideoPlayerGUI,
        )
        self.assertFalse(self.app.ensure_main_output())
        self.assertIsNone(self.app.main_mpv.process)

    def test_rescan_that_finds_a_projector_starts_mpv_and_restores_controls(self):
        self.app.output_manager._outputs = ["eDP-1", "HDMI-A-1"]
        cinema_gui.VideoPlayerGUI.rescan_beamer(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.started, [True])
        self.assertEqual(self.app.beamer_output.get(), "HDMI-A-1")
        self.assertEqual(self.app.program_body.winfo_manager(), "grid")
        self.assertEqual(self.app.program_missing.winfo_manager(), "")
        self.assertEqual(self.app.beamer_ok.winfo_manager(), "pack")

    def test_rescan_that_finds_nothing_stops_mpv(self):
        self.app.program_state = "PROGRAM"
        self.app.main_mpv.process = object()
        quit_calls = []
        self.app.main_mpv.quit = lambda: quit_calls.append("quit")
        cinema_gui.VideoPlayerGUI.rescan_beamer(self.app)
        self.root.update_idletasks()
        self.assertEqual(quit_calls, ["quit"])
        self.assertEqual(self.app.program_state, "OFF")
        self.assertEqual(self.app.program_missing.winfo_manager(), "grid")
        self.assertEqual(self.started, [])

    def test_startup_warning_does_not_open_a_dialog(self):
        offered = []
        self.app._offer_playlist_library = lambda: offered.append("library")
        with mock.patch.object(cinema_gui.messagebox, "showwarning") as warning:
            cinema_gui.VideoPlayerGUI._warn_if_no_beamer_output(self.app)
        warning.assert_not_called()
        self.assertEqual(offered, ["library"])
        self.assertEqual(self.app.program_missing.winfo_manager(), "grid")


if __name__ == "__main__":
    unittest.main()
