"""Shelly lights over the LAN: discovery, switches, and dimmers."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields
from ipaddress import IPv4Address, IPv4Network
from urllib.parse import urlparse

PRESETS = ("bright", "medium", "dark")
DEFAULT_PRESETS = {"bright": 100, "medium": 40, "dark": 0}
DEFAULT_TRANSITION_MS = 2500
DEFAULT_START_LEAD_MS = 0
DEFAULT_END_LEAD_MS = 0
HTTP_TIMEOUT = 1.2


@dataclass
class ShellyDevice:
    host: str
    name: str = ""
    device_id: str = ""
    model: str = ""
    kind: str = "switch"
    gen: int = 1
    enabled: bool = False
    username: str = ""
    password: str = ""

    def __post_init__(self):
        self.host = str(self.host or "").strip()
        self.kind = "dimmer" if self.kind == "dimmer" else "switch"
        try:
            self.gen = int(self.gen)
        except (TypeError, ValueError):
            self.gen = 1
        self.enabled = bool(self.enabled)
        self.username = str(self.username or "").strip()
        self.password = str(self.password or "")

    @classmethod
    def from_dict(cls, data):
        names = {item.name for item in fields(cls)}
        raw = data if isinstance(data, dict) else {}
        return cls(**{key: value for key, value in raw.items() if key in names})

    def to_dict(self):
        return asdict(self)

    def label(self):
        title = self.name or self.device_id or self.host
        kind = "dimmer" if self.kind == "dimmer" else "switch"
        return f"{title}  ({self.host}, {kind})"


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


def brightness_for_preset(preset, presets=None):
    table = dict(DEFAULT_PRESETS)
    if isinstance(presets, dict):
        for key in PRESETS:
            if key in presets:
                table[key] = clamp_percent(presets[key], table[key])
    key = normalize_preset(preset) or "dark"
    return table.get(key, 0)


def switch_on_for_brightness(brightness):
    return clamp_percent(brightness) > 0


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


def _sha256_hex(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def rpc_auth(username, password, realm, nonce, nc=1):
    """Shelly Gen2 RPC digest (SHA-256). Username defaults to admin."""
    user = str(username or "").strip() or "admin"
    nonce_text = str(nonce)
    try:
        nc_value = int(nc)
    except (TypeError, ValueError):
        nc_value = 1
    cnonce = _sha256_hex(os.urandom(16).hex())
    ha1 = _sha256_hex(f"{user}:{realm}:{password}")
    ha2 = _sha256_hex("dummy_method:dummy_uri")
    response = _sha256_hex(f"{ha1}:{nonce_text}:{nc_value}:{cnonce}:auth:{ha2}")
    return {
        "realm": realm,
        "username": user,
        "nonce": nonce,
        "cnonce": cnonce,
        "response": response,
        "nc": nc_value,
        "algorithm": "SHA-256",
    }


def _auth_from_error(payload, username, password):
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return None
    message = error.get("message")
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            message = {}
    if not isinstance(message, dict):
        return None
    realm = str(message.get("realm") or "")
    nonce = message.get("nonce")
    if not realm or nonce is None:
        return None
    return rpc_auth(username, password, realm, nonce, message.get("nc") or 1)


def _basic_header(username, password):
    if not password:
        return {}
    token = base64.b64encode(f"{username or ''}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _auth_opener(url, username, password):
    opener = urllib.request.build_opener()
    if not password:
        return opener
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    manager.add_password(None, base, username or "", password)
    return urllib.request.build_opener(
        urllib.request.HTTPBasicAuthHandler(manager),
        urllib.request.HTTPDigestAuthHandler(manager),
    )


def _http_json(url, data=None, username="", password="", timeout=HTTP_TIMEOUT, _retry=True):
    headers = {"Accept": "application/json"}
    payload = dict(data) if isinstance(data, dict) else None
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    headers.update(_basic_header(username, password))
    request = urllib.request.Request(url, data=body, headers=headers)
    opener = _auth_opener(url, username, password)
    raw = ""
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        parsed = {}
        if raw.strip():
            try:
                loaded = json.loads(raw)
                parsed = loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                parsed = {}
        if exc.code == 401 and _retry and password:
            retry = _retry_with_rpc_auth(url, payload, parsed, username, password, timeout)
            if retry is not None:
                return retry
        raise
    if not raw.strip():
        return {}
    parsed = json.loads(raw)
    parsed = parsed if isinstance(parsed, dict) else {}
    error = parsed.get("error") if parsed else None
    if _retry and password and isinstance(error, dict) and error.get("code") == 401:
        retry = _retry_with_rpc_auth(url, payload, parsed, username, password, timeout)
        if retry is not None:
            return retry
    return parsed


def _retry_with_rpc_auth(url, payload, parsed, username, password, timeout):
    auth = _auth_from_error(parsed, username, password)
    if not auth:
        return None
    retry_url = url
    retry_data = dict(payload) if payload is not None else None
    if retry_data is None and "/rpc/" in url:
        method = url.rsplit("/rpc/", 1)[-1]
        retry_url = url.split("/rpc/", 1)[0] + "/rpc"
        retry_data = {
            "id": 1,
            "src": "cinema-player",
            "method": method,
            "params": {},
        }
    if not isinstance(retry_data, dict):
        return None
    retry_data["auth"] = auth
    return _http_json(
        retry_url,
        retry_data,
        username=username,
        password=password,
        timeout=timeout,
        _retry=False,
    )


def _rpc(host, method, params=None, username="", password="", timeout=HTTP_TIMEOUT):
    return _http_json(
        f"http://{host}/rpc",
        {
            "id": 1,
            "src": "cinema-player",
            "method": method,
            "params": params or {},
        },
        username=username,
        password=password,
        timeout=timeout,
    )


def _kind_from_status(info, status):
    blob = json.dumps({"info": info or {}, "status": status or {}}).lower()
    if any(token in blob for token in ("light:0", '"lights"', "dimmer", "rgbw")):
        return "dimmer"
    return "switch"


def probe_host(host, username="", password="", timeout=HTTP_TIMEOUT):
    """Return a ShellyDevice if this address answers like a Shelly, else None."""
    host = str(host or "").strip()
    if not host:
        return None
    username = str(username or "").strip()
    password = str(password or "")
    info = {}
    status = {}
    gen = 1
    try:
        info = _rpc(host, "Shelly.GetDeviceInfo", username=username, password=password, timeout=timeout)
        gen = int(info.get("gen") or 2)
        try:
            status = _rpc(host, "Shelly.GetStatus", username=username, password=password, timeout=timeout)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
            status = {}
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
        try:
            info = _http_json(
                f"http://{host}/shelly", username=username, password=password, timeout=timeout,
            )
            gen = 1
            try:
                status = _http_json(
                    f"http://{host}/status", username=username, password=password, timeout=timeout,
                )
            except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
                status = {}
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
            return None
    if not info and not status:
        return None
    name = (
        str(info.get("name") or info.get("id") or info.get("type") or "").strip()
        or host
    )
    device_id = str(info.get("id") or info.get("mac") or "").strip()
    model = str(info.get("model") or info.get("app") or info.get("type") or "").strip()
    if "shelly" not in json.dumps(info).lower() and "light" not in json.dumps(status).lower() and "relay" not in json.dumps(status).lower() and "switch:" not in json.dumps(status).lower():
        if not device_id and not model:
            return None
    return ShellyDevice(
        host=host,
        name=name,
        device_id=device_id,
        model=model,
        kind=_kind_from_status(info, status),
        gen=gen,
        username=username,
        password=password,
    )


def _local_ipv4_networks():
    networks = []
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("1.1.1.1", 80))
        address = probe.getsockname()[0]
        probe.close()
        ip = IPv4Address(address)
        if not ip.is_loopback and not ip.is_link_local:
            networks.append(IPv4Network(f"{ip}/24", strict=False))
    except OSError:
        pass
    return networks


def _avahi_hosts():
    hosts = []
    browse = shutil_which("avahi-browse")
    if not browse:
        return hosts
    for service in ("_shelly._tcp", "_http._tcp"):
        try:
            result = subprocess.run(
                [browse, "-prt", service],
                capture_output=True,
                text=True,
                timeout=4,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in (result.stdout or "").splitlines():
            if not line.startswith("="):
                continue
            parts = line.split(";")
            if len(parts) < 8:
                continue
            name = parts[3]
            ip = parts[7]
            if "shelly" not in name.lower() and "shelly" not in ";".join(parts).lower():
                continue
            if ip and ip not in hosts:
                hosts.append(ip)
    return hosts


def shutil_which(name):
    import shutil
    return shutil.which(name)


def discover_devices(username="", password="", timeout=HTTP_TIMEOUT):
    """Find Shelly devices on the LAN (mDNS if available, then a /24 HTTP probe)."""
    hosts = list(_avahi_hosts())
    for network in _local_ipv4_networks():
        for ip in network.hosts():
            text = str(ip)
            if text not in hosts:
                hosts.append(text)
    found = []
    seen = set()
    if not hosts:
        return found
    workers = min(32, max(4, len(hosts)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(probe_host, host, username, password, timeout): host
            for host in hosts
        }
        for future in as_completed(futures):
            try:
                device = future.result()
            except Exception:
                continue
            if not device or device.host in seen:
                continue
            seen.add(device.host)
            found.append(device)
    found.sort(key=lambda item: (item.name.lower(), item.host))
    return found


def apply_to_device(device, brightness, transition_ms=DEFAULT_TRANSITION_MS):
    """Set one Shelly to a brightness (0–100). Relays use on/off from that value."""
    brightness = clamp_percent(brightness)
    on = switch_on_for_brightness(brightness)
    transition_ms = max(0, int(transition_ms))
    host = device.host
    username = getattr(device, "username", "") or ""
    password = getattr(device, "password", "") or ""
    if device.gen >= 2:
        if device.kind == "dimmer":
            _rpc(
                host,
                "Light.Set",
                {
                    "id": 0,
                    "on": on,
                    "brightness": brightness,
                    "transition_duration": transition_ms / 1000.0,
                },
                username=username,
                password=password,
                timeout=HTTP_TIMEOUT,
            )
        else:
            _rpc(
                host,
                "Switch.Set",
                {"id": 0, "on": on},
                username=username,
                password=password,
                timeout=HTTP_TIMEOUT,
            )
        return
    if device.kind == "dimmer":
        turn = "on" if on else "off"
        _http_json(
            f"http://{host}/light/0?turn={turn}&brightness={brightness}&transition={transition_ms}",
            username=username,
            password=password,
            timeout=HTTP_TIMEOUT,
        )
        return
    turn = "on" if on else "off"
    _http_json(
        f"http://{host}/relay/0?turn={turn}",
        username=username,
        password=password,
        timeout=HTTP_TIMEOUT,
    )


def apply_preset(devices, preset, presets=None, transition_ms=DEFAULT_TRANSITION_MS):
    """Apply a named preset to every enabled device. Returns per-host errors."""
    brightness = brightness_for_preset(preset, presets)
    errors = []
    for device in devices:
        if not getattr(device, "enabled", False) or not device.host:
            continue
        try:
            apply_to_device(device, brightness, transition_ms)
        except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
            errors.append(f"{device.host}: {exc}")
    return errors


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
    devices = [ShellyDevice.from_dict(item) for item in data.get("devices") or [] if item]
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
        devices,
        presets,
        max(0, transition_ms),
        enabled,
        start_lead_ms,
        end_lead_ms,
    )


def dump_lights_config(
    devices,
    presets,
    transition_ms,
    enabled=True,
    start_lead_ms=0,
    end_lead_ms=0,
    username="",
    password="",
):
    return {
        "enabled": bool(enabled),
        "username": str(username or "").strip(),
        "password": str(password or ""),
        "devices": [device.to_dict() for device in devices],
        "presets": {
            key: clamp_percent((presets or {}).get(key), DEFAULT_PRESETS[key])
            for key in PRESETS
        },
        "transition_ms": max(0, int(transition_ms)),
        "start_lead_ms": max(0, int(start_lead_ms or 0)),
        "end_lead_ms": max(0, int(end_lead_ms or 0)),
    }


def merge_discovered(saved, found):
    """Keep enabled flags and login; add newly seen devices."""
    by_host = {device.host: device for device in saved if device.host}
    for device in found:
        existing = by_host.get(device.host)
        if existing:
            existing.name = device.name or existing.name
            existing.device_id = device.device_id or existing.device_id
            existing.model = device.model or existing.model
            existing.kind = device.kind or existing.kind
            existing.gen = device.gen or existing.gen
            if not existing.username and device.username:
                existing.username = device.username
            if not existing.password and device.password:
                existing.password = device.password
        else:
            by_host[device.host] = device
    return sorted(by_host.values(), key=lambda item: (item.name.lower(), item.host))
