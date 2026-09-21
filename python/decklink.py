"""Blackmagic DeckLink detection and program playout.

DeckLink cards are not desktop connectors. Program video is encoded by mpv
(raw UYVY or Nut on stdout) and handed to ffmpeg (`-f decklink`) or
GStreamer (`decklinkvideosink`). mpv keeps sending frames (a looping black
clip while idle) so SDI/HDMI stay locked; the card mode is the GStreamer
`mode=` / ffmpeg `-format_code` used when the sink process starts.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import struct
import subprocess
import tempfile
import threading
import time
import ctypes
from ctypes import util as ctypes_util
from dataclasses import dataclass
from fractions import Fraction


OUTPUT_PREFIX = "decklink:"
CONNECTOR_SDI = "sdi"
CONNECTOR_HDMI = "hdmi"
CONNECTOR_OPTICAL = "optical"
CONNECTOR_SEP = "|"
CONNECTOR_ORDER = (CONNECTOR_SDI, CONNECTOR_HDMI, CONNECTOR_OPTICAL)
CONNECTOR_BITS = {
    CONNECTOR_SDI: 1 << 0,
    CONNECTOR_HDMI: 1 << 1,
    CONNECTOR_OPTICAL: 1 << 2,
}
CONNECTOR_LABELS = {
    CONNECTOR_SDI: "SDI",
    CONNECTOR_HDMI: "HDMI",
    CONNECTOR_OPTICAL: "Optical SDI",
}
CONNECTOR_LABEL_KEYS = {
    CONNECTOR_SDI: "decklink_sdi",
    CONNECTOR_HDMI: "decklink_hdmi",
    CONNECTOR_OPTICAL: "decklink_optical_sdi",
}
_CONNECTOR_ALIASES = {
    "sdi": CONNECTOR_SDI,
    "hdmi": CONNECTOR_HDMI,
    "optical": CONNECTOR_OPTICAL,
    "optical_sdi": CONNECTOR_OPTICAL,
    "optical-sdi": CONNECTOR_OPTICAL,
    "opticalsdi": CONNECTOR_OPTICAL,
}
# Cards that expose more than one program video connector when the name is silent.
_MULTI_OUTPUT_RE = re.compile(
    r"mini monitor|ultrastudio|\bstudio\b|extreme|8k pro|\bintensity\b",
    re.IGNORECASE,
)

_BMD_VIDEO_OUTPUT_CONNECTIONS = 0x766F636E  # 'vocn'
_BMD_CONFIG_VIDEO_OUTPUT = 0x766F6362  # 'vocb'
_IID_ATTRIBUTES = (
    "ABC11843-17FE-4B49-9FEA-046B8DC59F3D",  # IDeckLinkAttributes
    "2B54EDEF-5B32-429F-BA11-BB990596EACD",  # IDeckLinkProfileAttributes
)
_IID_CONFIGURATION = (
    "1E69F0D6-BC8A-4A4E-92D3-7DF60A4BF3E0",  # IDeckLinkConfiguration
)

_DEVICE_CACHE = (None, ())
# gst-device-monitor takes ~2.5 s here; the TTL must outlive that or every
# lookup misses and clip start waits on a full rescan.
_DEVICE_CACHE_TTL = 45.0
_MODE_CACHE = {}
_FFMPEG_DECKLINK = {}
_GST_DECKLINK = None
_BACKEND_CACHE = None
_SILENCE_WAV = None

_SINK_LINE = re.compile(
    r"^\s*(?:\[[^\]]+\]\s*)?(?:['\"]([^'\"]+)['\"]|(.+?))\s*(?:\[[^\]]+\])?\s*$"
)
_FORMAT_LINE = re.compile(
    r"(?P<code>[A-Za-z0-9][A-Za-z0-9_ ]{1,12})\s+"
    r"(?P<width>\d+)\s*[x×]\s*(?P<height>\d+)\s*"
    r"(?P<scan>[ip])?\s+"
    r"(?P<fps>\d+(?:\.\d+)?(?:\s*/\s*\d+)?)",
    re.IGNORECASE,
)
_FORMAT_ALT = re.compile(
    r"(?:format\s+\d+|format_code)\s*[:=]?\s*(?P<code>\S+).*?"
    r"(?P<width>\d+)\s*[x×]\s*(?P<height>\d+).*?"
    r"(?P<fps>\d+(?:\.\d+)?(?:/\d+)?)\s*(?:fps|p|i)?",
    re.IGNORECASE,
)
_GST_OUTPUT_SUFFIX = re.compile(
    r"\s*\((?:Video|Audio)\s+Output\)\s*$",
    re.IGNORECASE,
)
_GST_CAPS_LINE = re.compile(
    r"width\s*=\s*(?P<width>\d+)[^\n]*?"
    r"height\s*=\s*(?P<height>\d+)[^\n]*?"
    r"interlace-mode\s*=\s*(?P<scan>[^,;\s]+)[^\n]*?"
    r"framerate\s*=\s*(?P<num>\d+)\s*/\s*(?P<den>\d+)",
    re.IGNORECASE,
)


@dataclass
class DeckLinkDevice:
    name: str
    index: int = 0
    backend: str = ""
    connectors: tuple = ()
    persistent_id: int | None = None
    advertised_modes: tuple = ()

    def __post_init__(self):
        if self.connectors:
            self.connectors = tuple(ordered_connectors(self.connectors))
        else:
            self.connectors = tuple(infer_connectors(self.name))

    @property
    def output_id(self):
        return make_output_id(self.name)

    def output_ids(self):
        if needs_connector_selector(self.connectors):
            return [make_output_id(self.name, connector) for connector in self.connectors]
        return [self.output_id]


@dataclass
class DeckLinkMode:
    width: int
    height: int
    refresh: float
    format_code: str = ""
    gst_mode: str = ""
    interlaced: bool = False
    description: str = ""


@dataclass
class DeckLinkSink:
    """Running ffmpeg/gst process that reads mpv stdout."""

    process: subprocess.Popen
    backend: str
    log_path: str
    stdin: object = None


def is_decklink_output(name):
    return bool(name) and str(name).startswith(OUTPUT_PREFIX)


def parse_output_id(name):
    """Split `decklink:Card|sdi` into (device_name, connector_or_None)."""
    text = name or ""
    if not is_decklink_output(text):
        return text, None
    rest = text[len(OUTPUT_PREFIX):]
    if CONNECTOR_SEP in rest:
        device, suffix = rest.rsplit(CONNECTOR_SEP, 1)
        connector = _CONNECTOR_ALIASES.get(suffix.strip().lower())
        if connector and device:
            return canonical_device_name(device), connector
    return canonical_device_name(rest), None


def make_output_id(device_name, connector=None):
    if connector:
        return f"{OUTPUT_PREFIX}{device_name}{CONNECTOR_SEP}{connector}"
    return f"{OUTPUT_PREFIX}{device_name}"


def canonical_device_name(name):
    """Strip GStreamer suffixes such as '(Video Output)'."""
    return _GST_OUTPUT_SUFFIX.sub("", (name or "").strip())


def decklink_device_name(name):
    if not is_decklink_output(name):
        return canonical_device_name(name)
    device, _connector = parse_output_id(name)
    return canonical_device_name(device)


def ordered_connectors(connectors):
    wanted = {str(item).strip().lower() for item in connectors or () if item}
    wanted = {_CONNECTOR_ALIASES.get(item, item) for item in wanted}
    return tuple(item for item in CONNECTOR_ORDER if item in wanted)


def connectors_from_mask(mask):
    try:
        bits = int(mask)
    except (TypeError, ValueError):
        return ()
    found = tuple(
        name for name, bit in CONNECTOR_BITS.items() if bits & bit
    )
    return ordered_connectors(found)


def infer_connectors(device_name):
    """SDI / HDMI / Optical SDI from the product name when the SDK is silent."""
    text = re.sub(r"\s+", " ", device_name or "").strip().lower()
    named = []
    if "optical" in text:
        named.append(CONNECTOR_OPTICAL)
    elif "sdi" in text:
        named.append(CONNECTOR_SDI)
    if "hdmi" in text:
        named.append(CONNECTOR_HDMI)
    named = list(ordered_connectors(named))
    if CONNECTOR_SDI in named and CONNECTOR_HDMI in named:
        return tuple(named)
    if CONNECTOR_OPTICAL in named and CONNECTOR_HDMI in named:
        return tuple(named)
    if named and not _MULTI_OUTPUT_RE.search(text):
        return tuple(named)
    if _MULTI_OUTPUT_RE.search(text):
        if "intensity" in text and "sdi" not in text and "optical" not in text:
            return (CONNECTOR_HDMI,)
        extra = list(named)
        if CONNECTOR_SDI not in extra and CONNECTOR_OPTICAL not in extra:
            extra.insert(0, CONNECTOR_SDI)
        if CONNECTOR_HDMI not in extra:
            extra.append(CONNECTOR_HDMI)
        return ordered_connectors(extra)
    if named:
        return tuple(named)
    return (CONNECTOR_SDI,)


def needs_connector_selector(connectors):
    return len(ordered_connectors(connectors)) > 1


def connector_label_key(connector):
    return CONNECTOR_LABEL_KEYS.get(connector, "decklink_sdi")


def connector_label(connector):
    return CONNECTOR_LABELS.get(connector, (connector or "").upper())


def format_device_label(device_name):
    name = device_name or ""
    if name.lower().startswith("decklink"):
        return name
    return f"DeckLink · {name}"


def format_output_label(name):
    if not is_decklink_output(name):
        return name or ""
    device, connector = parse_output_id(name)
    label = format_device_label(device)
    if connector:
        return f"{label} · {connector_label(connector)}"
    return label


def group_decklink_outputs(output_ids):
    """Preserve order; each group is (device_name, [(output_id, connector), ...])."""
    groups = []
    index = {}
    for output_id in output_ids or ():
        device, connector = parse_output_id(output_id)
        if device not in index:
            index[device] = []
            groups.append((device, index[device]))
        index[device].append((output_id, connector))
    return groups


def fps_fraction(fps):
    if not fps:
        return Fraction(25, 1)
    known = (
        Fraction(24000, 1001),
        Fraction(24, 1),
        Fraction(25, 1),
        Fraction(30000, 1001),
        Fraction(30, 1),
        Fraction(50, 1),
        Fraction(60000, 1001),
        Fraction(60, 1),
    )
    for frac in known:
        if abs(float(frac) - float(fps)) < 0.02:
            return frac
    return Fraction(float(fps)).limit_denominator(1001)


def fps_arg(fps):
    frac = fps_fraction(fps)
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


def gst_mode_name(width, height, refresh, interlaced=False):
    frac = fps_fraction(refresh)
    token = {
        Fraction(24000, 1001): "2398",
        Fraction(24, 1): "24",
        Fraction(25, 1): "25",
        Fraction(30000, 1001): "2997",
        Fraction(30, 1): "30",
        Fraction(50, 1): "50",
        Fraction(60000, 1001): "5994",
        Fraction(60, 1): "60",
    }.get(frac, str(frac.numerator) if frac.denominator == 1 else "25")
    scan = "i" if interlaced else "p"
    # GStreamer uses 2kdcip25 / 4kdcip25 for DCI; 1080p25 is strictly 1920x1080.
    if width >= 4000 and height >= 2100:
        return f"4kdci{scan}{token}"
    if width >= 3800 and height >= 2100:
        return f"2160{scan}{token}"
    if width >= 2000 and height >= 1000:
        return f"2kdci{scan}{token}"
    if width == 1920 and height == 1080:
        return f"1080{scan}{token}"
    if width == 1280 and height == 720:
        return f"720{scan}{token}"
    if width == 720 and height in (486, 480):
        return "ntsc"
    if width == 720 and height == 576:
        return "pal"
    return f"1080{scan}{token}"


def parse_fps_token(text):
    token = (text or "").replace(" ", "")
    if "/" in token:
        num, den = token.split("/", 1)
        try:
            value = float(num) / float(den)
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0
        return value if value > 0 else 0.0
    try:
        return float(token)
    except (TypeError, ValueError):
        return 0.0


def parse_sinks(text):
    """Parse `ffmpeg -sinks decklink` / deprecated list_devices output."""
    names = []
    if not text:
        return names
    collecting = False
    for raw in text.splitlines():
        line = raw.strip()
        lower = line.lower()
        if "sink" in lower and "decklink" in lower:
            collecting = True
            continue
        if "output device" in lower and "decklink" in lower:
            collecting = True
            continue
        if "input device" in lower and "decklink" in lower:
            continue
        if not line or line.startswith("["):
            # Keep bracketed ffmpeg lines that still carry a quoted name.
            quoted = re.findall(r"['\"]([^'\"]+)['\"]", line)
            if quoted and ("decklink" in lower or collecting):
                for name in quoted:
                    if name and name not in names:
                        names.append(name)
            continue
        if lower.startswith("auto-detected") or lower.startswith("devices"):
            collecting = True
            continue
        match = _SINK_LINE.match(line)
        if not match:
            continue
        name = (match.group(1) or match.group(2) or "").strip()
        name = re.sub(r"\s*\[decklink\]\s*$", "", name, flags=re.IGNORECASE)
        name = name.strip(" -:\t")
        if not name or name.lower() in {"dummy", "none", "null"}:
            continue
        if name not in names:
            names.append(name)
    return names


def parse_list_formats(text):
    """Parse ffmpeg `-f decklink -list_formats 1` listings."""
    modes = []
    seen = set()
    if not text:
        return modes
    for raw in text.splitlines():
        line = raw.strip()
        if not line or "supported format" in line.lower() or line.lower().startswith("format_code"):
            continue
        match = _FORMAT_LINE.search(line) or _FORMAT_ALT.search(line)
        if not match:
            continue
        width = int(match.group("width"))
        height = int(match.group("height"))
        fps = parse_fps_token(match.group("fps"))
        if width < 320 or height < 240 or fps < 10:
            continue
        scan = ""
        if "scan" in match.groupdict() and match.group("scan"):
            scan = match.group("scan").lower()
        interlaced = scan == "i" or bool(re.search(r"\binterlace", line, re.IGNORECASE))
        if interlaced:
            continue
        code = (match.group("code") or "").strip()
        if code.lower() in {"format", "format_code", "frame_size", "fps"}:
            code = ""
        key = (width, height, round(fps, 3))
        if key in seen:
            continue
        seen.add(key)
        modes.append(DeckLinkMode(
            width=width,
            height=height,
            refresh=fps,
            format_code=code,
            gst_mode=gst_mode_name(width, height, fps, interlaced=False),
            interlaced=False,
            description=line,
        ))
    return modes


def parse_gst_caps_modes(text):
    """Progressive modes advertised on a gst-device-monitor block."""
    modes = []
    seen = set()
    for match in _GST_CAPS_LINE.finditer(text or ""):
        scan = (match.group("scan") or "").lower()
        if "interleave" in scan or scan == "mixed":
            continue
        width = int(match.group("width"))
        height = int(match.group("height"))
        num = int(match.group("num"))
        den = int(match.group("den") or 1) or 1
        fps = num / den
        if width < 320 or height < 240 or fps < 10:
            continue
        key = (width, height, round(fps, 3))
        if key in seen:
            continue
        seen.add(key)
        modes.append(DeckLinkMode(
            width=width,
            height=height,
            refresh=fps,
            gst_mode=gst_mode_name(width, height, fps, interlaced=False),
        ))
    return modes


def parse_gst_device_monitor(text):
    """Unique DeckLink sinks from `gst-device-monitor-1.0 Video/Sink`."""
    devices = []
    seen = set()
    if not text:
        return devices
    blocks = re.split(r"\nDevice found:\n", "\n" + text)
    for block in blocks[1:]:
        blob = block.lower()
        if "decklink" not in blob and "blackmagic" not in blob:
            continue
        display = re.search(r"display-name\s*=\s*(.+)$", block, re.MULTILINE)
        model = re.search(r"model-name\s*=\s*(.+)$", block, re.MULTILINE)
        named = re.search(r"^\tname\s*:\s*(.+)$", block, re.MULTILINE)
        raw = ""
        if display:
            raw = display.group(1).strip()
        elif model:
            raw = model.group(1).strip()
        elif named:
            raw = named.group(1).strip()
        name = canonical_device_name(raw)
        if not name:
            continue
        persistent = None
        pid = re.search(r"persistent-id\s*=\s*(-?\d+)", block)
        if pid:
            persistent = int(pid.group(1))
        key = persistent if persistent not in (None, -1) else name.lower()
        if key in seen:
            continue
        seen.add(key)
        devices.append(DeckLinkDevice(
            name=name,
            index=len(devices),
            backend="gstreamer",
            persistent_id=persistent if persistent not in (None, -1) else None,
            advertised_modes=tuple(parse_gst_caps_modes(block)),
        ))
    return devices


def fallback_modes():
    """Progressive HD/UHD family used when the card cannot list formats."""
    rates = (
        (24000 / 1001, "Hp2398", "1080p2398"),
        (24.0, "Hp24", "1080p24"),
        (25.0, "Hp25", "1080p25"),
        (30000 / 1001, "Hp2997", "1080p2997"),
        (30.0, "Hp30", "1080p30"),
        (50.0, "Hp50", "1080p50"),
        (60000 / 1001, "Hp5994", "1080p5994"),
        (60.0, "Hp60", "1080p60"),
    )
    sizes = (
        (1920, 1080, "H"),
        (3840, 2160, "U"),
        (1280, 720, "hp"),
    )
    modes = []
    for width, height, prefix in sizes:
        for fps, hd_code, gst in rates:
            if width == 1280 and fps < 49:
                continue
            if prefix == "H":
                code = hd_code
                gst_name = gst
            elif prefix == "U":
                code = hd_code.replace("Hp", "Up", 1)
                gst_name = gst.replace("1080", "2160", 1)
            else:
                code = hd_code.replace("Hp", "hp", 1)
                gst_name = gst.replace("1080", "720", 1)
            modes.append(DeckLinkMode(
                width=width,
                height=height,
                refresh=fps,
                format_code=code,
                gst_mode=gst_name,
            ))
    return modes


def _run(command, timeout=8):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return f"{result.stdout or ''}\n{result.stderr or ''}"


def find_host_ffmpeg(preferred=None):
    """Prefer a distro ffmpeg; Pixi's build is almost never DeckLink-enabled."""
    candidates = []
    if preferred:
        candidates.append(preferred)
    candidates.extend([
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        shutil.which("ffmpeg"),
    ])
    seen = set()
    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def ffmpeg_has_decklink(ffmpeg_path):
    if not ffmpeg_path:
        return False
    cached = _FFMPEG_DECKLINK.get(ffmpeg_path)
    if cached is not None:
        return cached
    text = _run([ffmpeg_path, "-hide_banner", "-sinks", "decklink"], timeout=6)
    lower = text.lower()
    found = False
    if "unknown output format" in lower or "unknown input format" in lower:
        found = False
    elif "not enabled" in lower or "no such device" in lower and "decklink" in lower:
        if "auto-detected" not in lower and "sink" not in lower:
            found = False
        elif "decklink" in lower and ("sink" in lower or "device" in lower or "[" in lower):
            found = True
    elif "decklink" in lower and ("sink" in lower or "device" in lower or "[" in lower):
        found = True
    elif "decklink" in lower:
        muxers = _run([ffmpeg_path, "-hide_banner", "-muxers"], timeout=6)
        found = bool(re.search(r"\bdecklink\b", muxers, re.IGNORECASE))
    _FFMPEG_DECKLINK[ffmpeg_path] = found
    return found


def decklink_api_present():
    if ctypes_util.find_library("DeckLinkAPI"):
        return True
    return any(
        os.path.exists(path)
        for path in (
            "/usr/lib/libDeckLinkAPI.so",
            "/usr/lib/x86_64-linux-gnu/libDeckLinkAPI.so",
            "/usr/local/lib/libDeckLinkAPI.so",
        )
    )


def gst_has_decklink():
    global _GST_DECKLINK
    if _GST_DECKLINK is not None:
        return _GST_DECKLINK
    inspect = shutil.which("gst-inspect-1.0")
    if not inspect:
        _GST_DECKLINK = False
        return False
    text = _run([inspect, "decklinkvideosink"], timeout=6)
    _GST_DECKLINK = (
        "decklinkvideosink" in text.lower() and "no such element" not in text.lower()
    )
    return _GST_DECKLINK


def find_gst_launch():
    return shutil.which("gst-launch-1.0")


def _list_ffmpeg_devices(ffmpeg_path):
    if not ffmpeg_has_decklink(ffmpeg_path):
        return []
    text = _run([ffmpeg_path, "-hide_banner", "-sinks", "decklink"], timeout=6)
    names = parse_sinks(text)
    if names:
        return names
    text = _run(
        [ffmpeg_path, "-hide_banner", "-f", "decklink", "-list_devices", "1", "-i", "dummy"],
        timeout=6,
    )
    return parse_sinks(text)


def _probe_gst_devices():
    """Ask GStreamer for DeckLink sinks; fall back to device-number 0 if the plugin exists."""
    if not gst_has_decklink():
        return []
    monitor = shutil.which("gst-device-monitor-1.0")
    if monitor:
        text = _run([monitor, "Video/Sink"], timeout=8)
        devices = parse_gst_device_monitor(text)
        if devices:
            return devices
    if decklink_api_present():
        return [DeckLinkDevice(name="DeckLink", index=0, backend="gstreamer")]
    return []


class _CFUUID(ctypes.Structure):
    _fields_ = [
        ("data1", ctypes.c_uint32),
        ("data2", ctypes.c_uint16),
        ("data3", ctypes.c_uint16),
        ("data4", ctypes.c_uint8 * 8),
    ]


def _guid(text):
    hex_str = (text or "").replace("-", "")
    data4 = (ctypes.c_uint8 * 8)(
        *[int(hex_str[16 + index * 2:18 + index * 2], 16) for index in range(8)]
    )
    return _CFUUID(
        int(hex_str[0:8], 16),
        int(hex_str[8:12], 16),
        int(hex_str[12:16], 16),
        data4,
    )


def _load_decklink_api():
    names = [
        ctypes_util.find_library("DeckLinkAPI"),
        "libDeckLinkAPI.so",
        "/usr/lib/libDeckLinkAPI.so",
        "/usr/lib/x86_64-linux-gnu/libDeckLinkAPI.so",
        "/usr/local/lib/libDeckLinkAPI.so",
    ]
    seen = set()
    for name in names:
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


def _com_vtbl(obj):
    return ctypes.cast(obj, ctypes.POINTER(ctypes.c_void_p))[0]


def _com_method(obj, index, restype, *argtypes):
    slot = ctypes.cast(_com_vtbl(obj), ctypes.POINTER(ctypes.c_void_p))[index]
    proto = ctypes.CFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(slot)


def _com_release(obj):
    if not obj:
        return
    try:
        _com_method(obj, 2, ctypes.c_uint32)(obj)
    except Exception:
        pass


def _com_query_interface(obj, iid_text):
    out = ctypes.c_void_p()
    iid = _guid(iid_text)
    method = _com_method(
        obj, 0, ctypes.c_int32, ctypes.POINTER(_CFUUID), ctypes.POINTER(ctypes.c_void_p)
    )
    result = method(obj, ctypes.byref(iid), ctypes.byref(out))
    if result != 0 or not out.value:
        return None
    return out.value


def _com_string(obj, index):
    raw = ctypes.c_void_p()
    method = _com_method(obj, index, ctypes.c_int32, ctypes.POINTER(ctypes.c_void_p))
    if method(obj, ctypes.byref(raw)) != 0 or not raw.value:
        return ""
    try:
        value = ctypes.cast(raw, ctypes.c_char_p).value or b""
        text = value.decode("utf-8", "replace")
    finally:
        try:
            libc = ctypes.CDLL(ctypes_util.find_library("c") or "libc.so.6")
            libc.free.argtypes = [ctypes.c_void_p]
            libc.free(raw)
        except Exception:
            pass
    return text


def _iter_sdk_devices():
    library = _load_decklink_api()
    if library is None:
        return
    try:
        create = library.CreateDeckLinkIteratorInstance
        create.restype = ctypes.c_void_p
        create.argtypes = []
        iterator = create()
    except Exception:
        return
    if not iterator:
        return
    try:
        while True:
            item = ctypes.c_void_p()
            nxt = _com_method(
                iterator, 3, ctypes.c_int32, ctypes.POINTER(ctypes.c_void_p)
            )
            if nxt(iterator, ctypes.byref(item)) != 0 or not item.value:
                break
            yield item.value
    finally:
        _com_release(iterator)


def _sdk_attribute_int(device, attr_id):
    for iid in _IID_ATTRIBUTES:
        iface = _com_query_interface(device, iid)
        if not iface:
            continue
        try:
            value = ctypes.c_int64()
            getter = _com_method(
                iface, 4, ctypes.c_int32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_int64)
            )
            if getter(iface, attr_id, ctypes.byref(value)) == 0:
                return int(value.value)
        finally:
            _com_release(iface)
    return None


def _sdk_set_config_int(device, cfg_id, value):
    for iid in _IID_CONFIGURATION:
        iface = _com_query_interface(device, iid)
        if not iface:
            continue
        try:
            setter = _com_method(
                iface, 5, ctypes.c_int32, ctypes.c_uint32, ctypes.c_int64
            )
            if setter(iface, cfg_id, int(value)) != 0:
                return False
            try:
                write = _com_method(iface, 11, ctypes.c_int32)
                write(iface)
            except Exception:
                pass
            return True
        finally:
            _com_release(iface)
    return False


def query_sdk_output_connections():
    """Map DeckLink display names to connector tuples. Empty if the SDK is missing."""
    found = {}
    try:
        for device in _iter_sdk_devices():
            try:
                display = _com_string(device, 4) or _com_string(device, 3)
                mask = _sdk_attribute_int(device, _BMD_VIDEO_OUTPUT_CONNECTIONS)
                connectors = connectors_from_mask(mask) if mask else ()
                if display and connectors:
                    found[display] = connectors
            finally:
                _com_release(device)
    except Exception:
        return {}
    return found


def configure_video_connection(device_name, connector):
    """Switch the card to SDI, HDMI, or Optical SDI. Fail-soft if ctypes cannot."""
    bit = CONNECTOR_BITS.get(connector)
    if not bit or not device_name:
        return False
    wanted = device_name.strip().lower()
    try:
        for device in _iter_sdk_devices():
            try:
                display = _com_string(device, 4) or _com_string(device, 3)
                if (display or "").strip().lower() != wanted:
                    continue
                return _sdk_set_config_int(device, _BMD_CONFIG_VIDEO_OUTPUT, bit)
            finally:
                _com_release(device)
    except Exception:
        return False
    return False


def _lookup_connectors(name, sdk_connectors):
    if not sdk_connectors:
        return infer_connectors(name)
    wanted = (name or "").strip().lower()
    for sdk_name, connectors in sdk_connectors.items():
        if (sdk_name or "").strip().lower() == wanted and connectors:
            return connectors
    return infer_connectors(name)


def list_decklink_devices(ffmpeg_path=None, refresh=False):
    """Connected DeckLink outputs that can be offered as the beamer."""
    global _DEVICE_CACHE
    now = time.monotonic()
    cached_at, cached = _DEVICE_CACHE
    if (
        not refresh
        and cached_at is not None
        and now - cached_at < _DEVICE_CACHE_TTL
    ):
        return list(cached)

    ffmpeg_path = find_host_ffmpeg(ffmpeg_path)
    names = _list_ffmpeg_devices(ffmpeg_path)
    sdk_connectors = query_sdk_output_connections()
    if names:
        devices = [
            DeckLinkDevice(
                name=canonical_device_name(name),
                index=index,
                backend="ffmpeg",
                connectors=_lookup_connectors(canonical_device_name(name), sdk_connectors),
            )
            for index, name in enumerate(names)
        ]
    else:
        devices = []
        for index, device in enumerate(_probe_gst_devices()):
            device.index = index
            device.backend = device.backend or "gstreamer"
            device.name = canonical_device_name(device.name)
            device.connectors = _lookup_connectors(device.name, sdk_connectors)
            devices.append(device)
    _DEVICE_CACHE = (time.monotonic(), tuple(devices))
    return list(devices)


def list_decklink_output_ids(ffmpeg_path=None, refresh=False):
    ids = []
    for device in list_decklink_devices(ffmpeg_path, refresh):
        ids.extend(device.output_ids())
    return ids


def find_device(output_id, ffmpeg_path=None):
    wanted = canonical_device_name(
        decklink_device_name(output_id) if is_decklink_output(output_id) else output_id
    )
    wanted_lower = wanted.lower()
    for device in list_decklink_devices(ffmpeg_path):
        if canonical_device_name(device.name).lower() == wanted_lower:
            return device
        if device.output_id == make_output_id(wanted):
            return device
    return None


def canonicalize_output_id(output_id, ffmpeg_path=None):
    """Map a saved `decklink:Card` id onto SDI when the card has several ports."""
    if not is_decklink_output(output_id):
        return output_id
    device = find_device(output_id, ffmpeg_path)
    if device is None:
        return output_id
    _name, connector = parse_output_id(output_id)
    if not needs_connector_selector(device.connectors):
        return device.output_id
    if connector in device.connectors:
        return make_output_id(device.name, connector)
    for fallback in CONNECTOR_ORDER:
        if fallback in device.connectors:
            return make_output_id(device.name, fallback)
    return device.output_id


def list_decklink_modes(output_id, ffmpeg_path=None):
    device = find_device(output_id, ffmpeg_path)
    if device is None:
        return []
    cache_key = device.name
    cached = _MODE_CACHE.get(cache_key)
    if cached is not None:
        return list(cached)

    ffmpeg_path = find_host_ffmpeg(ffmpeg_path)
    modes = []
    if device.advertised_modes:
        modes = list(device.advertised_modes)
    elif ffmpeg_path and ffmpeg_has_decklink(ffmpeg_path):
        text = _run(
            [
                ffmpeg_path, "-hide_banner",
                "-f", "lavfi", "-i", "color=c=black:s=64x64:r=25",
                "-t", "0.04",
                "-f", "decklink", "-list_formats", "1",
                device.name,
            ],
            timeout=10,
        )
        modes = parse_list_formats(text)
    if not modes:
        modes = fallback_modes()
    _MODE_CACHE[cache_key] = tuple(modes)
    return list(modes)


def choose_decklink_backend(ffmpeg_path=None):
    global _BACKEND_CACHE
    if _BACKEND_CACHE is not None:
        return _BACKEND_CACHE
    ffmpeg_path = find_host_ffmpeg(ffmpeg_path)
    if ffmpeg_path and ffmpeg_has_decklink(ffmpeg_path):
        _BACKEND_CACHE = ("ffmpeg", ffmpeg_path)
        return _BACKEND_CACHE
    if gst_has_decklink() and find_gst_launch():
        _BACKEND_CACHE = ("gstreamer", find_gst_launch())
        return _BACKEND_CACHE
    _BACKEND_CACHE = (None, ffmpeg_path)
    return _BACKEND_CACHE


def playout_available(ffmpeg_path=None):
    backend, _path = choose_decklink_backend(ffmpeg_path)
    return backend is not None


def video_filter(width, height, refresh, pixel_format="yuv422p"):
    rate = fps_arg(refresh)
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"fps={rate},format={pixel_format}"
    )


def encoder_time_base(fps):
    """rawvideo/yuv4mpeg time_base (1/fps). mpv 0.41 dropped --oautofps."""
    frac = fps_fraction(fps)
    return f"{frac.denominator}/{frac.numerator}"


def black_video_path(width, height, refresh, ffmpeg_path=None):
    """1 s looping black clip so the encoder keeps sending frames (PNG cannot)."""
    width = int(width or 1920)
    height = int(height or 1080)
    rate = fps_arg(refresh)
    path = os.path.join(
        tempfile.gettempdir(),
        f"cinema-player-decklink-black-{width}x{height}-{rate.replace('/', '-')}.mp4",
    )
    if os.path.isfile(path) and os.path.getsize(path) > 1000:
        return path
    ffmpeg_path = find_host_ffmpeg(ffmpeg_path)
    if not ffmpeg_path:
        return None
    try:
        result = subprocess.run(
            [
                ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi",
                "-i", f"color=c=black:s={width}x{height}:r={rate}",
                "-t", "1", "-pix_fmt", "yuv420p", "-c:v", "mpeg4", "-q:v", "8",
                path,
            ],
            capture_output=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not os.path.isfile(path):
        return None
    return path


def silence_wav_path():
    """1 s of stereo 48 kHz silence so image clips still produce an audio stream."""
    global _SILENCE_WAV
    if _SILENCE_WAV and os.path.isfile(_SILENCE_WAV):
        return _SILENCE_WAV
    path = os.path.join(tempfile.gettempdir(), "cinema-player-decklink-silence.wav")
    rate = 48000
    frames = rate  # 1 second
    data = b"\x00\x00" * frames * 2
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(data),
        b"WAVE",
        b"fmt ",
        16,
        1,
        2,
        rate,
        rate * 4,
        4,
        16,
        b"data",
        len(data),
    )
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(data)
    _SILENCE_WAV = path
    return path


def mpv_arguments(mode, backend, audio_file=None):
    """mpv encoding args that write a live stream to stdout for the DeckLink sink."""
    vf = video_filter(
        mode.width, mode.height, mode.refresh,
        pixel_format="uyvy422" if backend == "gstreamer" else "yuv422p",
    )
    tb = encoder_time_base(mode.refresh)
    common = [
        "--force-window=no",
        "--keepaspect=yes",
        "--hwdec=no",
        "--osd-level=0",
        "--osc=no",
        "--sid=no",
        "--sub-auto=no",
        "--image-display-duration=inf",
        # Encoding has no display to wait for; untimed keeps raw frames flowing.
        "--untimed=yes",
        f"--vf={vf}",
        "--o=-",
        f"--ovcopts=time_base={tb}",
    ]
    if backend == "gstreamer":
        # Raw UYVY, no Y4M header — gst y4mdec aborts if the first stdin chunk is short.
        return common + [
            "--of=rawvideo",
            "--ovc=rawvideo",
            "--ovcopts-append=pixel_format=uyvy422",
            "--no-audio",
        ]
    silence = audio_file or silence_wav_path()
    return common + [
        f"--audio-file={silence}",
        "--audio-samplerate=48000",
        "--audio-channels=stereo",
        "--video-sync=audio",
        "--of=nut",
        "--ovc=rawvideo",
        "--oac=pcm_s16le",
        "--ovcopts-append=pixel_format=uyvy422",
    ]


def _ffmpeg_command(ffmpeg_path, device, mode):
    width, height = mode.width, mode.height
    rate = fps_arg(mode.refresh)
    vf_in = (
        f"[2:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={rate},format=yuv422p[vsrc];"
        f"[0:v][vsrc]overlay=eof_action=repeat:repeatlast=1:shortest=0[vout];"
        f"[2:a]aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo[asrc];"
        f"[1:a][asrc]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    )
    command = [
        ffmpeg_path, "-hide_banner", "-loglevel", "warning",
        "-f", "lavfi", "-thread_queue_size", "64",
        "-i", f"color=c=black:s={width}x{height}:r={rate}",
        "-f", "lavfi", "-thread_queue_size", "64",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-fflags", "+nobuffer", "-thread_queue_size", "64",
        "-i", "pipe:0",
        "-filter_complex", vf_in,
        "-map", "[vout]", "-map", "[aout]",
        "-pix_fmt", "uyvy422",
        "-s", f"{width}x{height}",
        "-r", rate,
        "-ac", "2", "-ar", "48000",
        "-f", "decklink",
    ]
    if getattr(mode, "format_code", ""):
        command.extend(["-format_code", mode.format_code])
    command.append(device.name)
    return command


def _gst_command(gst_launch, device, mode):
    width, height = int(mode.width), int(mode.height)
    frac = fps_fraction(mode.refresh)
    gst_mode = mode.gst_mode or gst_mode_name(width, height, mode.refresh)
    caps = (
        f"video/x-raw,format=UYVY,width={width},height={height},"
        f"framerate={frac.numerator}/{frac.denominator}"
    )
    sink_id = (
        f"persistent-id={device.persistent_id}"
        if device.persistent_id not in (None, -1)
        else f"device-number={device.index}"
    )
    # One live video path: compositor+empty fdsrc never pushes to the card, so
    # EnableVideoOutput never runs (no picture, no frequency switch). mpv's
    # looping black clip keeps the raster up until the program clip arrives.
    frame_bytes = max(width * height * 2, 4096)
    return [
        gst_launch, "-q",
        "fdsrc", "fd=0", "is-live=true", "do-timestamp=true",
        f"blocksize={frame_bytes}",
        "!", "queue", "max-size-buffers=8", "leaky=downstream",
        "!", "rawvideoparse", "use-sink-caps=false", "format=UYVY",
        f"width={width}", f"height={height}",
        f"framerate={frac.numerator}/{frac.denominator}",
        "!", "videoconvert", "!", caps,
        "!", "decklinkvideosink", sink_id, f"mode={gst_mode}", "sync=true",
    ]


def start_sink(output_id, mode, ffmpeg_path=None, log_path=None):
    """Start ffmpeg or GStreamer reading mpv's stdout. Returns DeckLinkSink."""
    device = find_device(output_id, ffmpeg_path)
    if device is None:
        raise RuntimeError(f"DeckLink-Gerät {decklink_device_name(output_id)} ist nicht angeschlossen.")
    _name, connector = parse_output_id(output_id)
    if connector:
        configure_video_connection(device.name, connector)
    backend, tool = choose_decklink_backend(ffmpeg_path)
    if backend is None:
        raise RuntimeError(
            "DeckLink-Ausgabe braucht Blackmagic Desktop Video und ffmpeg "
            "(--enable-decklink) oder GStreamer decklinkvideosink."
        )
    if log_path is None:
        log_path = f"/tmp/cinema-player-decklink-{os.getpid()}.log"
    if backend == "ffmpeg":
        command = _ffmpeg_command(tool, device, mode)
    else:
        command = _gst_command(tool, device, mode)
    log_handle = open(log_path, "ab")
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
    except (ValueError, OSError):
        pass
    env = os.environ.copy()
    env.setdefault("GST_DEBUG", "0")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    except OSError as exc:
        log_handle.close()
        raise RuntimeError(f"DeckLink-Ausgabe konnte nicht gestartet werden: {exc}") from exc

    # Detect an immediate failure (missing plugin, busy card) before mpv attaches.
    for _ in range(2):
        time.sleep(0.05)
        if process.poll() is not None:
            break
    if process.poll() is not None:
        log_handle.close()
        detail = ""
        try:
            with open(log_path, encoding="utf-8", errors="replace") as handle:
                detail = handle.read()[-1500:]
        except OSError:
            detail = ""
        message = "DeckLink-Ausgabe ist beim Start beendet."
        if detail.strip():
            message = f"{message}\n{detail.strip()}"
        raise RuntimeError(message)

    def _close_log():
        try:
            log_handle.close()
        except OSError:
            pass

    threading.Thread(target=lambda: (process.wait(), _close_log()), daemon=True).start()
    return DeckLinkSink(
        process=process,
        backend=backend,
        log_path=log_path,
        stdin=process.stdin,
    )


def stop_sink(sink):
    if not sink:
        return
    process = sink.process
    if process is None:
        return
    if sink.stdin:
        try:
            sink.stdin.close()
        except OSError:
            pass
        sink.stdin = None
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=0.4)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=0.4)
            except subprocess.TimeoutExpired:
                pass


def formats_report(output_id, ffmpeg_path=None):
    """Text dump of advertised DeckLink modes for the EDID-style window."""
    device = find_device(output_id, ffmpeg_path)
    name = decklink_device_name(output_id)
    _ignored, connector = parse_output_id(output_id)
    lines = [f"DeckLink: {device.name if device else name}"]
    if device:
        lines.append(f"Index: {device.index}")
        if device.backend:
            lines.append(f"Backend: {device.backend}")
        if device.connectors:
            lines.append(
                "Connectors: "
                + ", ".join(connector_label(item) for item in device.connectors)
            )
    if connector:
        lines.append(f"Output: {connector_label(connector)}")
    backend, tool = choose_decklink_backend(ffmpeg_path)
    lines.append(f"Playout: {backend or 'unavailable'}" + (f" ({tool})" if tool else ""))
    lines.append("")
    modes = list_decklink_modes(output_id, ffmpeg_path)
    if not modes:
        lines.append("No modes were reported.")
        return "\n".join(lines)
    lines.append("Progressive modes:")
    for mode in modes:
        code = mode.format_code or mode.gst_mode or "--"
        lines.append(f"  {mode.width}x{mode.height}  {mode.refresh:.3f} Hz  {code}")
    return "\n".join(lines)
