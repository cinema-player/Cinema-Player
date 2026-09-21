#!/usr/bin/env python3
"""Parser and mode-selection tests for DeckLink integration (no hardware)."""

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import decklink
from cinema_player import DisplayMode, VideoOutputManager


FFMPEG_SINKS = """
Auto-detected sinks for decklink:
DeckLink Mini Monitor 4K [decklink]
DeckLink SDI (1) [decklink]
"""

FFMPEG_LIST_DEVICES = """
[decklink @ 0x55] Blackmagic DeckLink output devices:
    'DeckLink Mini Monitor 4K'
    'DeckLink Quad 2 (2)'
"""

FFMPEG_FORMATS = """
[decklink @ 0x55] Supported formats for 'DeckLink Mini Monitor 4K':
        format_code     description
        ntsc            720x486i 29.97 fps (interlaced)
        pal             720x576i 25 fps (interlaced)
        Hp2398          1920x1080p 24000/1001
        Hp24            1920x1080p 24
        Hp25            1920x1080 25p
        Hp50            1920x1080p 50
        Up25            3840x2160p 25
        hp50            1280x720p 50
"""


class DeckLinkParseTests(unittest.TestCase):
    def test_output_id_and_label(self):
        output_id = "decklink:DeckLink Mini Monitor 4K"
        self.assertTrue(decklink.is_decklink_output(output_id))
        self.assertFalse(decklink.is_decklink_output("HDMI-1"))
        self.assertEqual(
            decklink.decklink_device_name(output_id),
            "DeckLink Mini Monitor 4K",
        )
        self.assertEqual(
            decklink.format_output_label(output_id),
            "DeckLink Mini Monitor 4K",
        )
        self.assertEqual(
            decklink.format_output_label("decklink:UltraStudio 4K"),
            "DeckLink · UltraStudio 4K",
        )
        self.assertEqual(
            decklink.parse_output_id("decklink:DeckLink Mini Monitor 4K|hdmi"),
            ("DeckLink Mini Monitor 4K", "hdmi"),
        )
        self.assertEqual(
            decklink.decklink_device_name("decklink:DeckLink Mini Monitor 4K|sdi"),
            "DeckLink Mini Monitor 4K",
        )
        self.assertEqual(
            decklink.format_output_label("decklink:DeckLink Mini Monitor 4K|sdi"),
            "DeckLink Mini Monitor 4K · SDI",
        )
        self.assertEqual(
            decklink.make_output_id("DeckLink Mini Monitor 4K", "hdmi"),
            "decklink:DeckLink Mini Monitor 4K|hdmi",
        )

    def test_infer_connectors_only_when_card_has_several_ports(self):
        self.assertEqual(
            decklink.infer_connectors("DeckLink Mini Monitor 4K"),
            ("sdi", "hdmi"),
        )
        self.assertEqual(
            decklink.infer_connectors("DeckLink 4K Extreme 12G"),
            ("sdi", "hdmi"),
        )
        self.assertEqual(
            decklink.infer_connectors("UltraStudio 4K Mini"),
            ("sdi", "hdmi"),
        )
        self.assertEqual(
            decklink.infer_connectors("DeckLink SDI (1)"),
            ("sdi",),
        )
        self.assertEqual(
            decklink.infer_connectors("DeckLink Quad 2 (2)"),
            ("sdi",),
        )
        self.assertEqual(
            decklink.infer_connectors("Intensity Pro 4K"),
            ("hdmi",),
        )
        self.assertEqual(
            decklink.infer_connectors("DeckLink"),
            ("sdi",),
        )
        self.assertTrue(decklink.needs_connector_selector(("sdi", "hdmi")))
        self.assertFalse(decklink.needs_connector_selector(("sdi",)))
        self.assertEqual(decklink.connectors_from_mask(1 | 2), ("sdi", "hdmi"))
        self.assertEqual(decklink.connectors_from_mask(4), ("optical",))

    def test_dual_card_expands_output_ids(self):
        mini = decklink.DeckLinkDevice(name="DeckLink Mini Monitor 4K")
        self.assertEqual(
            mini.output_ids(),
            [
                "decklink:DeckLink Mini Monitor 4K|sdi",
                "decklink:DeckLink Mini Monitor 4K|hdmi",
            ],
        )
        sdi = decklink.DeckLinkDevice(name="DeckLink SDI (1)")
        self.assertEqual(sdi.output_ids(), ["decklink:DeckLink SDI (1)"])
        groups = decklink.group_decklink_outputs([
            "decklink:DeckLink Mini Monitor 4K|sdi",
            "decklink:DeckLink Mini Monitor 4K|hdmi",
            "decklink:DeckLink SDI (1)",
        ])
        self.assertEqual(groups[0][0], "DeckLink Mini Monitor 4K")
        self.assertEqual(len(groups[0][1]), 2)
        self.assertEqual(groups[1][0], "DeckLink SDI (1)")

    def test_canonicalize_old_id_defaults_to_sdi(self):
        device = decklink.DeckLinkDevice(name="DeckLink Mini Monitor 4K", index=0)
        with patch.object(decklink, "list_decklink_devices", return_value=[device]):
            self.assertEqual(
                decklink.canonicalize_output_id("decklink:DeckLink Mini Monitor 4K"),
                "decklink:DeckLink Mini Monitor 4K|sdi",
            )
            self.assertEqual(
                decklink.canonicalize_output_id("decklink:DeckLink Mini Monitor 4K|hdmi"),
                "decklink:DeckLink Mini Monitor 4K|hdmi",
            )
            found = decklink.find_device("decklink:DeckLink Mini Monitor 4K|hdmi")
            self.assertIs(found, device)
        sdi = decklink.DeckLinkDevice(name="DeckLink SDI (1)", index=1)
        with patch.object(decklink, "list_decklink_devices", return_value=[sdi]):
            self.assertEqual(
                decklink.canonicalize_output_id("decklink:DeckLink SDI (1)"),
                "decklink:DeckLink SDI (1)",
            )
        self.assertFalse(decklink.configure_video_connection("missing-card", "sdi"))

    def test_parse_sinks(self):
        names = decklink.parse_sinks(FFMPEG_SINKS)
        self.assertEqual(
            names,
            ["DeckLink Mini Monitor 4K", "DeckLink SDI (1)"],
        )

    def test_parse_list_devices(self):
        names = decklink.parse_sinks(FFMPEG_LIST_DEVICES)
        self.assertIn("DeckLink Mini Monitor 4K", names)
        self.assertIn("DeckLink Quad 2 (2)", names)

    def test_parse_formats_skips_interlaced(self):
        modes = decklink.parse_list_formats(FFMPEG_FORMATS)
        sizes = {(m.width, m.height, round(m.refresh, 3)) for m in modes}
        self.assertIn((1920, 1080, 25.0), sizes)
        self.assertIn((3840, 2160, 25.0), sizes)
        self.assertIn((1280, 720, 50.0), sizes)
        self.assertTrue(any(abs(m.refresh - 24000 / 1001) < 0.02 for m in modes))
        self.assertFalse(any(m.interlaced for m in modes))
        self.assertFalse(any(m.height in (486, 576) for m in modes))
        hp25 = next(m for m in modes if m.format_code == "Hp25")
        self.assertEqual(hp25.gst_mode, "1080p25")

    def test_fps_arg(self):
        self.assertEqual(decklink.fps_arg(25), "25")
        self.assertEqual(decklink.fps_arg(24000 / 1001), "24000/1001")
        self.assertEqual(decklink.gst_mode_name(1920, 1080, 25), "1080p25")
        self.assertEqual(decklink.gst_mode_name(3840, 2160, 50), "2160p50")

    def test_fallback_modes_include_hd_and_uhd(self):
        modes = decklink.fallback_modes()
        self.assertTrue(any(m.width == 1920 and abs(m.refresh - 25) < 0.01 for m in modes))
        self.assertTrue(any(m.width == 3840 and abs(m.refresh - 24) < 0.01 for m in modes))

    def test_video_filter_letterbox(self):
        vf = decklink.video_filter(1920, 1080, 25)
        self.assertIn("scale=1920:1080:force_original_aspect_ratio=decrease", vf)
        self.assertIn("pad=1920:1080", vf)
        self.assertIn("fps=25", vf)
        self.assertIn("format=uyvy422", vf)

    def test_mpv_arguments_pick_container(self):
        mode = DisplayMode("decklink:card", 1920, 1080, 25, name="Hp25")
        ffmpeg_args = decklink.mpv_arguments(mode, "ffmpeg", audio_file="/tmp/silence.wav")
        self.assertIn("--o=-", ffmpeg_args)
        self.assertIn("--of=nut", ffmpeg_args)
        self.assertIn("--oac=pcm_s16le", ffmpeg_args)
        gst_args = decklink.mpv_arguments(mode, "gstreamer", audio_file="/tmp/silence.wav")
        self.assertIn("--of=yuv4mpegpipe", gst_args)
        self.assertIn("--no-audio", gst_args)


class DeckLinkOutputManagerTests(unittest.TestCase):
    def test_find_best_mode_prefers_matching_decklink_mode(self):
        manager = VideoOutputManager("decklink:test")
        hd25 = DisplayMode("decklink:test", 1920, 1080, 25.0, name="Hp25")
        hd50 = DisplayMode("decklink:test", 1920, 1080, 50.0, name="Hp50")
        uhd25 = DisplayMode("decklink:test", 3840, 2160, 25.0, name="Up25")
        manager.get_modes = lambda _name: [hd25, hd50, uhd25]
        video = SimpleNamespace(width=1920, height=1080, fps=25.0)
        mode, matched = manager.find_best_mode(video)
        self.assertTrue(matched)
        self.assertEqual(mode.name, "Hp25")
        self.assertEqual(mode.refresh, 25.0)

    def test_find_best_mode_accepts_double_rate(self):
        manager = VideoOutputManager("decklink:test")
        hd50 = DisplayMode("decklink:test", 1920, 1080, 50.0, name="Hp50")
        manager.get_modes = lambda _name: [hd50]
        video = SimpleNamespace(width=1920, height=1080, fps=25.0)
        mode, matched = manager.find_best_mode(video)
        self.assertTrue(matched)
        self.assertEqual(mode.refresh, 50.0)

    def test_has_dedicated_beamer_with_only_decklink(self):
        manager = VideoOutputManager()
        manager.get_desktop_outputs = lambda: ["eDP-1"]
        manager.get_decklink_outputs = lambda: ["decklink:DeckLink Mini Monitor 4K"]
        self.assertTrue(manager.has_dedicated_beamer())
        manager.get_decklink_outputs = lambda: []
        self.assertFalse(manager.has_dedicated_beamer())

    def test_select_old_decklink_id_uses_sdi(self):
        device = decklink.DeckLinkDevice(name="DeckLink Mini Monitor 4K", index=0)
        outputs = [
            "eDP-1",
            "decklink:DeckLink Mini Monitor 4K|sdi",
            "decklink:DeckLink Mini Monitor 4K|hdmi",
        ]
        manager = VideoOutputManager()
        manager.get_outputs = lambda: list(outputs)
        with patch.object(decklink, "list_decklink_devices", return_value=[device]):
            chosen = manager.select_video_output("decklink:DeckLink Mini Monitor 4K")
        self.assertEqual(chosen, "decklink:DeckLink Mini Monitor 4K|sdi")


if __name__ == "__main__":
    unittest.main()
