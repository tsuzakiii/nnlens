import json
from pathlib import Path

from layerlens.models import Explanation
from layerlens.renderer import (
    build_html,
    delete_explanation,
    reconcile_index,
    update_index,
    write_explanation,
)

ROOT = Path(__file__).resolve().parents[1]


def _example() -> dict:
    return json.loads((ROOT / "examples" / "transformer_attention.json").read_text(encoding="utf-8"))


def test_build_html_embeds_data_and_libs():
    html = build_html(_example())
    assert "__LAYERLENS_DATA__" not in html, "token must be replaced"
    assert "scaled-dot-product-attention" in html
    assert "mermaid" in html and "katex" in html
    # No raw </script> breakout from the embedded JSON.
    assert "</script></script>" not in html


def test_build_html_embeds_related():
    # The example fixture carries a related link to layer-normalization; it must
    # survive into the embedded JSON payload (the JS side renders it as a chip).
    html = build_html(_example())
    assert '"related"' in html
    assert "layer-normalization" in html


def test_write_explanation_creates_file(tmp_path):
    ex = Explanation.model_validate(_example())
    path = write_explanation(ex.model_dump(), str(tmp_path), ex.slug())
    p = Path(path)
    assert p.exists()
    assert p.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_update_index_upserts(tmp_path):
    update_index(str(tmp_path), "a", "Alpha", "technique")
    update_index(str(tmp_path), "b", "Beta", "component")
    update_index(str(tmp_path), "a", "Alpha v2", "technique")  # same slug -> upsert, not duplicate
    data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    exps = data["explanations"]
    slugs = [e["slug"] for e in exps]
    assert sorted(slugs) == ["a", "b"], "no duplicate for re-rendered slug"
    titles = {e["slug"]: e["title"] for e in exps}
    assert titles["a"] == "Alpha v2"


def test_update_index_survives_corrupt_file(tmp_path):
    (tmp_path / "index.json").write_text("not json {{{", encoding="utf-8")
    update_index(str(tmp_path), "a", "Alpha", "technique")
    data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [e["slug"] for e in data["explanations"]] == ["a"]


def test_reconcile_index_picks_up_disk_files(tmp_path):
    # A rendered file with no index entry must still appear (metadata read from HTML).
    ex = Explanation.model_validate(_example())
    write_explanation(ex.model_dump(), str(tmp_path), ex.slug())
    entries = reconcile_index(str(tmp_path))
    entry = next(e for e in entries if e["slug"] == ex.slug())
    assert entry["title"] == ex.title
    assert entry["kind"] == ex.kind


def test_reconcile_index_drops_missing_then_delete(tmp_path):
    ex = Explanation.model_validate(_example())
    write_explanation(ex.model_dump(), str(tmp_path), ex.slug())
    update_index(str(tmp_path), ex.slug(), ex.title, ex.kind)
    update_index(str(tmp_path), "ghost", "Ghost", "technique")  # index entry with no file
    slugs = [e["slug"] for e in reconcile_index(str(tmp_path))]
    assert "ghost" not in slugs and ex.slug() in slugs

    assert delete_explanation(str(tmp_path), ex.slug()) is True
    assert not (tmp_path / "e" / f"{ex.slug()}.html").exists()
    assert ex.slug() not in [e["slug"] for e in reconcile_index(str(tmp_path))]


def test_delete_explanation_rejects_traversal(tmp_path):
    assert delete_explanation(str(tmp_path), "../secret") is False
    assert delete_explanation(str(tmp_path), "a/b") is False


def test_index_drops_unservable_slugs(tmp_path):
    # A slug the server's URL allowlist can't serve must never appear in the
    # library (it would render as a link that always 404s).
    update_index(str(tmp_path), "a b", "Spaces", "technique")
    update_index(str(tmp_path), "日本語", "Unicode", "technique")
    update_index(str(tmp_path), "ok-slug", "Fine", "technique")
    data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert [e["slug"] for e in data["explanations"]] == ["ok-slug"]


def test_update_index_normalizes_bad_entries(tmp_path):
    # Valid JSON but malformed entry (title is a dict, kind is an int) must not crash.
    (tmp_path / "index.json").write_text(
        json.dumps({"explanations": [{"slug": "x", "title": {}, "kind": 3}]}), encoding="utf-8"
    )
    update_index(str(tmp_path), "y", "Why", "technique")
    data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    by = {e["slug"]: e for e in data["explanations"]}
    assert set(by) == {"x", "y"}
    assert by["x"]["title"] == "x"  # bad title coerced to slug fallback
    assert isinstance(by["x"]["kind"], str)
