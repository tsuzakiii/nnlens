import json
from pathlib import Path

from layerlens.models import Explanation
from layerlens.renderer import build_html, write_explanation

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
