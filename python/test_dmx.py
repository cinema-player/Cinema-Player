"""DMX house lights: Enttec frames, Art-Net, fades, and preset cues."""

import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import dmx
import language


class RecordingPort:
    def __init__(self, device):
        self.device = device
        self.frames = []
        self.closed = False

    def write_frame(self, frame):
        self.frames.append(bytes(frame))

    def close(self):
        self.closed = True


class PresetTests(unittest.TestCase):
    def test_normalize_preset(self):
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
        table = {"medium": 35}
        self.assertEqual(dmx.brightness_for_preset("mittel", table), 35)
        self.assertEqual(dmx.percent_to_dmx(100), 255)
        self.assertEqual(dmx.percent_to_dmx(40), 102)
        self.assertEqual(dmx.percent_to_dmx(0), 0)

    def test_playlist_cues(self):
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
        self.assertTrue(dmx.already_at_preset("dark", "dunkel"))
        self.assertFalse(dmx.already_at_preset("bright", "dark"))
        self.assertEqual(dmx.play_delay_ms(2500, 0), 2500)
        self.assertEqual(dmx.play_delay_ms(2500, 500), 2000)
        self.assertEqual(dmx.play_delay_ms(2500, 4000), 0)
        self.assertEqual(dmx.seconds_to_ms("2.5"), 2500)

    def test_channels(self):
        self.assertEqual(dmx.parse_channels("1, 2, 5-7"), [1, 2, 5, 6, 7])
        self.assertEqual(dmx.parse_channels(""), [])
        self.assertEqual(dmx.parse_channels("0, 513, nope"), [])
        self.assertEqual(dmx.format_channels([2, 1, 1]), "2, 1")


class PacketTests(unittest.TestCase):
    def test_artdmx_header(self):
        values = bytearray(512)
        values[0] = 200
        values[255] = 7
        packet = dmx.artnet_output_packet(0, values, sequence=1)
        self.assertEqual(packet[:8], b"Art-Net\x00")
        self.assertEqual(packet[8], 0x00)
        self.assertEqual(packet[9], 0x50)
        self.assertEqual(packet[11], 14)
        self.assertEqual(packet[12], 1)
        self.assertEqual(packet[14], 0)
        self.assertEqual(packet[15], 0)
        self.assertEqual(packet[16], 0x02)
        self.assertEqual(packet[17], 0x00)
        self.assertEqual(packet[18], 200)
        self.assertEqual(packet[18 + 255], 7)
        self.assertEqual(len(packet), 18 + 512)

    def test_artdmx_universe_is_split_into_subuni_and_net(self):
        packet = dmx.artnet_output_packet(256, bytes(512), sequence=1)
        self.assertEqual(packet[14], 0)
        self.assertEqual(packet[15], 1)

    def test_enttec_frame(self):
        values = bytearray(512)
        values[0] = 10
        values[1] = 20
        packet = dmx.build_enttec(values)
        self.assertEqual(packet[0], 0x7E)
        self.assertEqual(packet[1], 0x06)
        self.assertEqual(packet[2], 513 & 0xFF)
        self.assertEqual(packet[3], (513 >> 8) & 0xFF)
        self.assertEqual(packet[4], 0x00)
        self.assertEqual(packet[5], 10)
        self.assertEqual(packet[6], 20)
        self.assertEqual(packet[-1], 0xE7)
        self.assertEqual(len(packet), 4 + 513 + 1)

    def test_frame_for_level_maps_percent(self):
        frame = dmx.frame_for_level([1, 4], 40)
        self.assertEqual(frame[0], 102)
        self.assertEqual(frame[3], 102)
        self.assertEqual(frame[1], 0)
        self.assertEqual(len(frame), 512)


class FadeTests(unittest.TestCase):
    def test_first_level_snaps_and_later_cue_fades(self):
        sent = []
        clock = {"t": 0.0}
        controller = dmx.DmxController(
            send=lambda host, port, packet: sent.append(packet),
            monotonic=lambda: clock["t"],
            start_thread=False,
        )
        output = dmx.DmxOutput(mode="artnet", host="127.0.0.1", channels=[1])
        self.assertEqual(controller.apply(output, 100, 2500), "")
        self.assertEqual(controller.level, 100)
        self.assertEqual(sent[-1][18], 255)
        clock["t"] = 10.0
        self.assertEqual(controller.apply(output, 0, 1000), "")
        self.assertEqual(controller.level, 100)
        clock["t"] = 10.5
        controller._tick()
        self.assertAlmostEqual(controller.level, 50.0, places=2)
        self.assertEqual(sent[-1][18], 128)
        clock["t"] = 11.0
        controller._tick()
        self.assertEqual(controller.level, 0)
        self.assertEqual(sent[-1][18], 0)
        controller.close()

    def test_missing_enttec_device_does_not_raise(self):
        controller = dmx.DmxController(start_thread=False)
        output = dmx.DmxOutput(mode="enttec", device="/tmp/no-such-dmx-device", channels=[1])
        error = controller.apply(output, 255, 0)
        self.assertIn("/tmp/no-such-dmx-device", error)
        self.assertIn("No such file", error)
        self.assertFalse(controller.connected)
        controller.close()

    def test_enttec_pty_frame(self):
        import pty
        import select

        master, slave = pty.openpty()
        try:
            port = dmx.EnttecPort(os.ttyname(slave))
            port.write_frame(dmx.frame_for_level([1], 40))
            port.close()
            ready, _, _ = select.select([master], [], [], 1)
            self.assertTrue(ready)
            data = os.read(master, 2048)
        finally:
            os.close(master)
            os.close(slave)
        self.assertEqual(data[0], 0x7E)
        self.assertEqual(data[1], 0x06)
        self.assertEqual(data[2] + (data[3] << 8), 513)
        self.assertEqual(data[4], 0x00)
        self.assertEqual(data[5], 102)
        self.assertEqual(data[-1], 0xE7)
        self.assertEqual(len(data), 518)

    def test_enttec_port_writes_label_6(self):
        port = RecordingPort("/dev/ttyUSB0")
        controller = dmx.DmxController(open_port=lambda device: port, start_thread=False)
        output = dmx.DmxOutput(mode="enttec", device="/dev/ttyUSB0", channels=[1])
        self.assertEqual(controller.apply(output, 100, 0), "")
        self.assertEqual(len(port.frames), 1)
        self.assertEqual(port.frames[0][0], 255)
        self.assertEqual(port.frames[0][1], 0)
        controller.close()
        self.assertTrue(port.closed)


class ArtNetSendTests(unittest.TestCase):
    def test_apply_reaches_the_socket(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        sock.settimeout(2)
        port = sock.getsockname()[1]
        output = dmx.DmxOutput(mode="artnet", host="127.0.0.1", port=port, universe=0, channels=[1])
        try:
            error = dmx.apply_preset(output, "bright", transition_ms=0)
            self.assertEqual(error, "")
            packet = sock.recvfrom(1024)[0]
            self.assertEqual(packet[:8], b"Art-Net\x00")
            self.assertEqual(packet[18], 255)
            self.assertTrue(dmx.connected())
        finally:
            dmx.shutdown()
            sock.close()


class ConfigTests(unittest.TestCase):
    def test_shelly_settings_keep_presets_and_stay_off(self):
        output, presets, transition, enabled, start_lead, end_lead = dmx.load_lights_config({
            "enabled": True,
            "devices": [{"host": "10.0.0.8", "enabled": True}],
            "presets": {"bright": 90, "medium": 30, "dark": 5},
            "transition_ms": 1800,
            "start_lead_ms": 400,
            "end_lead_ms": 900,
        })
        self.assertFalse(enabled)
        self.assertEqual(output.mode, "enttec")
        self.assertEqual(output.device, "/dev/ttyUSB0")
        self.assertEqual(output.channels, [1])
        self.assertEqual(presets["bright"], 90)
        self.assertEqual(presets["medium"], 30)
        self.assertEqual(transition, 1800)
        self.assertEqual(start_lead, 400)
        self.assertEqual(end_lead, 900)

    def test_round_trip_artnet(self):
        dumped = dmx.dump_lights_config(
            dmx.DmxOutput(mode="artnet", host="10.0.0.5", universe=2, channels="1, 3-4"),
            {"bright": 80, "medium": 40, "dark": 0},
            1000,
            True,
            200,
            300,
        )
        output, presets, transition, enabled, start_lead, end_lead = dmx.load_lights_config(dumped)
        self.assertTrue(enabled)
        self.assertEqual(output.mode, "artnet")
        self.assertEqual(output.host, "10.0.0.5")
        self.assertEqual(output.universe, 2)
        self.assertEqual(output.channels, [1, 3, 4])
        self.assertEqual(presets["bright"], 80)
        self.assertEqual(transition, 1000)
        self.assertEqual(start_lead, 200)
        self.assertEqual(end_lead, 300)

    def test_light_strings_in_english_and_german(self):
        keys = (
            "lights",
            "lights_hint",
            "lights_mode",
            "lights_mode_artnet",
            "lights_mode_enttec",
            "lights_host",
            "lights_universe",
            "lights_device",
            "lights_device_hint",
            "lights_channels",
            "lights_channels_hint",
            "lights_close",
            "lights_none_ready",
            "lights_none_ready_enttec",
            "lights_control",
            "lights_control_off",
            "lights_transition",
            "lights_start_lead",
            "lights_start_lead_hint",
            "lights_end_lead",
            "lights_end_lead_hint",
            "light_play",
            "light_bright",
            "light_medium",
            "light_dark",
        )
        for key in keys:
            self.assertTrue(language.STRINGS["en"][key], key)
            self.assertTrue(language.STRINGS["de"][key], key)
        self.assertEqual(language.STRINGS["de"]["light_bright"], "Hell")
        self.assertEqual(language.STRINGS["de"]["light_medium"], "Mittel")
        self.assertEqual(language.STRINGS["de"]["light_dark"], "Dunkel")
        self.assertIn("Enttec", language.STRINGS["en"]["lights_mode_enttec"])
        self.assertIn("Enttec", language.STRINGS["de"]["lights_mode_enttec"])


if __name__ == "__main__":
    unittest.main()
