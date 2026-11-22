"""Offline subtitle pipeline tests without installed speech/translation models."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from subtitle_jobs import (Cue, JobState, SubtitleJob, SubtitleProcessor,
                           render_srt)


class FakeRecognizer:
    name = "test recognizer"
    def recognize(self, wav, cancel):
        return "en", [Cue(0, 1.2, "Hello"), Cue(1.3, 2.5, "World")]


class FakeTranslator:
    name = "test translator"
    def translate(self, text, source, target):
        assert (source, target) == ("en", "de")
        return {"Hello": "Hallo", "World": "Welt"}[text]


class FakeProcess:
    returncode = 0
    def __init__(self):
        import io
        self.stderr = io.BytesIO()
    def poll(self):
        return 0


class SubtitleJobTests(unittest.TestCase):
    def test_srt_timestamp_and_overlap(self):
        output = render_srt([Cue(0, 1.2, "Hello"), Cue(1, 2, " World ")])
        self.assertIn("00:00:00,000 --> 00:00:01,200", output)
        self.assertIn("00:00:01,200 --> 00:00:02,000", output)

    def test_pipeline_writes_srt_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "sample.mkv"
            video.write_bytes(b"video")
            job = SubtitleJob(video, 3, Path(directory))
            probe = {"streams": [{"codec_type": "audio", "index": 3,
                                  "codec_name": "aac"}]}
            with patch("subtitle_jobs.probe_media", return_value=probe), \
                 patch("subtitle_jobs.subprocess.Popen", return_value=FakeProcess()) as popen:
                result = SubtitleProcessor(FakeRecognizer(), FakeTranslator()).run(job)
            self.assertEqual(result.state, JobState.COMPLETED, result.error)
            self.assertIn("-map", popen.call_args.args[0])
            self.assertIn("0:3", popen.call_args.args[0])
            self.assertIn("Hallo", result.srt_path.read_text(encoding="utf-8"))
            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["audio_stream_index"], 3)
            self.assertEqual(metadata["recognition_tool"], "test recognizer")
            self.assertEqual(metadata["translation_tool"], "test translator")

    def test_invalid_audio_track_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "sample.mkv"
            video.write_bytes(b"video")
            job = SubtitleJob(video, 99, Path(directory))
            with patch("subtitle_jobs.probe_media", return_value={"streams": []}):
                result = SubtitleProcessor(FakeRecognizer(), FakeTranslator()).run(job)
            self.assertEqual(result.state, JobState.FAILED)
            self.assertIsNone(result.srt_path)

    def test_cancel_before_start(self):
        with tempfile.TemporaryDirectory() as directory:
            job = SubtitleJob(Path(directory) / "missing.mkv", 1, Path(directory))
            job.cancel()
            result = SubtitleProcessor(FakeRecognizer(), FakeTranslator()).run(job)
            self.assertEqual(result.state, JobState.CANCELLED)


if __name__ == "__main__":
    unittest.main()
