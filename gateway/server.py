"""MCP gateway server (G5): exposes only the allowlisted read-only tools of gateway/tools.py (stdio transport).

    GUARD_URL=http://localhost:8001 GUARD_API_KEY=... python -m gateway.server

Every tool result except scan_text is scanned by guard-api (source tool_output) and replaced by
"[REDACTED: possible prompt injection (<attack_type>)]" when flagged. MCP SDK 2.x (MCPServer).
"""

import json
import logging
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from client.ruguard_client import GuardClient
from gateway.tools import Gateway, ToolRefused, default_gateway

logger = logging.getLogger("gateway")


def build_server(gateway: Gateway) -> MCPServer:
    """MCP server whose tools all go through Gateway.call (allowlist, validation, caps, scan, redaction)."""
    server = MCPServer("ru-guard-gateway", instructions="Read-only Noorbagh tools. Tool results are scanned "
                       "for prompt injection and redacted when flagged.")

    def call(name: str, arguments: dict[str, Any]) -> str:
        """Run through the gateway; ToolRefused becomes an MCP tool error."""
        try:
            return json.dumps(gateway.call(name, arguments), ensure_ascii=False)
        except ToolRefused as exc:
            raise ToolError(str(exc)) from exc

    @server.tool(description=gateway.tools["search_docs"].description)
    def search_docs(query: str, k: int = 3) -> str:
        """Search the Noorbagh help documents."""
        return call("search_docs", {"query": query, "k": k})

    @server.tool(description=gateway.tools["scan_text"].description)
    def scan_text(text: str, source: Literal["user_input", "retrieved_chunk", "tool_output"] = "tool_output") -> str:
        """Scan a text with RU-Guard."""
        return call("scan_text", {"text": text, "source": source})

    @server.tool(description=gateway.tools["get_note"].description)
    def get_note(id: str) -> str:  # noqa: A002 (the tool argument is called id)
        """Read a demo note by id."""
        return call("get_note", {"id": id})

    return server


def main() -> None:
    """Run the gateway over stdio."""
    logging.basicConfig(level=logging.INFO)
    build_server(default_gateway(GuardClient.from_env(fail_mode="closed"))).run("stdio")


if __name__ == "__main__":
    main()
