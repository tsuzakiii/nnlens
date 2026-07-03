import copy
import json
from pathlib import Path

from nnlens.lint import lint_explanation
from nnlens.models import Explanation

ROOT = Path(__file__).resolve().parents[1]


def _fixture(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def _clean() -> dict:
    """A minimal explanation that satisfies the whole cross-view contract."""
    return {
        "id": "demo",
        "title": "Demo",
        "source": {"name": "demo"},
        "summary": "これは {{重み}} のデモ。",
        "components": [
            {
                "id": "demo",
                "name": "Demo",
                "ledger": [
                    {"plain": "重み", "symbol": "w", "formal": "weight", "intuition": "係数"}
                ],
                "structure": {"diagram_mermaid": "graph LR; A-->B"},
                "words": "ここで {{重み}} を掛ける。",
                "math": "式は $y = w x$（{{重み}} $w$）。",
                "naive": {"code": "print(1)", "run_stdout": "1\n", "run_ok": True},
                "optimized": {"code": "y = w @ x", "is_self_impl": True},
            }
        ],
    }


def _lint(data: dict) -> list[str]:
    return lint_explanation(Explanation.model_validate(data))


def test_clean_explanation_yields_no_warnings():
    assert _lint(_clean()) == []


def test_bundled_fixtures_pass_their_own_lint():
    # Dogfood: the examples we ship must satisfy the contract we enforce.
    for name in ("transformer_attention.json", "layer_norm.json"):
        assert _lint(_fixture(name)) == [], f"{name} should be lint-clean"


def test_unmarked_ledger_term_is_flagged():
    data = _clean()
    data["components"][0]["words"] = "重み を掛ける。"  # mention without {{...}}
    data["components"][0]["math"] = "式は $y = w x$。"
    data["summary"] = ""
    warnings = _lint(data)
    assert any("'重み'" in w and "never marked" in w for w in warnings)


def test_mark_without_ledger_entry_is_flagged():
    data = _clean()
    data["components"][0]["words"] += " そして {{謎の用語}} も。"
    warnings = _lint(data)
    assert any("謎の用語" in w and "no component's ledger" in w for w in warnings)


def test_marks_inside_code_or_math_do_not_count():
    # The renderer's term-walker skips code and math nodes, so a mark that only
    # exists there is NOT wired (rule 1 fires) and code examples of the mark
    # syntax must not trigger bogus unresolved-mark warnings (rule 2 silent).
    data = _clean()
    data["summary"] = ""
    data["components"][0]["words"] = "記法の例: `{{重み}}` と書く。"
    data["components"][0]["math"] = "式は $y = w x$ です。"
    warnings = _lint(data)
    assert any("'重み'" in w and "never marked" in w for w in warnings)
    assert not any("no component's ledger" in w for w in warnings)


def test_dollar_inside_code_span_in_words_not_flagged():
    data = _clean()
    data["components"][0]["words"] = "環境変数 `$PATH` を使う。{{重み}} を掛ける。"
    assert not any("'$'" in w for w in _lint(data))


def test_cross_component_marks_resolve_globally():
    # viewer.js merges all components' ledgers into one tooltip map, so a mark in
    # component A referencing component B's term renders fine — no warning.
    data = _clean()
    comp_b = {
        "id": "other",
        "name": "Other",
        "ledger": [{"plain": "勾配", "symbol": "∇", "formal": "gradient", "intuition": "傾き"}],
        "structure": {"diagram_mermaid": "graph LR; A-->B"},
        "words": "ここで {{勾配}} と {{重み}} を使う。",  # 重み is defined in component A
        "math": "式 $g = \\nabla f$（{{勾配}}）。",
        "naive": {"code": "print(1)", "run_stdout": "1\n", "run_ok": True},
        "optimized": {"code": "pass", "is_self_impl": True},
    }
    data["components"].append(comp_b)
    assert _lint(data) == []


def test_symbols_in_words_view_are_flagged():
    data = _clean()
    data["components"][0]["words"] = "ここで {{重み}} $w$ を掛ける。"
    assert any("'$'" in w for w in _lint(data))

    data = _clean()
    data["components"][0]["ledger"][0]["symbol"] = "α"
    data["components"][0]["words"] = "ここで {{重み}} α を掛ける。"
    assert any("symbol 'α'" in w for w in _lint(data))


def test_single_ascii_letter_symbol_not_flagged_in_words():
    # 'w' appears inside English words too often; single ASCII letters are skipped.
    data = _clean()
    data["components"][0]["words"] = "ここで {{重み}} w を掛ける。"
    assert not any("symbol" in w for w in _lint(data))


def test_mathless_math_view_is_flagged():
    data = _clean()
    data["components"][0]["math"] = "数式はありません（{{重み}}）。"
    assert any("no $" in w for w in _lint(data))


def test_sourceless_optimized_view_is_flagged():
    data = _clean()
    data["components"][0]["optimized"] = {"code": "y", "is_self_impl": False}
    assert any("optimized view has no source" in w for w in _lint(data))


def test_unverified_naive_run_is_flagged():
    data = _clean()
    data["components"][0]["naive"] = {"code": "print(1)"}  # run_ok defaults to None
    assert any("run_ok" in w for w in _lint(data))


def test_summary_mark_without_any_ledger_is_flagged():
    data = _clean()
    data["summary"] = "これは {{未定義語}} のデモ。"
    assert any("[summary]" in w and "未定義語" in w for w in _lint(data))


def test_render_tool_returns_warnings(monkeypatch, tmp_path):
    monkeypatch.setenv("NNLENS_STORE", str(tmp_path))
    from nnlens import server

    bad = copy.deepcopy(_clean())
    bad["components"][0]["naive"] = {"code": "print(1)"}  # unverified
    result = server.render(bad)
    assert "url" in result
    assert any("run_ok" in w for w in result["warnings"])

    good = server.render(_clean())
    assert good["warnings"] == []
