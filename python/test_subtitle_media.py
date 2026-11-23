"""Unit tests for offline subtitle media metadata (no ffmpeg runtime needed)."""
import unittest

from subtitle_media import (
    audio_tracks, insert_profile, requires_subtitle_notice, selected_audio_map,
)


class SubtitleMediaTests(unittest.TestCase):
    def setUp(self):
        self.probe = {"streams": [
            {"index": 0, "codec_type": "video", "width": 3840, "height": 2160,
             "avg_frame_rate": "24000/1001", "sample_aspect_ratio": "1:1",
             "color_transfer": "smpte2084"},
            {"index": 1, "codec_type": "audio", "codec_name": "aac",
             "tags": {"language": "en", "title": "Original"}, "channels": 2},
            {"index": 3, "codec_type": "audio", "codec_name": "ac3",
             "tags": {"language": "de"}, "channels": 6},
        ]}

    def test_audio_selection_uses_absolute_stream_index(self):
        tracks = audio_tracks(self.probe)
        self.assertEqual([t.stream_index for t in tracks], [1, 3])
        self.assertEqual(selected_audio_map(tracks[1]), "0:3")

    def test_insert_preserves_exact_frame_rate(self):
        p = insert_profile(self.probe, output_hdr=True)
        self.assertEqual(str(p.frame_rate), "24000/1001")
        self.assertEqual((p.width, p.height), (3840, 2160))
        self.assertTrue(p.output_hdr)

    def test_tone_mapped_output_is_explicit(self):
        p = insert_profile(self.probe, output_hdr=False,
                           output_color_transfer="bt709")
        self.assertFalse(p.output_hdr)
        self.assertEqual(p.color_transfer, "bt709")

    def test_notice_only_for_active_generated_subtitles(self):
        self.assertTrue(requires_subtitle_notice(generated=True, enabled=True))
        self.assertFalse(requires_subtitle_notice(generated=True, enabled=False))
        self.assertFalse(requires_subtitle_notice(generated=False, enabled=True))


if __name__ == "__main__":
    unittest.main()
