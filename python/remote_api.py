"""LAN HTTP API for Cinema Player, used by a smartphone remote."""

from __future__ import annotations

import json
import os
import socket
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from cinema_player import APP_VERSION, ROOT_DIR, format_clock

REMOTE_PAGE = os.path.join(ROOT_DIR, "assets", "remote", "index.html")
DEFAULT_PORT = 8765


def lan_addresses():
    """IPv4 addresses other hosts on the LAN can use to reach this machine."""
    found = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("1.1.1.1", 80))
        found.append(sock.getsockname()[0])
        sock.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                found.append(ip)
    except OSError:
        pass
    unique = []
    for ip in found:
        if ip not in unique:
            unique.append(ip)
    return unique


def lan_urls(port):
    return [f"http://{ip}:{port}/" for ip in lan_addresses()]


class RemoteAPIServer:
    """Background HTTP server. All player calls run on the Tk thread."""

    def __init__(self, gui):
        self.gui = gui
        self.httpd = None
        self.thread = None
        self.host = "0.0.0.0"
        self.port = 0
        self.token = ""
        self.error = ""

    @property
    def running(self):
        return self.httpd is not None

    def urls(self):
        if not self.running:
            return []
        return lan_urls(self.port)

    def start(self, port=DEFAULT_PORT, token=""):
        self.stop()
        self.token = str(token or "")
        self.error = ""
        try:
            httpd = ThreadingHTTPServer((self.host, int(port)), RemoteAPIHandler)
        except OSError as exc:
            self.error = str(exc)
            self.port = 0
            return False
        httpd.gui = self.gui
        httpd.api = self
        self.httpd = httpd
        self.port = httpd.server_address[1]
        self.thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        httpd = self.httpd
        self.httpd = None
        self.port = 0
        self.error = ""
        if httpd is None:
            return
        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass
        thread = self.thread
        self.thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.5)

    def invoke(self, method, *args, timeout=8):
        gui = self.gui
        box = {}
        done = threading.Event()

        def run():
            try:
                box["result"] = getattr(gui, method)(*args)
            except Exception as exc:
                box["error"] = f"{type(exc).__name__}: {exc}"
            done.set()

        try:
            gui.root.after(0, run)
        except Exception:
            return {"ok": False, "error": "player_closed"}
        if not done.wait(timeout):
            return {"ok": False, "error": "timeout"}
        if "error" in box:
            return {"ok": False, "error": box["error"]}
        return box.get("result") or {"ok": False, "error": "empty"}


class RemoteAPIHandler(BaseHTTPRequestHandler):
    server_version = f"CinemaPlayer/{APP_VERSION}"

    def log_message(self, format, *args):
        return

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Cinema-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload, status=200):
        self._send(status, json.dumps(payload, ensure_ascii=False, default=str))

    def do_OPTIONS(self):
        self._send(204, b"")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        if path in ("/", "/remote"):
            self._serve_remote_page()
            return
        if not self._authorized():
            return
        if path == "/api":
            self._send_json(self._info())
            return
        if path == "/api/status":
            self._send_json(self.server.api.invoke("remote_status"))
            return
        if path == "/api/playlist":
            payload = self.server.api.invoke("remote_status")
            self._send_json({
                "ok": payload.get("ok", False),
                "playlist": payload.get("playlist", []),
                "playlist_name": payload.get("playlist_name", ""),
                "program_index": payload.get("program_index", 0),
            })
            return
        self._send_json({"ok": False, "error": "not_found"}, 404)

    def do_POST(self):
        self._dispatch_command()

    def do_PUT(self):
        self._dispatch_command()

    def _dispatch_command(self):
        if not self._authorized():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_json()
        query = parse_qs(parsed.query)
        if path == "/api/resume":
            self._send_json(self.server.api.invoke("remote_resume"))
            return
        if path == "/api/pause":
            self._send_json(self.server.api.invoke("remote_pause"))
            return
        if path == "/api/still":
            self._send_json(self.server.api.invoke("remote_still"))
            return
        if path == "/api/stop":
            self._send_json(self.server.api.invoke("remote_stop"))
            return
        if path == "/api/volume":
            value = body.get("volume", query.get("volume", [None])[0])
            if value is None:
                self._send_json({"ok": False, "error": "volume_required"}, 400)
                return
            self._send_json(self.server.api.invoke("remote_set_volume", value))
            return
        if path == "/api/program":
            value = body.get("index", query.get("index", [None])[0])
            if value is None:
                self._send_json({"ok": False, "error": "index_required"}, 400)
                return
            self._send_json(self.server.api.invoke("remote_set_program", value))
            return
        self._send_json({"ok": False, "error": "not_found"}, 404)

    def _authorized(self):
        token = self.server.api.token
        if not token:
            return True
        header = self.headers.get("X-Cinema-Token") or ""
        auth = self.headers.get("Authorization") or ""
        if auth.lower().startswith("bearer "):
            header = auth[7:].strip()
        if header == token:
            return True
        self._send_json({"ok": False, "error": "unauthorized"}, 401)
        return False

    def _info(self):
        api = self.server.api
        return {
            "ok": True,
            "name": "Cinema Player",
            "version": APP_VERSION,
            "port": api.port,
            "urls": api.urls(),
            "endpoints": {
                "status": "GET /api/status",
                "playlist": "GET /api/playlist",
                "resume": "POST /api/resume",
                "pause": "POST /api/pause",
                "still": "POST /api/still",
                "stop": "POST /api/stop",
                "volume": "PUT /api/volume",
                "program": "POST /api/program",
            },
        }

    def _serve_remote_page(self):
        try:
            with open(REMOTE_PAGE, encoding="utf-8") as handle:
                html = handle.read()
        except OSError:
            self._send_json({"ok": False, "error": "remote_page_missing"}, 404)
            return
        self._send(200, html, "text/html; charset=utf-8")

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(min(length, 1_000_000))
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}


def clip_times(state, duration, position):
    """Seconds and clock labels for the four program clocks."""
    duration = float(duration or 0)
    position = float(position or 0) if state == "PLAYING" else 0.0
    remaining = None
    if state != "OFF" and duration > 0:
        remaining = max(0.0, duration - position)
    progress = 0.0
    if duration > 0 and state == "PLAYING":
        progress = max(0.0, min(1.0, position / duration))
    end_clock = "--:--"
    if remaining is not None:
        end_clock = (datetime.now() + timedelta(seconds=remaining)).strftime("%H:%M:%S")
    return {
        "total_s": duration if state != "OFF" else None,
        "elapsed_s": position if state == "PLAYING" else (0.0 if state == "PROGRAM" else None),
        "remaining_s": remaining,
        "progress": progress,
        "total": format_clock(duration if state != "OFF" else None),
        "elapsed": format_clock(position if state == "PLAYING" else (0 if state != "OFF" else None)),
        "remaining": format_clock(remaining),
        "end": end_clock if state != "OFF" else "--:--",
    }
