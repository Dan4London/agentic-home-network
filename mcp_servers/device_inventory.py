"""MCP server: device inventory and baseline diff."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from agent.config import Settings
from probes.device_baseline import known_mac_addresses
from probes.device_identity import discover_devices, identities_to_yaml_records, list_lan_devices

mcp = FastMCP("device_inventory")


@mcp.tool()
def list_devices() -> str:
    """List devices visible on the LAN via the probe's neighbour table."""
    devices = list_lan_devices(Settings())
    return json.dumps({"devices": devices}, indent=2)


@mcp.tool()
def identify_devices() -> str:
    """Discover and identify LAN devices (MAC OUI, DNS, mDNS, HTTP banner)."""
    identities = discover_devices(Settings())
    return json.dumps(identities_to_yaml_records(identities), indent=2)


@mcp.tool()
def diff_against_known() -> str:
    """Compare live devices against the known-devices allow-list."""
    live = json.loads(list_devices())
    known_macs = known_mac_addresses()
    unknown = [d for d in live.get("devices", []) if d.get("mac", "").lower() not in known_macs]
    return json.dumps({"unknown_devices": unknown, "known_count": len(known_macs)}, indent=2)


if __name__ == "__main__":
    mcp.run()
