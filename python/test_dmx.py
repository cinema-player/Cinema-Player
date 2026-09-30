#!/usr/bin/env python3
"""DMX/Art-Net house lights and playlist cue resolution (no network)."""

import struct
import unittest

import dmx


class PresetTests(unittest.TestCase):
    def test_normalize_preset_accepts_german_and_english(self):
        self.assertEqual(dmx.normalize_preset("Hell"), "bright")
        self.assertEqual(dmx.normalize_preset("mittel"), "medium")
        self.assertEqual(dmx.normalize_preset("dunkel"), "dark")
        self.assertEqual(dmx.normalize_preset("bright"), "bright")
        self.assertEqual(dmx.normalize_preset(""), "")
        self.assertEqual(dmx.normalize_preset("auto"), "")

    def test_brightness_defaults(self):
        self.assertEqual(dmx.brightness_for_preset("bright"), 100)
        self.assertEqual(dmx.brightness_for_preset("medium"), 40)
        self.assertEqual(dmx.brightness_for_preset("dark"), 0)
        self.assertEqual(dmx.brightness_for_preset(""), 0)

    def test_custom_presets(self):
        table = {"bright": 90, "medium": 35, "dark": 5}
        self.assertEqual(dmx.brightness_for_preset("mittel", table), 35)
        self.assertEqual(dmx.percent_to_dmx(0), 0)
        self.assertEqual(dmx.percent_to_dmx(100), 255)
        self.assertEqual(dmx.percent_to_dmx(40), 102)

    def test_start_and_end_cues(self):
        self.assertEqual(dmx.resolve_start_preset(""), "dark")
        self.assertEqual(dmx.resolve_start_preset("hell"), "bright")
        self.assertEqual(dmx.resolve_end_preset("", autoplay_continues=False), "bright")
        self.assertEqual(dmx.resolve_end_preset("", autoplay_continues=True), "dark")
        self.assertEqual(dmx.resolve_end_preset("mittel", autoplay_continues=True), "medium")
        self.assertEqual(dmx.play_preset(""), "")
        self.assertEqual(dmx.play_preset("dark"), "")
        self.assertEqual(dmx.play_preset("dunkel"), "")
        self.assertEqual(dmx.play_preset("mittel"), "medium")
        self.assertEqual(dmx.play_preset("hell"), "bright")
        self.assertEqual(dmx.resolve_start_preset("mittel"), "medium")

    def test_already_at_preset_skips_repeat_dark(self):
        self.assertTrue(dmx.already_at_preset("dark", "dunkel"))
        self.assertTrue(dmx.already_at_preset("dark", "dark"))
        self.assertFalse(dmx.already_at_preset("", "dark"))
        self.assertFalse(dmx.already_at_preset("bright", "dark"))
        self.assertFalse(dmx.already_at_preset("dark", ""))

    def test_config_roundtrip(self):
        output = dmx.DmxOutput(host="10.0.0.20", universe=2, channels="1, 3-4")
        dumped = dmx.dump_lights_config(
            output, {"bright": 80, "medium": 30, "dark": 0}, 1800,
        )
        loaded, presets, transition, enabled, start_lead, end_lead = dmx.load_lights_config(dumped)
        self.assertEqual(loaded.host, "10.0.0.20")
        self.assertEqual(loaded.universe, 2)
        self.assertEqual(loaded.channels, [1, 3, 4])
        self.assertEqual(presets["bright"], 80)
        self.assertEqual(transition, 1800)
        self.assertTrue(enabled)
        self.assertEqual(start_lead, 0)
        self.assertEqual(end_lead, 0)

    def test_control_switch_roundtrip(self):
        dumped = dmx.dump_lights_config(dmx.DmxOutput(), {}, 2500, False)
        self.assertFalse(dumped["enabled"])
        _, _, _, enabled, _, _ = dmx.load_lights_config(dumped)
        self.assertFalse(enabled)
        output, _, _, enabled, start_lead, end_lead = dmx.load_lights_config({})
        self.assertTrue(enabled)
        self.assertFalse(output.ready())
        self.assertEqual(start_lead, 0)
        self.assertEqual(end_lead, 0)

    def test_old_shelly_config_is_not_ready(self):
        output, presets, *_ = dmx.load_lights_config({
            "enabled": True,
            "devices": [{"host": "192.168.1.20", "enabled": True}],
            "presets": {"bright": 70},
        })
        self.assertFalse(output.ready())
        self.assertEqual(presets["bright"], 70)

    def test_play_delay_and_leads(self):
        self.assertEqual(dmx.play_delay_ms(2500, 0), 2500)
        self.assertEqual(dmx.play_delay_ms(2500, 500), 2000)
        self.assertEqual(dmx.play_delay_ms(2500, 4000), 0)
        self.assertEqual(dmx.seconds_to_ms("2.5"), 2500)
        dumped = dmx.dump_lights_config(dmx.DmxOutput(), {}, 2500, True, 800, 5000)
        _, _, _, _, start_lead, end_lead = dmx.load_lights_config(dumped)
        self.assertEqual(start_lead, 800)
        self.assertEqual(end_lead, 5000)
        _, _, _, _, start_lead, end_lead = dmx.load_lights_config(
            {"start_lead_s": 1.5, "end_lead_s": 3}
        )
        self.assertEqual(start_lead, 1500)
        self.assertEqual(end_lead, 3000)


class ArtNetTests(unittest.TestCase):
    def test_parse_and_format_channels(self):
        self.assertEqual(dmx.parse_channels("1, 2, 5-7"), [1, 2, 5, 6, 7])
        self.assertEqual(dmx.parse_channels([3, 1, 1, 0, 513]), [3, 1])
        self.assertEqual(dmx.format_channels([1, 4]), "1, 4")
        self.assertEqual(dmx.parse_channels(""), [])

    def test_output_ready(self):
        self.assertFalse(dmx.DmxOutput().ready())
        self.assertFalse(dmx.DmxOutput(host="10.0.0.1").ready())
        self.assertTrue(dmx.DmxOutput(host="10.0.0.1", channels="1").ready())

    def test_artnet_packet_layout(self):
        packet = dmx.artnet_output_packet(3, dmx.frame_for_level([1, 2], 100), sequence=7)
        self.assertTrue(packet.startswith(b"Art-Net\x00"))
        self.assertEqual(struct.unpack_from("<H", packet, 8)[0], 0x5000)
        self.assertEqual(struct.unpack_from(">H", packet, 10)[0], 14)
        self.assertEqual(packet[12], 7)
        self.assertEqual(struct.unpack_from("<H", packet, 14)[0], 3)
        self.assertEqual(struct.unpack_from(">H", packet, 16)[0], 512)
        self.assertEqual(len(packet), 18 + 512)
        self.assertEqual(packet[18], 255)
        self.assertEqual(packet[19], 255)
        self.assertEqual(packet[20], 0)

    def test_apply_sends_artnet_without_socket(self):
        sent = []
        controller = dmx.ArtNetController(send=lambda host, port, packet: sent.append((host, port, packet)))
        output = dmx.DmxOutput(host="10.1.2.3", port=6454, universe=1, channels="4")
        error = controller.apply(output, 40, 0)
        self.assertEqual(error, "")
        self.assertEqual(len(sent), 1)
        host, port, packet = sent[0]
        self.assertEqual(host, "10.1.2.3")
        self.assertEqual(port, 6454)
        self.assertEqual(packet[18 + 3], 102)
        self.assertEqual(controller.level, 40)
        controller.close()

    def test_apply_without_channel_is_not_ready(self):
        controller = dmx.ArtNetController(send=lambda *_args: None)
        self.assertEqual(controller.apply(dmx.DmxOutput(host="10.0.0.1"), 100, 0), "dmx_not_ready")
        controller.close()


class LanguageTests(unittest.TestCase):
    def test_light_strings_in_english_and_german(self):
        import language

        keys = (
            "lights",
            "lights_hint",
            "lights_host",
            "lights_universe",
            "lights_channels",
            "lights_channels_hint",
            "lights_close",
            "lights_none_ready",
            "lights_control",
            "lights_control_off",
            "lights_transition",
            "lights_start_lead",
            "lights_start_lead_hint",
            "lights_end_lead",
            "lights_end_lead_hint",
            "light_play",
            "light_start",
            "light_end",
            "light_auto",
            "light_bright",
            "light_medium",
            "light_dark",
            "light_badge",
            "light_medium_badge",
            "light_bright_badge",
            "setting_badge",
            "settings_warning_active",
            "clip_settings_warning",
        )
        for lang in ("en", "de"):
            table = language.STRINGS[lang]
            for key in keys:
                self.assertIn(key, table)
                self.assertTrue(table[key])
        self.assertEqual(language.STRINGS["de"]["light_bright"], "Hell")
        self.assertEqual(language.STRINGS["de"]["light_medium"], "Mittel")
        self.assertEqual(language.STRINGS["de"]["light_dark"], "Dunkel")


if __name__ == "__main__":
    unittest.main()
