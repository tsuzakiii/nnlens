"""Inline an explanation dict into the HTML template, and manage the library index."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from pathlib import Path

_TEMPLATE = Path(__file__).with_name("template.html")
_VIEWER = Path(__file__).with_name("viewer.js")
_DATA_TOKEN = "__LAYERLENS_DATA__"
_JS_TOKEN = "__LAYERLENS_JS__"

_index_lock = threading.Lock()
_DATA_RE = re.compile(r'<script type="application/json" id="data">(.*?)</script>', re.S)


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


# --- library index --------------------------------------------------------


# Must match the local server's path allowlist — an entry with any other slug
# would be listed/linked but always 404 when fetched.
_SLUG_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _clean_entry(entry: object) -> dict | None:
    """Normalize one index entry; return None if it isn't a usable record."""
    if not isinstance(entry, dict):
        return None
    slug = entry.get("slug")
    if not isinstance(slug, str) or not _SLUG_RE.match(slug) or ".." in slug:
        return None
    title = entry.get("title")
    kind = entry.get("kind")
    return {
        "slug": slug,
        "title": title if isinstance(title, str) else slug,
        "kind": kind if isinstance(kind, str) else "",
    }


def _load_entries(store_dir: str) -> list[dict]:
    """Load + normalize the cached index.json entries (caller may hold the lock)."""
    path = os.path.join(store_dir, "index.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
    except Exception:  # noqa: BLE001 — a corrupt index shouldn't break anything
        return []
    if not isinstance(loaded, dict) or not isinstance(loaded.get("explanations"), list):
        return []
    return [c for c in (_clean_entry(e) for e in loaded["explanations"]) if c]


def _write_index_atomic(store_dir: str, entries: list[dict]) -> None:
    """Sort + atomically write index.json (caller must hold ``_index_lock``)."""
    entries = sorted(entries, key=lambda e: e["title"].lower())
    path = os.path.join(store_dir, "index.json")
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


def _read_meta(html_path: str) -> dict:
    """Extract the embedded explanation metadata ({title, kind, ...}) from a page."""
    try:
        text = Path(html_path).read_text(encoding="utf-8")
        m = _DATA_RE.search(text)
        if not m:
            return {}
        data = json.loads(m.group(1))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def update_index(store_dir: str, slug: str, title: str, kind: str) -> None:
    """Upsert one explanation into ``<store_dir>/index.json`` (atomic, locked)."""
    entry = _clean_entry({"slug": slug, "title": title, "kind": kind})
    if entry is None:
        return
    with _index_lock:
        entries = [e for e in _load_entries(store_dir) if e["slug"] != slug]
        entries.append(entry)
        _write_index_atomic(store_dir, entries)


def reconcile_index(store_dir: str) -> list[dict]:
    """Rebuild the index from what actually exists on disk, and return the entries.

    Guarantees the library lists *every* ``e/<slug>.html`` (including ones made
    before indexing existed, or after the index was lost) and drops entries whose
    file was deleted. Metadata is reused from the cached index when present, else
    read from the page's embedded JSON.
    """
    e_dir = os.path.join(store_dir, "e")
    with _index_lock:
        cached = {e["slug"]: e for e in _load_entries(store_dir)}
        entries: list[dict] = []
        if os.path.isdir(e_dir):
            for name in sorted(os.listdir(e_dir)):
                if not name.endswith(".html"):
                    continue
                slug = name[:-5]
                if slug in cached:
                    entries.append(cached[slug])
                else:
                    meta = _read_meta(os.path.join(e_dir, name))
                    cleaned = _clean_entry(
                        {"slug": slug, "title": meta.get("title"), "kind": meta.get("kind")}
                    )
                    if cleaned:
                        entries.append(cleaned)
        _write_index_atomic(store_dir, entries)
        return sorted(entries, key=lambda e: e["title"].lower())


def delete_explanation(store_dir: str, slug: str) -> bool:
    """Delete an explanation's HTML and drop it from the index. True if a file was removed."""
    if not isinstance(slug, str) or "/" in slug or "\\" in slug or ".." in slug:
        return False
    html = os.path.join(store_dir, "e", f"{slug}.html")
    with _index_lock:
        removed = False
        if os.path.isfile(html):
            try:
                os.remove(html)
                removed = True
            except OSError:
                pass
        entries = [e for e in _load_entries(store_dir) if e["slug"] != slug]
        _write_index_atomic(store_dir, entries)
        return removed
