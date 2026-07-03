import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nnlens.models import Explanation, RelatedRef

ROOT = Path(__file__).resolve().parents[1]


def _minimal_explanation(**overrides):
    base = {
        "id": "x",
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
    base.update(overrides)
    return base


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


def test_examples_have_mutual_related_links():
    attention = Explanation.model_validate(
        json.loads((ROOT / "examples" / "transformer_attention.json").read_text(encoding="utf-8"))
    )
    layernorm = Explanation.model_validate(
        json.loads((ROOT / "examples" / "layer_norm.json").read_text(encoding="utf-8"))
    )
    assert any(r.slug == layernorm.slug() for r in attention.related)
    assert any(r.slug == attention.slug() for r in layernorm.related)


def test_explanation_defaults_to_no_related():
    ex = Explanation.model_validate(_minimal_explanation())
    assert ex.related == []


def test_related_ref_accepts_valid_slug():
    ex = Explanation.model_validate(
        _minimal_explanation(
            related=[{"slug": "layer-normalization", "label": "LN", "relation": "builds-on"}]
        )
    )
    assert len(ex.related) == 1
    ref = ex.related[0]
    assert ref.slug == "layer-normalization"
    assert ref.label == "LN"
    assert ref.relation == "builds-on"


def test_related_ref_defaults_relation_to_related():
    ref = RelatedRef.model_validate({"slug": "layer-normalization"})
    assert ref.relation == "related"
    assert ref.label == ""


@pytest.mark.parametrize(
    "bad_slug",
    [
        "../secret", "a/b", "a\\b", "../../etc",  # traversal / separators
        "a b", "注意機構", "a:b", "a%2eb", "",  # unservable by the local server's allowlist
    ],
)
def test_related_ref_rejects_unservable_slugs(bad_slug):
    with pytest.raises(ValidationError):
        RelatedRef.model_validate({"slug": bad_slug})
    with pytest.raises(ValidationError):
        Explanation.model_validate(_minimal_explanation(related=[{"slug": bad_slug}]))


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


def test_language_defaults_ja_and_accepts_codes():
    assert Explanation.model_validate(_minimal_explanation()).language == "ja"
    assert Explanation.model_validate(_minimal_explanation(language="en")).language == "en"
    with pytest.raises(ValidationError):
        Explanation.model_validate(_minimal_explanation(language="x" * 17))


def test_ui_labels_accepts_dict_and_caps_size():
    ex = Explanation.model_validate(
        _minimal_explanation(language="fr", ui_labels={"structure": "Structure", "library": "Bibliothèque"})
    )
    assert ex.ui_labels["library"] == "Bibliothèque"
    with pytest.raises(ValidationError):
        Explanation.model_validate(_minimal_explanation(ui_labels={"k": "x" * 121}))
    with pytest.raises(ValidationError):
        Explanation.model_validate(_minimal_explanation(ui_labels={f"k{i}": "v" for i in range(41)}))
