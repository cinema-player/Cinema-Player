#!/usr/bin/env python3
"""Loudness and peak-envelope helpers."""

import array
import io
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

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


if __name__ == "__main__":
    unittest.main()
