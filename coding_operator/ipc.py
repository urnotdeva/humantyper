"""Localhost control API so GUI and MCP share one executor process."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class ControlAPI:
    """Serves POST /action with JSON body {type, ...} → executor result."""

    def __init__(self, executor, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.executor = executor
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A003
                return

            def _json(self, code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                path = urlparse(self.path).path
                if path in ("/health", "/"):
                    self._json(200, {"ok": True, "service": "ai-coding-operator"})
                    return
                self._json(404, {"ok": False, "error": "not found"})

            def do_POST(self):  # noqa: N802
                path = urlparse(self.path).path
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    data = json.loads(raw.decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    self._json(400, {"ok": False, "error": "invalid json"})
                    return
                if path == "/action":
                    result = api.executor.execute(data)
                    self._json(200, result)
                    return
                self._json(404, {"ok": False, "error": "not found"})

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None


def call_action(payload: dict[str, Any], base_url: str | None = None) -> dict[str, Any]:
    """HTTP client used by the MCP process to reach the GUI daemon."""
    import os
    import urllib.error
    import urllib.request

    url = (base_url or os.environ.get("OPERATOR_URL") or f"http://{DEFAULT_HOST}:{DEFAULT_PORT}").rstrip(
        "/"
    )
    req = urllib.request.Request(
        f"{url}/action",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "error": (
                f"Cannot reach Operator GUI at {url} ({exc}). "
                "Start `ai-coding-operator` first, then retry."
            ),
        }
