#!/usr/bin/env python3
"""UI text-size helpers."""

import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import cinema_player as player


class TextSizeTests(unittest.TestCase):
    def tearDown(self):
        player.apply_text_size(player.DEFAULT_TEXT_SIZE)

    def test_clamp_rejects_junk_and_snaps(self):
        self.assertEqual(player.clamp_text_size("nope"), 0)
        self.assertEqual(player.clamp_text_size(None), 0)
        self.assertEqual(player.clamp_text_size(9), 2)
        self.assertEqual(player.clamp_text_size(-9), -2)
        self.assertEqual(player.clamp_text_size(1), 1)

    def test_apply_shifts_ui_font(self):
        self.assertEqual(player.apply_text_size(0), 0)
        default = player.FONT_UI[1]
        player.apply_text_size(2)
        self.assertEqual(player.FONT_UI[1], default + 2)
        self.assertEqual(player.FONT_SMALL[1], player.FONT_UI[1] - 1)
        player.apply_text_size(-2)
        self.assertEqual(player.FONT_UI[1], default - 2)
        self.assertGreaterEqual(player.FONT_SMALL[1], 6)


if __name__ == "__main__":
    unittest.main()
