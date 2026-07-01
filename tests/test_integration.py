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

    # The library index is written by render() and served.
    with urllib.request.urlopen(base + "/index.json", timeout=5) as r:
        assert r.status == 200
        index = json.loads(r.read().decode("utf-8"))
    assert any(e["slug"] == "scaled-dot-product-attention" for e in index["explanations"])

    # Not under /e/ and not the index -> 404
    for bad in ("/secret.html", "/e/other.txt", "/e/", "/other.json"):
        try:
            urllib.request.urlopen(base + bad, timeout=5)
            raise AssertionError(f"expected 404 for {bad}")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404, f"{bad} -> {exc.code}"

    # DELETE removes the file and drops it from the (disk-reconciled) index.
    slug = url.rsplit("/e/", 1)[1].split("?", 1)[0][:-5]
    with urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=5) as r:
        assert r.status == 204
    with urllib.request.urlopen(base + "/index.json", timeout=5) as r:
        after = json.loads(r.read().decode("utf-8"))
    assert all(e["slug"] != slug for e in after["explanations"])
    try:
        urllib.request.urlopen(url, timeout=5)
        raise AssertionError("expected 404 after delete")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404


def test_render_rejects_invalid_explanation(monkeypatch, tmp_path):
    monkeypatch.setenv("LAYERLENS_STORE", str(tmp_path))
    from layerlens import server

    result = server.render({"id": "x", "title": "t"})  # missing required fields
    assert result.get("error") == "validation_failed"
    assert "detail" in result
