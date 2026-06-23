from __future__ import annotations

import re
import uuid
from datetime import datetime

from agent.config import settings
from agent.policies import LATENCY_THRESHOLDS, classify_latency, severity_for_status
from agent.schemas import (
    Action,
    ActionType,
    AgentReport,
    HealthStatus,
    Incident,
    LatencyResult,
    Metric,
    Severity,
)
from agent.security import devices_to_dict, gather_security_metrics, security_incidents
from probes.latency import measure_latency_batch
from probes.ssh_runner import SSHConfig


def _ssh_config() -> SSHConfig:
    return SSHConfig(
        host=settings.probe_host,
        user=settings.probe_user,
        password=settings.probe_password,
        key_path=settings.probe_ssh_key,
    )


def gather_latency_metrics(targets: list[str] | None = None) -> list[LatencyResult]:
    return measure_latency_batch(
        targets or settings.targets,
        ssh_config=None if settings.use_mock_probes else _ssh_config(),
        mock=settings.use_mock_probes,
    )


def rule_based_report(
    results: list[LatencyResult],
    *,
    all_devices: list | None = None,
    unknown_devices: list | None = None,
) -> AgentReport:
    """Analyse probe results without an LLM."""
    perf_incidents: list[Incident] = []
    worst = HealthStatus.HEALTHY

    for result in results:
        status = classify_latency(result, LATENCY_THRESHOLDS)
        result.status = status
        if status == HealthStatus.DOWN:
            worst = HealthStatus.DOWN
        elif status == HealthStatus.DEGRADED and worst != HealthStatus.DOWN:
            worst = HealthStatus.DEGRADED

        if status != HealthStatus.HEALTHY:
            severity = severity_for_status(status)
            loss = result.packet_loss_pct
            rtt = result.rtt_avg_ms
            perf_incidents.append(
                Incident(
                    id=str(uuid.uuid4())[:8],
                    title=f"Latency issue to {result.target}",
                    summary=(
                        f"Probe to {result.target}: "
                        f"{loss:.0f}% packet loss, avg RTT {rtt:.1f} ms"
                        if rtt is not None
                        else f"Probe to {result.target}: {loss:.0f}% packet loss"
                    ),
                    severity=severity,
                    category="performance",
                    evidence=[
                        Metric(name="packet_loss_pct", value=loss, unit="%"),
                        Metric(name="rtt_avg_ms", value=rtt or 0, unit="ms"),
                    ],
                    root_cause=_guess_root_cause(result),
                    recommended_action=_suggest_action(result),
                )
            )

    sec_incidents = security_incidents(unknown_devices or [])
    incidents = perf_incidents + sec_incidents
    security_status = "alert" if sec_incidents else "clear"

    reasoning = _build_reasoning(
        results,
        worst,
        perf_incidents,
        all_devices=all_devices,
        unknown_devices=unknown_devices,
    )
    return AgentReport(
        overall_health=worst,
        security_status=security_status,
        latency_results=results,
        devices_on_lan=devices_to_dict(all_devices or []),
        unknown_devices=devices_to_dict(unknown_devices or []),
        incidents=incidents,
        reasoning=reasoning,
    )


def _guess_root_cause(result: LatencyResult) -> str:
    if result.packet_loss_pct >= 50:
        return "Target appears unreachable — check link, routing, or upstream ISP."
    if result.target.startswith("192.168.") or result.target.startswith("10."):
        return "LAN path degraded — check Wi-Fi, switch, or gateway load."
    return "WAN path degraded — possible ISP congestion or DNS/routing issue."


def _suggest_action(result: LatencyResult) -> Action:
    if result.packet_loss_pct >= 50:
        return Action(
            action_type=ActionType.NOTIFY,
            description=f"Alert: {result.target} unreachable from probe",
            target=result.target,
            dry_run=settings.dry_run,
        )
    return Action(
        action_type=ActionType.NOTIFY,
        description=f"Monitor {result.target} — performance degraded",
        target=result.target,
        dry_run=settings.dry_run,
    )


def _build_reasoning(
    results: list[LatencyResult],
    overall: HealthStatus,
    perf_incidents: list[Incident],
    *,
    all_devices: list | None = None,
    unknown_devices: list | None = None,
) -> str:
    lines = [f"Performance health: {overall.value}."]
    for r in results:
        rtt = f"{r.rtt_avg_ms:.1f} ms" if r.rtt_avg_ms is not None else "n/a"
        lines.append(
            f"  {r.target}: loss {r.packet_loss_pct:.0f}%, avg RTT {rtt} → {r.status.value}"
        )
    if perf_incidents:
        lines.append(f"{len(perf_incidents)} performance incident(s).")
    else:
        lines.append("All latency targets within policy thresholds.")

    device_count = len(all_devices or [])
    unknown_count = len(unknown_devices or [])
    if device_count:
        lines.append(f"\nSecurity: {device_count} device(s) on LAN, {unknown_count} unknown.")
    if unknown_count:
        lines.append("Unknown devices require review — see security incidents.")
    else:
        lines.append("All observed devices match the known_devices baseline.")
    return "\n".join(lines)


async def llm_enhanced_report(
    results: list[LatencyResult],
    base: AgentReport,
    *,
    all_devices: list | None = None,
    unknown_devices: list | None = None,
) -> AgentReport:
    """Optional LLM pass to enrich reasoning when API key is set."""
    import json

    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    from agent.prompts import REASONING_PROMPT, SYSTEM_PROMPT

    payload = {
        "latency": [r.model_dump(mode="json") for r in results],
        "devices_on_lan": base.devices_on_lan,
        "unknown_devices": base.unknown_devices,
    }
    llm = ChatAnthropic(model="claude-sonnet-4-20250514", temperature=0)
    response = await llm.ainvoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=REASONING_PROMPT.format(metrics_json=json.dumps(payload, indent=2))),
        ]
    )
    base.reasoning = str(response.content)
    return base
