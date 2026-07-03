"""End-to-end regression test over a real MCP stdio connection.

This reproduces the exact context that broke `run_python`: when nnlens runs
behind an MCP stdio pipe, a spawned child that inherits the parent's (pipe) stdin
deadlocked on Windows, so even `print(2+2)` "timed out". A normal pytest run has a
console/devnull stdin and does NOT reproduce it — only launching the server over
stdio does. Hence this test.
"""

import asyncio
import json
import sys

import pytest

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def _call_run_python() -> dict:
    params = StdioServerParameters(command=sys.executable, args=["-m", "nnlens"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool("run_python", {"code": "print(2 + 2)", "timeout": 10})
    payload = res.structuredContent
    if not payload:
        payload = json.loads(res.content[0].text)
    # FastMCP may wrap a dict return under a "result" key in structuredContent.
    if isinstance(payload, dict) and "ok" not in payload and "result" in payload:
        payload = payload["result"]
    return payload


def test_run_python_works_over_mcp_stdio():
    result = asyncio.run(_call_run_python())
    assert result.get("ok") is True, f"run_python failed over stdio: {result}"
    assert "4" in (result.get("stdout") or "")
