"""Classify source HDR/SDR from ffprobe video-stream metadata.

This describes the *source*, not the actual mpv output. Tone mapping must be
reported separately from mpv's active video-output configuration.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

_HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}
# BT.2020-10/12 are the SDR opto-electronic transfer, not PQ or HLG.
_SDR_TRANSFERS = {
    "bt709", "smpte170m", "bt470m", "bt470bg", "bt601", "smpte240m",
    "iec61966-2-1", "iec61966-2-4", "bt1361e",
    "gamma22", "gamma28", "bt2020-10", "bt2020-12",
}
_UNSPECIFIED = {"", "unknown", "unspecified", "reserved", "n/a", "na", "none"}
_PACKED_10 = re.compile(r"^p0(\d{2})")
_HIGH_BIT = re.compile(r"p(\d{2})(?:le|be)?$")


def _token(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    return "" if text in _UNSPECIFIED else text


def _bit_depth(stream: Mapping[str, Any]) -> int | None:
    """Bits per sample, or 8 when the pixel format is an ordinary 8-bit layout."""
    raw = stream.get("bits_per_raw_sample")
    try:
        depth = int(raw)
    except (TypeError, ValueError):
        depth = 0
    if depth > 0:
        return depth
    fmt = _token(stream.get("pix_fmt"))
    if not fmt:
        return None
    packed = _PACKED_10.match(fmt)
    if packed:
        return int(packed.group(1))
    high = _HIGH_BIT.search(fmt)
    if high:
        return int(high.group(1))
    return 8


def classify_video_stream(stream: Mapping[str, Any]) -> str:
    """Return 'HDR', 'SDR' or 'Unknown'.

    PQ, HLG and HDR mastering metadata are HDR. A named SDR transfer, including
    Rec.2020's 10- and 12-bit curves, is SDR. Untagged 8-bit pictures are SDR
    too: that is the usual file from cameras and editors. Untagged 10-bit
    stays unknown, because it can be either.
    """
    transfer = _token(stream.get("color_transfer"))
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
    depth = _bit_depth(stream)
    if not transfer and depth is not None and depth <= 8:
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
