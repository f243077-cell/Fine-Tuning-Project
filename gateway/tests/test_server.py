"""MCP-level tests: an in-process MCP client sees only the allowlisted tools; poisoned notes come back redacted."""

import asyncio
import json

from mcp import Client

from gateway.server import build_server
from gateway.tests.test_gateway import FakeGuard
from gateway.tools import default_gateway


def text_of(result) -> str:  # type: ignore[no-untyped-def]
    """Concatenated text content of a tool result."""
    return "".join(getattr(c, "text", "") for c in result.content)


def is_error(result) -> bool:  # type: ignore[no-untyped-def]
    """Tool-error flag across SDK naming styles."""
    return bool(getattr(result, "is_error", None) or getattr(result, "isError", None))


def test_mcp_lists_only_allowlisted_tools_and_redacts() -> None:
    """list_tools has exactly three tools; get_note on a poisoned Roman Urdu note is redacted."""
    async def run() -> None:
        async with Client(build_server(default_gateway(FakeGuard()))) as c:
            tools = await c.list_tools()
            assert sorted(t.name for t in tools.tools) == ["get_note", "scan_text", "search_docs"]
            res = await c.call_tool("get_note", {"id": "note-2"})
            body = json.loads(text_of(res))
            assert body["redacted"] and "PINEAPPLE" not in body["result"]
            clean = json.loads(text_of(await c.call_tool("get_note", {"id": "note-4"})))
            assert not clean["redacted"] and "Shams lantern" in clean["result"]

    asyncio.run(run())


def test_mcp_refuses_unknown_tool_and_bad_args() -> None:
    """A non-allowlisted tool and an invalid note id both come back as tool errors."""
    async def run() -> None:
        async with Client(build_server(default_gateway(FakeGuard()))) as c:
            unknown = await c.call_tool("delete_all_orders", {})
            assert is_error(unknown)
            bad = await c.call_tool("get_note", {"id": "../../.env"})
            assert is_error(bad) and "invalid arguments" in text_of(bad)

    asyncio.run(run())
