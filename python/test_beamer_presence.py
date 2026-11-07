#!/usr/bin/env python3
"""Program and beamer stay dark until a projector is connected."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
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

    def test_link_down_hides_the_program_while_another_display_remains(self):
        self.app.output_manager = _Manager(["eDP-1", "HDMI-A-1"])
        self.app._beamer_link_down = True
        cinema_gui.VideoPlayerGUI._apply_beamer_presence(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.app.program_missing.winfo_manager(), "grid")
        self.assertEqual(self.app.program_body.winfo_manager(), "")
        self.assertEqual(self.app.beamer_ok.winfo_manager(), "")

    def _arm_running_beamer(self, status):
        self.app.output_manager = _Manager(["eDP-1", "HDMI-A-1"])
        self.app.output_manager.video_output = "HDMI-A-1"
        self.app.output_manager.video_mode = "1920x1080"
        self.app.output_manager.projector_link_status = lambda: status
        self.app.beamer_output.set("HDMI-A-1")
        self.app.program_state = "PLAYING"
        self.app.volume_setup = True
        self.app.main_mpv.process = object()
        self.quit_calls = []
        self.app.main_mpv.quit = lambda: self.quit_calls.append("quit")
        self.lights = []
        self.app.lights_control = tk.BooleanVar(master=self.root, value=True)
        self.app._apply_lights = lambda preset, force=False: self.lights.append(preset)

    def test_one_disconnected_sample_keeps_the_beamer_mpv(self):
        self._arm_running_beamer("disconnected")
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.assertEqual(self.quit_calls, [])
        self.assertEqual(self.app.program_state, "PLAYING")
        self.assertEqual(self.app.output_manager.video_output, "HDMI-A-1")
        self.assertEqual(self.app._beamer_unplug_hits, 1)

    def test_unplugging_the_projector_quits_the_beamer_mpv(self):
        self._arm_running_beamer("disconnected")
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.root.update_idletasks()
        self.assertEqual(self.quit_calls, ["quit"])
        self.assertEqual(self.app.program_state, "OFF")
        self.assertFalse(self.app.volume_setup)
        self.assertIsNone(self.app.output_manager.video_output)
        self.assertIsNone(self.app.output_manager.video_mode)
        self.assertEqual(self.app.beamer_output.get(), "")
        self.assertTrue(self.app._beamer_link_down)
        self.assertEqual(self.lights, ["bright"])
        self.assertEqual(self.app.program_missing.winfo_manager(), "grid")
        self.assertEqual(self.app.program_body.winfo_manager(), "")
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.assertEqual(self.quit_calls, ["quit"])

    def test_a_connected_projector_keeps_the_running_mpv(self):
        self._arm_running_beamer("connected")
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.assertEqual(self.quit_calls, [])
        self.assertEqual(self.app.program_state, "PLAYING")
        self.assertEqual(self.lights, [])

    def test_a_disconnect_blip_does_not_quit_when_the_cable_returns(self):
        self._arm_running_beamer("disconnected")
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.app.output_manager.projector_link_status = lambda: "connected"
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.assertEqual(self.quit_calls, [])
        self.assertEqual(self.app._beamer_unplug_hits, 0)
        self.assertEqual(self.app.program_state, "PLAYING")

    def test_idle_black_window_quits_without_raising_the_house_lights(self):
        self._arm_running_beamer("disconnected")
        self.app.program_state = "OFF"
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.assertEqual(self.quit_calls, ["quit"])
        self.assertEqual(self.lights, [])

    def test_unknown_link_status_does_not_quit(self):
        self._arm_running_beamer("")
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        cinema_gui.VideoPlayerGUI._stop_main_mpv_if_beamer_unplugged(self.app)
        self.assertEqual(self.quit_calls, [])
        self.assertEqual(self.app.program_state, "PLAYING")

    def test_rescan_ignores_a_disconnected_connector(self):
        self.app.output_manager._outputs = ["eDP-1", "HDMI-A-1"]
        self.app.output_manager.projector_link_status = lambda: "disconnected"
        self.app.program_state = "PROGRAM"
        self.app.main_mpv.process = object()
        quit_calls = []
        self.app.main_mpv.quit = lambda: quit_calls.append("quit")
        cinema_gui.VideoPlayerGUI.rescan_beamer(self.app)
        self.root.update_idletasks()
        self.assertEqual(quit_calls, ["quit"])
        self.assertIsNone(self.app.output_manager.video_output)
        self.assertEqual(self.started, [])
        self.assertTrue(self.app._beamer_link_down)
        self.assertEqual(self.app.program_state, "OFF")

    def test_rescan_that_finds_a_projector_clears_link_down(self):
        self.app._beamer_link_down = True
        self.app.output_manager._outputs = ["eDP-1", "HDMI-A-1"]
        self.app.output_manager.projector_link_status = lambda: "connected"
        cinema_gui.VideoPlayerGUI.rescan_beamer(self.app)
        self.root.update_idletasks()
        self.assertFalse(self.app._beamer_link_down)
        self.assertEqual(self.started, [True])
        self.assertEqual(self.app.program_body.winfo_manager(), "grid")

    def test_gui_tick_checks_the_projector_cable(self):
        seen = []
        self.app._stop_main_mpv_if_beamer_unplugged = lambda: seen.append("check")
        self.app._drain_light_errors = lambda: None
        self.app.still_started = None
        self.app.main_progress = type("Bar", (), {"dragging": True})()
        self.app.preview_progress = type("Bar", (), {"dragging": True})()

        def stop():
            raise RuntimeError("stop")

        self.app._refresh_live_bitrates = stop
        with mock.patch("builtins.print"):
            cinema_gui.VideoPlayerGUI.update_gui(self.app)
        self.assertEqual(seen, ["check"])
        for after_id in self.root.tk.call("after", "info"):
            self.root.after_cancel(after_id)


class ProjectorLinkTests(unittest.TestCase):
    def test_sysfs_disconnect_does_not_ask_the_desktop(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card0-HDMI-A-1"
            path.mkdir()
            (path / "status").write_text("disconnected\n")
            manager = player.VideoOutputManager("HDMI-A-1")

            def fail():
                raise AssertionError("desktop probe")

            manager.get_outputs = fail
            self.assertEqual(manager.projector_link_status(folder), "disconnected")

    def test_hdmi0_reads_the_hdmi_a1_status(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card1-HDMI-A-1"
            path.mkdir()
            (path / "status").write_text("connected\n")
            manager = player.VideoOutputManager("HDMI-0")
            self.assertEqual(manager.projector_link_status(folder), "connected")
            self.assertEqual(player.drm_connector_status("HDMI-A-1", folder), "connected")

    def test_unknown_or_missing_status_is_not_a_disconnect(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "card0-HDMI-A-1"
            path.mkdir()
            (path / "status").write_text("unknown\n")
            self.assertEqual(player.drm_connector_status("HDMI-A-1", folder), "")
            (path / "status").write_text("connected\n")
            self.assertEqual(player.drm_connector_status("DP-1", folder), "")
            self.assertEqual(player.drm_connector_status("", folder), "")

    def test_desktop_list_reports_a_missing_output_once(self):
        with tempfile.TemporaryDirectory() as folder:
            calls = []
            manager = player.VideoOutputManager("HDMI-A-1")

            def outputs():
                calls.append("probe")
                return ["eDP-1"]

            manager.get_outputs = outputs
            self.assertEqual(manager.projector_link_status(folder), "disconnected")
            self.assertEqual(manager.projector_link_status(folder), "disconnected")
            self.assertEqual(calls, ["probe"])

    def test_desktop_probe_failure_stays_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = player.VideoOutputManager("HDMI-A-1")

            def fail():
                raise RuntimeError("kscreen")

            manager.get_outputs = fail
            self.assertEqual(manager.projector_link_status(folder), "")

    def test_no_selected_output_is_unknown(self):
        manager = player.VideoOutputManager()
        self.assertEqual(manager.projector_link_status(), "")


class FullscreenWithoutBeamerTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.root.geometry("800x600+40+40")
        self.root.update()
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.root = self.root
        self.app._beamer_link_down = False
        self.app._posted_menu = None
        self.app.row_menu = None
        self.app._fullscreen_applied = False
        self.app._fullscreen_contain_after = None
        self.app._windowed_geometry = "1600x900+20+20"
        self.app.window_fullscreen = tk.BooleanVar(master=self.root, value=True)
        self.attributes = []

        def attributes(*args):
            self.attributes.append(args)
            return 0

        self.root.attributes = attributes
        self.root.overrideredirect = lambda *_args: None

    def tearDown(self):
        after_id = getattr(self.app, "_fullscreen_contain_after", None)
        if after_id:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self.root.destroy()
        set_language("en")

    def _manager(self, dedicated, output="eDP-1"):
        class Manager:
            video_output = output

            def has_dedicated_beamer(self):
                return dedicated

            def get_tk_output_geometry(self, _name):
                return (
                    self_root.winfo_width(),
                    self_root.winfo_height(),
                    self_root.winfo_rootx(),
                    self_root.winfo_rooty(),
                )

            def get_tk_control_output_geometry(self, prefer_x=None, prefer_y=None):
                return (800, 600, 40, 40)

        self_root = self.root
        return Manager()

    def test_the_only_screen_does_not_end_fullscreen(self):
        self.app.output_manager = self._manager(False)
        self.assertFalse(cinema_gui.VideoPlayerGUI._window_overlaps_beamer(self.app))
        cinema_gui.VideoPlayerGUI._apply_window_fullscreen(self.app)
        self.assertTrue(self.app.window_fullscreen.get())
        self.assertIn(("-fullscreen", True), self.attributes)
        self.assertNotIn(("-fullscreen", False), self.attributes)

    def test_a_covered_projector_still_leaves_fullscreen(self):
        self.app.output_manager = self._manager(True, "HDMI-A-1")
        self.assertTrue(cinema_gui.VideoPlayerGUI._window_overlaps_beamer(self.app))
        cinema_gui.VideoPlayerGUI._apply_window_fullscreen(self.app)
        self.assertEqual(self.attributes[-1], ("-fullscreen", False))
        self.assertTrue(self.app.window_fullscreen.get())


if __name__ == "__main__":
    unittest.main()
