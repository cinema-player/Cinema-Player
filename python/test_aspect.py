#!/usr/bin/env python3
"""16:9 mpv output for narrow formats and non-square PAR."""

import json
import sys
import unittest
from fractions import Fraction
from unittest.mock import MagicMock, patch

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import cinema_player as player


def _video(width, height, fps=25.0, aspect="--", pixel_aspect="--"):
    return player.VideoInfo(
        "/clip.mp4", width, height, fps, Fraction(fps),
        aspect=aspect, pixel_aspect=pixel_aspect,
    )


def _mode(width, height, refresh=50.0, output="HDMI-1"):
    return player.DisplayMode(output, width, height, refresh, name=f"{width}x{height}")


class Needs16x9OutputTests(unittest.TestCase):
    def test_square_16x9_is_left_alone(self):
        self.assertFalse(player.needs_16x9_output("16:9", "1:1", 1920, 1080))
        self.assertFalse(player.needs_16x9_output(width=1920, height=1080))

    def test_narrower_than_16x9_is_padded(self):
        self.assertTrue(player.needs_16x9_output("4:3", "1:1", 1440, 1080))
        self.assertTrue(player.needs_16x9_output("4:3", "16:15", 720, 576))
        self.assertTrue(player.needs_16x9_output(width=720, height=576))

    def test_non_square_par_on_16x9_is_padded(self):
        self.assertTrue(player.needs_16x9_output("16:9", "64:45", 720, 576))

    def test_wider_formats_are_left_alone(self):
        self.assertFalse(player.needs_16x9_output("21:9", "1:1", 2560, 1080))
        self.assertFalse(player.needs_16x9_output("1.85", "1:1", 1998, 1080))
        self.assertFalse(player.needs_16x9_output("2:1", "1:1", 2160, 1080))
        self.assertFalse(player.needs_16x9_output("21:9", "64:45", 2560, 1080))

    def test_missing_aspect_is_not_padded(self):
        self.assertFalse(player.needs_16x9_output())
        self.assertFalse(player.needs_16x9_output("--", "--"))


class MpvPictureFilterTests(unittest.TestCase):
    def test_filter_is_the_16x9_pad_for_4x3(self):
        entry = player.PlaylistEntry(
            path="/clip.mp4", aspect="4:3", pixel_aspect="1:1",
            width=1440, height=1080,
        )
        self.assertEqual(player.mpv_picture_filter(entry), player.MPV_16X9_VF)
        self.assertIn("setsar=1", player.MPV_16X9_VF)
        self.assertIn("16/9", player.MPV_16X9_VF)

    def test_wide_and_square_16x9_have_no_filter(self):
        wide = player.PlaylistEntry(
            path="/wide.mp4", aspect="21:9", pixel_aspect="1:1",
            width=2560, height=1080,
        )
        hd = player.PlaylistEntry(
            path="/hd.mp4", aspect="16:9", pixel_aspect="1:1",
            width=1920, height=1080,
        )
        self.assertEqual(player.mpv_picture_filter(wide), "")
        self.assertEqual(player.mpv_picture_filter(hd), "")

    def test_compose_keeps_the_pad_in_front_of_a_still_fade(self):
        fade = "lavfi=[eq=brightness=-1.000]"
        self.assertEqual(
            player.compose_mpv_vf(player.MPV_16X9_VF, fade),
            f"{player.MPV_16X9_VF},{fade}",
        )
        self.assertEqual(player.compose_mpv_vf("", fade), fade)
        self.assertEqual(player.compose_mpv_vf(player.MPV_16X9_VF, ""), player.MPV_16X9_VF)


class ProjectionSizeTests(unittest.TestCase):
    def setUp(self):
        self.manager = player.VideoOutputManager("HDMI-1")
        self.modes = [
            _mode(1920, 1080, 50),
            _mode(1920, 1080, 25),
            _mode(2560, 1080, 50),
            _mode(720, 576, 50),
        ]

    def test_4x3_uses_native_16x9(self):
        with patch.object(self.manager, "native_resolution", return_value=(1920, 1080)):
            width, height = self.manager.projection_size_for_video(
                _video(1440, 1080, aspect="4:3", pixel_aspect="1:1"),
                self.modes,
            )
        self.assertEqual((width, height), (1920, 1080))

    def test_anamorphic_16x9_uses_native_16x9(self):
        with patch.object(self.manager, "native_resolution", return_value=(1920, 1080)):
            width, height = self.manager.projection_size_for_video(
                _video(720, 576, aspect="16:9", pixel_aspect="64:45"),
                self.modes,
            )
        self.assertEqual((width, height), (1920, 1080))

    def test_21x9_keeps_storage_size(self):
        with patch.object(self.manager, "native_resolution", return_value=(1920, 1080)):
            width, height = self.manager.projection_size_for_video(
                _video(2560, 1080, aspect="21:9", pixel_aspect="1:1"),
                self.modes,
            )
        self.assertEqual((width, height), (2560, 1080))

    def test_square_16x9_keeps_storage_size(self):
        with patch.object(self.manager, "native_resolution", return_value=(1920, 1080)):
            width, height = self.manager.projection_size_for_video(
                _video(1920, 1080, aspect="16:9", pixel_aspect="1:1"),
                self.modes,
            )
        self.assertEqual((width, height), (1920, 1080))

    def test_falls_back_to_a_computed_16x9_canvas(self):
        self.manager.video_output = ""
        width, height = self.manager.projection_size_for_video(
            _video(720, 576, aspect="4:3", pixel_aspect="16:15"),
            [],
        )
        self.assertEqual((width, height), (1024, 576))

    def test_find_best_mode_picks_16x9_refresh_for_4x3(self):
        video = _video(720, 576, fps=25, aspect="4:3", pixel_aspect="16:15")
        with patch.object(self.manager, "get_modes", return_value=self.modes), \
                patch.object(self.manager, "native_resolution", return_value=(1920, 1080)):
            mode, matched = self.manager.find_best_mode(video, create=False)
        self.assertTrue(matched)
        self.assertEqual((mode.width, mode.height), (1920, 1080))
        self.assertEqual(mode.refresh, 50.0)

    def test_find_best_mode_keeps_21x9_storage(self):
        video = _video(2560, 1080, fps=25, aspect="21:9", pixel_aspect="1:1")
        with patch.object(self.manager, "get_modes", return_value=self.modes), \
                patch.object(self.manager, "native_resolution", return_value=(1920, 1080)):
            mode, matched = self.manager.find_best_mode(video, create=False)
        self.assertTrue(matched)
        self.assertEqual((mode.width, mode.height), (2560, 1080))


class LoadfilePictureFilterTests(unittest.TestCase):
    def tearDown(self):
        player._mpv_version_cache.clear()

    def test_mpv_038_sends_the_pad_as_a_per_file_option(self):
        player._mpv_version_cache["/usr/bin/mpv"] = "0.38.0"
        ctl = player.MPVController("t", "/usr/bin/mpv")
        ctl.socket = MagicMock()
        ctl.load_file("/tmp/clip.mp4", play=True, vf=player.MPV_16X9_VF)
        payload = json.loads(ctl.socket.sendall.call_args[0][0].decode())
        self.assertEqual(payload["command"][4]["vf"], player.MPV_16X9_VF)
        self.assertEqual(ctl.output_vf, player.MPV_16X9_VF)

    def test_mpv_037_keeps_the_pad_off_the_option_string(self):
        player._mpv_version_cache["/usr/bin/mpv"] = "0.37.0"
        ctl = player.MPVController("t", "/usr/bin/mpv")
        ctl.socket = MagicMock()
        ctl.load_file("/tmp/clip.mp4", play=True, sid="no", vf=player.MPV_16X9_VF)
        payload = json.loads(ctl.socket.sendall.call_args[0][0].decode())
        packed = payload["command"][3]
        self.assertEqual(packed, "sid=no")
        self.assertNotIn("vf=", packed)
        self.assertEqual(ctl.output_vf, player.MPV_16X9_VF)

    def test_apply_pending_range_restores_the_pad(self):
        ctl = player.MPVController("t", "/usr/bin/mpv")
        sent = []
        ctl.socket = object()
        ctl.command = lambda *args: sent.append(args)
        ctl.output_vf = player.MPV_16X9_VF
        ctl.play_on_load = True
        ctl.apply_pending_range()
        self.assertIn(("set_property", "vf", player.MPV_16X9_VF), sent)

    def test_apply_picture_filter_stacks_a_still_fade(self):
        ctl = player.MPVController("t", "/usr/bin/mpv")
        sent = []
        ctl.socket = object()
        ctl.command = lambda *args: sent.append(args)
        ctl.output_vf = player.MPV_16X9_VF
        fade = "lavfi=[eq=brightness=-1.000]"
        ctl.apply_picture_filter(fade)
        self.assertEqual(
            sent[-1],
            ("set_property", "vf", f"{player.MPV_16X9_VF},{fade}"),
        )


if __name__ == "__main__":
    unittest.main()
