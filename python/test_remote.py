#!/usr/bin/env python3
"""Remote pairing URL and QR tests (no network)."""

import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("tkinter", MagicMock())
sys.modules.setdefault("font_setup", MagicMock())

import qr_code
from remote_api import RemoteAPIHandler, connect_url, connect_urls


class ConnectUrlTests(unittest.TestCase):
    def test_connect_url_includes_ip_port_token_and_language(self):
        url = connect_url("192.168.1.20", 8765, "secret-token", "de")
        self.assertEqual(
            url,
            "http://192.168.1.20:8765/?token=secret-token&lang=de",
        )

    def test_connect_url_encodes_token(self):
        url = connect_url("10.0.0.8", 9000, "a b/c", "en")
        self.assertIn("token=a+b%2Fc", url)
        self.assertIn("lang=en", url)
        self.assertTrue(url.startswith("http://10.0.0.8:9000/?"))

    def test_connect_urls_uses_lan_order(self):
        from unittest.mock import patch
        with patch("remote_api.lan_addresses", return_value=["192.168.0.5"]):
            urls = connect_urls(8765, "tok", "en")
        self.assertEqual(urls, ["http://192.168.0.5:8765/?token=tok&lang=en"])


class QrCodeTests(unittest.TestCase):
    def test_finder_patterns(self):
        grid = qr_code.matrix("http://192.168.1.20:8765/?token=abc&lang=de")
        size = len(grid)
        self.assertEqual(size, len(grid[0]))
        self.assertGreaterEqual(size, 21)
        finder = [
            [1, 1, 1, 1, 1, 1, 1],
            [1, 0, 0, 0, 0, 0, 1],
            [1, 0, 1, 1, 1, 0, 1],
            [1, 0, 1, 1, 1, 0, 1],
            [1, 0, 1, 1, 1, 0, 1],
            [1, 0, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 1, 1],
        ]
        for row0, col0 in ((0, 0), (0, size - 7), (size - 7, 0)):
            block = [grid[row0 + r][col0:col0 + 7] for r in range(7)]
            self.assertEqual(block, finder)
        self.assertEqual(grid[size - 8][8], 1)

    def test_pairing_payload_fits(self):
        url = connect_url("192.168.100.200", 8765, "cinema-token-value-32chars______", "de")
        grid = qr_code.matrix(url)
        self.assertTrue(all(bit in (0, 1) for row in grid for bit in row))
        self.assertIn("token=", url)
        self.assertIn("192.168.100.200", url)


class RemotePageTests(unittest.TestCase):
    def test_pairing_get_returns_html(self):
        import threading
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer

        class DummyApi:
            token = "secret-token"
            port = 0

            def urls(self):
                return []

            def invoke(self, *args, **kwargs):
                return {"ok": True}

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), RemoteAPIHandler)
        httpd.api = DummyApi()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            port = httpd.server_address[1]
            conn = HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("GET", "/?token=secret-token&lang=de")
            response = conn.getresponse()
            body = response.read()
            conn.close()
            self.assertEqual(response.status, 200)
            self.assertIn(b"text/html", (response.getheader("Content-Type") or "").encode())
            self.assertIn(b"Cinema Player", body)
            self.assertGreater(len(body), 100)
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
