"""The ``/explain`` prompt: the methodology the host LLM follows.

This is the heart of layerlens as an MCP server. The server owns the *hard,
deterministic* parts (fetching sources, running code, rendering); this prompt tells
the host how to assemble the five linked views and thread the concept ledger, then
hand the finished JSON to the ``render`` tool.
"""

EXPLAIN_PROMPT = """\
You are producing a **layerlens explanation** of: **{topic}**

Audience: someone learning neural networks. Write the prose in Japanese.

# The five views (per component)
Every component (a layer, block, or technique) is explained in FIVE linked views:

1. **structure** — a Mermaid diagram of the data flow, plus a 1-3 sentence note.
2. **words** — a plain-language explanation. **No symbols, no jargon.** Explain the
   math using everyday words only (e.g. say "how much to look at each word" instead
   of "attention weight α").
3. **math** — the same explanation with real notation. It must **carry over the
   everyday words introduced in view 2** and attach each to its symbol and formal
   name. Use KaTeX: inline `$...$`, display `$$...$$`.
4. **naive** — a from-scratch implementation that is *literally the math*: pure
   Python or numpy only, **absolutely no torch / tensorflow / jax**. It must be
   self-contained and print a small shape/values sanity check.
5. **optimized** — the real, fast implementation. Prefer an excerpt from the
   **official repository** (use the tools to find and fetch it) with a source link.
   If none is findable, write your own optimized version and set `is_self_impl=true`.

# The concept ledger (this is what links the views)
For each component, build a `ledger`: a list of concepts, each with
`plain` (everyday word), `symbol`, `formal` (textbook term), and `intuition`.
In the `words` and `math` prose, wrap every ledger concept in double braces the
first time it matters, e.g. write `{{{{注目度}}}}`. The renderer turns these into
hover tooltips that show the symbol + formal name + intuition. This is how view 2's
plain words stay wired to view 3's symbols.

# How to work (use the MCP tools)
1. Call `list_library` first to see which explanations already exist (slug, title,
   kind). If any are related to this topic, link them: add a `related` entry, and/or
   write `[[slug]]` (or `[[slug|display text]]`) in the prose to reference that
   explanation by name — only use slugs that `list_library` actually returned.
2. Call `fetch_paper` and/or `find_official_repo` to ground yourself in the real
   source. For the optimized view, `fetch_repo_code` the actual file and excerpt it.
3. Write the naive code, then call `run_python` on it. Put the real captured
   `stdout` into `naive.run_stdout` and the success flag into `naive.run_ok`. If it
   errors, fix the code and re-run — never fake the output.
4. Assemble the full Explanation object (schema below) and call `render` with it.
5. Give the user the returned URL and a one-line summary.

# Explanation JSON shape
`kind` must be exactly one of: `architecture`, `component`, or `technique`.

```json
{{
  "id": "kebab-slug",
  "title": "…",
  "kind": "component",
  "summary": "one paragraph",
  "source": {{ "name": "…", "paper_url": "…", "repo_url": "…" }},
  "related": [ {{ "slug": "…", "label": "…", "relation": "contains | part-of | builds-on | related" }} ],
  "components": [
    {{
      "id": "kebab-slug",
      "name": "…",
      "ledger": [ {{ "plain": "…", "symbol": "…", "formal": "…", "intuition": "…" }} ],
      "structure": {{ "diagram_mermaid": "graph LR; …", "note": "…" }},
      "words": "markdown with {{{{plain-word}}}} marks, no symbols",
      "math": "markdown + KaTeX, carries the {{{{plain-word}}}} marks and their symbols",
      "naive": {{ "code": "…", "language": "python", "run_stdout": "", "run_ok": null }},
      "optimized": {{ "source": {{ "repo": "owner/name", "path": "…", "url": "…" }},
                      "code": "…", "language": "python", "note": "…", "is_self_impl": false }}
    }}
  ]
}}
```

For an architecture, decompose it into its meaningful components (e.g. a Transformer
block → attention, feed-forward, layer norm, residual) and give each all five views.
For a single technique, one component is enough.
"""
