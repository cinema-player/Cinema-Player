#!/usr/bin/env python3
"""Bundled Inter must stay visible without hiding system fonts."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))


def _ensure_real_font_setup():
    current = sys.modules.get("font_setup")
    if current is not None and type(current).__module__ == "unittest.mock":
        del sys.modules["font_setup"]


_ensure_real_font_setup()

import font_setup


class FontConfigTests(unittest.TestCase):
    def test_document_keeps_system_fonts_and_adds_the_app_directory(self):
        text = font_setup.fontconfig_source(
            "/opt/cinema/fonts", "/etc/fonts/fonts.conf"
        )
        self.assertIn('ignore_missing="yes"', text)
        self.assertIn("/etc/fonts/fonts.conf", text)
        self.assertIn("<dir>/opt/cinema/fonts</dir>", text)

    def test_paths_are_escaped(self):
        text = font_setup.fontconfig_source("/tmp/a&b<c>")
        self.assertIn("/tmp/a&amp;b&lt;c&gt;", text)
        self.assertNotIn("/tmp/a&b<c>", text)


if __name__ == "__main__":
    unittest.main()
