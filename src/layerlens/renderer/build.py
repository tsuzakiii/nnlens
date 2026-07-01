"""Inline an explanation dict into the HTML template."""

from __future__ import annotations

import json
import os
from pathlib import Path

_TEMPLATE = Path(__file__).with_name("template.html")
_VIEWER = Path(__file__).with_name("viewer.js")
_DATA_TOKEN = "__LAYERLENS_DATA__"
_JS_TOKEN = "__LAYERLENS_JS__"


def build_html(explanation: dict) -> str:
    """Return a self-contained HTML document rendering ``explanation``."""
    template = _TEMPLATE.read_text(encoding="utf-8")
    viewer_js = _VIEWER.read_text(encoding="utf-8")
    # Inline the viewer script first (trusted, no tokens of its own), then the data.
    html = template.replace(_JS_TOKEN, viewer_js)
    # Embed as JSON in a <script type="application/json"> tag parsed by JSON.parse.
    # The only sequence that could break out of that context is "</" (e.g. an
    # embedded "</script>"), so escape just that.
    payload = json.dumps(explanation, ensure_ascii=False).replace("</", "<\\/")
    return html.replace(_DATA_TOKEN, payload)


def write_explanation(explanation: dict, store_dir: str, slug: str) -> str:
    """Write ``<store_dir>/e/<slug>.html`` and return the file path."""
    out_dir = os.path.join(store_dir, "e")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{slug}.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_html(explanation))
    return path
