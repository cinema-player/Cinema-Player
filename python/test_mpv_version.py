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

    def test_version_tuple(self):
        self.assertEqual(player.mpv_version_tuple("0.37.0"), (0, 37, 0))
        self.assertEqual(player.mpv_version_tuple("0.38.0-107-gabc"), (0, 38, 0))
        self.assertEqual(player.mpv_version_tuple(""), (0, 0, 0))


class LoadfileCommandTests(unittest.TestCase):
    def tearDown(self):
        player._mpv_version_cache.clear()

    def test_mpv_037_uses_option_string(self):
        player._mpv_version_cache["/mpv"] = "0.37.0"
        command = player.mpv_loadfile_command(
            "/clip.mp4", options={"sid": "no", "start": "1.0"}, mpv_path="/mpv",
        )
        self.assertEqual(command[:3], ["loadfile", "/clip.mp4", "replace"])
        self.assertEqual(command[3], "sid=no,start=1.0")
        self.assertEqual(len(command), 4)

    def test_mpv_038_uses_index_and_map(self):
        player._mpv_version_cache["/mpv"] = "0.38.0"
        command = player.mpv_loadfile_command(
            "/clip.mp4", options={"sid": "no", "start": "1.0"}, mpv_path="/mpv",
        )
        self.assertEqual(command[:4], ["loadfile", "/clip.mp4", "replace", 0])
        self.assertEqual(command[4], {"sid": "no", "start": "1.0"})

    def test_plain_replace_has_no_options(self):
        self.assertEqual(
            player.mpv_loadfile_command("/clip.mp4"),
            ["loadfile", "/clip.mp4", "replace"],
        )


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


class ToolVersionTests(unittest.TestCase):
    def test_ffmpeg_version_line(self):
        text = "ffmpeg version 8.0.1-3ubuntu2 Copyright (c) 2000-2025 the FFmpeg developers\n"
        self.assertEqual(player.parse_tool_version(text), "8.0.1-3ubuntu2")

    def test_edid_decode_sha(self):
        self.assertEqual(
            player.parse_tool_version("edid-decode SHA: cb74358c2896 2025-12-10 22:39:09\n"),
            "cb74358c2896",
        )

    def test_usage_text_has_no_version(self):
        self.assertEqual(player.parse_tool_version("usage: gdctl [-h] COMMAND ...\n"), "")

    def test_missing_program(self):
        with patch.object(player.shutil, "which", return_value=None):
            self.assertIsNone(player.read_tool_version("ffmpeg", ["-version"]))

    def test_about_rows_start_with_python_tk_and_mpv(self):
        found = {"ffmpeg": "8.0.1", "ffprobe": None}

        def lookup(binary, _args):
            return found.get(binary, "")

        with patch.object(player, "read_mpv_version", return_value="0.41.0"), \
                patch.object(player, "read_tool_version", side_effect=lookup):
            rows = dict(player.about_package_rows(
                "/usr/bin/mpv", "3.12.13", "Tk 8.6.16, Tcl 8.6.16",
            ))
        self.assertEqual(rows["Python"], "3.12.13")
        self.assertEqual(rows["Tcl/Tk"], "Tk 8.6.16, Tcl 8.6.16")
        self.assertEqual(rows["mpv"], "0.41.0")
        self.assertEqual(rows["FFmpeg"], "8.0.1")
        self.assertIsNone(rows["FFprobe"])
        self.assertIn("xrandr", rows)
        self.assertIn("gdctl", rows)


class CopyrightFileTests(unittest.TestCase):
    def test_reads_the_usual_notice(self):
        info = player.read_copyright()
        self.assertEqual(info["notice"], "Copyright (C) 2026 Thomas Winkler")
        self.assertEqual(info["email"], "thomas.winkler@iggmp.net")
        self.assertEqual(info["url"], "http://cinema-player.github.io")

    def test_missing_file_is_empty(self):
        self.assertEqual(
            player.read_copyright("/tmp/cinema-player-no-such-copyright"),
            {"notice": "", "email": "", "url": ""},
        )


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
