#!/usr/bin/env python3
"""Loudness and peak-envelope helpers."""

import array
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave
from unittest.mock import MagicMock, patch

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import cinema_player as player


class AudioClockTests(unittest.TestCase):
    def test_half_rate_hdmi_clock_is_fed_at_double_speed(self):
        self.assertEqual(player.audio_clock_compensation(0.5), 2)
        self.assertEqual(player.audio_clock_compensation(0.48), 2)
        self.assertEqual(player.audio_clock_compensation(0.62), 2)

    def test_healthy_clock_is_left_alone(self):
        self.assertEqual(player.audio_clock_compensation(1.0), 1)
        self.assertEqual(player.audio_clock_compensation(0.97), 1)
        self.assertEqual(player.audio_clock_compensation(None), 1)
        self.assertEqual(player.audio_clock_compensation("nope"), 1)

    def test_half_rate_launch_follows_the_audio_clock(self):
        hdmi = "alsa/hdmi:CARD=HDMI,DEV=0"
        manager = player.VideoOutputManager("HDMI-1")
        mode = player.DisplayMode("HDMI-1", 1920, 1080, 50.0, name="1920x1080")
        with patch.object(manager, "effective_mode", return_value=mode), patch(
            "cinema_player.session_is_wayland", return_value=True,
        ), patch(
            "cinema_player.gpu_context_for_mpv", return_value="wayland",
        ), patch(
            "cinema_player.mpv_has_option", return_value=True,
        ), patch.object(manager, "program_audio_device", return_value=hdmi), patch(
            "cinema_player.measure_audio_clock_ratio", return_value=0.5,
        ), patch(
            "cinema_player.ensure_audio_keepalive_wav", return_value="/tmp/silence.wav",
        ):
            args = manager.get_mpv_arguments("/usr/bin/mpv")
        self.assertIn("--video-sync=audio", args)
        self.assertIn("--speed=2", args)
        self.assertNotIn("--video-sync=display-resample", args)
        self.assertEqual(
            manager.program_clock_properties(True),
            [("speed", 2), ("video-sync", "audio")],
        )
        self.assertEqual(
            manager.program_clock_properties(False),
            [("speed", 1), ("video-sync", "display-resample")],
        )
        self.assertEqual(manager.program_clock_properties(None), [])


class EnvelopeHelpersTests(unittest.TestCase):
    def test_resample_keeps_bin_count_and_peaks(self):
        values = [0.0, 0.5, 1.0, 0.25]
        out = player.resample_peak_envelope(values, bins=4)
        self.assertEqual(out, [0.0, 0.5, 1.0, 0.25])
        stretched = player.resample_peak_envelope(values, bins=8)
        self.assertEqual(len(stretched), 8)
        self.assertEqual(max(stretched), 1.0)

    def test_normalize_rejects_empty_and_clamps(self):
        self.assertIsNone(player.normalize_envelope(None))
        self.assertIsNone(player.normalize_envelope([]))
        out = player.normalize_envelope([2.0, "0.5", "nope"], bins=2)
        self.assertEqual(len(out), 2)
        self.assertLessEqual(max(out), 1.0)

    def test_envelope_from_pcm_reads_float32_peaks(self):
        samples = [0.0] * 160 + [0.8] * 160 + [-0.4] * 160
        payload = array.array("f", samples).tobytes()
        peaks = player.envelope_from_pcm(io.BytesIO(payload), rate=8000, window_hz=50, bins=3)
        self.assertEqual(len(peaks), 3)
        self.assertGreater(peaks[1], peaks[0])
        self.assertGreater(peaks[1], peaks[2])

    def test_playlist_entry_stores_envelope(self):
        entry = player.PlaylistEntry.from_dict({
            "path": "/tmp/clip.mp4",
            "loudness_lufs": -18.3,
            "audio_envelope": [0.1, 0.9, 0.2],
        })
        self.assertEqual(entry.loudness_lufs, -18.3)
        self.assertEqual(len(entry.audio_envelope), player.ENVELOPE_BINS)
        self.assertGreater(max(entry.audio_envelope), 0.8)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is required")
class ProbeAudioTests(unittest.TestCase):
    def test_probe_audio_returns_lufs_and_envelope(self):
        ffmpeg = shutil.which("ffmpeg")
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "tone.wav")
            result = subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4",
                    "-ar", "48000", "-ac", "1", path,
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lufs, envelope = player.probe_audio(path, ffmpeg_path=ffmpeg)
        self.assertIsNotNone(lufs)
        self.assertTrue(math.isfinite(lufs))
        self.assertIsNotNone(envelope)
        self.assertEqual(len(envelope), player.ENVELOPE_BINS)
        self.assertGreater(max(envelope), 0.05)


class HdmiKeepaliveTests(unittest.TestCase):
    def test_writes_silent_stereo_wav(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "keep.wav")
            out = player.ensure_audio_keepalive_wav(path)
            self.assertEqual(out, path)
            with wave.open(path, "rb") as handle:
                self.assertEqual(handle.getnchannels(), 2)
                self.assertEqual(handle.getsampwidth(), 2)
                self.assertEqual(handle.getframerate(), player.AUDIO_KEEPALIVE_RATE)
                self.assertGreater(handle.getnframes(), 0)
            again = player.ensure_audio_keepalive_wav(path)
            self.assertEqual(again, path)

    def test_keepopen_args_when_mpv_supports_them(self):
        with patch("cinema_player.mpv_has_option", return_value=True):
            args = player.program_audio_keepopen_args("/usr/bin/mpv")
        self.assertIn("--audio-stream-silence=yes", args)
        self.assertIn("--gapless-audio=weak", args)
        self.assertIn("--replaygain=no", args)
        self.assertIn("--audio-spdif=", args)

    def test_keepopen_args_when_unsupported(self):
        with patch("cinema_player.mpv_has_option", return_value=False):
            self.assertEqual(player.program_audio_keepopen_args("/usr/bin/mpv"), [])

    def test_playback_af_keeps_volume_fader(self):
        self.assertIn("volume", player.PLAYBACK_AF.split(",")[-1])
        self.assertIn("astats", player.PLAYBACK_AF)

    def test_prefers_pipewire_hdmi_over_raw_alsa(self):
        devices = [
            ("alsa/hdmi:CARD=NVidia,DEV=0", "HDMI 0"),
            ("pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo", "HDMI stereo"),
        ]
        chosen = player.choose_program_audio_device(devices, "HDMI-0")
        self.assertTrue(chosen.startswith("pipewire/"))

    def test_program_ignores_alsa_when_pulse_hdmi_exists(self):
        devices = [
            ("alsa/hdmi:CARD=NVidia,DEV=1", "HDMI 1"),
            ("pulse/alsa_output.pci-0000_01_00.1.hdmi-stereo-extra1", "HDMI stereo extra1"),
        ]
        chosen = player.choose_program_audio_device(devices, "HDMI-1")
        self.assertTrue(chosen.startswith("pulse/"))

    def test_preview_skips_hdmi_and_program_device(self):
        devices = [
            ("pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo", "HDMI stereo"),
            ("pipewire/alsa_output.pci-0000_00_1f.3.analog-stereo", "Built-in Audio Analog Stereo"),
            ("auto", "Autoselect device"),
        ]
        program = "pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo"
        chosen = player.choose_preview_audio_device(devices, program_device=program)
        self.assertIn("analog", chosen)

    def test_preview_rejects_auto(self):
        self.assertEqual(
            player.score_preview_audio_device("auto", "Autoselect device"),
            -1,
        )

    def test_audio_labels_are_unique_and_skip_generic_backends(self):
        devices = [
            ("auto", "Autoselect device"),
            ("pipewire", "PipeWire"),
            ("pipewire/alsa_output.analog-stereo", "Analog Stereo"),
            ("pulse/alsa_output.analog-stereo", "Analog Stereo"),
        ]
        rows = player.unique_audio_device_labels(devices)
        labels = [label for label, _device in rows]
        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(labels[0], "Analog Stereo")
        self.assertIn("pulse/alsa_output.analog-stereo", labels[1])
        self.assertNotIn("auto", [device for _label, device in rows])

    def test_video_output_label_includes_monitor_name(self):
        self.assertEqual(player.video_output_menu_label("HDMI-1", "Epson"), "HDMI-1 — Epson")
        self.assertEqual(player.video_output_menu_label("HDMI-1", "HDMI-1"), "HDMI-1")
        self.assertEqual(player.video_output_menu_label("DP-1", ""), "DP-1")

    def test_normalize_audio_patch(self):
        patch = player.normalize_audio_patch({"beamer": "Auto", "preview": "NULL", "extra": "x"})
        self.assertEqual(patch, {"beamer": "", "preview": "none"})
        self.assertEqual(player.normalize_audio_patch_choice("pipewire/hdmi"), "pipewire/hdmi")

    def _manager(self, beamer="", preview=""):
        manager = player.VideoOutputManager("HDMI-0")
        manager.set_audio_patch({"beamer": beamer, "preview": preview})
        return manager

    def _silence_display(self, manager):
        return (
            patch.object(manager, "uses_gdctl", return_value=False),
            patch.object(manager, "uses_kscreen", return_value=False),
            patch.object(manager, "get_outputs", return_value=["HDMI-0", "DP-1"]),
            patch.object(manager, "get_primary_output", return_value="DP-1"),
        )

    def test_explicit_beamer_patch_overrides_hdmi_match(self):
        devices = [
            ("pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo", "HDMI stereo"),
            ("pipewire/alsa_output.analog-stereo", "Analog Stereo"),
        ]
        manager = self._manager(beamer="pipewire/alsa_output.analog-stereo")
        display = self._silence_display(manager)
        with display[0], display[1], display[2], display[3], patch(
            "cinema_player.list_mpv_audio_devices", return_value=devices,
        ):
            chosen = manager.program_audio_device("/usr/bin/mpv")
            args = manager.audio_launch_args("beamer", "/usr/bin/mpv")
        self.assertEqual(chosen, "pipewire/alsa_output.analog-stereo")
        self.assertEqual(args, ["--audio-device=pipewire/alsa_output.analog-stereo"])

    def test_stale_patch_falls_back_to_automatic(self):
        devices = [
            ("pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo", "HDMI stereo"),
            ("pipewire/alsa_output.analog-stereo", "Analog Stereo"),
        ]
        manager = self._manager(beamer="pipewire/missing")
        display = self._silence_display(manager)
        with display[0], display[1], display[2], display[3], patch(
            "cinema_player.list_mpv_audio_devices", return_value=devices,
        ):
            chosen = manager.program_audio_device("/usr/bin/mpv")
        self.assertIn("hdmi", chosen)

    def test_preview_patch_may_use_the_projector_output(self):
        hdmi = "pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo"
        devices = [
            (hdmi, "HDMI stereo"),
            ("pipewire/alsa_output.analog-stereo", "Analog Stereo"),
        ]
        manager = self._manager(preview=hdmi)
        display = self._silence_display(manager)
        with display[0], display[1], display[2], display[3], patch(
            "cinema_player.list_mpv_audio_devices", return_value=devices,
        ):
            chosen = manager.preview_audio_device("/usr/bin/mpv")
        self.assertEqual(chosen, hdmi)

    def test_preview_automatic_avoids_patched_beamer_device(self):
        analog = "pipewire/alsa_output.analog-stereo"
        usb = "pipewire/alsa_output.usb-headset"
        devices = [
            ("pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo", "HDMI stereo"),
            (analog, "Analog Stereo"),
            (usb, "USB Headset"),
        ]
        manager = self._manager(beamer=analog)
        display = self._silence_display(manager)
        display = (
            display[0],
            display[1],
            display[2],
            patch.object(manager, "get_primary_output", return_value="HDMI-0"),
        )
        with display[0], display[1], display[2], display[3], patch(
            "cinema_player.list_mpv_audio_devices", return_value=devices,
        ):
            chosen = manager.preview_audio_device("/usr/bin/mpv")
        self.assertEqual(chosen, usb)

    def test_off_patch_disconnects_both_players(self):
        manager = self._manager(beamer="none", preview="off")
        self.assertTrue(manager.audio_patch_is_off("beamer"))
        self.assertTrue(manager.audio_patch_is_off("preview"))
        self.assertIsNone(manager.program_audio_device("/usr/bin/mpv"))
        self.assertIsNone(manager.preview_audio_device("/usr/bin/mpv"))
        self.assertEqual(manager.audio_launch_args("beamer", "/usr/bin/mpv"), ["--ao=null"])
        self.assertEqual(manager.audio_launch_args("preview", "/usr/bin/mpv"), ["--ao=null"])

    def test_launch_arguments_use_the_patched_device(self):
        analog = "pipewire/alsa_output.analog-stereo"
        devices = [
            ("pipewire/alsa_output.pci-0000_01_00.1.hdmi-stereo", "HDMI stereo"),
            (analog, "Analog Stereo"),
        ]
        manager = self._manager(beamer=analog)
        mode = player.DisplayMode("HDMI-0", 1920, 1080, 60.0, name="1920x1080")
        with patch.object(manager, "effective_mode", return_value=mode), patch(
            "cinema_player.session_is_wayland", return_value=False,
        ), patch(
            "cinema_player.gpu_context_for_mpv", return_value="x11egl",
        ), patch(
            "cinema_player.mpv_has_option", return_value=False,
        ), patch(
            "cinema_player.list_mpv_audio_devices", return_value=devices,
        ):
            args = manager.get_mpv_arguments("/usr/bin/mpv")
        self.assertIn(f"--audio-device={analog}", args)
        self.assertIn("--screen-name=HDMI-0", args)
        self.assertNotIn("--ao=null", args)

    def test_audio_route_commands_switch_without_restarting(self):
        self.assertEqual(player.audio_route_commands("none"), [("ao", "null")])
        self.assertEqual(player.audio_route_commands(None), [("ao", "null")])
        self.assertEqual(
            player.audio_route_commands(None, when_missing="auto"),
            [("ao", "auto"), ("audio-device", "auto")],
        )
        self.assertEqual(
            player.audio_route_commands("jack"),
            [("ao", "jack"), ("audio-device", "jack")],
        )
        self.assertEqual(
            player.audio_route_commands("pipewire/alsa_output.analog-stereo"),
            [("ao", "pipewire"), ("audio-device", "pipewire/alsa_output.analog-stereo")],
        )

    def test_load_file_passes_aid_before_playback(self):
        ctl = player.MPVController("t", "/usr/bin/mpv")
        ctl.socket = MagicMock()
        ctl.load_file("/tmp/clip.mp4", start=1.0, play=True, aid=2, sid="no")
        payload = json.loads(ctl.socket.sendall.call_args[0][0].decode())
        self.assertEqual(payload["command"][0], "loadfile")
        options = payload["command"][4]
        self.assertEqual(options["aid"], "2")
        self.assertEqual(options["sid"], "no")
        self.assertEqual(options["start"], "1.0")


if __name__ == "__main__":
    unittest.main()
