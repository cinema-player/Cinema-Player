#!/usr/bin/env python3

"""
X11 / NVIDIA / mpv Video Player
Two mpv instances:
    - Main: exclusive video output on a separate HDMI output
    - Preview: separate mpv window on the control monitor
"""

import font_setup  # noqa: F401  — load Inter before tkinter opens fontconfig

import tkinter as tk
import subprocess
import socket
import json
import os
import re
import shutil
import math
import time
import threading
import tomllib
from dataclasses import dataclass, field, fields
from fractions import Fraction


VIDEO_OUTPUT = None
PREVIEW_WIDTH = 480
PREVIEW_HEIGHT = 270
PREVIEW_MARGIN = 20
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_app_version():
    """Program version lives in pyproject.toml so packaging and the GUI stay in sync."""
    path = os.path.join(ROOT_DIR, "pyproject.toml")
    try:
        with open(path, "rb") as handle:
            return tomllib.load(handle)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"


APP_VERSION = read_app_version()
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".dpx"}
VIDEO_EXTS = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m2ts", ".ts",
    ".mxf", ".mpg", ".mpeg", ".m4v", ".ogv",
}

FONT_FAMILY = "Inter"
FONT_TITLE = (FONT_FAMILY, 18, "bold")
FONT_STATUS = (FONT_FAMILY, 11, "bold")
FONT_UI = (FONT_FAMILY, 10)
FONT_UI_BOLD = (FONT_FAMILY, 10, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_ROW = (FONT_FAMILY, 9)
FONT_ROW_BOLD = (FONT_FAMILY, 10, "bold")


def mpv_supports_x11(path):
    try:
        result = subprocess.run(
            [path, "--gpu-context=help"],
            capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    text = f"{result.stdout}\n{result.stderr}".lower()
    return "x11" in text


def find_mpv():
    candidates = []
    env_path = os.environ.get("CINEMA_MPV")
    if env_path:
        candidates.append(env_path)
    candidates.extend([
        os.path.join(ROOT_DIR, ".tools", "bin", "mpv"),
        "/usr/bin/mpv",
    ])
    which = shutil.which("mpv")
    if which:
        candidates.append(which)

    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path) and os.access(path, os.X_OK) and mpv_supports_x11(path):
            return path

    raise RuntimeError(
        "Kein X11-fähiges mpv gefunden. "
        "Bitte `sudo apt install mpv` ausführen oder scripts/fetch-mpv.sh."
    )


def find_ffmpeg():
    which = shutil.which("ffmpeg")
    if which:
        return which
    raise RuntimeError("ffmpeg wurde nicht gefunden.")


_EBUR_INTEGRATED = re.compile(
    r"Integrated loudness:.*?I:\s*([+-]?\d+(?:\.\d+)?)\s*LUFS",
    re.IGNORECASE | re.DOTALL,
)


def format_loudness(lufs):
    if lufs is None:
        return "--"
    try:
        value = float(lufs)
    except (TypeError, ValueError):
        return "--"
    if not math.isfinite(value):
        return "--"
    return f"{value:.1f} LUFS"


def probe_loudness(path, ffmpeg_path=None):
    """Return integrated EBU R128 loudness in LUFS, or None if it cannot be measured."""
    ffmpeg = ffmpeg_path or find_ffmpeg()
    command = [
        ffmpeg, "-hide_banner", "-nostats",
        "-i", path,
        "-vn", "-sn", "-dn",
        "-map", "0:a:0",
        "-af", "ebur128",
        "-f", "null", "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    text = f"{result.stderr or ''}\n{result.stdout or ''}"
    match = _EBUR_INTEGRATED.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


@dataclass
class DisplayMode:
    output: str
    width: int
    height: int
    refresh: float
    x: int = 0
    y: int = 0
    name: str = ""

    @property
    def mode(self):
        return self.name or f"{self.width}x{self.height}"


@dataclass
class ModeTiming:
    width: int
    height: int
    pixel_clock: float
    hsync_start: int
    hsync_end: int
    htotal: int
    vsync_start: int
    vsync_end: int
    vtotal: int
    hsync: str
    vsync: str
    refresh: float


@dataclass
class VideoInfo:
    filename: str
    width: int
    height: int
    fps: float
    fps_fraction: Fraction


@dataclass
class PlaylistEntry:
    path: str
    filename: str = ""
    duration: float = 0.0
    container: str = ""
    video_codec: str = ""
    audio_codec: str = ""
    video_bitrate: int = 0
    audio_bitrate: int = 0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    aspect: str = "--"
    pixel_aspect: str = "--"
    resolution_label: str = ""
    autoplay: bool = False
    audio_tracks: list = field(default_factory=list)
    subtitle_tracks: list = field(default_factory=list)
    audio_track: str = "--"
    subtitle_track: str = "--"
    in_point: float | None = None
    out_point: float | None = None
    # Seconds a still image stays on screen; 0 keeps it until the operator resumes.
    display_time: float = 0.0
    is_image: bool = False
    refresh_ok: bool = True
    aspect_warning: bool = False
    par_warning: bool = False
    colorspace_warning: bool = False
    played: bool = False
    missing: bool = False
    volume: int = 100
    colorspace: str = "--"
    loudness_lufs: float | None = None

    def __post_init__(self):
        if not self.filename:
            self.filename = os.path.basename(self.path)
        self.volume = clamp_volume(self.volume)

    @classmethod
    def from_dict(cls, data):
        """Load an entry, ignoring keys from older playlist versions."""
        names = {f.name for f in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in names})


def clamp_volume(value, default=100):
    """Keep playlist and fader values in the 0–100 range used by mpv."""
    try:
        volume = int(round(float(value)))
    except (TypeError, ValueError):
        volume = default
    return max(0, min(100, volume))


def format_fps_label(fps):
    if not fps:
        return "--"
    known = (
        ("23.976p", 24000 / 1001),
        ("29.97p", 30000 / 1001),
        ("59.94p", 60000 / 1001),
    )
    for label, value in known:
        if abs(fps - value) < 0.02:
            return label
    if abs(fps - round(fps)) < 0.02:
        return f"{int(round(fps))}p"
    return f"{fps:.3f}p"


def resolution_label(width, height):
    if width >= 4096:
        return "DCI 4K"
    if width >= 3800:
        return "UHD"
    if width >= 1900:
        return "HD"
    if width and height:
        return f"{width}x{height}"
    return "--"


def parse_aspect_ratio(value):
    """Return (numerator, denominator) from ffprobe values like 16:9 or 64/45."""
    if value in (None, "", "--", "N/A", "nan"):
        return None
    text = str(value).strip()
    if text in ("0:1", "0/1", "0:0", "0/0"):
        return None
    separator = ":" if ":" in text else "/" if "/" in text else None
    try:
        if separator:
            left, right = text.split(separator, 1)
            num, den = float(left), float(right)
        else:
            num, den = float(text), 1.0
    except ValueError:
        return None
    if num <= 0 or den <= 0:
        return None
    return num, den


def format_aspect_ratio(num, den):
    fraction = Fraction(num / den).limit_denominator(1000)
    return f"{fraction.numerator}:{fraction.denominator}"


def same_aspect_ratio(left, right, tolerance=0.012):
    parsed_left = parse_aspect_ratio(left)
    parsed_right = parse_aspect_ratio(right)
    if not parsed_left or not parsed_right:
        return False
    return abs((parsed_left[0] / parsed_left[1]) - (parsed_right[0] / parsed_right[1])) < tolerance


def pixel_aspect_label(width, height, sample_ar=None, display_ar=None):
    parsed = parse_aspect_ratio(sample_ar)
    if not parsed and width and height:
        display = parse_aspect_ratio(display_ar)
        if display:
            storage = width / height
            if storage:
                parsed = (display[0] / display[1] / storage, 1.0)
    if not parsed:
        return "1:1" if width and height else "--"
    if abs(parsed[0] / parsed[1] - 1.0) < 0.001:
        return "1:1"
    return format_aspect_ratio(parsed[0], parsed[1])


def display_aspect_ratio(width, height, display_ar=None, sample_ar=None):
    parsed = parse_aspect_ratio(display_ar)
    if parsed:
        return parsed[0] / parsed[1]
    if width and height:
        storage = width / height
        sample = parse_aspect_ratio(sample_ar)
        if sample:
            return storage * (sample[0] / sample[1])
        return storage
    return 0.0


def aspect_label(width, height, display_ar=None, sample_ar=None):
    ratio = display_aspect_ratio(width, height, display_ar, sample_ar)
    if not ratio:
        return "--"
    presets = (
        (2.39, "21:9"), (2.35, "21:9"), (1.85, "1.85"),
        (16 / 9, "16:9"), (4 / 3, "4:3"), (2.0, "2:1"),
    )
    for value, label in presets:
        if abs(ratio - value) < 0.05:
            return label
    return format_aspect_ratio(ratio, 1.0)


def media_file_available(entry):
    """True when the playlist entry still points at a readable file."""
    return bool(entry and entry.path and os.path.isfile(entry.path))


def mark_missing_media(entries):
    """Flag entries whose media file is gone. Returns how many are missing."""
    missing = 0
    for entry in entries:
        entry.missing = not media_file_available(entry)
        if entry.missing:
            missing += 1
    return missing


def apply_playlist_warnings(entries, projection_zoom):
    """Mark aspect, PAR and colorspace changes against the previous readable clip."""
    previous_aspect = None
    previous_par = None
    previous_colorspace = None
    for entry in entries:
        if entry.missing:
            entry.aspect_warning = False
            entry.par_warning = False
            entry.colorspace_warning = False
            continue
        aspect_changed = (
            previous_aspect is not None
            and entry.aspect not in ("", "--")
            and entry.aspect != previous_aspect
        )
        par_ok = parse_aspect_ratio(entry.pixel_aspect) is not None
        par_changed = (
            previous_par is not None
            and par_ok
            and not same_aspect_ratio(previous_par, entry.pixel_aspect)
        )
        colorspace_ok = entry.colorspace not in ("", "--", None)
        colorspace_changed = (
            previous_colorspace is not None
            and colorspace_ok
            and entry.colorspace != previous_colorspace
        )
        entry.aspect_warning = bool(projection_zoom and aspect_changed)
        entry.par_warning = bool(projection_zoom and par_changed)
        entry.colorspace_warning = bool(projection_zoom and colorspace_changed)
        if entry.aspect not in ("", "--"):
            previous_aspect = entry.aspect
        if par_ok:
            previous_par = entry.pixel_aspect
        if colorspace_ok:
            previous_colorspace = entry.colorspace


def refresh_entry_aspect(entry):
    """Read display and pixel aspect from the media file when it is still on disk."""
    if os.path.isfile(entry.path):
        try:
            probed = probe_media(entry.path)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError, TypeError, ValueError, KeyError):
            probed = None
        if probed:
            entry.width = probed.width
            entry.height = probed.height
            entry.aspect = probed.aspect
            entry.pixel_aspect = probed.pixel_aspect
            entry.resolution_label = probed.resolution_label
            entry.video_codec = probed.video_codec
            entry.audio_codec = probed.audio_codec
            entry.video_bitrate = probed.video_bitrate
            entry.audio_bitrate = probed.audio_bitrate
            entry.colorspace = probed.colorspace
            return entry
    entry.pixel_aspect = pixel_aspect_label(
        entry.width, entry.height, entry.pixel_aspect, entry.aspect
    )
    entry.aspect = aspect_label(
        entry.width, entry.height, entry.aspect, entry.pixel_aspect
    )
    return entry


def parse_bitrate_bps(value):
    """Parse ffprobe bit/s values; 0 means unknown."""
    if value in (None, "", "N/A", "n/a"):
        return 0
    try:
        bps = float(str(value).strip())
    except (TypeError, ValueError):
        return 0
    if bps <= 0:
        return 0
    return int(round(bps))


def stream_bitrate_bps(stream, duration=0.0):
    """Read a stream bitrate, including MKV-style BPS tags when bit_rate is missing."""
    if not stream:
        return 0
    bps = parse_bitrate_bps(stream.get("bit_rate"))
    if bps:
        return bps
    tags = {str(key).upper(): value for key, value in (stream.get("tags") or {}).items()}
    for key in ("BPS", "BPS-ENG", "BITRATE", "BIT_RATE"):
        bps = parse_bitrate_bps(tags.get(key))
        if bps:
            return bps
    size = parse_bitrate_bps(tags.get("NUMBER_OF_BYTES") or tags.get("NUMBER_OF_BYTES-ENG"))
    if size and duration > 0:
        return int(round(size * 8 / duration))
    return 0


def format_bitrate(bps):
    """Human-readable media bitrate: Mbps for video-scale rates, kbps otherwise."""
    bps = parse_bitrate_bps(bps)
    if not bps:
        return ""
    if bps >= 1_000_000:
        mbps = bps / 1_000_000
        if mbps >= 10 or abs(mbps - round(mbps)) < 0.05:
            return f"{int(round(mbps))} Mbps"
        return f"{mbps:.1f} Mbps"
    kbps = bps / 1000
    if kbps >= 10 or abs(kbps - round(kbps)) < 0.5:
        return f"{int(round(kbps))} kbps"
    return f"{kbps:.1f} kbps"


def format_codec_rate(codec, bps):
    name = (codec or "").strip()
    rate = format_bitrate(bps)
    if name and rate:
        return f"{name} {rate}"
    return name or rate or "--"


_COLOR_UNSPECIFIED = {"", "unknown", "unspecified", "reserved", "n/a", "na", "none"}
_COLOR_GAMUT = {
    "bt709": "Rec.709",
    "bt470m": "NTSC",
    "bt470bg": "Rec.601",
    "smpte170m": "Rec.601",
    "smpte240m": "SMPTE 240M",
    "film": "Film",
    "bt2020": "Rec.2020",
    "bt2020nc": "Rec.2020",
    "bt2020-ncl": "Rec.2020",
    "bt2020c": "Rec.2020",
    "bt2020-cl": "Rec.2020",
    "smpte428": "CIE XYZ",
    "smpte431": "DCI-P3",
    "smpte432": "Display P3",
    "jedec-p22": "EBU 3213",
    "ebu3213": "EBU 3213",
    "fcc": "FCC",
    "rgb": "RGB",
    "ycgco": "YCgCo",
    "ictcp": "ICtCp",
}
_COLOR_TRANSFER = {
    "smpte2084": "PQ",
    "arib-std-b67": "HLG",
    "iec61966-2-1": "sRGB",
    "linear": "Linear",
    "log": "Log",
    "log_sqrt": "Log",
    "gamma22": "Gamma 2.2",
    "gamma28": "Gamma 2.8",
    "smpte428": "DCI",
}
_SDR_TRANSFER = {
    "bt709", "smpte170m", "bt601", "iec61966-2-4", "bt1361e",
    "bt2020-10", "bt2020-12", "smpte240m",
}


def _color_token(value):
    text = str(value or "").strip().lower().replace("_", "-")
    return "" if text in _COLOR_UNSPECIFIED else text


def format_colorspace(stream):
    """Compact operator label such as Rec.709 or Rec.2020 PQ."""
    if not stream:
        return "--"
    primaries = _COLOR_GAMUT.get(_color_token(stream.get("color_primaries")))
    matrix = _COLOR_GAMUT.get(_color_token(stream.get("color_space")))
    gamut = primaries or matrix
    transfer_key = _color_token(stream.get("color_transfer"))
    transfer = _COLOR_TRANSFER.get(transfer_key)
    if transfer == "sRGB":
        return "sRGB"
    if gamut and transfer and transfer_key not in _SDR_TRANSFER:
        return f"{gamut} {transfer}"
    if gamut:
        return gamut
    if transfer:
        return transfer
    return "--"


def format_clock(seconds):
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "--:--"
    if not math.isfinite(seconds) or seconds < 0:
        return "--:--"
    seconds = int(seconds)
    hours, rel = divmod(seconds, 3600)
    minutes, secs = divmod(rel, 60)
    if hours:
        return f"{hours:02}:{minutes:02}:{secs:02}"
    return f"{minutes:02}:{secs:02}"


def probe_media(path):
    entry = PlaylistEntry(path=path)
    entry.is_image = os.path.splitext(path)[1].lower() in IMAGE_EXTS
    command = [
        "ffprobe", "-v", "error",
        "-show_format", "-show_streams",
        "-of", "json", path,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    fmt = data.get("format") or {}
    entry.duration = float(fmt.get("duration") or 0)
    ext = os.path.splitext(path)[1].replace(".", "").upper()
    entry.container = ext or (fmt.get("format_name") or "").split(",")[0].upper()

    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]

    if video:
        entry.width = int(video.get("width") or 0)
        entry.height = int(video.get("height") or 0)
        rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
        if rate in ("0/0", "0/1", "", None):
            rate = video.get("r_frame_rate") or "0/1"
        try:
            entry.fps = float(Fraction(rate))
        except (ZeroDivisionError, ValueError):
            entry.fps = 0.0
        entry.video_codec = (video.get("codec_name") or "").upper()
        sample_ar = video.get("sample_aspect_ratio")
        display_ar = video.get("display_aspect_ratio")
        entry.pixel_aspect = pixel_aspect_label(
            entry.width, entry.height, sample_ar, display_ar
        )
        entry.aspect = aspect_label(
            entry.width, entry.height, display_ar, sample_ar
        )
        entry.resolution_label = resolution_label(entry.width, entry.height)
        entry.video_bitrate = stream_bitrate_bps(video, entry.duration)
        entry.colorspace = format_colorspace(video)

    if audios:
        names = []
        for index, stream in enumerate(audios, start=1):
            codec = (stream.get("codec_name") or "audio").upper()
            lang = stream.get("tags", {}).get("language", "")
            label = f"{index}: {codec}"
            if lang:
                label += f" ({lang})"
            names.append(label)
        entry.audio_tracks = names
        entry.audio_codec = (audios[0].get("codec_name") or "").upper()
        entry.audio_track = names[0]
        entry.audio_bitrate = stream_bitrate_bps(audios[0], entry.duration)
    if not entry.video_bitrate:
        leftover = parse_bitrate_bps(fmt.get("bit_rate")) - entry.audio_bitrate
        if leftover > 0:
            entry.video_bitrate = leftover
    if subs:
        names = ["--"]
        for index, stream in enumerate(subs, start=1):
            codec = (stream.get("codec_name") or "sub").upper()
            lang = stream.get("tags", {}).get("language", "")
            label = f"{index}: {codec}"
            if lang:
                label += f" ({lang})"
            names.append(label)
        entry.subtitle_tracks = names
        entry.subtitle_track = "--"
    return entry


def parse_mpv_audio_devices(help_text):
    """Parse `mpv --audio-device=help` into (id, description) pairs."""
    devices = []
    for line in (help_text or "").splitlines():
        match = re.match(r"\s+'([^']+)'\s+\((.*)\)\s*$", line)
        if match:
            devices.append((match.group(1), match.group(2)))
    return devices


def connector_hdmi_index(output_name):
    """Guess the HDMI audio endpoint index for an xrandr connector.

    NVIDIA typically exposes HDMI-0 as audio HDMI 0 and then DisplayPort
    pairs DP-0/1, DP-2/3, DP-4/5 as HDMI 1, 2 and 3.
    DRM names such as HDMI-A-1 are 1-based and map to HDMI 0.
    """
    if not output_name:
        return 0
    name = output_name.strip().upper().replace("DISPLAYPORT", "DP")
    number = re.search(r"(\d+)$", name)
    if not number:
        return 0
    index = int(number.group(1))
    if name.startswith("HDMI-A-") or re.match(r"^HDMI-A\d", name):
        return max(0, index - 1)
    if name.startswith("HDMI"):
        return index
    if name.startswith("DP-") or name.startswith("DP"):
        return 1 + (index // 2)
    return index


def score_program_audio_device(device_id, description, hdmi_index):
    """Higher scores are a better match for the projector HDMI audio jack."""
    ident = (device_id or "").lower()
    desc = (description or "").lower()
    if ident in {"auto", "pulse", "pipewire", "alsa", "jack", "sdl", "openal"}:
        return -1
    if ident == "alsa/pipewire":
        return -1
    if "hdmi" not in ident and "hdmi" not in desc:
        return -1
    if "plughw" in ident or "dmix" in ident or "surround" in ident:
        return -1

    score = 0
    if ident.startswith("pipewire/"):
        score += 80
    elif ident.startswith("pulse/"):
        score += 70
    elif ident.startswith("alsa/hdmi:"):
        score += 40
    else:
        return -1

    extra = re.search(r"hdmi(?:-stereo)?-extra(\d+)", ident)
    if extra:
        if int(extra.group(1)) == hdmi_index:
            score += 40
    elif hdmi_index == 0 and "hdmi-stereo" in ident:
        score += 40

    dev = re.search(r"dev=(\d+)", ident)
    if dev and int(dev.group(1)) == hdmi_index:
        score += 40

    alsa_hdmi = re.search(r"hdmi\s+(\d+)/", desc)
    if alsa_hdmi and int(alsa_hdmi.group(1)) == hdmi_index:
        score += 20
    return score


def choose_program_audio_device(devices, output_name):
    """Pick the mpv audio device that belongs to the projector output."""
    hdmi_index = connector_hdmi_index(output_name)
    ranked = []
    for device_id, description in devices:
        score = score_program_audio_device(device_id, description, hdmi_index)
        if score >= 0:
            ranked.append((score, device_id))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return ranked[0][1]


def list_mpv_audio_devices(mpv_path):
    try:
        result = subprocess.run(
            [mpv_path, "--no-config", "--audio-device=help"],
            capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_mpv_audio_devices(f"{result.stdout}\n{result.stderr}")


class VideoOutputManager:
    def __init__(self, video_output=None):
        self.video_output = video_output
        self.original_mode = None
        self.video_mode = None
        self.target_refresh = None
        self._program_audio_device = None
        self._program_audio_output = None

    @staticmethod
    def run(command):
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout

    def xrandr(self, *extra):
        return self.run(["xrandr", "--query", *extra])

    def get_outputs(self):
        outputs = []
        for line in self.xrandr().splitlines():
            match = re.match(r"^(\S+)\s+connected", line)
            if match:
                outputs.append(match.group(1))
        return outputs

    def get_primary_output(self):
        for line in self.xrandr().splitlines():
            match = re.match(r"^(\S+)\s+connected\s+primary", line)
            if match:
                return match.group(1)
        return None

    def get_output_geometry(self, output_name):
        pattern = (
            rf"^{re.escape(output_name)}\s+connected(?:\s+primary)?\s+"
            r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)"
        )
        for line in self.xrandr().splitlines():
            match = re.match(pattern, line)
            if match:
                return tuple(map(int, match.groups()))
        return None

    def get_control_output_geometry(self, prefer_x=None, prefer_y=None):
        """Control-monitor rectangle (width, height, x, y), never the projector.

        Tk -fullscreen covers the whole Xinerama desktop, including the beamer.
        Callers must size the GUI to this rectangle instead.
        """
        named = []
        for name in self.get_outputs():
            geometry = self.get_output_geometry(name)
            if geometry:
                named.append((name, geometry))
        if not named:
            return None

        beamer = self.video_output
        usable = [(name, geometry) for name, geometry in named if name != beamer]
        if not usable:
            return named[0][1]

        def contains(geometry, px, py):
            width, height, x, y = geometry
            return x <= px < x + width and y <= py < y + height

        if prefer_x is not None and prefer_y is not None:
            for name, geometry in usable:
                if contains(geometry, prefer_x, prefer_y):
                    return geometry

        primary = self.get_primary_output()
        for name, geometry in usable:
            if name == primary:
                return geometry
        return usable[0][1]

    def select_video_output(self, preferred=None):
        outputs = self.get_outputs()
        if not outputs:
            raise RuntimeError("Keine angeschlossenen X11-Ausgänge gefunden.")

        if preferred:
            if preferred not in outputs:
                raise RuntimeError(f"Ausgang {preferred} ist nicht angeschlossen.")
            self.video_output = preferred
            self._program_audio_device = None
            return preferred

        if self.video_output:
            if self.video_output not in outputs:
                raise RuntimeError(f"Ausgang {self.video_output} ist nicht angeschlossen.")
            return self.video_output

        primary = self.get_primary_output()
        for output in outputs:
            if output != primary:
                self.video_output = output
                self._program_audio_device = None
                return output

        self.video_output = outputs[0]
        self._program_audio_device = None
        return self.video_output

    def set_video_output(self, name):
        """Switch the projector connector and restore the previous display mode."""
        outputs = self.get_outputs()
        if name not in outputs:
            raise RuntimeError(f"Ausgang {name} ist nicht angeschlossen.")
        if name == self.video_output:
            return name
        self.restore_original_mode()
        self.video_output = name
        self.video_mode = None
        self._program_audio_device = None
        self._program_audio_output = None
        return name

    def program_audio_device(self, mpv_path):
        """Audio device for program playback: the projector HDMI, not the desktop default."""
        output = self.video_output
        if not output:
            try:
                output = self.select_video_output()
            except RuntimeError:
                return None
        if self._program_audio_device and self._program_audio_output == output:
            return self._program_audio_device
        device = choose_program_audio_device(list_mpv_audio_devices(mpv_path), output)
        self._program_audio_device = device
        self._program_audio_output = output
        return device

    def get_modes(self, output_name):
        modes = []
        inside = False
        for line in self.xrandr().splitlines():
            if re.match(r"^\S+\s+connected", line):
                inside = line.startswith(output_name + " ")
                continue
            if not inside:
                continue
            if re.match(r"^\S+", line):
                break

            match = re.match(r"^\s*(\S+)\s+(.+)$", line)
            if not match:
                continue

            name = match.group(1)
            dim = re.search(r"(\d+)x(\d+)", name)
            if not dim or re.search(r"\di(?:\s|$)", name.lower()):
                continue

            width = int(dim.group(1))
            height = int(dim.group(2))

            for token in match.group(2).split():
                current = "*" in token
                token = token.replace("*", "").replace("+", "")
                if token.endswith("i"):
                    continue
                try:
                    refresh = float(token)
                except ValueError:
                    continue
                modes.append(DisplayMode(
                    output_name, width, height, refresh,
                    name=name, x=0, y=0
                ))
                if current:
                    modes[-1].name = name
        return modes

    def get_current_mode(self, output_name):
        lines = self.xrandr().splitlines()
        width = height = x = y = None
        inside = False

        for line in lines:
            if line.startswith(output_name + " "):
                inside = True
                match = re.search(
                    r"connected.*?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line
                )
                if match:
                    width, height, x, y = map(int, match.groups())
                continue

            if inside and re.match(r"^\S+", line):
                break

            if not inside or width is None or height is None:
                continue

            match = re.match(r"^\s*(\S+)\s+(.+)$", line)
            if not match:
                continue

            name = match.group(1)
            dim = re.search(r"(\d+)x(\d+)", name)
            if not dim:
                continue
            if int(dim.group(1)) != width or int(dim.group(2)) != height:
                continue

            for token in match.group(2).split():
                if "*" not in token:
                    continue
                token = token.replace("*", "").replace("+", "")
                try:
                    refresh = float(token)
                except ValueError:
                    continue
                return DisplayMode(
                    output_name, width, height, refresh, x, y, name=name
                )
        return None

    def get_preferred_mode(self, output_name):
        inside = False
        for line in self.xrandr().splitlines():
            if re.match(r"^\S+\s+connected", line):
                inside = line.startswith(output_name + " ")
                continue
            if not inside:
                continue
            if re.match(r"^\S+", line):
                break
            if "+" not in line:
                continue
            match = re.match(r"^\s*(\S+)\s+(.+)$", line)
            if not match:
                continue
            name = match.group(1)
            dim = re.search(r"(\d+)x(\d+)", name)
            if not dim:
                continue
            for token in match.group(2).split():
                if "+" not in token:
                    continue
                token = token.replace("*", "").replace("+", "")
                try:
                    refresh = float(token)
                except ValueError:
                    continue
                return DisplayMode(
                    output_name,
                    int(dim.group(1)), int(dim.group(2)),
                    refresh, name=name
                )
        return None

    def get_timings(self, output_name):
        timings = []
        inside = False
        lines = self.run(["xrandr", "--verbose"]).splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if re.match(r"^\S+\s+(dis)?connected", line):
                inside = line.startswith(output_name + " ")
                i += 1
                continue
            if not inside:
                i += 1
                continue

            header = re.match(
                r"^\s+(\d+)x(\d+)\s+\(\S+\)\s+([\d.]+)MHz\s+"
                r"([+-])HSync\s+([+-])VSync",
                line,
            )
            if not header:
                i += 1
                continue

            h_line = lines[i + 1] if i + 1 < len(lines) else ""
            v_line = lines[i + 2] if i + 2 < len(lines) else ""
            h = re.search(
                r"h:\s+width\s+(\d+)\s+start\s+(\d+)\s+end\s+(\d+)\s+total\s+(\d+)",
                h_line,
            )
            v = re.search(
                r"v:\s+height\s+(\d+)\s+start\s+(\d+)\s+end\s+(\d+)\s+total\s+(\d+)"
                r".*?clock\s+([\d.]+)Hz",
                v_line,
            )
            if h and v:
                pixel_clock = float(header.group(3))
                htotal = int(h.group(4))
                vtotal = int(v.group(4))
                refresh = float(v.group(5))
                if htotal and vtotal:
                    refresh = pixel_clock * 1_000_000 / (htotal * vtotal)
                timings.append(ModeTiming(
                    width=int(header.group(1)),
                    height=int(header.group(2)),
                    pixel_clock=pixel_clock,
                    hsync_start=int(h.group(2)),
                    hsync_end=int(h.group(3)),
                    htotal=htotal,
                    vsync_start=int(v.group(2)),
                    vsync_end=int(v.group(3)),
                    vtotal=vtotal,
                    hsync=f"{header.group(4)}HSync",
                    vsync=f"{header.group(5)}VSync",
                    refresh=refresh,
                ))
            i += 3
        return timings

    def get_video_info(self, filename):
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
                "-of", "json", filename
            ],
            capture_output=True, text=True, check=True
        )
        stream = json.loads(result.stdout)["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        rate = stream.get("avg_frame_rate")
        if not rate or rate == "0/0":
            rate = stream["r_frame_rate"]
        fps_fraction = Fraction(rate)
        return VideoInfo(filename, width, height, float(fps_fraction), fps_fraction)

    @staticmethod
    def refresh_matches(fps, refresh):
        if fps <= 0 or refresh <= 0:
            return False
        if abs(fps - refresh) < 0.03:
            return True
        for multiplier in range(1, 5):
            if abs(refresh - fps * multiplier) / fps < 0.01:
                return True
        return False

    @staticmethod
    def refresh_close(left, right):
        return abs(left - right) <= max(0.15, right * 0.003)

    @staticmethod
    def target_refresh_rates(fps):
        """Rates that give judder-free playback, best first.

        For 24/25 fps prefer 48/50 Hz over 24/25 Hz (less flicker).
        """
        candidates = []
        for multiplier in range(1, 5):
            rate = fps * multiplier
            if rate < 20 or rate > 120:
                continue
            if multiplier == 2 and fps < 48:
                rank = 0
            elif multiplier == 1 and fps < 48:
                rank = 1
            else:
                rank = multiplier + 1
            candidates.append((rank, multiplier, rate))
        candidates.sort()
        return [(rate, multiplier) for rank, multiplier, rate in candidates]

    @staticmethod
    def refresh_score(fps, refresh):
        if abs(fps - refresh) < 0.03:
            return abs(fps - refresh)

        best = float("inf")
        for multiplier in range(1, 5):
            expected = fps * multiplier
            relative_error = abs(expected - refresh) / fps
            if relative_error < 0.01:
                score = relative_error + multiplier * 0.0001
                best = min(best, score)

        if best != float("inf"):
            return best
        return 10 + abs(refresh - fps) / fps

    def native_resolution(self, output_name):
        current = self.get_current_mode(output_name)
        if current:
            return current.width, current.height
        preferred = self.get_preferred_mode(output_name)
        if preferred:
            return preferred.width, preferred.height
        modes = self.get_modes(output_name)
        if not modes:
            return None
        best = max(modes, key=lambda m: m.width * m.height)
        return best.width, best.height

    def find_refresh_mode(self, modes, width, height, rate):
        matches = [
            m for m in modes
            if m.width == width and m.height == height
            and self.refresh_close(m.refresh, rate)
        ]
        if matches:
            return matches[0]
        return None

    def find_best_mode(self, video, create=True):
        modes = self.get_modes(self.video_output)
        if not modes:
            return None, False

        native = self.native_resolution(self.video_output)
        targets = self.target_refresh_rates(video.fps)
        self.target_refresh = targets[0][0] if targets else video.fps

        if native:
            native_modes = [
                m for m in modes
                if m.width == native[0] and m.height == native[1]
            ]
            for rate, _multiplier in targets:
                found = self.find_refresh_mode(modes, native[0], native[1], rate)
                if found:
                    return found, True

            if create:
                for rate, _multiplier in targets:
                    created = self.ensure_custom_mode(
                        self.video_output, native[0], native[1], rate
                    )
                    if created:
                        return created, True

            if native_modes:
                native_modes.sort(key=lambda m: self.refresh_score(video.fps, m.refresh))
                fallback = native_modes[0]
                return fallback, self.refresh_matches(video.fps, fallback.refresh)

        for rate, _multiplier in targets:
            rated = [
                m for m in modes
                if self.refresh_close(m.refresh, rate)
            ]
            if not rated:
                continue
            if native:
                rated.sort(
                    key=lambda m: abs(m.width * m.height - native[0] * native[1])
                )
            return rated[0], True

        modes.sort(key=lambda m: self.refresh_score(video.fps, m.refresh))
        fallback = modes[0]
        return fallback, self.refresh_matches(video.fps, fallback.refresh)

    def ensure_custom_mode(self, output_name, width, height, refresh):
        modes = self.get_modes(output_name)
        existing = self.find_refresh_mode(modes, width, height, refresh)
        if existing:
            return existing

        timing = None
        for candidate in self.get_timings(output_name):
            if candidate.width == width and candidate.height == height:
                timing = candidate
                break
        if timing is None:
            timings = self.get_timings(output_name)
            timing = timings[0] if timings else None
            if timing is None or timing.width != width or timing.height != height:
                return None

        name, modeline = self.modeline_for_refresh(timing, refresh)
        try:
            subprocess.run(
                ["xrandr", "--newmode", name, *modeline],
                capture_output=True, text=True, check=False,
            )
            added = subprocess.run(
                ["xrandr", "--addmode", output_name, name],
                capture_output=True, text=True, check=False,
            )
        except OSError:
            return None

        if added.returncode != 0:
            print(
                f"xrandr --addmode {output_name} {name} fehlgeschlagen: "
                f"{added.stderr.strip() or added.stdout.strip()}"
            )
            return None

        for mode in self.get_modes(output_name):
            if mode.name == name or self.find_refresh_mode(
                [mode], width, height, refresh
            ):
                return mode
        return DisplayMode(output_name, width, height, refresh, name=name)

    @staticmethod
    def modeline_for_refresh(timing, refresh):
        current = timing.refresh or (
            timing.pixel_clock * 1_000_000 / (timing.htotal * timing.vtotal)
        )
        clock = timing.pixel_clock * (refresh / current)
        name = f"cinema_{timing.width}x{timing.height}_{refresh:.2f}".replace(".", "p")
        modeline = [
            f"{clock:.4f}",
            str(timing.width),
            str(timing.hsync_start),
            str(timing.hsync_end),
            str(timing.htotal),
            str(timing.height),
            str(timing.vsync_start),
            str(timing.vsync_end),
            str(timing.vtotal),
            timing.hsync,
            timing.vsync,
        ]
        return name, modeline

    def set_mode(self, mode):
        if self.original_mode is None:
            self.original_mode = self.get_current_mode(mode.output)

        current = self.get_current_mode(mode.output)
        if (
            current
            and current.width == mode.width
            and current.height == mode.height
            and self.refresh_close(current.refresh, mode.refresh)
        ):
            mode.x, mode.y = current.x, current.y
            self.video_mode = mode
            return

        command = [
            "xrandr", "--output", mode.output,
            "--mode", mode.mode,
        ]
        if re.fullmatch(r"\d+x\d+", mode.mode):
            command.extend(["--rate", f"{mode.refresh:.3f}"])

        subprocess.run(command, capture_output=True, text=True, check=True)
        time.sleep(0.2)

        geometry = self.get_output_geometry(mode.output)
        if geometry:
            mode.x = geometry[2]
            mode.y = geometry[3]

        actual = self.get_current_mode(mode.output)
        if actual:
            mode.refresh = actual.refresh
            mode.width = actual.width
            mode.height = actual.height
            mode.x, mode.y = actual.x, actual.y

        self.video_mode = mode

    def prepare_for_video(self, filename):
        if not self.video_output:
            self.select_video_output()

        video = self.get_video_info(filename)
        mode, matched = self.find_best_mode(video)
        if mode is None:
            raise RuntimeError("Kein geeigneter Display-Modus gefunden.")

        self.set_mode(mode)
        actual = self.get_current_mode(self.video_output) or mode
        matched = self.refresh_matches(video.fps, actual.refresh)
        self.video_mode = actual if actual.output else mode
        if actual:
            actual.name = actual.name or mode.name
            self.video_mode = actual
        return video, self.video_mode, matched

    def effective_mode(self):
        """The mode the video window covers, even before a clip was prepared."""
        if self.video_mode:
            return self.video_mode
        if not self.video_output:
            self.select_video_output()
        return self.get_current_mode(self.video_output)

    def get_mpv_geometry(self):
        mode = self.effective_mode()
        if not mode:
            raise RuntimeError("Kein Video-Modus gesetzt.")
        # Offsets are relative to --screen-name, not the virtual desktop.
        return f"{mode.width}x{mode.height}+0+0"

    def get_mpv_arguments(self, mpv_path=None):
        mode = self.effective_mode()
        if not mode:
            raise RuntimeError("Kein Video-Modus gesetzt.")
        arguments = [
            "--no-border",
            "--fullscreen=no",
            "--keepaspect=yes",
            "--video-sync=display-resample",
            f"--override-display-fps={mode.refresh:.3f}",
            "--hwdec=auto-safe",
            "--vo=gpu",
            "--gpu-context=x11egl",
            "--force-window=yes",
            "--osd-level=0",
            "--osc=no",
            "--cursor-autohide=always",
            # Stills stay up until the player decides otherwise, not for mpv's default second.
            "--image-display-duration=inf",
            f"--geometry={self.get_mpv_geometry()}",
        ]
        if self.video_output:
            arguments.append(f"--screen-name={self.video_output}")
            arguments.append(f"--fs-screen-name={self.video_output}")
        audio = self.program_audio_device(mpv_path or find_mpv())
        if audio:
            arguments.append(f"--audio-device={audio}")
        return arguments

    def restore_original_mode(self):
        if not self.original_mode:
            return

        mode = self.original_mode
        try:
            subprocess.run(
                [
                    "xrandr", "--output", mode.output,
                    "--mode", mode.mode,
                    "--rate", f"{mode.refresh:.6f}"
                ],
                check=True
            )
        except Exception as e:
            print("Fehler beim Wiederherstellen:", e)

        self.original_mode = None
        self.video_mode = None


class MPVController:
    def __init__(self, name, mpv_path):
        self.name = name
        self.mpv_path = mpv_path
        self.socket_path = f"/tmp/mpv_{name}_{os.getpid()}.sock"
        self.log_path = f"/tmp/mpv_{name}_{os.getpid()}.log"
        self.process = None
        self.socket = None
        self.running = False
        self.callbacks = []
        self.reader_thread = None
        self._send_lock = threading.Lock()
        self.loaded_path = None
        self.pending_start = None
        self.pending_end = None
        self.play_on_load = False

    def _read_log_tail(self, limit=2000):
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as handle:
                return handle.read()[-limit:]
        except OSError:
            return ""

    def _startup_error(self, reason):
        details = self._read_log_tail()
        if details:
            return f"{reason}\n\nmpv-Log ({self.log_path}):\n{details}"
        return reason

    def start(self, arguments):
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        command = [self.mpv_path] + list(arguments) + [
            "--idle=yes",
            "--keep-open=yes",
            "--input-ipc-server=" + self.socket_path,
            "--terminal=no",
            "--log-file=" + self.log_path,
        ]

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(100):
            if self.process.poll() is not None:
                raise RuntimeError(self._startup_error(
                    f"mpv {self.name} ist beim Start beendet."
                ))
            if os.path.exists(self.socket_path):
                break
            time.sleep(0.05)

        if not os.path.exists(self.socket_path):
            raise RuntimeError(self._startup_error(
                f"IPC-Socket von mpv {self.name} wurde nicht erzeugt."
            ))

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(self.socket_path)
        self.running = True

        self.reader_thread = threading.Thread(
            target=self._reader, daemon=True
        )
        self.reader_thread.start()

        self.observe("time-pos", 1)
        self.observe("duration", 2)
        self.observe("pause", 3)
        self.observe("eof-reached", 4)

    def set_vid(self, enabled):
        self.command("set_property", "vid", "auto" if enabled else "no")

    def set_loop_file(self, enabled):
        self.command("set_property", "loop-file", "inf" if enabled else "no")

    def _reader(self):
        buffer = b""
        while self.running:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
                buffer += data

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        message = json.loads(line.decode())
                    except Exception:
                        continue

                    for callback in self.callbacks:
                        try:
                            callback(self, message)
                        except Exception:
                            pass
            except Exception:
                break

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def command(self, *args):
        if not self.socket:
            return

        data = (json.dumps({"command": list(args)}) + "\n").encode()
        try:
            with self._send_lock:
                self.socket.sendall(data)
        except Exception as exc:
            print(f"mpv {self.name} IPC-Fehler: {exc}")

    def observe(self, property_name, observer_id):
        self.command("observe_property", observer_id, property_name)

    def load_file(self, filename, start=None, end=None, play=True):
        self.loaded_path = os.path.abspath(filename)
        self.pending_start = None if start is None else float(start)
        self.pending_end = None if end is None else float(end)
        self.play_on_load = play
        options = {}
        if self.pending_start is not None:
            options["start"] = str(self.pending_start)
        if self.pending_end is not None:
            options["end"] = str(self.pending_end)
        if options:
            option_str = ",".join(f"{key}={value}" for key, value in options.items())
            self.command("loadfile", filename, "replace", option_str)
        else:
            self.command("loadfile", filename, "replace")

    def apply_pending_range(self):
        if self.pending_start is not None:
            self.set_position(self.pending_start)
        if self.pending_end is not None:
            self.command("set_property", "end", self.pending_end)
        else:
            self.command("set_property", "end", "no")
        if self.play_on_load:
            self.set_pause(False)
        else:
            self.set_pause(True)

    def has_file(self, path):
        if not self.loaded_path or not path:
            return False
        return os.path.abspath(self.loaded_path) == os.path.abspath(path)

    def play_pause(self):
        self.command("cycle", "pause")

    def set_pause(self, value):
        self.command("set_property", "pause", bool(value))

    def stop(self):
        self.loaded_path = None
        self.pending_start = None
        self.pending_end = None
        self.command("stop")

    def seek(self, seconds):
        self.command("seek", seconds, "relative")

    def set_position(self, position):
        self.command("set_property", "time-pos", float(position))

    def set_volume(self, volume):
        self.command("set_property", "volume", float(volume))

    def quit(self):
        self.running = False

        try:
            self.command("quit")
        except Exception:
            pass

        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        if self.process:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass



def main():
    import cinema_gui
    root = tk.Tk()
    cinema_gui.VideoPlayerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
