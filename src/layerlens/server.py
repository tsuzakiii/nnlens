"""The layerlens MCP server.

The host LLM (the user's own Claude/Codex/Cursor subscription) drives these tools;
the server never calls an LLM itself. Tools cover the deterministic work — fetching
sources, running code, and rendering — while the ``explain`` prompt tells the host
how to assemble the five linked views.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import config, sources
from .lint import lint_explanation
from .models import Explanation
from .prompts import EXPLAIN_PROMPT
from .renderer import ensure_server, reconcile_index, update_index, write_explanation
from .sandbox import run_python as _run_python

mcp = FastMCP("layerlens")


# --- retrieval -------------------------------------------------------------


@mcp.tool()
def fetch_paper(query: str) -> dict:
    """Resolve an arXiv id, url, or free-text query to a paper's title, abstract, and url."""
    return sources.fetch_paper(query)


@mcp.tool()
def find_official_repo(name: str) -> dict:
    """Search GitHub for candidate official repositories for a technique/architecture."""
    return sources.find_official_repo(name)


@mcp.tool()
def fetch_repo_code(full_name: str, path: str, ref: str = "HEAD") -> dict:
    """Fetch a single source file from a GitHub repo (e.g. for the optimized view)."""
    return sources.fetch_repo_code(full_name, path, ref)


# --- verification ----------------------------------------------------------


@mcp.tool()
def run_python(code: str, timeout: float = 15.0) -> dict:
    """Execute a Python snippet and capture stdout/stderr.

    Use this to *prove* the naive (view 4) implementation runs: put the returned
    ``stdout`` into ``naive.run_stdout`` and ``ok`` into ``naive.run_ok``.
    """
    return _run_python(code, timeout=timeout)


# --- rendering -------------------------------------------------------------


@mcp.tool()
def render(explanation: dict) -> dict:
    """Validate a full Explanation object, render it to a local web page, and return its URL.

    ``explanation`` must match the layerlens Explanation schema (see the ``explain``
    prompt). On success returns ``{"url", "path", "components"}``; on a schema error
    returns ``{"error", "detail"}`` so the host can fix and retry.
    """
    try:
        ex = Explanation.model_validate(explanation)
    except Exception as exc:  # noqa: BLE001 — surface validation errors to the host
        return {"error": "validation_failed", "detail": str(exc)}
    store = config.store_dir()
    path = write_explanation(ex.model_dump(), store, ex.slug())
    update_index(store, ex.slug(), ex.title, ex.kind)
    port = ensure_server(store, start_port=config.start_port())
    return {
        "url": f"http://127.0.0.1:{port}/e/{ex.slug()}.html",
        "path": path,
        "components": [c.name for c in ex.components],
        # Contract lint (never blocking): fix these and re-render, or justify them.
        "warnings": lint_explanation(ex),
    }


@mcp.tool()
def explanation_schema() -> dict:
    """Return the JSON schema for an Explanation (handy for the host to self-check)."""
    return Explanation.model_json_schema()


@mcp.tool()
def list_library() -> dict:
    """Return every explanation in the local library ({slug, title, kind} each).

    Call this before writing ``related`` refs or ``[[slug]]`` wikilinks so the
    host knows which slugs already exist in the store.
    """
    try:
        return {"explanations": reconcile_index(config.store_dir())}
    except Exception as exc:  # noqa: BLE001 — a filesystem hiccup must not kill the tool
        return {"explanations": [], "error": "list_library_failed", "detail": str(exc)}


# --- prompt ----------------------------------------------------------------


@mcp.prompt()
def explain(topic: str) -> str:
    """Produce a five-view layerlens explanation of a neural-network topic."""
    return EXPLAIN_PROMPT.format(topic=topic)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
