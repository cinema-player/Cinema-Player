#!/usr/bin/env python3
"""Beamer-block hwdec and drop-frame helpers."""

import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import cinema_player as player


class HwdecFormatTests(unittest.TestCase):
    def test_idle_is_empty(self):
        self.assertEqual(player.format_hwdec_current(None), "")
        self.assertEqual(player.format_hwdec_current(""), "")
        self.assertEqual(player.format_hwdec_current("none"), "")

    def test_keeps_decoder_name(self):
        self.assertEqual(player.format_hwdec_current("nvdec"), "nvdec")
        self.assertEqual(player.format_hwdec_current("no"), "no")
        self.assertEqual(player.format_hwdec_current("vaapi-copy"), "vaapi-copy")


class DropframeTests(unittest.TestCase):
    def test_counts_are_zero_when_missing(self):
        self.assertEqual(player.parse_mpv_count(None), 0)
        self.assertEqual(player.parse_mpv_count("nope"), 0)
        self.assertEqual(player.format_dropframe_counts(None, None), "mpv 0  decoder 0")
        self.assertFalse(player.frames_were_dropped(0, 0))

    def test_vo_or_decoder_drops_mark_dropped(self):
        self.assertEqual(
            player.format_dropframe_counts(3, 1, mpv_label="mpv", decoder_label="decoder"),
            "mpv 3  decoder 1",
        )
        self.assertTrue(player.frames_were_dropped(1, 0))
        self.assertTrue(player.frames_were_dropped(0, 2))
        self.assertFalse(player.frames_were_dropped("0", "0"))


class RefreshRateTests(unittest.TestCase):
    def test_25_fps_is_shown_at_50_hz(self):
        rates = player.VideoOutputManager.target_refresh_rates(25)
        self.assertEqual(rates[0][0], 50)
        self.assertIn(25, [rate for rate, _mult in rates])
        self.assertTrue(player.VideoOutputManager.refresh_matches(25, 50))
        self.assertTrue(player.VideoOutputManager.refresh_matches(25, 25))

    def test_50_fps_can_fall_back_to_25_hz(self):
        rates = [rate for rate, _mult in player.VideoOutputManager.target_refresh_rates(50)]
        self.assertEqual(rates[0], 50)
        self.assertIn(25, rates)
        self.assertTrue(player.VideoOutputManager.refresh_matches(50, 25))


if __name__ == "__main__":
    unittest.main()
