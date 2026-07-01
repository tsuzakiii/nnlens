"""A tiny background static-file server, started once per process.

The MCP ``render`` tool writes an HTML file into ``<store>/e/<slug>.html`` and then
ensures this server is running, so the host can hand the user a clickable URL.

It only serves ``/e/<slug>.html`` (slug = alphanumerics, ``-``, ``_``, ``.``), returns
404 for anything else, and never lists directories — so pointing ``LAYERLENS_STORE``
at a broad directory can't expose unrelated files.
"""

from __future__ import annotations

import functools
import http.server
import re
import socketserver
import threading

_lock = threading.Lock()
_server: socketserver.TCPServer | None = None
_port: int | None = None

_ALLOWED = re.compile(r"^/e/[A-Za-z0-9_.\-]+\.html$")


class _Handler(http.server.SimpleHTTPRequestHandler):
    def _allowed(self) -> bool:
        return bool(_ALLOWED.match(self.path.split("?", 1)[0].split("#", 1)[0]))

    def do_GET(self):  # noqa: N802
        if not self._allowed():
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):  # noqa: N802
        if not self._allowed():
            self.send_error(404)
            return
        super().do_HEAD()

    def list_directory(self, path):  # never list directories
        self.send_error(404)
        return None

    def log_message(self, *args):  # silence request logging
        pass


def ensure_server(store_dir: str, start_port: int = 8787, tries: int = 64) -> int:
    """Ensure the static server is serving ``store_dir``; return its port (idempotent)."""
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
