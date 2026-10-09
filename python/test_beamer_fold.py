#!/usr/bin/env python3
"""Collapsed beamer readout and the arrow that opens the full block."""

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
from cinema_player import VideoOutputManager
from language import set_language, t


class _Mode:
    def __init__(self, width, height, refresh):
        self.width = width
        self.height = height
        self.refresh = refresh


class _Output:
    def __init__(self, mode=None):
        self.video_output = "HDMI-A-1"
        self.video_mode = mode
        self.color_format = "YCbCr444"
        self.refresh_close = VideoOutputManager.refresh_close
        self.refresh_matches = VideoOutputManager.refresh_matches
        self.half_refresh_rate = VideoOutputManager.half_refresh_rate

    def get_current_mode(self, _name):
        return self.video_mode

    def select_video_output(self):
        return None

    def get_modes(self, _output):
        return [
            _Mode(3840, 2160, 24.0),
            _Mode(3840, 2160, 60.0),
            _Mode(1920, 1080, 24.0),
            _Mode(1920, 1080, 50.0),
        ]

    def get_color_formats(self, _output):
        return ["RGB", "YCbCr444", "YCbCr422"]

    def get_output_device_name(self):
        return "Cinema Projector"


def _arrow_points(canvas):
    item = canvas.find_all()[0]
    coords = canvas.coords(item)
    return list(zip(coords[0::2], coords[1::2]))


def _tip_is_down(points):
    tip = max(points, key=lambda point: point[1])
    others = [point for point in points if point is not tip]
    return tip[1] > others[0][1] and abs(tip[0] - (others[0][0] + others[1][0]) / 2) < 1


def _tip_is_up(points):
    tip = min(points, key=lambda point: point[1])
    others = [point for point in points if point is not tip]
    return tip[1] < others[0][1] and abs(tip[0] - (others[0][0] + others[1][0]) / 2) < 1


class BeamerFoldTests(unittest.TestCase):
    def setUp(self):
        set_language("de")
        self.root = tk.Tk()
        self.root.geometry("720x480+40+40")
        self.app = cinema_gui.VideoPlayerGUI.__new__(cinema_gui.VideoPlayerGUI)
        self.app.beamer_details_open = False
        parent = tk.Frame(self.root)
        parent.pack(fill="both", expand=True)
        cinema_gui.VideoPlayerGUI._build_beamer(self.app, parent)
        self.app.output_manager = _Output(_Mode(1920, 1080, 24.0))
        self.app.program_state = "OFF"
        self.app.beamer_output = tk.StringVar(value="HDMI-A-1")
        self.app._beamer_caps_cache = None
        self.app.current_entry = lambda: None
        self.app._preview_clip = lambda: None

    def tearDown(self):
        self.root.destroy()
        set_language("en")

    def test_language_keys(self):
        self.assertEqual(t("beamer_resolution"), "Auflösung")
        self.assertEqual(t("beamer_rate"), "Bildrate")
        self.assertEqual(t("beamer_colorspace"), "Farbraum")
        set_language("en")
        self.assertEqual(t("beamer_resolution"), "Resolution")
        self.assertEqual(t("beamer_rate"), "Frame rate")
        self.assertEqual(t("beamer_colorspace"), "Color space")

    def test_starts_collapsed_on_set_values(self):
        self.root.update_idletasks()
        self.assertEqual(self.app.beamer_summary.winfo_manager(), "pack")
        self.assertEqual(self.app.beamer_details.winfo_manager(), "")
        self.assertTrue(_tip_is_down(_arrow_points(self.app.beamer_fold_arrow)))
        self.assertEqual(self.app.beamer_fold_tip.text, t("beamer_show_details"))
        cinema_gui.VideoPlayerGUI.refresh_beamer(self.app)
        self.assertEqual(self.app.beamer_resolution.cget("text"), "1920x1080")
        self.assertEqual(self.app.beamer_rate.cget("text"), "24p")
        self.assertEqual(self.app.beamer_colorspace_value.cget("text"), "YCbCr444")
        self.assertEqual(self.app.beamer_ok.cget("text"), "OK")

    def test_arrow_opens_and_closes_the_full_readout(self):
        cinema_gui.VideoPlayerGUI.refresh_beamer(self.app)
        self.root.update()
        self.app.beamer_fold_arrow.event_generate("<Button-1>")
        self.root.update_idletasks()
        self.assertTrue(self.app.beamer_details_open)
        self.assertEqual(self.app.beamer_summary.winfo_manager(), "")
        self.assertEqual(self.app.beamer_details.winfo_manager(), "pack")
        self.assertTrue(_tip_is_up(_arrow_points(self.app.beamer_fold_arrow)))
        self.assertEqual(self.app.beamer_fold_tip.text, "Nur eingestellte Werte anzeigen")
        self.assertEqual(self.app.beamer_device.cget("text"), "Cinema Projector")
        self.assertEqual(self.app.beamer_aspect.cget("text"), "16:9")
        self.assertIn("24p", self.app.beamer_rates._signature[1])
        self.assertIn("1920x1080", self.app.beamer_resolutions._signature[1])
        self.assertIn("YCbCr444", self.app.beamer_colorspaces._signature[1])

        self.app.beamer_fold_arrow.event_generate("<Button-1>")
        self.root.update_idletasks()
        self.assertFalse(self.app.beamer_details_open)
        self.assertEqual(self.app.beamer_summary.winfo_manager(), "pack")
        self.assertEqual(self.app.beamer_details.winfo_manager(), "")
        self.assertTrue(_tip_is_down(_arrow_points(self.app.beamer_fold_arrow)))

    def test_missing_mode_clears_the_summary(self):
        self.app.output_manager.video_mode = None
        self.app.output_manager.video_output = ""
        cinema_gui.VideoPlayerGUI.refresh_beamer(self.app)
        self.assertEqual(self.app.beamer_resolution.cget("text"), "--")
        self.assertEqual(self.app.beamer_rate.cget("text"), "--")
        self.assertEqual(self.app.beamer_colorspace_value.cget("text"), "--")
        self.assertEqual(self.app.beamer_ok.cget("text"), "--")


if __name__ == "__main__":
    unittest.main()
