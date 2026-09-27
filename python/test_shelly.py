#!/usr/bin/env python3
"""Shelly light presets and playlist cue resolution (no network)."""

import unittest

import shelly


class PresetTests(unittest.TestCase):
    def test_normalize_preset_accepts_german_and_english(self):
        self.assertEqual(shelly.normalize_preset("Hell"), "bright")
        self.assertEqual(shelly.normalize_preset("mittel"), "medium")
        self.assertEqual(shelly.normalize_preset("dunkel"), "dark")
        self.assertEqual(shelly.normalize_preset("bright"), "bright")
        self.assertEqual(shelly.normalize_preset(""), "")
        self.assertEqual(shelly.normalize_preset("auto"), "")

    def test_brightness_defaults(self):
        self.assertEqual(shelly.brightness_for_preset("bright"), 100)
        self.assertEqual(shelly.brightness_for_preset("medium"), 40)
        self.assertEqual(shelly.brightness_for_preset("dark"), 0)
        self.assertEqual(shelly.brightness_for_preset(""), 0)

    def test_custom_presets_and_switch_on(self):
        table = {"bright": 90, "medium": 35, "dark": 5}
        self.assertEqual(shelly.brightness_for_preset("mittel", table), 35)
        self.assertTrue(shelly.switch_on_for_brightness(5))
        self.assertFalse(shelly.switch_on_for_brightness(0))

    def test_start_and_end_cues(self):
        self.assertEqual(shelly.resolve_start_preset(""), "dark")
        self.assertEqual(shelly.resolve_start_preset("hell"), "bright")
        self.assertEqual(shelly.resolve_end_preset("", autoplay_continues=False), "bright")
        self.assertEqual(shelly.resolve_end_preset("", autoplay_continues=True), "dark")
        self.assertEqual(shelly.resolve_end_preset("mittel", autoplay_continues=True), "medium")
        self.assertEqual(shelly.play_preset(""), "")
        self.assertEqual(shelly.play_preset("dark"), "")
        self.assertEqual(shelly.play_preset("dunkel"), "")
        self.assertEqual(shelly.play_preset("mittel"), "medium")
        self.assertEqual(shelly.play_preset("hell"), "bright")
        self.assertEqual(shelly.resolve_start_preset("mittel"), "medium")

    def test_already_at_preset_skips_repeat_dark(self):
        self.assertTrue(shelly.already_at_preset("dark", "dunkel"))
        self.assertTrue(shelly.already_at_preset("dark", "dark"))
        self.assertFalse(shelly.already_at_preset("", "dark"))
        self.assertFalse(shelly.already_at_preset("bright", "dark"))
        self.assertFalse(shelly.already_at_preset("dark", ""))

    def test_merge_keeps_enabled_device(self):
        saved = [shelly.ShellyDevice(host="10.0.0.8", name="old", enabled=True, username="booth", password="x")]
        found = [shelly.ShellyDevice(host="10.0.0.8", name="Saal", kind="dimmer", gen=2)]
        merged = shelly.merge_discovered(saved, found)
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0].enabled)
        self.assertEqual(merged[0].password, "x")
        self.assertEqual(merged[0].username, "booth")
        self.assertEqual(merged[0].name, "Saal")
        self.assertEqual(merged[0].kind, "dimmer")

    def test_rpc_auth_defaults_username_to_admin(self):
        auth = shelly.rpc_auth("", "secret", "shelly", 99, 1)
        self.assertEqual(auth["username"], "admin")
        self.assertEqual(auth["algorithm"], "SHA-256")
        self.assertEqual(auth["nonce"], 99)
        copied = shelly.ShellyDevice.from_dict(
            shelly.ShellyDevice(host="10.0.0.1", username="admin", password="pw").to_dict()
        )
        self.assertEqual(copied.username, "admin")
        self.assertEqual(copied.password, "pw")

    def test_config_roundtrip(self):
        devices = [shelly.ShellyDevice(host="192.168.1.20", enabled=True, kind="dimmer")]
        dumped = shelly.dump_lights_config(
            devices, {"bright": 80, "medium": 30, "dark": 0}, 1800, username="admin", password="secret",
        )
        loaded, presets, transition, enabled, start_lead, end_lead = shelly.load_lights_config(dumped)
        self.assertEqual(loaded[0].host, "192.168.1.20")
        self.assertTrue(loaded[0].enabled)
        self.assertEqual(presets["bright"], 80)
        self.assertEqual(transition, 1800)
        self.assertTrue(enabled)
        self.assertEqual(start_lead, 0)
        self.assertEqual(end_lead, 0)
        self.assertEqual(dumped["username"], "admin")
        self.assertEqual(dumped["password"], "secret")

    def test_control_switch_roundtrip(self):
        dumped = shelly.dump_lights_config([], {}, 2500, False)
        self.assertFalse(dumped["enabled"])
        _, _, _, enabled, _, _ = shelly.load_lights_config(dumped)
        self.assertFalse(enabled)
        _, _, _, enabled, start_lead, end_lead = shelly.load_lights_config({"devices": []})
        self.assertTrue(enabled)
        self.assertEqual(start_lead, 0)
        self.assertEqual(end_lead, 0)

    def test_play_delay_and_leads(self):
        self.assertEqual(shelly.play_delay_ms(2500, 0), 2500)
        self.assertEqual(shelly.play_delay_ms(2500, 500), 2000)
        self.assertEqual(shelly.play_delay_ms(2500, 4000), 0)
        self.assertEqual(shelly.seconds_to_ms("2.5"), 2500)
        dumped = shelly.dump_lights_config([], {}, 2500, True, 800, 5000)
        _, _, _, _, start_lead, end_lead = shelly.load_lights_config(dumped)
        self.assertEqual(start_lead, 800)
        self.assertEqual(end_lead, 5000)
        _, _, _, _, start_lead, end_lead = shelly.load_lights_config(
            {"start_lead_s": 1.5, "end_lead_s": 3}
        )
        self.assertEqual(start_lead, 1500)
        self.assertEqual(end_lead, 3000)


class LanguageTests(unittest.TestCase):
    def test_light_strings_in_english_and_german(self):
        import language

        keys = (
            "lights",
            "lights_hint",
            "lights_scan",
            "lights_add",
            "lights_username",
            "lights_password",
            "lights_close",
            "lights_empty",
            "lights_scanning",
            "lights_found",
            "lights_none",
            "lights_probe_failed",
            "lights_none_enabled",
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
