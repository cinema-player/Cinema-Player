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
