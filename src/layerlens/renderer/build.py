"""Inline an explanation dict into the HTML template."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

_TEMPLATE = Path(__file__).with_name("template.html")
_index_lock = threading.Lock()
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


def _clean_entry(entry: object) -> dict | None:
    """Normalize one index entry; return None if it isn't a usable record."""
    if not isinstance(entry, dict):
        return None
    slug = entry.get("slug")
    if not isinstance(slug, str) or not slug:
        return None
    title = entry.get("title")
    kind = entry.get("kind")
    return {
        "slug": slug,
        "title": title if isinstance(title, str) else slug,
        "kind": kind if isinstance(kind, str) else "",
    }


def update_index(store_dir: str, slug: str, title: str, kind: str) -> None:
    """Maintain ``<store_dir>/index.json`` listing every rendered explanation.

    The sidebar fetches this to show a library of all explanations, so each new
    render makes the whole set navigable from any page.

    Concurrency: a process-wide lock serializes read-modify-write, and the file is
    replaced atomically (temp file + ``os.replace``) so a concurrent reader/render
    never sees a truncated/partial index. Across separate processes sharing one
    store the update is best-effort last-writer-wins (self-heals on re-render), but
    never corrupt.
    """
    path = os.path.join(store_dir, "index.json")
    entry = _clean_entry({"slug": slug, "title": title, "kind": kind})
    if entry is None:  # slug is always a non-empty str in practice, but be safe
        return
    with _index_lock:
        entries: list[dict] = []
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("explanations"), list):
                    entries = [c for c in (_clean_entry(e) for e in loaded["explanations"]) if c]
            except Exception:  # noqa: BLE001 — a corrupt index shouldn't break rendering
                entries = []
        entries = [e for e in entries if e["slug"] != slug]
        entries.append(entry)
        entries.sort(key=lambda e: e["title"].lower())

        fd, tmp = tempfile.mkstemp(dir=store_dir, prefix=".index-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"explanations": entries}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
