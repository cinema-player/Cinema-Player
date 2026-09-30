"""House lights over DMX512.

Output is an Enttec DMX USB Pro compatible interface (57600 baud, label 6),
or Art-Net (ArtDMX, UDP 6454). Open DMX (a raw 250 kBd RS485 break) is not
supported. A missing interface does not stop playback.
"""

from __future__ import annotations

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

MODE_ARTNET = "artnet"
MODE_ENTTEC = "enttec"
MODES = (MODE_ARTNET, MODE_ENTTEC)
DEFAULT_MODE = MODE_ENTTEC

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
        if self.mode == MODE_ENTTEC and not self.device:
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
        if self.mode == MODE_ENTTEC:
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
        "artnet": MODE_ARTNET,
        "art-net": MODE_ARTNET,
        "lan": MODE_ARTNET,
        "net": MODE_ARTNET,
        "network": MODE_ARTNET,
    }
    return aliases.get(key, DEFAULT_MODE)


def normalize_preset(value):
    key = str(value or "").strip().lower()
    aliases = {
        "bright": "bright",
        "hell": "bright",
        "medium": "medium",
        "mittel": "medium",
        "dark": "dark",
        "dunkel": "dark",
    }
    return aliases.get(key, "")


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


def already_at_preset(current, target):
    """True when house lights are already on the requested cue."""
    key = normalize_preset(target)
    return bool(key) and key == normalize_preset(current)


def resolve_start_preset(light_start):
    """Film start: playlist cue, otherwise house lights down."""
    return play_preset(light_start) or "dark"


def play_preset(value):
    """Dimmer while the clip plays. Empty or dark is the default (not shown)."""
    key = normalize_preset(value)
    if key in ("medium", "bright"):
        return key
    return ""


def resolve_end_preset(light_end, autoplay_continues=False):
    """Film end: playlist cue, else up — except autoplay, which keeps lights down."""
    preset = normalize_preset(light_end)
    if preset:
        return preset
    return "dark" if autoplay_continues else "bright"


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
    presets = dict(DEFAULT_PRESETS)
    incoming = data.get("presets") if isinstance(data.get("presets"), dict) else {}
    for key in PRESETS:
        if key in incoming:
            presets[key] = clamp_percent(incoming[key], presets[key])
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
        presets,
        max(0, transition_ms),
        enabled,
        start_lead_ms,
        end_lead_ms,
    )


def dump_lights_config(
    output,
    presets,
    transition_ms,
    enabled=True,
    start_lead_ms=0,
    end_lead_ms=0,
):
    payload = DmxOutput.from_dict(output.to_dict() if hasattr(output, "to_dict") else output).to_dict()
    payload.update({
        "enabled": bool(enabled),
        "presets": {
            key: clamp_percent((presets or {}).get(key), DEFAULT_PRESETS[key])
            for key in PRESETS
        },
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


def frame_for_level(channels, percent):
    frame = bytearray(DMX_CHANNELS)
    value = percent_to_dmx(percent)
    for channel in parse_channels(channels):
        frame[channel - 1] = value
    return bytes(frame)


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


def frame_for_level_bytes(frame):
    payload = bytes(frame or b"")[:DMX_CHANNELS]
    if len(payload) < DMX_CHANNELS:
        payload = payload + bytes(DMX_CHANNELS - len(payload))
    return payload


class DmxController:
    """Fade house-light levels and repeat the last DMX frame."""

    def __init__(self, send=None, open_port=None, monotonic=None, sleep=None, start_thread=True):
        self._send = send or self._send_udp
        self._open_port = open_port or EnttecPort
        self._time = monotonic or time.monotonic
        self._sleep = sleep or time.sleep
        self._start_thread = start_thread
        self._lock = threading.Lock()
        self._io_lock = threading.Lock()
        self._sock = None
        self._port = None
        self._output = DmxOutput()
        self.level = 0.0
        self._fade_start = 0.0
        self._target = 0.0
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

    def _serial_port(self, device):
        port = self._port
        if port is not None and getattr(port, "device", "") != device:
            try:
                port.close()
            except OSError:
                pass
            port = None
            self._port = None
        if port is None:
            port = self._open_port(device)
            self._port = port
        return port

    def _emit(self, output, percent):
        frame = frame_for_level(output.channels, percent)
        with self._io_lock:
            if output.mode == MODE_ENTTEC:
                try:
                    self._serial_port(output.device).write_frame(frame)
                except OSError:
                    port = self._port
                    self._port = None
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
                fading = self._fade_ms > 0 and abs(self.level - self._target) > 0.05
            interval = self._interval(output, fading)
            if self._stop.wait(0):
                break
            self._wake.wait(interval)
            self._wake.clear()
            if self._stop.is_set():
                break
            self._tick()

    def _tick(self):
        with self._lock:
            output = DmxOutput.from_dict(self._output.to_dict())
            level = mixed_level(
                self._fade_start, self._target, self._fade_started, self._time(), self._fade_ms,
            )
            self.level = level
        if not output.ready():
            return
        try:
            self._emit(output, level)
        except OSError as exc:
            self._note_error(output, exc)
            return
        self.connected = True
        self.last_error = ""

    def apply(self, output, percent, transition_ms=0):
        """Fade to percent. The first level snaps; later cues fade. Returns an error string."""
        output = DmxOutput.from_dict(output.to_dict() if hasattr(output, "to_dict") else output)
        if not output.ready():
            return "dmx_not_ready"
        target = float(clamp_percent(percent))
        try:
            duration = max(0, int(transition_ms))
        except (TypeError, ValueError):
            duration = 0
        with self._lock:
            if not self._have_level:
                duration = 0
            self._output = output
            self._fade_start = target if duration <= 0 else self.level
            self._target = target
            self._fade_started = self._time()
            self._fade_ms = duration
            if duration <= 0:
                self.level = target
        try:
            self._emit(output, target if duration <= 0 else self.level)
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
        if output.mode == MODE_ENTTEC and output.device:
            self.last_error = f"{output.device}: {detail}"
        elif output.host:
            self.last_error = f"{output.host}:{output.port}: {detail}"
        else:
            self.last_error = detail
        self.connected = False
        return self.last_error


_controller = DmxController()


def apply_preset(output, preset, presets=None, transition_ms=DEFAULT_TRANSITION_MS):
    """Set the configured DMX channels to a named house-light preset."""
    return _controller.apply(output, brightness_for_preset(preset, presets), transition_ms)


def connected():
    return bool(_controller.connected)


def last_error():
    return _controller.last_error


def shutdown():
    """Stop DMX refresh and release the USB port when Cinema Player quits."""
    _controller.close()
