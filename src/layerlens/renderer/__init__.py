"""Local renderer: turn a validated Explanation into a self-contained HTML page
and serve it from a background static file server on localhost."""

from .build import build_html, write_explanation
from .server import ensure_server

__all__ = ["build_html", "write_explanation", "ensure_server"]
