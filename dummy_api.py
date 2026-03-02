#!/usr/bin/env python3
"""
Simple dummy JSON API for local testing.

Usage (from repo root):
  python dummy_api.py --port 8000

Example endpoints:
  GET  /health          -> {"status": "ok"}
  GET  /items           -> [{"id": 1, "name": "Example item"}, ...]
  GET  /items/1         -> {"id": 1, "name": "Example item"}
  POST /echo            -> echoes back the JSON body you send
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


MOCK_ITEMS = [
    {"id": 1, "name": "Example item 1"},
    {"id": 2, "name": "Example item 2"},
    {"id": 3, "name": "Example item 3"},
]


class DummyRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    MAX_BODY_BYTES = 1024 * 1024

    def _send_json(self, obj, status: int = 200) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _not_found(self) -> None:
        self._send_json({"error": "Not found"}, status=404)

    def log_message(self, format, *args):  # type: ignore[override]
        # Quieter logging; comment out to see all requests
        return

    def do_GET(self):  # type: ignore[override]
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/":
            self._send_json(
                {
                    "message": "Dummy API is running",
                    "endpoints": [
                        "GET  /health",
                        "GET  /items",
                        "GET  /items/<id>",
                        "POST /echo",
                    ],
                }
            )
            return

        if path == "/health":
            self._send_json({"status": "ok"})
            return

        if path == "/items":
            self._send_json(MOCK_ITEMS)
            return

        if path.startswith("/items/"):
            try:
                item_id = int(path.split("/", maxsplit=2)[-1])
            except ValueError:
                self._send_json({"error": "Invalid item id"}, status=400)
                return
            for item in MOCK_ITEMS:
                if item["id"] == item_id:
                    self._send_json(item)
                    return
            self._not_found()
            return

        self._not_found()

    def do_POST(self):  # type: ignore[override]
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path == "/echo":
            content_length = self.headers.get("Content-Length", "0")
            try:
                length = int(content_length or 0)
            except ValueError:
                self._send_json({"error": "Invalid Content-Length header"}, status=400)
                return
            if length > self.MAX_BODY_BYTES:
                self._send_json({"error": "Request body too large"}, status=413)
                return
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json({"error": "Invalid JSON body"}, status=400)
                return

            self._send_json({"received": body})
            return

        self._not_found()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple dummy JSON API.")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    args = parser.parse_args()

    server_address = ("127.0.0.1", args.port)
    httpd = HTTPServer(server_address, DummyRequestHandler)
    print(f"Dummy API listening on http://{server_address[0]}:{server_address[1]}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()

