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


def update_index(store_dir: str, slug: str, title: str, kind: str) -> None:
    """Maintain ``<store_dir>/index.json`` listing every rendered explanation.

    The sidebar fetches this to show a library of all explanations, so each new
    render makes the whole set navigable from any page.
    """
    path = os.path.join(store_dir, "index.json")
    data: dict = {"explanations": []}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict) and isinstance(loaded.get("explanations"), list):
                data = loaded
        except Exception:  # noqa: BLE001 — a corrupt index shouldn't break rendering
            data = {"explanations": []}
    exps = [e for e in data["explanations"] if isinstance(e, dict) and e.get("slug") != slug]
    exps.append({"slug": slug, "title": title, "kind": kind})
    exps.sort(key=lambda e: (e.get("title") or "").lower())
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"explanations": exps}, f, ensure_ascii=False, indent=2)
