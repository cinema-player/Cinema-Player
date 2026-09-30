"""House lights over Art-Net (DMX512 on the LAN)."""

from __future__ import annotations

import socket
import struct
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
ARTNET_HEADER = b"Art-Net\x00"
ARTNET_OPCODE_OUTPUT = 0x5000
ARTNET_VERSION = 14
DMX_CHANNELS = 512
REFRESH_S = 0.8
FADE_HZ = 40


@dataclass
class DmxOutput:
    host: str = ""
    port: int = DEFAULT_PORT
    universe: int = DEFAULT_UNIVERSE
    channels: list = field(default_factory=list)

    def __post_init__(self):
        self.host = str(self.host or "").strip()
        self.port = clamp_port(self.port)
        self.universe = clamp_universe(self.universe)
        self.channels = parse_channels(self.channels)

    @classmethod
    def from_dict(cls, data):
        raw = data if isinstance(data, dict) else {}
        return cls(
            host=raw.get("host", ""),
            port=raw.get("port", DEFAULT_PORT),
            universe=raw.get("universe", DEFAULT_UNIVERSE),
            channels=raw.get("channels", []),
        )

    def to_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "universe": self.universe,
            "channels": list(self.channels),
        }

    def ready(self):
        return bool(self.host) and bool(self.channels)


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


def load_lights_config(raw):
    data = raw if isinstance(raw, dict) else {}
    output = DmxOutput.from_dict(data)
    presets = dict(DEFAULT_PRESETS)
    incoming = data.get("presets") if isinstance(data.get("presets"), dict) else {}
    for key in PRESETS:
        if key in incoming:
            presets[key] = clamp_percent(incoming[key], presets[key])
    try:
        transition_ms = int(data.get("transition_ms", DEFAULT_TRANSITION_MS))
    except (TypeError, ValueError):
        transition_ms = DEFAULT_TRANSITION_MS
    enabled = True
    if "enabled" in data:
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
    """Build an Art-Net OpOutput / OpDmx datagram."""
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


def frame_for_level(channels, percent):
    frame = bytearray(DMX_CHANNELS)
    value = percent_to_dmx(percent)
    for channel in parse_channels(channels):
        frame[channel - 1] = value
    return bytes(frame)


class ArtNetController:
    """Send house-light levels as Art-Net; fade in a background thread."""

    def __init__(self, send=None):
        self._send = send or self._send_udp
        self._lock = threading.Lock()
        self._sock = None
        self._output = DmxOutput()
        self.level = 0
        self._sequence = 0
        self._stop_fade = threading.Event()
        self._fade_thread = None
        self._stop_refresh = threading.Event()
        self._refresh_thread = None

    def close(self):
        self._stop_fade.set()
        self._stop_refresh.set()
        thread = self._fade_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1)
        refresh = self._refresh_thread
        if refresh and refresh.is_alive() and refresh is not threading.current_thread():
            refresh.join(timeout=1)
        with self._lock:
            sock = self._sock
            self._sock = None
        if sock is not None:
            try:
                sock.close()
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

    def _emit(self, output, percent):
        packet = artnet_output_packet(
            output.universe,
            frame_for_level(output.channels, percent),
            self._next_sequence(),
        )
        self._send(output.host, output.port, packet)

    def _arm_refresh(self):
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop_refresh.clear()
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()

    def _refresh_loop(self):
        while not self._stop_refresh.wait(REFRESH_S):
            with self._lock:
                output = DmxOutput.from_dict(self._output.to_dict())
                level = self.level
            if not output.ready():
                continue
            try:
                self._emit(output, level)
            except OSError:
                pass

    def apply(self, output, percent, transition_ms=0):
        """Fade to percent and keep sending the last Art-Net frame."""
        output = DmxOutput.from_dict(output.to_dict() if hasattr(output, "to_dict") else output)
        if not output.ready():
            return "dmx_not_ready"
        target = clamp_percent(percent)
        self._stop_fade.set()
        previous = self._fade_thread
        if previous and previous.is_alive() and previous is not threading.current_thread():
            previous.join(timeout=1)
        with self._lock:
            self._output = output
            start = self.level
        self._stop_fade.clear()
        self._arm_refresh()
        try:
            duration = max(0, int(transition_ms))
        except (TypeError, ValueError):
            duration = 0
        if duration <= 0 or start == target:
            try:
                self._emit(output, target)
            except OSError as exc:
                return str(exc)
            with self._lock:
                self.level = target
            return ""

        def worker():
            steps = max(1, int(duration / (1000.0 / FADE_HZ)))
            for step in range(1, steps + 1):
                if self._stop_fade.is_set():
                    return
                mix = start + (target - start) * (step / steps)
                try:
                    self._emit(output, mix)
                except OSError:
                    return
                with self._lock:
                    self.level = mix
                time.sleep(duration / 1000.0 / steps)
            try:
                self._emit(output, target)
            except OSError:
                return
            with self._lock:
                self.level = target

        self._fade_thread = threading.Thread(target=worker, daemon=True)
        self._fade_thread.start()
        return ""


_controller = ArtNetController()


def apply_preset(output, preset, presets=None, transition_ms=DEFAULT_TRANSITION_MS):
    """Set the configured DMX channels to a named house-light preset."""
    return _controller.apply(output, brightness_for_preset(preset, presets), transition_ms)


def shutdown():
    """Stop Art-Net refresh when Cinema Player quits."""
    _controller.close()
