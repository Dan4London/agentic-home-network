"""LangGraph control loop: perceive → reason → decide → act → observe."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import TypedDict

from langgraph.graph import END, StateGraph

from agent.actuator import execute_action, propose_action, should_auto_execute
from agent.analyzer import gather_latency_metrics, llm_enhanced_report, rule_based_report
from agent.config import settings
from agent.schemas import Action, AgentReport, LatencyResult
from agent.security import gather_security_metrics
from probes.device_identity import DeviceIdentity


class AgentState(TypedDict):
    targets: list[str]
    latency_results: list[dict]
    all_devices: list[dict]
    unknown_devices: list[dict]
    pending_actions: list[dict]
    report: dict
    use_mcp: bool
    skip_security: bool
    enable_act: bool
    approve_all: bool
    allow_block: bool
    interactive: bool
    step: str


async def _call_mcp_latency(targets: list[str]) -> list[LatencyResult]:
    """Gather metrics via MCP perf_probe server."""
    from langchain_mcp_adapters.client import MultiServerMCPClient

    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    python = sys.executable

    client = MultiServerMCPClient(
        {
            "perf_probe": {
                "command": python,
                "args": [str(root / "mcp_servers" / "perf_probe.py")],
                "transport": "stdio",
            }
        }
    )
    tools = await client.get_tools()
    tool = next(t for t in tools if t.name == "measure_latency")
    raw = await tool.ainvoke({"targets": targets})
    data = json.loads(raw) if isinstance(raw, str) else raw
    return [LatencyResult.model_validate(item) for item in data]


async def perceive(state: AgentState) -> AgentState:
    targets = state.get("targets") or settings.targets
    if state.get("use_mcp", True):
        try:
            results = await _call_mcp_latency(targets)
        except Exception:
            results = gather_latency_metrics(targets)
    else:
        results = gather_latency_metrics(targets)

    all_devices: list[DeviceIdentity] = []
    unknown_devices: list[DeviceIdentity] = []
    if not state.get("skip_security", False):
        all_devices, unknown_devices = gather_security_metrics()

    return {
        **state,
        "latency_results": [r.model_dump(mode="json") for r in results],
        "all_devices": [asdict(d) for d in all_devices],
        "unknown_devices": [asdict(d) for d in unknown_devices],
        "step": "perceive",
    }


async def reason(state: AgentState) -> AgentState:
    results = [LatencyResult.model_validate(r) for r in state["latency_results"]]
    all_devices = [DeviceIdentity(**d) for d in state.get("all_devices", [])]
    unknown_devices = [DeviceIdentity(**d) for d in state.get("unknown_devices", [])]

    report = rule_based_report(
        results,
        all_devices=all_devices,
        unknown_devices=unknown_devices,
    )

    if settings.has_llm:
        try:
            report = await llm_enhanced_report(
                results,
                report,
                all_devices=all_devices,
                unknown_devices=unknown_devices,
            )
        except Exception:
            pass

    return {
        **state,
        "report": report.model_dump(mode="json"),
        "step": "reason",
    }


async def decide(state: AgentState) -> AgentState:
    """Collect recommended actions from incidents; enrich security with block proposals."""
    from agent.schemas import ActionType

    report = AgentReport.model_validate(state["report"])
    pending: list[Action] = []
    for incident in report.incidents:
        if incident.recommended_action:
            pending.append(incident.recommended_action)
        if (
            state.get("enable_act")
            and incident.category == "security"
            and incident.severity.value in {"warning", "critical"}
        ):
            target_ip = next((e.value for e in incident.evidence if e.name == "ip"), None)
            if target_ip:
                pending.append(
                    Action(
                        action_type=ActionType.BLOCK_DEVICE,
                        description=f"Block unknown device pending review ({incident.title})",
                        target=str(target_ip),
                        dry_run=settings.dry_run,
                    )
                )
    return {**state, "pending_actions": [a.model_dump(mode="json") for a in pending], "step": "decide"}


async def act(state: AgentState) -> AgentState:
    """Propose and optionally execute guarded remediations."""
    report = AgentReport.model_validate(state["report"])
    taken: list[Action] = []

    for raw in state.get("pending_actions", []):
        action = Action.model_validate(raw)
        proposal = propose_action(action)

        if not state.get("enable_act", False):
            action.result = f"Not executed (report-only): {proposal.message}"
            taken.append(action)
            continue

        approved = False
        if state.get("interactive", True):
            prompt = f"Approve {action.action_type.value} on {action.target}? [y/N] "
            answer = await asyncio.to_thread(input, prompt)
            approved = answer.strip().lower() in {"y", "yes"}
        elif should_auto_execute(
            action,
            approve_all=state.get("approve_all", False),
            allow_block=state.get("allow_block", False),
        ):
            approved = True

        if not approved:
            action.result = "Declined or skipped — no changes made"
            taken.append(action)
            continue

        result = execute_action(action, approved=True)
        action.approved = True
        action.dry_run = result.dry_run
        action.result = result.message
        taken.append(action)

    report.actions_taken = taken
    return {**state, "report": report.model_dump(mode="json"), "step": "act"}


async def observe(state: AgentState) -> AgentState:
    return {**state, "step": "observe"}


def _route_after_reason(state: AgentState) -> str:
    if state.get("enable_act", False):
        return "decide"
    return "observe"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("perceive", perceive)
    graph.add_node("reason", reason)
    graph.add_node("decide", decide)
    graph.add_node("act", act)
    graph.add_node("observe", observe)
    graph.set_entry_point("perceive")
    graph.add_edge("perceive", "reason")
    graph.add_conditional_edges("reason", _route_after_reason, {"decide": "decide", "observe": "observe"})
    graph.add_edge("decide", "act")
    graph.add_edge("act", "observe")
    graph.add_edge("observe", END)
    return graph.compile()


async def run_agent(
    targets: list[str] | None = None,
    use_mcp: bool = True,
    skip_security: bool = False,
    *,
    enable_act: bool = False,
    approve_all: bool = False,
    allow_block: bool = False,
    interactive: bool = False,
) -> AgentReport:
    app = build_graph()
    final = await app.ainvoke(
        {
            "targets": targets or settings.targets,
            "latency_results": [],
            "all_devices": [],
            "unknown_devices": [],
            "pending_actions": [],
            "report": {},
            "use_mcp": use_mcp,
            "skip_security": skip_security,
            "enable_act": enable_act,
            "approve_all": approve_all,
            "allow_block": allow_block,
            "interactive": interactive,
            "step": "start",
        }
    )
    return AgentReport.model_validate(final["report"])
