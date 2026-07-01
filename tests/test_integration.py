"""Runtime integration: the render() tool actually serves the page over HTTP,
and the static server refuses anything outside /e/<slug>.html."""

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _example() -> dict:
    return json.loads((ROOT / "examples" / "transformer_attention.json").read_text(encoding="utf-8"))


def test_render_tool_serves_page_and_restricts_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("LAYERLENS_STORE", str(tmp_path))
    from layerlens import server

    result = server.render(_example())
    assert "url" in result, result
    url = result["url"]

    with urllib.request.urlopen(url, timeout=5) as r:
        assert r.status == 200
        body = r.read().decode("utf-8")
    assert body.lower().startswith("<!doctype html>")
    assert "Scaled Dot-Product Attention" in body

    base = url.rsplit("/e/", 1)[0]
    # Not under /e/  -> 404
    for bad in ("/secret.html", "/e/other.txt", "/e/"):
        try:
            urllib.request.urlopen(base + bad, timeout=5)
            raise AssertionError(f"expected 404 for {bad}")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404, f"{bad} -> {exc.code}"


def test_render_rejects_invalid_explanation(monkeypatch, tmp_path):
    monkeypatch.setenv("LAYERLENS_STORE", str(tmp_path))
    from layerlens import server

    result = server.render({"id": "x", "title": "t"})  # missing required fields
    assert result.get("error") == "validation_failed"
    assert "detail" in result
