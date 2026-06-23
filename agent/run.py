"""CLI entry point for the home-network ops agent."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os

from agent.config import settings
from agent.graph import run_agent

logging.getLogger("paramiko").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic home-network operations agent")
    parser.add_argument(
        "--targets",
        help="Comma-separated ping targets (overrides LATENCY_TARGETS)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use static mock probe data (no SSH)",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Call probes directly instead of via MCP server",
    )
    parser.add_argument(
        "--skip-security",
        action="store_true",
        help="Skip LAN device inventory and unknown-device checks",
    )
    parser.add_argument(
        "--act",
        action="store_true",
        help="Run closed-loop act phase (propose → confirm → execute)",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Auto-approve safe actions (notify); use with --act",
    )
    parser.add_argument(
        "--allow-block",
        action="store_true",
        help="Allow block_device/rate_limit when used with --approve",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt before each action (with --act)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON report",
    )
    args = parser.parse_args()

    if args.mock:
        os.environ["USE_MOCK_PROBES"] = "true"
        settings.use_mock_probes = True

    targets = None
    if args.targets:
        targets = [t.strip() for t in args.targets.split(",")]

    report = asyncio.run(
        run_agent(
            targets=targets,
            use_mcp=not args.no_mcp,
            skip_security=args.skip_security,
            enable_act=args.act,
            approve_all=args.approve,
            allow_block=args.allow_block,
            interactive=args.interactive,
        )
    )

    if args.json:
        print(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
        return

    print("=" * 60)
    print("HOME NETWORK OPS AGENT — INCIDENT REPORT")
    print("=" * 60)
    print(f"Overall health : {report.overall_health.value}")
    print(f"Security status: {report.security_status}")
    print(f"Probe host     : {settings.probe_host}")
    print()
    print("Latency probes:")
    for r in report.latency_results:
        rtt = f"{r.rtt_avg_ms:.1f} ms" if r.rtt_avg_ms is not None else "n/a"
        print(f"  {r.target:16s}  loss {r.packet_loss_pct:5.1f}%  rtt {rtt:>8s}  [{r.status.value}]")
    print()
    if report.devices_on_lan:
        unknown_macs = {d["mac"] for d in report.unknown_devices}
        print(f"LAN devices ({len(report.devices_on_lan)}):")
        for d in report.devices_on_lan:
            name = d.get("hostname") or d.get("device_type") or "unknown"
            tag = "UNKNOWN" if d["mac"] in unknown_macs else "known"
            print(f"  {d['ip']:16s}  {d['mac']}  {name}  [{tag}]")
        print()
    print("Reasoning:")
    print(report.reasoning)
    print()
    if report.incidents:
        perf = [i for i in report.incidents if i.category == "performance"]
        sec = [i for i in report.incidents if i.category == "security"]
        if perf:
            print(f"Performance incidents ({len(perf)}):")
            for inc in perf:
                _print_incident(inc)
        if sec:
            print(f"Security incidents ({len(sec)}):")
            for inc in sec:
                _print_incident(inc)
    else:
        print("No incidents — network within policy thresholds.")
    if report.actions_taken:
        print()
        print(f"Actions taken ({len(report.actions_taken)}):")
        for action in report.actions_taken:
            status = "approved" if action.approved else "skipped"
            dry = " [dry-run]" if action.dry_run else ""
            print(f"  [{status}]{dry} {action.action_type.value} → {action.target}")
            if action.result:
                print(f"    {action.result}")
    print("=" * 60)


def _print_incident(inc) -> None:
    print(f"  [{inc.severity.value}] {inc.title}")
    print(f"    {inc.summary}")
    if inc.root_cause:
        print(f"    Root cause: {inc.root_cause}")
    if inc.recommended_action:
        print(f"    Action: {inc.recommended_action.description}")


if __name__ == "__main__":
    main()
