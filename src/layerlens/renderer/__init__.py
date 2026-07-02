"""Local renderer: turn a validated Explanation into a self-contained HTML page
and serve it from a background static file server on localhost."""

from .build import (
    build_html,
    delete_explanation,
    rebuild_store,
    reconcile_index,
    template_hash,
    update_index,
    write_explanation,
)
from .server import ensure_server

__all__ = [
    "build_html",
    "write_explanation",
    "update_index",
    "reconcile_index",
    "rebuild_store",
    "template_hash",
    "delete_explanation",
    "ensure_server",
]
