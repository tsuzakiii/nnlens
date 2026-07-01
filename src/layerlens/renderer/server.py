"""A tiny background server for rendered explanations + the library index.

Serves only:
  - ``GET /e/<slug>.html``     — a rendered explanation (static file)
  - ``GET /index.json``        — the library, rebuilt from disk on every request
  - ``DELETE /e/<slug>.html``  — remove an explanation (file + index entry)

Everything else 404s, directory listings are disabled, and it binds to 127.0.0.1
only. DELETE is a non-simple method, so browsers preflight it cross-origin; since
the server sends no CORS approval, only the layerlens page (same origin) can delete.
"""

from __future__ import annotations

import functools
import http.server
import json
import re
import socketserver
import threading

from .build import delete_explanation, reconcile_index

_lock = threading.Lock()
_server: socketserver.TCPServer | None = None
_port: int | None = None

_E_HTML = re.compile(r"^/e/([A-Za-z0-9_.\-]+)\.html$")
_INDEX = "/index.json"


class _Handler(http.server.SimpleHTTPRequestHandler):
    def _path(self) -> str:
        return self.path.split("?", 1)[0].split("#", 1)[0]

    def do_GET(self):  # noqa: N802
        path = self._path()
        if path == _INDEX:
            self._serve_index()
            return
        if not _E_HTML.match(path):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        path = self._path()
        if path == _INDEX or _E_HTML.match(path):
            super().do_HEAD()
            return
        self.send_error(404)

    def do_DELETE(self):  # noqa: N802
        match = _E_HTML.match(self._path())
        if not match:
            self.send_error(404)
            return
        try:
            delete_explanation(self.directory, match.group(1))
        except Exception:  # noqa: BLE001
            self.send_error(500)
            return
        self.send_response(204)
        self.end_headers()

    def _serve_index(self):
        try:
            entries = reconcile_index(self.directory)
        except Exception:  # noqa: BLE001
            entries = []
        body = json.dumps({"explanations": entries}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def list_directory(self, path):  # never list directories
        self.send_error(404)
        return None

    def log_message(self, *args):  # silence request logging
        pass


def ensure_server(store_dir: str, start_port: int = 8787, tries: int = 64) -> int:
    """Ensure the server is serving ``store_dir``; return its port (idempotent)."""
    global _server, _port
    with _lock:
        if _server is not None:
            return _port  # type: ignore[return-value]
        handler = functools.partial(_Handler, directory=store_dir)
        port = start_port
        last_err: Exception | None = None
        for _ in range(tries):
            try:
                httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), handler)
                break
            except OSError as exc:
                last_err = exc
                port += 1
        else:
            raise RuntimeError(f"no free port in [{start_port}, {start_port + tries}): {last_err}")
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _server = httpd
        _port = port
        return port
