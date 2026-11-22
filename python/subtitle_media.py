"""Media metadata and projector-insert profile for offline subtitle notices.

No display mode is changed here. The caller must resolve the actual mpv output
mode (especially HDR tone mapping) before requesting an insert profile.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping


@dataclass(frozen=True)
class AudioTrack:
    stream_index: int  # Absolute ffprobe stream index; usable with ffmpeg -map 0:<index>
    codec: str
    language: str | None
    title: str | None
    channels: int | None


@dataclass(frozen=True)
class InsertProfile:
    width: int
    height: int
    frame_rate: Fraction
    sample_aspect_ratio: Fraction
    color_primaries: str | None
    color_transfer: str | None
    color_space: str | None
    output_hdr: bool

    def cache_key(self) -> tuple:
        return (self.width, self.height, str(self.frame_rate),
                str(self.sample_aspect_ratio), self.color_primaries,
                self.color_transfer, self.color_space, self.output_hdr)


def probe_media(path: str | Path, *, ffprobe: str = "ffprobe") -> dict[str, Any]:
    """Probe all streams; subprocess arguments never pass through a shell."""
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def audio_tracks(probe: Mapping[str, Any]) -> list[AudioTrack]:
    tracks = []
    for stream in probe.get("streams", []):
        if stream.get("codec_type") != "audio":
            continue
        tags = stream.get("tags") or {}
        tracks.append(AudioTrack(
            stream_index=int(stream["index"]),
            codec=str(stream.get("codec_name") or "unknown"),
            language=tags.get("language"),
            title=tags.get("title"),
            channels=stream.get("channels"),
        ))
    return tracks


def selected_audio_map(track: AudioTrack) -> str:
    """Return an unambiguous FFmpeg stream mapping for manual track selection."""
    return f"0:{track.stream_index}"


def _ratio(value: Any, name: str) -> Fraction:
    try:
        ratio = Fraction(str(value))
        if ratio <= 0:
            raise ValueError
        return ratio
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"Invalid {name}: {value!r}") from exc


def insert_profile(
    probe: Mapping[str, Any],
    *,
    output_hdr: bool,
    output_color_primaries: str | None = None,
    output_color_transfer: str | None = None,
    output_color_space: str | None = None,
) -> InsertProfile:
    """Create a profile matching the source geometry and *actual* output color mode.

    HDR source metadata is not enough to infer output HDR: mpv may tone-map.
    Caller explicitly supplies output_hdr and resolved output color properties.
    """
    video = next((s for s in probe.get("streams", [])
                  if s.get("codec_type") == "video" and
                  (s.get("disposition") or {}).get("attached_pic") != 1), None)
    if video is None:
        raise ValueError("No video stream found")
    rate = video.get("avg_frame_rate")
    if not rate or rate == "0/0":
        rate = video.get("r_frame_rate")
    profile = InsertProfile(
        width=int(video["width"]),
        height=int(video["height"]),
        frame_rate=_ratio(rate, "frame rate"),
        sample_aspect_ratio=_ratio(
            video.get("sample_aspect_ratio") or "1:1", "sample aspect ratio"),
        color_primaries=output_color_primaries or video.get("color_primaries"),
        color_transfer=output_color_transfer or video.get("color_transfer"),
        color_space=output_color_space or video.get("color_space"),
        output_hdr=output_hdr,
    )
    if profile.width <= 0 or profile.height <= 0:
        raise ValueError("Invalid video dimensions")
    return profile


def requires_subtitle_notice(*, generated: bool, enabled: bool) -> bool:
    """The notice is shown only for selected, enabled, generated subtitles."""
    return generated and enabled
