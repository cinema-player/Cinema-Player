"""Audio/picture start detection tests."""
import unittest
from content_start import (parse_audio_start, parse_picture_start,
                           calculate_in_point)


class StartDetectionTests(unittest.TestCase):
    def test_audio_leading_silence(self):
        log = "[silencedetect] silence_start: 0\n[silencedetect] silence_end: 4.2 | silence_duration: 4.2"
        self.assertEqual(parse_audio_start(log), 4.2)

    def test_picture_leading_black(self):
        self.assertEqual(parse_picture_start("[blackdetect] black_start:0 black_end:6.3 black_duration:6.3"), 6.3)

    def test_earlier_audio_wins(self):
        self.assertAlmostEqual(calculate_in_point(3.0, 7.0, 1.0), 2.0)

    def test_earlier_picture_wins(self):
        self.assertAlmostEqual(calculate_in_point(8.0, 2.0, 0.5), 1.5)

    def test_clamp_to_zero(self):
        self.assertEqual(calculate_in_point(0.3, 5.0, 1.0), 0.0)

    def test_missing_audio_uses_picture(self):
        self.assertEqual(calculate_in_point(None, 4.0, 1.0), 3.0)


if __name__ == "__main__":
    unittest.main()
