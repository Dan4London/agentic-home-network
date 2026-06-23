#!/usr/bin/env python3
"""Smoke-test MCP servers: list tools and call one per server (no LLM required)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


SERVERS = {
    "perf_probe": {
        "command": PYTHON,
        "args": [str(ROOT / "mcp_servers" / "perf_probe.py")],
        "transport": "stdio",
        "env": {"USE_MOCK_PROBES": "true"},
    },
    "device_inventory": {
        "command": PYTHON,
        "args": [str(ROOT / "mcp_servers" / "device_inventory.py")],
        "transport": "stdio",
    },
    "actuator": {
        "command": PYTHON,
        "args": [str(ROOT / "mcp_servers" / "actuator.py")],
        "transport": "stdio",
        "env": {"DRY_RUN": "true"},
    },
}


async def main() -> None:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    client = MultiServerMCPClient(SERVERS)
    tools = await client.get_tools()

    print(f"Connected — {len(tools)} tool(s):\n")
    for t in tools:
        print(f"  • {t.name}: {t.description[:80] if t.description else ''}")

    print("\n--- sample calls ---\n")

    by_name = {t.name: t for t in tools}

    if "measure_latency" in by_name:
        raw = await by_name["measure_latency"].ainvoke({})
        print("measure_latency →")
        text = raw if isinstance(raw, str) else json.dumps(raw, indent=2)
        print(text[:500])

    if "propose_action_tool" in by_name:
        raw = await by_name["propose_action_tool"].ainvoke(
            {
                "action_type": "notify",
                "description": "Smoke test alert",
                "target": "192.168.1.1",
            }
        )
        print("\npropose_action_tool →")
        print(raw)

    if "diff_against_known" in by_name:
        raw = await by_name["diff_against_known"].ainvoke({})
        print("\ndiff_against_known →")
        print(raw[:400])


if __name__ == "__main__":
    asyncio.run(main())
