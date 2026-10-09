"""House lights over DMX512.

Output is an Enttec DMX USB Pro compatible interface (57600 baud, label 6),
an Open DMX USB compatible interface (250000 baud, 8N2, break before each
frame), or Art-Net (ArtDMX, UDP 6454). A missing interface does not stop
playback.
"""

from __future__ import annotations

import ctypes
import fcntl
import glob
import os
import socket
import struct
import termios
import threading
import time
from dataclasses import dataclass, field

PRESETS = ("bright", "medium", "dark")
DEFAULT_PRESETS = {"bright": 100, "medium": 40, "dark": 0}
SCENE_DARK = "dark"
SCENE_BRIGHT = "bright"
PROTECTED_SCENES = (SCENE_DARK, SCENE_BRIGHT)
SCENE_NAME_LIMIT = 40
DEFAULT_TRANSITION_MS = 2500
DEFAULT_START_LEAD_MS = 0
DEFAULT_END_LEAD_MS = 0
DEFAULT_HOST = "255.255.255.255"
DEFAULT_PORT = 6454
DEFAULT_UNIVERSE = 0
DEFAULT_DEVICE = "/dev/ttyUSB0"
ARTNET_HEADER = b"Art-Net\x00"
ARTNET_OPCODE_OUTPUT = 0x5000
ARTNET_VERSION = 14
DMX_CHANNELS = 512
# An Enttec Pro frame is about 520 bytes at 57600 baud (~90 ms).
ENTTEC_BAUD = 57600
ENTTEC_INTERVAL = 0.12
ARTNET_INTERVAL = 1.0 / 30.0
ARTNET_HOLD_INTERVAL = 0.8
# Open DMX is a bare RS485 line. The host sends the break; the widget does not
# refresh on its own. A full 512-slot frame is about 23 ms at 250 kbaud.
OPENDMX_BAUD = 250000
OPENDMX_BREAK = 0.001
OPENDMX_MAB = 0.0001
OPENDMX_PERIOD = 0.025
OPENDMX_INTERVAL = 0.001

MODE_ARTNET = "artnet"
MODE_ENTTEC = "enttec"
MODE_OPENDMX = "opendmx"
MODES = (MODE_ARTNET, MODE_ENTTEC, MODE_OPENDMX)
DEFAULT_MODE = MODE_ENTTEC
SERIAL_MODES = (MODE_ENTTEC, MODE_OPENDMX)

# Linux termios2 ioctl numbers for a 44-byte struct (TCGETS2 / TCSETS2).
_BOTHER = 0x00001000
_TIOCSBRK = 0x5427
_TIOCCBRK = 0x5428

SERIAL_PATTERNS = ("/dev/serial/by-id/*", "/dev/ttyUSB*", "/dev/ttyACM*")


@dataclass
class DmxOutput:
    host: str = ""
    port: int = DEFAULT_PORT
    universe: int = DEFAULT_UNIVERSE
    channels: list = field(default_factory=list)
    mode: str = DEFAULT_MODE
    device: str = ""

    def __post_init__(self):
        self.host = str(self.host or "").strip() or DEFAULT_HOST
        self.port = clamp_port(self.port)
        self.universe = clamp_universe(self.universe)
        self.mode = normalize_mode(self.mode)
        self.device = str(self.device or "").strip()
        if self.mode in SERIAL_MODES and not self.device:
            self.device = DEFAULT_DEVICE
        self.channels = parse_channels(self.channels) or [1]

    @classmethod
    def from_dict(cls, data):
        raw = data if isinstance(data, dict) else {}
        return cls(
            host=raw.get("host", ""),
            port=raw.get("port", DEFAULT_PORT),
            universe=raw.get("universe", DEFAULT_UNIVERSE),
            channels=raw.get("channels", []),
            mode=raw.get("mode", raw.get("output", DEFAULT_MODE)),
            device=raw.get("device", ""),
        )

    def to_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "universe": self.universe,
            "channels": list(self.channels),
            "mode": self.mode,
            "device": self.device,
        }

    def ready(self):
        if not self.channels:
            return False
        if self.mode in SERIAL_MODES:
            return bool(self.device)
        return bool(self.host)


def normalize_mode(value):
    key = str(value or "").strip().lower()
    aliases = {
        "": DEFAULT_MODE,
        "enttec": MODE_ENTTEC,
        "dmx": MODE_ENTTEC,
        "usb": MODE_ENTTEC,
        "usb-pro": MODE_ENTTEC,
        "pro": MODE_ENTTEC,
        "serial": MODE_ENTTEC,
        "opendmx": MODE_OPENDMX,
        "open-dmx": MODE_OPENDMX,
        "open_dmx": MODE_OPENDMX,
        "open dmx": MODE_OPENDMX,
        "opendmxusb": MODE_OPENDMX,
        "open-dmx-usb": MODE_OPENDMX,
        "open_dmx_usb": MODE_OPENDMX,
        "open dmx usb": MODE_OPENDMX,
        "artnet": MODE_ARTNET,
        "art-net": MODE_ARTNET,
        "lan": MODE_ARTNET,
        "net": MODE_ARTNET,
        "network": MODE_ARTNET,
    }
    return aliases.get(key, DEFAULT_MODE)


_SCENE_ALIASES = {
    "bright": SCENE_BRIGHT,
    "hell": SCENE_BRIGHT,
    "medium": "medium",
    "mittel": "medium",
    "dark": SCENE_DARK,
    "dunkel": SCENE_DARK,
}


@dataclass
class Scene:
    """One lighting cue: a name and a brightness for every global DMX channel."""

    id: str
    name: str = ""
    levels: dict = field(default_factory=dict)

    def copy(self):
        return Scene(self.id, self.name, dict(self.levels))

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "levels": {
                str(channel): int(percent)
                for channel, percent in sorted(self.levels.items())
            },
        }

    @classmethod
    def from_dict(cls, raw):
        if isinstance(raw, Scene):
            return raw.copy()
        if not isinstance(raw, dict):
            return None
        scene_id = _clean_scene_id(raw.get("id"))
        if not scene_id:
            return None
        name = str(raw.get("name") or "").strip()
        if len(name) > SCENE_NAME_LIMIT:
            name = name[:SCENE_NAME_LIMIT].strip()
        levels = {}
        incoming = raw.get("levels") if isinstance(raw.get("levels"), dict) else {}
        for key, value in incoming.items():
            channel = clamp_channel(key)
            if channel is None:
                continue
            levels[channel] = clamp_percent(value, 0)
        return cls(scene_id, name, levels)


def _clean_scene_id(value):
    text = str(value or "").strip().lower()
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch in "-_")
    return cleaned[:32]


def scene_locked(scene_id):
    return _clean_scene_id(scene_id) in PROTECTED_SCENES


def normalize_preset(value):
    return scene_key(value)


def scene_key(value, scenes=None):
    """Stable scene id. Empty and 'auto' stay empty. Built-in names map to dark/bright/medium."""
    text = str(value or "").strip()
    if not text:
        return ""
    folded = text.casefold()
    if folded == "auto":
        return ""
    if scenes:
        found = find_scene(scenes, text)
        if found is not None:
            return found.id
    if folded in _SCENE_ALIASES:
        return _SCENE_ALIASES[folded]
    if scenes:
        return ""
    return _clean_scene_id(text)


def find_scene(scenes, value):
    text = str(value or "").strip()
    if not text or not scenes:
        return None
    folded = text.casefold()
    for scene in scenes:
        if scene.id.casefold() == folded:
            return scene
    alias = _SCENE_ALIASES.get(folded)
    if alias:
        for scene in scenes:
            if scene.id == alias:
                return scene
    for scene in scenes:
        if scene.name and scene.name.casefold() == folded:
            return scene
    return None


def _levels_for(current, channels, default):
    levels = {}
    source = current or {}
    for channel in channels:
        if channel in source:
            levels[channel] = clamp_percent(source[channel], default)
        elif str(channel) in source:
            levels[channel] = clamp_percent(source[str(channel)], default)
        else:
            levels[channel] = clamp_percent(default, default)
    return levels


def align_scenes(scenes, channels):
    """Dark and bright always exist, and every scene has exactly the global channels."""
    channels = parse_channels(channels) or [1]
    incoming = []
    seen = set()
    for raw in scenes or []:
        scene = Scene.from_dict(raw)
        if scene is None or scene.id in seen:
            continue
        seen.add(scene.id)
        incoming.append(scene)
    by_id = {scene.id: scene for scene in incoming}
    result = []
    for scene_id, default in ((SCENE_DARK, 0), (SCENE_BRIGHT, 100)):
        scene = by_id.get(scene_id)
        result.append(Scene(
            scene_id,
            scene.name if scene else "",
            _levels_for(scene.levels if scene else {}, channels, default),
        ))
    for scene in incoming:
        if scene.id in PROTECTED_SCENES:
            continue
        result.append(Scene(scene.id, scene.name, _levels_for(scene.levels, channels, 0)))
    return result


def _fresh_scene_id(scenes):
    used = {scene.id for scene in scenes}
    number = 1
    while f"scene-{number}" in used:
        number += 1
    return f"scene-{number}"


def add_scene(scenes, channels, name=""):
    scenes = align_scenes(scenes, channels)
    name = str(name or "").strip()
    if len(name) > SCENE_NAME_LIMIT:
        name = name[:SCENE_NAME_LIMIT].strip()
    scenes.append(Scene(_fresh_scene_id(scenes), name, {}))
    return align_scenes(scenes, channels)


def delete_scene(scenes, scene_id, channels):
    if scene_locked(scene_id):
        return align_scenes(scenes, channels)
    target = _clean_scene_id(scene_id)
    kept = [scene for scene in align_scenes(scenes, channels) if scene.id != target]
    return align_scenes(kept, channels)


def scenes_from_config(data, channels):
    """Load scenes. Older configs stored one percent per Dark/Medium/Bright preset."""
    raw = data.get("scenes") if isinstance(data, dict) else None
    if isinstance(raw, list):
        return align_scenes(raw, channels)
    presets = data.get("presets") if isinstance(data, dict) and isinstance(data.get("presets"), dict) else None
    channels = parse_channels(channels) or [1]
    if not presets:
        return align_scenes([], channels)
    dark = clamp_percent(presets["dark"], 0) if "dark" in presets else 0
    bright = clamp_percent(presets["bright"], 100) if "bright" in presets else 100
    scenes = [
        Scene(SCENE_DARK, "", {channel: dark for channel in channels}),
        Scene(SCENE_BRIGHT, "", {channel: bright for channel in channels}),
    ]
    if "medium" in presets:
        medium = clamp_percent(presets["medium"], 40)
        scenes.append(Scene("medium", "", {channel: medium for channel in channels}))
    return align_scenes(scenes, channels)


def level_for(scenes, scene_id, channel, default=0):
    scene = find_scene(scenes, scene_id)
    number = clamp_channel(channel)
    if scene is None or number is None:
        return clamp_percent(default, default)
    return clamp_percent(scene.levels.get(number, default), default)


def clamp_percent(value, default=0):
    try:
        percent = int(round(float(value)))
    except (TypeError, ValueError):
        percent = int(default)
    return max(0, min(100, percent))


def clamp_port(value, default=DEFAULT_PORT):
    try:
        port = int(value)
    except (TypeError, ValueError):
        port = default
    if not 1 <= port <= 65535:
        return default
    return port


def clamp_universe(value, default=DEFAULT_UNIVERSE):
    try:
        universe = int(value)
    except (TypeError, ValueError):
        universe = default
    return max(0, min(32767, universe))


def clamp_channel(value):
    try:
        channel = int(value)
    except (TypeError, ValueError):
        return None
    if 1 <= channel <= DMX_CHANNELS:
        return channel
    return None


def parse_channels(value):
    """Accept a list or text such as '1, 2, 5-7' and return unique 1–512 channels."""
    if isinstance(value, (list, tuple, set, frozenset)):
        parts = [str(item) for item in value]
    else:
        parts = str(value or "").replace(";", ",").split(",")
    channels = []
    seen = set()
    for part in parts:
        text = part.strip()
        if not text:
            continue
        if "-" in text:
            start_text, end_text = text.split("-", 1)
            start = clamp_channel(start_text)
            end = clamp_channel(end_text)
            if start is None or end is None:
                continue
            low, high = (start, end) if start <= end else (end, start)
            for channel in range(low, high + 1):
                if channel not in seen:
                    seen.add(channel)
                    channels.append(channel)
            continue
        channel = clamp_channel(text)
        if channel is None or channel in seen:
            continue
        seen.add(channel)
        channels.append(channel)
    return channels


def format_channels(channels):
    return ", ".join(str(channel) for channel in parse_channels(channels))


def percent_to_dmx(percent):
    return int(round(clamp_percent(percent) * 255 / 100.0))


def brightness_for_preset(preset, presets=None):
    table = dict(DEFAULT_PRESETS)
    if isinstance(presets, dict):
        for key in PRESETS:
            if key in presets:
                table[key] = clamp_percent(presets[key], table[key])
    key = normalize_preset(preset) or "dark"
    return table.get(key, 0)


def already_at_preset(current, target, scenes=None):
    """True when house lights are already on the requested scene."""
    key = scene_key(target, scenes)
    return bool(key) and key == scene_key(current, scenes)


def resolve_start_preset(light_start, scenes=None):
    """Film start: the chosen scene, otherwise house lights down."""
    key = scene_key(light_start, scenes)
    if scenes is not None:
        found = find_scene(scenes, key) if key else None
        return found.id if found is not None else SCENE_DARK
    return key or SCENE_DARK


def play_preset(value, scenes=None):
    """Scene while the clip plays. Empty or dark is the default (not shown)."""
    key = scene_key(value, scenes)
    if key in ("", SCENE_DARK):
        return ""
    if scenes is not None and find_scene(scenes, key) is None:
        return ""
    return key


def resolve_end_preset(light_end, autoplay_continues=False, scenes=None):
    """Film end: playlist cue, else up — except autoplay, which keeps lights down."""
    key = scene_key(light_end, scenes)
    if key:
        if scenes is None or find_scene(scenes, key) is not None:
            return key
    return SCENE_DARK if autoplay_continues else SCENE_BRIGHT


def seconds_to_ms(value, default=0):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            seconds = float(default) / 1000.0
        except (TypeError, ValueError):
            seconds = 0.0
    return max(0, int(round(seconds * 1000)))


def ms_to_seconds_text(ms):
    seconds = max(0, int(ms or 0)) / 1000.0
    if abs(seconds - round(seconds)) < 0.05:
        return str(int(round(seconds)))
    return f"{seconds:.1f}"


def play_delay_ms(transition_ms, start_lead_ms):
    """Wait after dim-down starts so the clip rolls this far before the fade ends."""
    fade = max(0, int(transition_ms or 0))
    lead = max(0, int(start_lead_ms or 0))
    return max(0, fade - lead)


def _ms_setting(data, ms_key, seconds_key, default=0):
    if ms_key in data:
        try:
            return max(0, int(data.get(ms_key)))
        except (TypeError, ValueError):
            return default
    if seconds_key in data:
        return seconds_to_ms(data.get(seconds_key), default)
    return default


def _is_dmx_config(data):
    return any(key in data for key in ("mode", "output", "channels", "device", "host", "universe"))


def load_lights_config(raw):
    data = raw if isinstance(raw, dict) else {}
    output = DmxOutput.from_dict(data if _is_dmx_config(data) else {})
    scenes = scenes_from_config(data, output.channels)
    try:
        transition_ms = int(data.get("transition_ms", DEFAULT_TRANSITION_MS))
    except (TypeError, ValueError):
        transition_ms = DEFAULT_TRANSITION_MS
    enabled = False
    if _is_dmx_config(data) and "enabled" in data:
        value = data.get("enabled")
        if isinstance(value, str):
            enabled = value.strip().lower() not in ("0", "false", "off", "no", "")
        else:
            enabled = bool(value)
    start_lead_ms = _ms_setting(data, "start_lead_ms", "start_lead_s", DEFAULT_START_LEAD_MS)
    end_lead_ms = _ms_setting(data, "end_lead_ms", "end_lead_s", DEFAULT_END_LEAD_MS)
    return (
        output,
        scenes,
        max(0, transition_ms),
        enabled,
        start_lead_ms,
        end_lead_ms,
    )


def dump_lights_config(
    output,
    scenes,
    transition_ms,
    enabled=True,
    start_lead_ms=0,
    end_lead_ms=0,
):
    output = DmxOutput.from_dict(output.to_dict() if hasattr(output, "to_dict") else output)
    if isinstance(scenes, dict):
        scenes = scenes_from_config({"presets": scenes}, output.channels)
    payload = output.to_dict()
    payload.update({
        "enabled": bool(enabled),
        "scenes": [scene.to_dict() for scene in align_scenes(scenes, output.channels)],
        "transition_ms": max(0, int(transition_ms)),
        "start_lead_ms": max(0, int(start_lead_ms or 0)),
        "end_lead_ms": max(0, int(end_lead_ms or 0)),
    })
    return payload


def artnet_output_packet(universe, payload, sequence=0):
    """Art-Net ArtDMX packet (OpCode 0x5000) for one universe."""
    data = bytearray(DMX_CHANNELS)
    if payload:
        data[: min(len(payload), DMX_CHANNELS)] = payload[:DMX_CHANNELS]
    length = DMX_CHANNELS
    return (
        ARTNET_HEADER
        + struct.pack("<H", ARTNET_OPCODE_OUTPUT)
        + struct.pack(">H", ARTNET_VERSION)
        + bytes((sequence & 0xFF, 0))
        + struct.pack("<H", clamp_universe(universe))
        + struct.pack(">H", length)
        + bytes(data)
    )


def build_enttec(values):
    """Enttec DMX USB Pro 'Output Only Send DMX Packet' (label 6)."""
    if len(values) != DMX_CHANNELS:
        raise ValueError(f"DMX frame must contain {DMX_CHANNELS} channels")
    payload = b"\x00" + bytes(int(value) & 0xFF for value in values)
    return struct.pack("<BBH", 0x7E, 0x06, len(payload)) + payload + b"\xE7"


def build_opendmx(values):
    """Open DMX slot bytes: start code 0x00 followed by 512 channels."""
    if len(values) != DMX_CHANNELS:
        raise ValueError(f"DMX frame must contain {DMX_CHANNELS} channels")
    return b"\x00" + bytes(int(value) & 0xFF for value in values)


def frame_for_level(channels, percent):
    return frame_for_levels({channel: percent for channel in parse_channels(channels)})


def frame_for_levels(levels):
    """DMX frame where each channel can carry its own brightness."""
    frame = bytearray(DMX_CHANNELS)
    for channel, percent in (levels or {}).items():
        number = clamp_channel(channel)
        if number is None:
            continue
        frame[number - 1] = percent_to_dmx(percent)
    return bytes(frame)


def _tracked_level(levels):
    """One number for callers that still watch a single house-light level."""
    if not levels:
        return 0.0
    if 1 in levels and len(levels) == 1:
        return float(levels[1])
    values = [float(value) for value in levels.values()]
    if max(values) - min(values) < 0.001:
        return values[0]
    if 1 in levels:
        return float(levels[1])
    return float(levels[min(levels)])


def mixed_level(start, target, started, now, duration_ms):
    if duration_ms <= 0:
        return float(target)
    elapsed = max(0.0, (now - started) * 1000.0)
    pos = min(1.0, elapsed / float(duration_ms))
    return float(start) + (float(target) - float(start)) * pos


def list_serial_devices():
    """USB serial adapters that are plugged in right now."""
    devices = []
    for pattern in SERIAL_PATTERNS:
        for path in sorted(glob.glob(pattern)):
            if path not in devices:
                devices.append(path)
    return devices


class _Termios2(ctypes.Structure):
    """Linux `struct termios2` (44 bytes on x86_64). Custom baud rates need it."""

    _fields_ = [
        ("c_iflag", ctypes.c_uint),
        ("c_oflag", ctypes.c_uint),
        ("c_cflag", ctypes.c_uint),
        ("c_lflag", ctypes.c_uint),
        ("c_line", ctypes.c_ubyte),
        ("c_cc", ctypes.c_ubyte * 19),
        ("c_ispeed", ctypes.c_uint),
        ("c_ospeed", ctypes.c_uint),
    ]


def _ioctl_type(direction, number, size):
    return (direction << 30) | (size << 16) | (ord("T") << 8) | number


_TCGETS2 = _ioctl_type(2, 0x2A, ctypes.sizeof(_Termios2))
_TCSETS2 = _ioctl_type(1, 0x2B, ctypes.sizeof(_Termios2))


def line_settings(fd):
    """Return (baud, data bits, stop bits, parity) for an open serial port."""
    settings = _Termios2()
    fcntl.ioctl(fd, _TCGETS2, settings)
    size = settings.c_cflag & termios.CSIZE
    bits = {termios.CS5: 5, termios.CS6: 6, termios.CS7: 7, termios.CS8: 8}.get(size, 0)
    stop_bits = 2 if settings.c_cflag & termios.CSTOPB else 1
    parity = bool(settings.c_cflag & termios.PARENB)
    return int(settings.c_ospeed), bits, stop_bits, parity


def _configure_opendmx(fd):
    """250000 baud, 8 data bits, no parity, 2 stop bits, no flow control."""
    settings = _Termios2()
    fcntl.ioctl(fd, _TCGETS2, settings)
    settings.c_iflag = 0
    settings.c_oflag = 0
    settings.c_lflag = 0
    settings.c_cflag = termios.CS8 | termios.CSTOPB | termios.CREAD | termios.CLOCAL | _BOTHER
    settings.c_ispeed = OPENDMX_BAUD
    settings.c_ospeed = OPENDMX_BAUD
    settings.c_cc[termios.VMIN] = 0
    settings.c_cc[termios.VTIME] = 0
    fcntl.ioctl(fd, _TCSETS2, settings)


def ftdi_latency_path(device):
    """Sysfs latency timer for a tty such as /dev/ttyUSB0 or a by-id symlink."""
    name = os.path.basename(os.path.realpath(str(device or "")))
    if not name or name.startswith("."):
        return ""
    return f"/sys/class/tty/{name}/device/latency_timer"


def set_ftdi_latency(device, milliseconds=1):
    """Ask an FTDI adapter to release TX after 1 ms. Missing sysfs is ignored."""
    path = ftdi_latency_path(device)
    if not path:
        return False
    try:
        milliseconds = max(1, min(16, int(milliseconds)))
    except (TypeError, ValueError):
        milliseconds = 1
    try:
        with open(path, "w", encoding="ascii") as handle:
            handle.write(str(milliseconds))
    except OSError:
        return False
    return True


def _raise_rts(fd):
    """Hold RTS so RS485 clones that use it as the driver enable can transmit."""
    try:
        fcntl.ioctl(fd, termios.TIOCMBIS, struct.pack("I", termios.TIOCM_RTS))
    except OSError:
        pass


class EnttecPort:
    """Enttec DMX USB Pro compatible interface at 57600 baud, 8N1."""

    def __init__(self, device):
        self.device = str(device or "").strip()
        self.fd = None
        try:
            self.fd = os.open(self.device, os.O_RDWR | os.O_NOCTTY)
            attrs = termios.tcgetattr(self.fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0
            attrs[4] = termios.B57600
            attrs[5] = termios.B57600
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        except OSError:
            self.close()
            raise

    def write_frame(self, frame):
        packet = build_enttec(frame_for_level_bytes(frame))
        offset = 0
        while offset < len(packet):
            written = os.write(self.fd, packet[offset:])
            if written <= 0:
                raise OSError(f"short write on {self.device}")
            offset += written

    def close(self):
        fd = self.fd
        self.fd = None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            pass


class OpenDmxPort:
    """Open DMX USB compatible interface.

    The line is 250000 baud, 8N2. Each frame is a break, a short mark, start
    code 0x00, and 512 channel slots. The host repeats the frame; this port
    paces itself to about 40 Hz so a new break does not cut off the slots.
    """

    def __init__(self, device):
        self.device = str(device or "").strip()
        self.mode = MODE_OPENDMX
        self.fd = None
        try:
            self.fd = os.open(self.device, os.O_RDWR | os.O_NOCTTY)
            _configure_opendmx(self.fd)
            _raise_rts(self.fd)
            set_ftdi_latency(self.device)
            termios.tcflush(self.fd, termios.TCIOFLUSH)
        except OSError:
            self.close()
            raise

    def write_frame(self, frame):
        payload = build_opendmx(frame_for_level_bytes(frame))
        started = time.monotonic()
        self._send_break()
        offset = 0
        while offset < len(payload):
            written = os.write(self.fd, payload[offset:])
            if written <= 0:
                raise OSError(f"short write on {self.device}")
            offset += written
        termios.tcdrain(self.fd)
        remain = OPENDMX_PERIOD - (time.monotonic() - started)
        if remain > 0:
            time.sleep(remain)

    def _send_break(self):
        # USB serial cannot hold a 176 µs break precisely. 1 ms is inside
        # DMX512 (92 µs to 1 s) and is what Enttec's Open DMX sample sends.
        fcntl.ioctl(self.fd, _TIOCSBRK, 0)
        time.sleep(OPENDMX_BREAK)
        fcntl.ioctl(self.fd, _TIOCCBRK, 0)
        time.sleep(OPENDMX_MAB)

    def close(self):
        fd = self.fd
        self.fd = None
        if fd is None:
            return
        try:
            os.close(fd)
        except OSError:
            pass


def frame_for_level_bytes(frame):
    payload = bytes(frame or b"")[:DMX_CHANNELS]
    if len(payload) < DMX_CHANNELS:
        payload = payload + bytes(DMX_CHANNELS - len(payload))
    return payload


class DmxController:
    """Fade house-light levels and repeat the last DMX frame."""

    def __init__(
        self,
        send=None,
        open_port=None,
        open_opendmx=None,
        monotonic=None,
        sleep=None,
        start_thread=True,
    ):
        self._send = send or self._send_udp
        self._open_port = open_port or EnttecPort
        self._open_opendmx = open_opendmx or OpenDmxPort
        self._time = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._start_thread = start_thread
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._sock = None
        self._port = None
        self._port_mode = ""
        self._output = DmxOutput()
        self.level = 0.0
        self.levels = {}
        self._fade_start = 0.0
        self._target = 0.0
        self._fade_start_levels = {}
        self._target_levels = {}
        self._fade_started = 0.0
        self._fade_ms = 0
        self._have_level = False
        self._sequence = 0
        self.connected = False
        self.last_error = ""
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None

    def close(self):
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._thread = None
        self._close_socket()
        self._close_port()
        self.connected = False

    def _close_socket(self):
        with self._lock:
            sock = self._sock
            self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _close_port(self):
        with self._io_lock:
            port = self._port
            self._port = None
        if port is not None:
            try:
                port.close()
            except OSError:
                pass

    def _socket(self):
        if self._sock is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.4)
            self._sock = sock
        return self._sock

    def _send_udp(self, host, port, packet):
        self._socket().sendto(packet, (host, port))

    def _next_sequence(self):
        self._sequence = 1 if self._sequence >= 255 else self._sequence + 1
        return self._sequence

    def _serial_port(self, output):
        device = output.device
        mode = output.mode
        port = self._port
        if port is not None and (getattr(port, "device", "") != device or self._port_mode != mode):
            try:
                port.close()
            except OSError:
                pass
            port = None
            self._port = None
            self._port_mode = ""
        if port is None:
            opener = self._open_opendmx if mode == MODE_OPENDMX else self._open_port
            port = opener(device)
            self._port = port
            self._port_mode = mode
        return port

    def _emit(self, output, percent):
        self._emit_levels(output, {channel: percent for channel in output.channels})

    def _emit_levels(self, output, levels):
        frame = frame_for_levels(levels)
        with self._io_lock:
            if output.mode in SERIAL_MODES:
                try:
                    self._serial_port(output).write_frame(frame)
                except OSError:
                    port = self._port
                    self._port = None
                    self._port_mode = ""
                    if port is not None:
                        try:
                            port.close()
                        except OSError:
                            pass
                    raise
                return
            packet = artnet_output_packet(output.universe, frame, self._next_sequence())
            self._send(output.host, output.port, packet)

    def _interval(self, output, fading):
        if output.mode == MODE_OPENDMX:
            return OPENDMX_INTERVAL
        if output.mode == MODE_ENTTEC:
            return ENTTEC_INTERVAL
        return ARTNET_INTERVAL if fading else ARTNET_HOLD_INTERVAL

    def _arm(self):
        if not self._start_thread:
            return
        if self._thread and self._thread.is_alive():
            self._wake.set()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while not self._stop.is_set():
            with self._lock:
                output = DmxOutput.from_dict(self._output.to_dict())
                fading = self._still_fading()
            interval = self._interval(output, fading)
            if self._stop.wait(0):
                break
            self._wake.wait(interval)
            self._wake.clear()
            if self._stop.is_set():
                break
            self._tick()

    def _still_fading(self):
        if self._fade_ms <= 0:
            return False
        keys = set(self.levels) | set(self._target_levels)
        if not keys:
            return abs(self.level - self._target) > 0.05
        return any(
            abs(float(self.levels.get(channel, 0.0)) - float(self._target_levels.get(channel, 0.0))) > 0.05
            for channel in keys
        )

    def _mixed_levels(self, now):
        keys = set(self._fade_start_levels) | set(self._target_levels)
        return {
            channel: mixed_level(
                self._fade_start_levels.get(channel, 0.0),
                self._target_levels.get(channel, 0.0),
                self._fade_started,
                now,
                self._fade_ms,
            )
            for channel in keys
        }

    def _tick(self):
        with self._lock:
            output = DmxOutput.from_dict(self._output.to_dict())
            levels = self._mixed_levels(self._time())
            self.levels = levels
            self.level = _tracked_level(levels)
        if not output.ready():
            return
        try:
            self._emit_levels(output, levels)
        except OSError as exc:
            self._note_error(output, exc)
            return
        self.connected = True
        self.last_error = ""

    def apply(self, output, percent, transition_ms=0):
        """Fade every configured channel to the same percent."""
        output = DmxOutput.from_dict(output.to_dict() if hasattr(output, "to_dict") else output)
        levels = {channel: percent for channel in output.channels}
        return self.apply_levels(output, levels, transition_ms)

    def apply_levels(self, output, levels, transition_ms=0):
        """Fade each DMX channel to its own percent. The first cue snaps. Returns an error string."""
        output = DmxOutput.from_dict(output.to_dict() if hasattr(output, "to_dict") else output)
        if not output.ready():
            return "dmx_not_ready"
        target_levels = {}
        for channel, percent in (levels or {}).items():
            number = clamp_channel(channel)
            if number is None:
                continue
            target_levels[number] = float(clamp_percent(percent))
        if not target_levels:
            return "dmx_not_ready"
        try:
            duration = max(0, int(transition_ms))
        except (TypeError, ValueError):
            duration = 0
        with self._lock:
            if not self._have_level:
                duration = 0
            self._output = output
            if duration <= 0:
                self.levels = dict(target_levels)
                self.level = _tracked_level(self.levels)
                self._fade_start_levels = dict(target_levels)
                self._target_levels = dict(target_levels)
            else:
                keys = set(self.levels) | set(target_levels)
                self._fade_start_levels = {
                    channel: float(self.levels.get(channel, 0.0)) for channel in keys
                }
                self._target_levels = {
                    channel: float(target_levels.get(channel, 0.0)) for channel in keys
                }
            self._fade_start = _tracked_level(self._fade_start_levels)
            self._target = _tracked_level(self._target_levels)
            self._fade_started = self._time()
            self._fade_ms = duration
            shown = dict(self.levels)
        try:
            self._emit_levels(output, shown)
        except OSError as exc:
            with self._lock:
                self._have_level = False
            return self._note_error(output, exc)
        with self._lock:
            self._have_level = True
        self.connected = True
        self.last_error = ""
        self._arm()
        return ""

    def _note_error(self, output, exc):
        detail = getattr(exc, "strerror", None) or str(exc)
        if output.mode in SERIAL_MODES and output.device:
            self.last_error = f"{output.device}: {detail}"
        elif output.host:
            self.last_error = f"{output.host}:{output.port}: {detail}"
        else:
            self.last_error = detail
        self.connected = False
        return self.last_error


_controller = DmxController()


def apply_scene(output, scene_id, scenes=None, transition_ms=DEFAULT_TRANSITION_MS):
    """Set each global DMX channel to the brightness stored on a scene."""
    output = DmxOutput.from_dict(output.to_dict() if hasattr(output, "to_dict") else output)
    catalog = scenes if isinstance(scenes, list) else scenes_from_config(
        {"presets": scenes} if isinstance(scenes, dict) else {},
        output.channels,
    )
    scene = find_scene(catalog, scene_id) or find_scene(catalog, SCENE_DARK)
    if scene is None:
        return "dmx_not_ready"
    return _controller.apply_levels(output, scene.levels, transition_ms)


def apply_preset(output, preset, presets=None, transition_ms=DEFAULT_TRANSITION_MS):
    """Set a scene. A legacy percent table is still accepted as the third argument."""
    return apply_scene(output, preset, presets, transition_ms)


def connected():
    return bool(_controller.connected)


def last_error():
    return _controller.last_error


def shutdown():
    """Stop DMX refresh and release the USB port when Cinema Player quits."""
    _controller.close()
