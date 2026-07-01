import json
from pathlib import Path

from layerlens.models import Explanation

ROOT = Path(__file__).resolve().parents[1]


def test_example_fixture_is_valid():
    data = json.loads((ROOT / "examples" / "transformer_attention.json").read_text(encoding="utf-8"))
    ex = Explanation.model_validate(data)
    assert ex.components, "must have at least one component"
    comp = ex.components[0]
    # The naive view should have actually run.
    assert comp.naive.run_ok is True
    assert "shape" in comp.naive.run_stdout
    # Ledger terms used in prose should be defined.
    plains = {e.plain for e in comp.ledger}
    for term in ("注目度", "クエリ", "キー", "バリュー"):
        assert term in plains


def test_slug_is_url_safe():
    ex = Explanation.model_validate(
        {
            "id": "Weird Id / v2!",
            "title": "t",
            "source": {"name": "x"},
            "components": [
                {
                    "id": "c",
                    "name": "c",
                    "structure": {"diagram_mermaid": "graph LR; A-->B"},
                    "words": "w",
                    "math": "m",
                    "naive": {"code": "print(1)"},
                    "optimized": {"code": "print(1)"},
                }
            ],
        }
    )
    slug = ex.slug()
    assert "/" not in slug and " " not in slug and "!" not in slug


def test_slug_is_ascii_for_unicode_id():
    ex = Explanation.model_validate(
        {
            "id": "注意機構",
            "title": "t",
            "source": {"name": "x"},
            "components": [
                {
                    "id": "c",
                    "name": "c",
                    "structure": {"diagram_mermaid": "graph LR; A-->B"},
                    "words": "w",
                    "math": "m",
                    "naive": {"code": "print(1)"},
                    "optimized": {"code": "print(1)"},
                }
            ],
        }
    )
    slug = ex.slug()
    assert slug.isascii() and slug, "unicode id must yield a non-empty ASCII slug"
