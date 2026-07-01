"""A tiny background server for rendered explanations + the library index.

Serves only:
  - ``GET/HEAD /e/<slug>.html``  — a rendered explanation (static file)
  - ``GET/HEAD /index.json``     — the library (static; rebuilt from disk at start
                                    and on each render/delete, never on GET)
  - ``DELETE /e/<slug>.html``    — remove an explanation (file + index entry)

Hardening:
  - binds to 127.0.0.1 only, disables directory listings, 404s everything else;
  - validates the ``Host`` header is loopback (defeats DNS-rebinding, since a
    rebound hostname won't match) and, for DELETE, rejects non-loopback ``Origin``;
  - GET is read-only (no filesystem writes), so a cross-site GET can't drive disk
    churn.
"""

from __future__ import annotations

import functools
import http.server
import re
import socketserver
import threading
from urllib.parse import urlsplit

from .build import delete_explanation, reconcile_index

_lock = threading.Lock()
_server: socketserver.TCPServer | None = None
_port: int | None = None

_ALLOWED = re.compile(r"^/(?:e/[A-Za-z0-9_.\-]+\.html|index\.json)$")
_E_HTML = re.compile(r"^/e/([A-Za-z0-9_.\-]+)\.html$")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _hostname_of(value: str) -> str:
    try:
        return (urlsplit("//" + value).hostname or "").lower()
    except ValueError:
        return ""


def _origin_hostname(value: str) -> str:
    try:
        return (urlsplit(value).hostname or "").lower()
    except ValueError:
        return ""


class _Handler(http.server.SimpleHTTPRequestHandler):
    def _path(self) -> str:
        return self.path.split("?", 1)[0].split("#", 1)[0]

    def _host_ok(self) -> bool:
        # Defeats DNS rebinding: only requests addressed to a loopback host pass.
        return _hostname_of(self.headers.get("Host", "")) in _LOCAL_HOSTS

    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            self.send_error(403)
            return
        if not _ALLOWED.match(self._path()):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        if not self._host_ok():
            self.send_error(403)
            return
        if not _ALLOWED.match(self._path()):
            self.send_error(404)
            return
        super().do_HEAD()

    def do_DELETE(self):  # noqa: N802
        if not self._host_ok():
            self.send_error(403)
            return
        origin = self.headers.get("Origin")
        if origin and _origin_hostname(origin) not in _LOCAL_HOSTS:
            self.send_error(403)
            return
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

    def list_directory(self, path):  # never list directories
        self.send_error(404)
        return None

    def log_message(self, *args):  # silence request logging
        pass


def ensure_server(store_dir: str, start_port: int = 8787, tries: int = 64) -> int:
    """Ensure the server is serving ``store_dir``; return its port (idempotent).

    Reconciles the index from disk once at startup so every existing explanation
    (including ones rendered before/elsewhere) is listed without a GET-time write.
    """
    global _server, _port
    with _lock:
        if _server is not None:
            return _port  # type: ignore[return-value]
        try:
            reconcile_index(store_dir)
        except Exception:  # noqa: BLE001 — never let a bad index block serving
            pass
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
