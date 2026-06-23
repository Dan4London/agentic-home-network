"""MCP server: network performance probes (latency / throughput)."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from agent.config import Settings
from probes.latency import measure_latency_batch
from probes.ssh_runner import SSHConfig

mcp = FastMCP("perf_probe")


def _ssh_config(settings: Settings) -> SSHConfig | None:
    if settings.use_mock_probes:
        return None
    return SSHConfig(
        host=settings.probe_host,
        user=settings.probe_user,
        password=settings.probe_password,
        key_path=settings.probe_ssh_key,
    )


@mcp.tool()
def measure_latency(targets: list[str] | None = None) -> str:
    """Measure ICMP latency from the LAN probe to one or more targets.

    Args:
        targets: Hostnames or IPs to ping. Defaults to configured LATENCY_TARGETS.
    """
    settings = Settings()
    results = measure_latency_batch(
        targets or settings.targets,
        ssh_config=_ssh_config(settings),
        mock=settings.use_mock_probes,
    )
    return json.dumps([r.model_dump(mode="json") for r in results], indent=2)


@mcp.tool()
def measure_throughput() -> str:
    """Placeholder for iperf3 throughput measurement (Phase 1+)."""
    return json.dumps(
        {
            "status": "not_implemented",
            "message": "Install iperf3 on the probe host to enable throughput tests.",
        }
    )


if __name__ == "__main__":
    mcp.run()
