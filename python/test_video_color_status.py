#!/usr/bin/env python3
"""HDR/SDR classification for tagged and ordinary camera files."""

import json
import os
import subprocess
import unittest

import video_color_status as color


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTDATA = os.path.join(ROOT, "testdata", "videotestdata")


class ClassifyTests(unittest.TestCase):
    def test_pq_and_mastering_are_hdr(self):
        self.assertEqual(color.classify_video_stream({"color_transfer": "smpte2084"}), "HDR")
        self.assertEqual(
            color.classify_video_stream({
                "color_transfer": "bt2020-10",
                "side_data_list": [{"side_data_type": "Mastering display metadata"}],
            }),
            "HDR",
        )

    def test_rec2020_ten_bit_curve_is_sdr(self):
        self.assertEqual(
            color.classify_video_stream({
                "color_transfer": "bt2020-10",
                "color_primaries": "bt2020",
                "pix_fmt": "yuv420p10le",
            }),
            "SDR",
        )

    def test_untagged_eight_bit_is_sdr_and_ten_bit_stays_unknown(self):
        self.assertEqual(
            color.classify_video_stream({"color_transfer": "unknown", "pix_fmt": "yuv420p"}),
            "SDR",
        )
        self.assertEqual(
            color.classify_video_stream({"pix_fmt": "yuv420p10le", "bits_per_raw_sample": "N/A"}),
            "Unknown",
        )

    def test_videotestdata_matches_the_files(self):
        expected = {
            "HDR10_PQ_Rec2020.mp4": "HDR",
            "SDR_Rec709.mp4": "SDR",
            "rec2020-16x9.mp4": "SDR",
            "h264-subtitle.mp4": "SDR",
            "UHD_25fps.mp4": "SDR",
            "UHD_30fps.mp4": "SDR",
            "dv_pal_4x3.avi": "SDR",
            "dv_pal_16x9.avi": "SDR",
        }
        for name, want in expected.items():
            path = os.path.join(TESTDATA, name)
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-print_format", "json",
                    "-show_streams", "-select_streams", "v:0", path,
                ],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(color.classify_ffprobe(json.loads(probe.stdout)), want, name)


if __name__ == "__main__":
    unittest.main()
