"""Cancellation contract for LUFS measurement."""
import threading
import unittest
from unittest.mock import patch

from cinema_player import AudioAnalysisCancelled, probe_audio


class CancelLufsTests(unittest.TestCase):
    def test_pre_cancelled_measurement_never_starts_ffmpeg(self):
        stop = threading.Event()
        stop.set()
        with patch("cinema_player.subprocess.Popen") as popen:
            with self.assertRaises(AudioAnalysisCancelled):
                probe_audio("/unused/film.mkv", "ffmpeg", cancel_event=stop)
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
