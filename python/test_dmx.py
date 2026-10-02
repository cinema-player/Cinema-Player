#!/usr/bin/env python3
"""DMX house lights over Art-Net or USB-RS485, plus cue resolution (no hardware)."""

import struct
import unittest

import dmx


class FakeSerialPort:
    """Stands in for a USB-RS485 cable; records what would go on the line."""

    def __init__(self, device):
        self.device = device
        self.frames = []
        self.closed = False

    def write_frame(self, frame):
        self.frames.append(dmx.dmx_frame_bytes(frame))

    def close(self):
        self.closed = True


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
        self.assertEqual(loaded.mode, dmx.MODE_ARTNET)
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
        controller = dmx.DmxController(send=lambda host, port, packet: sent.append((host, port, packet)))
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
        controller = dmx.DmxController(send=lambda *_args: None)
        self.assertEqual(controller.apply(dmx.DmxOutput(host="10.0.0.1"), 100, 0), "dmx_not_ready")
        controller.close()


class UsbRs485Tests(unittest.TestCase):
    def test_normalize_mode(self):
        self.assertEqual(dmx.normalize_mode(""), dmx.MODE_ARTNET)
        self.assertEqual(dmx.normalize_mode("Art-Net"), dmx.MODE_ARTNET)
        self.assertEqual(dmx.normalize_mode("usb"), dmx.MODE_USB)
        self.assertEqual(dmx.normalize_mode("RS485"), dmx.MODE_USB)
        self.assertEqual(dmx.normalize_mode("serial"), dmx.MODE_USB)
        self.assertEqual(dmx.normalize_mode("nonsense"), dmx.MODE_ARTNET)

    def test_usb_output_needs_a_device(self):
        self.assertFalse(dmx.DmxOutput(mode="usb", channels="1").ready())
        self.assertFalse(dmx.DmxOutput(mode="usb", device="/dev/ttyUSB0").ready())
        self.assertTrue(dmx.DmxOutput(mode="usb", device="/dev/ttyUSB0", channels="1").ready())
        self.assertFalse(dmx.DmxOutput(mode="usb", host="10.0.0.1", channels="1").ready())

    def test_frame_bytes_carry_start_code_and_512_slots(self):
        packet = dmx.dmx_frame_bytes(dmx.frame_for_level([1, 3], 100))
        self.assertEqual(len(packet), 513)
        self.assertEqual(packet[0], 0)
        self.assertEqual(packet[1], 255)
        self.assertEqual(packet[2], 0)
        self.assertEqual(packet[3], 255)
        self.assertEqual(dmx.dmx_frame_bytes(b""), bytes(513))

    def test_termios2_block_is_250kbd_8n2(self):
        block = dmx.termios2_settings()
        self.assertEqual(len(block), struct.calcsize(dmx.TERMIOS2_FORMAT))
        iflag, oflag, cflag, lflag, _line, _cc, ispeed, ospeed = struct.unpack(
            dmx.TERMIOS2_FORMAT, block,
        )
        self.assertEqual((iflag, oflag, lflag), (0, 0, 0))
        self.assertEqual(ispeed, 250000)
        self.assertEqual(ospeed, 250000)
        for bit in (dmx.CS8, dmx.CSTOPB, dmx.CREAD, dmx.CLOCAL, dmx.BOTHER):
            self.assertTrue(cflag & bit)

    def test_apply_writes_to_the_usb_cable(self):
        ports = []

        def open_port(device):
            port = FakeSerialPort(device)
            ports.append(port)
            return port

        controller = dmx.DmxController(
            send=lambda *_args: self.fail("USB mode must not send Art-Net"),
            open_port=open_port,
        )
        output = dmx.DmxOutput(mode="usb", device="/dev/ttyUSB0", channels="2")
        self.assertEqual(controller.apply(output, 40, 0), "")
        self.assertEqual(controller.apply(output, 100, 0), "")
        self.assertEqual(len(ports), 1)
        self.assertEqual(ports[0].device, "/dev/ttyUSB0")
        self.assertEqual([frame[2] for frame in ports[0].frames], [102, 255])
        controller.close()
        self.assertTrue(ports[0].closed)

    def test_changing_the_device_reopens_the_port(self):
        ports = []

        def open_port(device):
            port = FakeSerialPort(device)
            ports.append(port)
            return port

        controller = dmx.DmxController(open_port=open_port)
        controller.apply(dmx.DmxOutput(mode="usb", device="/dev/ttyUSB0", channels="1"), 100, 0)
        controller.apply(dmx.DmxOutput(mode="usb", device="/dev/ttyUSB1", channels="1"), 100, 0)
        self.assertEqual([port.device for port in ports], ["/dev/ttyUSB0", "/dev/ttyUSB1"])
        self.assertTrue(ports[0].closed)
        controller.close()

    def test_write_failure_drops_the_port_so_it_reopens(self):
        ports = []

        class BrokenPort(FakeSerialPort):
            def write_frame(self, frame):
                raise OSError("no such device")

        def open_port(device):
            port = BrokenPort(device)
            ports.append(port)
            return port

        controller = dmx.DmxController(open_port=open_port)
        output = dmx.DmxOutput(mode="usb", device="/dev/ttyUSB0", channels="1")
        self.assertEqual(controller.apply(output, 100, 0), "no such device")
        self.assertEqual(controller.apply(output, 50, 0), "no such device")
        self.assertEqual(len(ports), 2)
        self.assertTrue(ports[0].closed)
        controller.close()

    def test_usb_config_roundtrip(self):
        dumped = dmx.dump_lights_config(
            dmx.DmxOutput(mode="usb", device=" /dev/ttyUSB0 ", channels="7"),
            {}, 2000,
        )
        self.assertEqual(dumped["mode"], "usb")
        self.assertEqual(dumped["device"], "/dev/ttyUSB0")
        loaded, _, transition, *_ = dmx.load_lights_config(dumped)
        self.assertEqual(loaded.mode, dmx.MODE_USB)
        self.assertEqual(loaded.device, "/dev/ttyUSB0")
        self.assertEqual(loaded.channels, [7])
        self.assertEqual(transition, 2000)
        self.assertTrue(loaded.ready())

    def test_list_serial_devices_returns_paths(self):
        self.assertIsInstance(dmx.list_serial_devices(), list)
        for device in dmx.list_serial_devices():
            self.assertTrue(device.startswith("/dev/"))


class LanguageTests(unittest.TestCase):
    def test_light_strings_in_english_and_german(self):
        import language

        keys = (
            "lights",
            "lights_hint",
            "lights_mode",
            "lights_mode_artnet",
            "lights_mode_usb",
            "lights_host",
            "lights_universe",
            "lights_device",
            "lights_device_hint",
            "lights_channels",
            "lights_channels_hint",
            "lights_close",
            "lights_none_ready",
            "lights_none_ready_usb",
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
