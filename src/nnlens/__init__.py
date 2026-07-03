"""nnlens — explain neural-network components in five linked views.

The package ships an MCP server (``nnlens.server``) whose tools are driven by
the *host* LLM (i.e. the user's own Claude / Codex / Cursor subscription). The
server itself never calls an LLM: it only fetches sources, executes code, and
renders the assembled explanation to a local web page.
"""

__version__ = "0.1.0"
