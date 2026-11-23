"""Tests for subtitle availability and provenance classification."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from subtitle_discovery import subtitle_badge, subtitle_status


class SubtitleDiscoveryTests(unittest.TestCase):
    def test_embedded_original(self):
        with tempfile.TemporaryDirectory() as folder:
            movie = Path(folder) / "film.mkv"
            movie.write_bytes(b"movie")
            with patch("subtitle_discovery.probe_media", return_value={
                "streams": [{"codec_type": "subtitle", "index": 2}]
            }):
                result = subtitle_status(movie)
            self.assertEqual(subtitle_badge(result), "UT Original")

    def test_generated_and_original_coexist(self):
        with tempfile.TemporaryDirectory() as folder:
            movie = Path(folder) / "film.mkv"
            movie.write_bytes(b"movie")
            (Path(folder) / "film.en.srt").write_text("original")
            (Path(folder) / "film.audio-3.de.srt").write_text("generated")
            stat = movie.stat()
            (Path(folder) / "film.audio-3.de.subtitles.json").write_text(json.dumps({
                "generated": True, "source_file": str(movie.resolve()),
                "source_size": stat.st_size, "source_mtime_ns": stat.st_mtime_ns,
            }))
            with patch("subtitle_discovery.probe_media", return_value={"streams": []}):
                result = subtitle_status(movie)
            self.assertEqual(subtitle_badge(result), "UT Original + KI")

    def test_unverified_provenance_not_called_generated(self):
        with tempfile.TemporaryDirectory() as folder:
            movie = Path(folder) / "film.mkv"
            movie.write_bytes(b"movie")
            (Path(folder) / "film.de.srt").write_text("subtitle")
            (Path(folder) / "film.de.subtitles.json").write_text('{"generated": true}')
            with patch("subtitle_discovery.probe_media", return_value={"streams": []}):
                result = subtitle_status(movie)
            self.assertEqual(subtitle_badge(result), "UT Original")


if __name__ == "__main__":
    unittest.main()
