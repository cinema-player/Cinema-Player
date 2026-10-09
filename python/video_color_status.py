"""Classify source HDR/SDR from ffprobe video-stream metadata.

This describes the *source*, not the actual mpv output. Tone mapping must be
reported separately from mpv's active video-output configuration.
"""
from __future__ import annotations

from typing import Any, Mapping

_HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}
_HDR_PRIMARIES = {"bt2020"}
_HDR_MATRICES = {"bt2020nc", "bt2020c"}
_SDR_TRANSFERS = {"bt709", "smpte170m", "bt470m", "bt470bg", "iec61966-2-1", "gamma22", "gamma28"}


def classify_video_stream(stream: Mapping[str, Any]) -> str:
    """Return 'HDR', 'SDR' or 'Unknown'; never infer SDR from missing tags."""
    transfer = str(stream.get("color_transfer") or "").lower()
    primaries = str(stream.get("color_primaries") or "").lower()
    side_data = stream.get("side_data_list") or []
    if transfer in _HDR_TRANSFERS:
        return "HDR"
    # Mastering metadata is strong HDR evidence, but BT.2020 primaries alone
    # are not: BT.2020 can also carry SDR.
    for entry in side_data:
        if not isinstance(entry, Mapping):
            continue
        kind = str(entry.get("side_data_type") or "").lower()
        if "mastering display metadata" in kind or "content light level metadata" in kind:
            return "HDR"
    if transfer in _SDR_TRANSFERS:
        return "SDR"
    return "Unknown"


def classify_ffprobe(probe: Mapping[str, Any]) -> str:
    """Classify the first video stream in ffprobe -show_streams JSON."""
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            return classify_video_stream(stream)
    return "Unknown"


def display_video_status(source: str, tone_mapping_active: bool | None = None) -> str:
    """Label source and output conversion without claiming unverified mapping."""
    if source == "SDR":
        return "Native SDR"
    if source == "HDR":
        if tone_mapping_active is True:
            return "HDR → SDR (Tone Mapping in mpv)"
        if tone_mapping_active is False:
            return "Native HDR"
        return "HDR (output not verified)"
    return "Unknown (insufficient metadata)"
