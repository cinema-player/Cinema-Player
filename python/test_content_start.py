"""Audio/picture start detection tests."""
import unittest
from content_start import (parse_audio_start, parse_picture_start,
                           calculate_in_point, parse_audio_end, parse_picture_end,
                           calculate_out_point)


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

    def test_trailing_audio_silence(self):
        log = "silence_start: 8.0"
        self.assertEqual(parse_audio_end(log, 100.0, 120.0), 108.0)

    def test_trailing_black(self):
        log = "black_start: 9.5 black_end: 11.0 black_start: 15.0"
        self.assertEqual(parse_picture_end(log, 100.0, 120.0), 115.0)

    def test_out_uses_later_end_and_tail(self):
        self.assertEqual(calculate_out_point(108.0, 115.0, 120.0, 2.0), 117.0)

    def test_out_clamped_to_duration(self):
        self.assertEqual(calculate_out_point(119.5, 118.0, 120.0, 2.0), 120.0)

    def test_missing_audio_uses_picture(self):
        self.assertEqual(calculate_in_point(None, 4.0, 1.0), 3.0)


if __name__ == "__main__":
    unittest.main()
