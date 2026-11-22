"""Offline, precomputed German subtitle generation.

Optional dependencies (installed separately): faster-whisper and argostranslate.
The selected ffprobe stream index is always mapped explicitly. No network access
is used by this module; ASR and translation models must already be installed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
from typing import Callable, Protocol

from subtitle_media import audio_tracks, probe_media


class JobState(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    TRANSLATING = "translating"
    WRITING = "writing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCancelled(Exception):
    pass


@dataclass
class Cue:
    start: float
    end: float
    text: str


class Recognizer(Protocol):
    name: str
    def recognize(self, wav: Path, cancel: threading.Event) -> tuple[str, list[Cue]]: ...


class Translator(Protocol):
    name: str
    def translate(self, text: str, source: str, target: str) -> str: ...


class FasterWhisperRecognizer:
    def __init__(self, model_path: str, device: str = "cpu", compute_type: str = "int8"):
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self.name = f"faster-whisper ({model_path})"

    def recognize(self, wav: Path, cancel: threading.Event) -> tuple[str, list[Cue]]:
        from faster_whisper import WhisperModel  # optional dependency
        # local_files_only prevents an implicit model download during a job.
        model = WhisperModel(self.model_path, device=self.device,
                             compute_type=self.compute_type, local_files_only=True)
        segments, info = model.transcribe(str(wav), vad_filter=True)
        cues = []
        for segment in segments:
            if cancel.is_set():
                raise JobCancelled()
            if segment.text.strip():
                cues.append(Cue(float(segment.start), float(segment.end),
                                segment.text.strip()))
        return info.language, cues


class ArgosTranslator:
    name = "Argos Translate"

    def translate(self, text: str, source: str, target: str) -> str:
        from argostranslate import translate  # optional dependency
        languages = translate.get_installed_languages()
        src = next((l for l in languages if l.code == source), None)
        dst = next((l for l in languages if l.code == target), None)
        if src is None or dst is None:
            raise RuntimeError(f"Offline translation package not installed: {source} -> {target}")
        translation = src.get_translation(dst)
        if translation is None:
            raise RuntimeError(f"No offline translation route: {source} -> {target}")
        return translation.translate(text)


def _srt_time(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def render_srt(cues: list[Cue]) -> str:
    lines = []
    previous_end = 0.0
    for cue in cues:
        start = max(previous_end, cue.start, 0.0)
        end = max(start + 0.001, cue.end)
        text = re.sub(r"\s+", " ", cue.text).strip()
        if not text:
            continue
        lines.append(f"{len(lines) + 1}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
        previous_end = end
    return "\n".join(lines) + ("\n" if lines else "")


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".subtitle-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@dataclass
class SubtitleJob:
    video: Path
    stream_index: int
    output_directory: Path
    state: JobState = JobState.PENDING
    error: str | None = None
    srt_path: Path | None = None
    metadata_path: Path | None = None
    progress: float = 0.0
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def cancel(self) -> None:
        self.cancel_event.set()

    def status(self) -> dict:
        return {"state": self.state.value, "progress": self.progress,
                "error": self.error, "srt": str(self.srt_path) if self.srt_path else None}


class SubtitleProcessor:
    def __init__(self, recognizer: Recognizer, translator: Translator,
                 *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe"):
        self.recognizer = recognizer
        self.translator = translator
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

    @staticmethod
    def _check(job: SubtitleJob) -> None:
        if job.cancel_event.is_set():
            raise JobCancelled()

    def run(self, job: SubtitleJob, callback: Callable[[SubtitleJob], None] | None = None) -> SubtitleJob:
        """Run synchronously; UI must invoke in a worker thread, not Tk mainloop."""
        if job.state not in (JobState.PENDING, JobState.FAILED, JobState.CANCELLED):
            raise RuntimeError("Job already running or completed")
        job.error = None
        job.progress = 0.0
        job.srt_path = None
        job.metadata_path = None

        def stage(state: JobState, progress: float) -> None:
            job.state, job.progress = state, progress
            if callback:
                callback(job)

        try:
            self._check(job)
            video = job.video.resolve(strict=True)
            probe = probe_media(video, ffprobe=self.ffprobe)
            if job.stream_index not in [t.stream_index for t in audio_tracks(probe)]:
                raise ValueError(f"Invalid audio stream index: {job.stream_index}")
            stage(JobState.EXTRACTING, 0.1)
            with tempfile.TemporaryDirectory(prefix="cinema-subtitle-") as temp:
                wav = Path(temp) / "audio.wav"
                cmd = [self.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                       "-y", "-i", str(video), "-map", f"0:{job.stream_index}",
                       "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
                process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.PIPE)
                try:
                    while process.poll() is None:
                        if job.cancel_event.wait(0.1):
                            process.terminate()
                            try:
                                process.wait(timeout=2)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait()
                            raise JobCancelled()
                    stderr = process.stderr.read().decode("utf-8", errors="replace")
                    if process.returncode != 0:
                        raise RuntimeError(f"FFmpeg extraction failed: {stderr[-2000:]}")
                finally:
                    process.stderr.close()
                self._check(job)
                stage(JobState.TRANSCRIBING, 0.35)
                language, source_cues = self.recognizer.recognize(wav, job.cancel_event)
                self._check(job)
                if not source_cues:
                    raise RuntimeError("No speech detected")
                stage(JobState.TRANSLATING, 0.65)
                translated = []
                for cue in source_cues:
                    self._check(job)
                    translated_text = (cue.text if language == "de" else
                                       self.translator.translate(cue.text, language, "de"))
                    translated.append(Cue(cue.start, cue.end, translated_text))
                self._check(job)
                stage(JobState.WRITING, 0.9)
                # A stable file name includes the manually selected audio stream.
                basename = f"{video.stem}.audio-{job.stream_index}.de"
                output = job.output_directory
                srt = output / f"{basename}.srt"
                metadata = output / f"{basename}.subtitles.json"
                stat = video.stat()
                provenance = {
                    "generated": True, "source_file": str(video),
                    "source_size": stat.st_size, "source_mtime_ns": stat.st_mtime_ns,
                    "audio_stream_index": job.stream_index,
                    "source_language": language, "target_language": "de",
                    "recognition_tool": self.recognizer.name,
                    "translation_tool": (self.translator.name if language != "de" else None),
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "source_segments": [asdict(c) for c in source_cues],
                    "translated_segments": [asdict(c) for c in translated],
                }
                self._check(job)
                # Metadata first; SRT last so consumers only see a complete subtitle.
                _atomic_write(metadata, json.dumps(provenance, ensure_ascii=False, indent=2))
                self._check(job)
                _atomic_write(srt, render_srt(translated))
                job.srt_path, job.metadata_path = srt, metadata
            stage(JobState.COMPLETED, 1.0)
        except JobCancelled:
            stage(JobState.CANCELLED, job.progress)
        except Exception as exc:
            job.error = str(exc)
            stage(JobState.FAILED, job.progress)
        return job

    def start(self, job: SubtitleJob,
              callback: Callable[[SubtitleJob], None] | None = None) -> threading.Thread:
        thread = threading.Thread(target=self.run, args=(job, callback), daemon=True)
        thread.start()
        return thread
