"""Quality lint for an Explanation — the cross-view contract, checked by the server.

The whole point of the five views is that they stay wired together by the concept
ledger. pydantic can only check the *shape*; these checks catch a host that filled
the shape but broke the contract (unmarked ledger terms, symbols leaking into the
plain-words view, an optimized view with no source, an unverified naive run).

The lint mirrors the renderer's actual behavior (Codex review): the viewer wraps
``{{term}}`` marks *after* markdown/KaTeX rendering and skips code and math nodes,
and it resolves tooltips against the union of ALL components' ledgers. So the lint
strips code/math regions before analysis and resolves marks globally — otherwise
it would warn about things that render fine (and vice versa).

Violations are returned as WARNINGS from the ``render`` tool — never hard errors —
so the host can fix and re-render, or consciously ship with a justified warning.
"""

from __future__ import annotations

import re

from .models import Explanation

_MARK_RE = re.compile(r"\{\{([^}]+)\}\}")
_NON_ASCII = re.compile(r"[^\x00-\x7F]")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.S)
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_DISPLAY_MATH_RE = re.compile(r"\$\$.*?\$\$", re.S)
_INLINE_MATH_RE = re.compile(r"\$[^$\n]*\$")


def _strip_code(text: str) -> str:
    """Remove code regions — the renderer never wraps marks or renders math there."""
    return _INLINE_CODE_RE.sub(" ", _FENCED_CODE_RE.sub(" ", text or ""))


def _strip_code_and_math(text: str) -> str:
    """Remove code and math regions — what's left is what the term-walker sees."""
    return _INLINE_MATH_RE.sub(" ", _DISPLAY_MATH_RE.sub(" ", _strip_code(text)))


def _marks(*texts: str) -> set[str]:
    found: set[str] = set()
    for t in texts:
        found.update(m.strip() for m in _MARK_RE.findall(_strip_code_and_math(t)))
    return found


def lint_explanation(ex: Explanation) -> list[str]:
    """Return human-readable warnings for contract violations (empty = clean)."""
    warnings: list[str] = []

    # Tooltip resolution is global at runtime (viewer.js merges every component's
    # ledger into one map), so marks resolve against the union of all ledgers, and
    # a ledger term counts as "wired" if it's marked anywhere in the explanation.
    all_plains = {e.plain for comp in ex.components for e in comp.ledger}
    per_comp_marks = {
        comp.id: _marks(comp.words, comp.math, comp.structure.note, comp.optimized.note)
        for comp in ex.components
    }
    summary_marks = _marks(ex.summary)
    all_marks = summary_marks.union(*per_comp_marks.values()) if per_comp_marks else summary_marks

    for comp in ex.components:
        # 1. Every ledger concept must actually be wired into the prose somewhere.
        for entry in comp.ledger:
            if entry.plain not in all_marks:
                warnings.append(
                    f"[{comp.id}] ledger term '{entry.plain}' is never marked as "
                    f"{{{{{entry.plain}}}}} in the prose (code/math regions don't "
                    f"count) — its hover link will never fire"
                )

        # 2. Marks must resolve to some ledger entry (else: no tooltip).
        for mark in sorted(per_comp_marks[comp.id] - all_plains):
            warnings.append(
                f"[{comp.id}] '{{{{{mark}}}}}' is marked in the prose but defined in "
                f"no component's ledger — it will render without a tooltip"
            )

        # 3. The words view (view 2) must stay symbol-free plain language.
        words_no_code = _strip_code(comp.words)
        if "$" in words_no_code:
            warnings.append(
                f"[{comp.id}] words view contains '$' math — view 2 must be "
                f"symbol-free plain language (symbols belong in view 3)"
            )
        words_prose = _strip_code_and_math(comp.words)
        for entry in comp.ledger:
            sym = entry.symbol.strip()
            # Single ASCII letters (Q, d, ...) are skipped: too many false positives.
            if sym and (len(sym) > 1 or _NON_ASCII.search(sym)) and sym in words_prose:
                warnings.append(
                    f"[{comp.id}] words view contains the symbol '{sym}' — view 2 "
                    f"must be symbol-free plain language"
                )

        # 4. The math view (view 3) should use real notation ('$' in code doesn't count).
        if "$" not in _strip_code(comp.math):
            warnings.append(
                f"[{comp.id}] math view contains no $…$ notation — view 3 should "
                f"state the actual equations"
            )

        # 5. The optimized view must cite its source or own up to being self-written.
        op = comp.optimized
        if not op.is_self_impl and not (op.source and (op.source.url or op.source.repo)):
            warnings.append(
                f"[{comp.id}] optimized view has no source reference and "
                f"is_self_impl is false — cite the repo (fetch_repo_code) or set "
                f"is_self_impl=true"
            )

        # 6. The naive view's execution proof must be real.
        if comp.naive.run_ok is not True:
            warnings.append(
                f"[{comp.id}] naive view was not verified (run_ok is not true) — "
                f"execute it with run_python and embed the real stdout"
            )

    # 7. Summary marks must resolve too.
    for mark in sorted(summary_marks - all_plains):
        warnings.append(
            f"[summary] '{{{{{mark}}}}}' is marked but defined in no component's "
            f"ledger — it will render without a tooltip"
        )

    return warnings
