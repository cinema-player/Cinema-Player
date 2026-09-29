#!/usr/bin/env python3
"""mpv version parsing and header label."""

import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import cinema_player as player


class ParseMpvVersionTests(unittest.TestCase):
    def test_plain_version(self):
        text = "mpv 0.38.0 Copyright © 2000-2024 mpv/MPlayer/mplayer2 projects\n"
        self.assertEqual(player.parse_mpv_version(text), "0.38.0")

    def test_strips_leading_v(self):
        text = "mpv v0.39.0 Copyright © 2000-2024 mpv/MPlayer/mplayer2 projects\n"
        self.assertEqual(player.parse_mpv_version(text), "0.39.0")

    def test_git_and_dirty_builds(self):
        self.assertEqual(
            player.parse_mpv_version("mpv 0.40.0-dirty Copyright © 2000-2025\n"),
            "0.40.0-dirty",
        )
        self.assertEqual(
            player.parse_mpv_version("mpv 0.38.0-107-gabc1234 Copyright © 2000-2024\n"),
            "0.38.0-107-gabc1234",
        )

    def test_ignores_noise_and_empty(self):
        self.assertEqual(player.parse_mpv_version(""), "")
        self.assertEqual(player.parse_mpv_version("FFmpeg library versions:\n"), "")
        self.assertEqual(player.parse_mpv_version("mpv Copyright © 2000-2024\n"), "")


class ReadMpvVersionTests(unittest.TestCase):
    def tearDown(self):
        player._mpv_version_cache.clear()

    def test_reads_stdout_and_caches(self):
        result = MagicMock(stdout="mpv 0.37.0 Copyright\n", stderr="")
        with patch("cinema_player.subprocess.run", return_value=result) as run:
            self.assertEqual(player.read_mpv_version("/usr/bin/mpv"), "0.37.0")
            self.assertEqual(player.read_mpv_version("/usr/bin/mpv"), "0.37.0")
        run.assert_called_once()

    def test_empty_path_skips_process(self):
        with patch("cinema_player.subprocess.run") as run:
            self.assertEqual(player.read_mpv_version(""), "")
        run.assert_not_called()


class HeaderVersionTextTests(unittest.TestCase):
    def test_places_mpv_beside_program_version(self):
        self.assertEqual(
            player.header_version_text("1.0.3", "0.38.0", "X11"),
            "v1.0.3  ·  mpv 0.38.0  ·  X11",
        )

    def test_omits_mpv_when_unknown(self):
        self.assertEqual(
            player.header_version_text("1.0.3", "", "Wayland"),
            "v1.0.3  ·  Wayland",
        )


if __name__ == "__main__":
    unittest.main()
