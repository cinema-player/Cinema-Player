"""Subtitle availability discovery for playlist rows.

Original means an embedded text subtitle stream or a sidecar without matching
Cinema Player provenance. Generated means a sidecar with valid provenance.
Both categories may coexist.
"""
from __future__ import annotations

import json
from pathlib import Path
from subtitle_media import probe_media

SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".vtt", ".sub")


def subtitle_status(path, *, ffprobe="ffprobe"):
    video = Path(path)
    result = {"original": False, "generated": False, "files": []}
    if not video.is_file():
        return result
    # Sidecars: video.srt, video.de.srt, video.audio-3.de.srt etc.
    for candidate in video.parent.iterdir():
        if not candidate.is_file() or candidate.suffix.lower() not in SUBTITLE_EXTENSIONS:
            continue
        if candidate.stem != video.stem and not candidate.stem.startswith(video.stem + "."):
            continue
        meta = candidate.with_suffix(".subtitles.json")
        generated = False
        if meta.is_file():
            try:
                info = json.loads(meta.read_text(encoding="utf-8"))
                stat = video.stat()
                generated = (info.get("generated") is True and
                             info.get("source_size") == stat.st_size and
                             info.get("source_mtime_ns") == stat.st_mtime_ns and
                             Path(info.get("source_file", "")).resolve() == video.resolve())
            except (OSError, ValueError, TypeError):
                pass
        result["generated" if generated else "original"] = True
        result["files"].append(str(candidate))
    try:
        probe = probe_media(video, ffprobe=ffprobe)
        if any(s.get("codec_type") == "subtitle" for s in probe.get("streams", [])):
            result["original"] = True
    except (OSError, ValueError, RuntimeError):
        pass
    return result


def subtitle_badge(status):
    if status["original"] and status["generated"]:
        return "UT Original + KI"
    if status["generated"]:
        return "UT KI"
    if status["original"]:
        return "UT Original"
    return ""
