"""Structured schema for a layerlens explanation.

The whole point of the five views is that they are *linked*: the plain-word view
(view 2) and the math view (view 3) share one concept ledger, so the same idea is
referred to by the same everyday word, the same symbol, and the same formal name
across every view. The renderer uses ``{{plain-word}}`` marks in the prose to wire
hover tooltips back to the matching ledger entry.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class LedgerEntry(BaseModel):
    """One concept, named three ways so the five views can cross-reference it."""

    plain: str = Field(..., description="Everyday word for the concept, e.g. '注目度'.")
    symbol: str = Field("", description="Math symbol, e.g. 'α' or 'Q'.")
    formal: str = Field("", description="Formal / textbook term, e.g. 'attention weight'.")
    intuition: str = Field("", description="One short sentence of intuition.")


class StructureView(BaseModel):
    """View 1 — a diagram plus a short note."""

    diagram_mermaid: str = Field(..., description="Mermaid source for the structure diagram.")
    note: str = Field("", description="A short (1-3 sentence) description of the diagram.")


class NaiveView(BaseModel):
    """View 4 — a from-scratch implementation that is literally the math, run to prove it works."""

    code: str = Field(..., description="Self-contained code (pure Python or numpy — no torch).")
    language: str = "python"
    run_stdout: str = Field("", description="Captured stdout from actually running the code.")
    run_ok: Optional[bool] = Field(None, description="Whether the code ran without error.")


class SourceRef(BaseModel):
    repo: str = Field("", description="owner/name of the source repository.")
    path: str = Field("", description="Path of the excerpted file within the repo.")
    url: str = Field("", description="Permalink to the excerpted code.")


class OptimizedView(BaseModel):
    """View 5 — the real, optimized implementation (official repo excerpt or a self-written one)."""

    source: Optional[SourceRef] = None
    code: str = Field("", description="The optimized implementation or an excerpt of it.")
    language: str = "python"
    note: str = Field("", description="What makes this fast / how it differs from the naive view.")
    is_self_impl: bool = Field(False, description="True if written here rather than taken from a repo.")


class Component(BaseModel):
    """One decomposable piece (a layer, block, or technique) with all five views."""

    id: str = Field(..., description="Stable slug, e.g. 'scaled-dot-product-attention'.")
    name: str = Field(..., description="Human-readable name.")
    ledger: list[LedgerEntry] = Field(default_factory=list)
    structure: StructureView
    words: str = Field(..., description="View 2: plain-word explanation. No symbols/jargon. Mark concepts as {{plain}}.")
    math: str = Field(..., description="View 3: math explanation carrying the {{plain}} terms from view 2 plus symbols.")
    naive: NaiveView
    optimized: OptimizedView


class Source(BaseModel):
    name: str = Field(..., description="Name of the technique/architecture being explained.")
    paper_url: str = ""
    repo_url: str = ""


class RelatedRef(BaseModel):
    """A link to another explanation in the local library."""

    slug: str = Field(..., description="Slug of the related explanation, e.g. 'layer-normalization'.")
    label: str = Field("", description="Display label; defaults to the slug at render time.")
    relation: Literal["contains", "part-of", "builds-on", "related"] = "related"

    @field_validator("slug")
    @classmethod
    def _require_servable_slug(cls, v: str) -> str:
        # Must match the local server's path allowlist (^/e/[A-Za-z0-9_.\-]+\.html$),
        # otherwise the link would render but always 404. This also excludes path
        # separators / traversal outright.
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", v) or ".." in v:
            raise ValueError(
                "related.slug must match [A-Za-z0-9_.-]+ (the server's URL allowlist)"
            )
        return v


class Explanation(BaseModel):
    """A complete explanation: one architecture/technique, decomposed into components."""

    id: str = Field(..., description="Stable slug for the whole explanation, used in the render URL.")
    title: str
    kind: Literal["architecture", "component", "technique"] = "component"
    summary: str = Field("", description="One-paragraph overview shown at the top.")
    source: Source
    components: list[Component] = Field(..., min_length=1)
    related: list[RelatedRef] = Field(default_factory=list)

    def slug(self) -> str:
        # ASCII-only: the local render server's allowlist is ASCII, so a Japanese/
        # Unicode id must not survive into the filename (it would 404 on fetch).
        safe = "".join(
            c if ((c.isascii() and c.isalnum()) or c in "-_") else "-" for c in self.id
        )
        while "--" in safe:
            safe = safe.replace("--", "-")
        safe = safe.strip("-_").lower()[:80]
        if not safe:
            # id was all non-ASCII (or empty): use a stable hash so distinct ids differ.
            safe = "explanation-" + hashlib.sha1(self.id.encode("utf-8")).hexdigest()[:8]
        return safe
