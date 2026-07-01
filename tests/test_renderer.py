import json
from pathlib import Path

from layerlens.models import Explanation
from layerlens.renderer import build_html, update_index, write_explanation

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
