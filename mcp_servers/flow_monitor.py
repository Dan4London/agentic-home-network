"""MCP server: active flow / connection visibility (Phase 2 stub)."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("flow_monitor")


@mcp.tool()
def list_active_flows() -> str:
    """List active network flows from the probe (stub — Phase 2)."""
    return json.dumps({"status": "not_implemented", "flows": []})


@mcp.tool()
def recent_destinations() -> str:
    """Recent external destinations seen by the probe (stub — Phase 2)."""
    return json.dumps({"status": "not_implemented", "destinations": []})


if __name__ == "__main__":
    mcp.run()
