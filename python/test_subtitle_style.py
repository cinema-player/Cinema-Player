"""Subtitle style validation and projector-only MPV IPC tests."""
import unittest

from subtitle_style import (DEFAULT_SUBTITLE_STYLE, STYLE_PRESETS,
                            apply_subtitle_style, normalize_subtitle_style)


class FakeMPV:
    def __init__(self):
        self.calls = []
    def command(self, *args):
        self.calls.append(args)


class SubtitleStyleTests(unittest.TestCase):
    def test_defaults_and_presets(self):
        self.assertEqual(normalize_subtitle_style({}), DEFAULT_SUBTITLE_STYLE)
        self.assertGreater(STYLE_PRESETS["Große Schrift"]["font_size"], 46)

    def test_reject_invalid_color(self):
        with self.assertRaises(ValueError):
            normalize_subtitle_style({"color": "not a color"})

    def test_projector_ipc_properties(self):
        mpv = FakeMPV()
        apply_subtitle_style(mpv, {"font_size": 54, "position": 90})
        self.assertIn(("set_property", "sub-font-size", 54), mpv.calls)
        self.assertIn(("set_property", "sub-pos", 90), mpv.calls)
        self.assertTrue(all(call[0] == "set_property" for call in mpv.calls))


if __name__ == "__main__":
    unittest.main()
