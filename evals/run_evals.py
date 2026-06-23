"""Grade the rule-based agent against scripted scenarios."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from agent.analyzer import rule_based_report
from agent.schemas import HealthStatus, LatencyResult
from probes.device_identity import DeviceIdentity

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"
PASS_THRESHOLD = 0.80


@dataclass
class ScenarioResult:
    name: str
    passed: bool
    score: float
    checks: list[str]
    failures: list[str]


def _latency_from_dict(raw: dict) -> LatencyResult:
    return LatencyResult(
        target=raw["target"],
        packets_sent=raw.get("packets_sent", 3),
        packets_received=raw.get("packets_received", 3 if raw.get("packet_loss_pct", 0) < 100 else 0),
        packet_loss_pct=float(raw["packet_loss_pct"]),
        rtt_min_ms=raw.get("rtt_min_ms"),
        rtt_avg_ms=raw.get("rtt_avg_ms"),
        rtt_max_ms=raw.get("rtt_max_ms"),
        status=HealthStatus(raw.get("status", "healthy")),
    )


def _device_from_dict(raw: dict) -> DeviceIdentity:
    return DeviceIdentity(
        ip=raw["ip"],
        mac=raw["mac"],
        state=raw.get("state", "REACHABLE"),
        hostname=raw.get("hostname"),
        vendor=raw.get("vendor"),
        device_type=raw.get("device_type"),
        identification_methods=raw.get("identification_methods", []),
        notes=raw.get("notes"),
        confidence=raw.get("confidence", "low"),
    )


def run_scenario(path: Path) -> ScenarioResult:
    data = json.loads(path.read_text())
    name = data.get("name", path.stem)
    inp = data["input"]
    expected = data["expected"]

    latency = [_latency_from_dict(r) for r in inp.get("latency_results", [])]
    unknown = [_device_from_dict(d) for d in inp.get("unknown_devices", [])]
    all_devices = [_device_from_dict(d) for d in inp.get("all_devices", [])]

    report = rule_based_report(latency, all_devices=all_devices, unknown_devices=unknown)

    checks: list[str] = []
    failures: list[str] = []
    points = 0.0
    total = 0.0

    def check(label: str, ok: bool, weight: float = 1.0) -> None:
        nonlocal points, total
        total += weight
        if ok:
            points += weight
            checks.append(f"✓ {label}")
        else:
            failures.append(f"✗ {label}")

    if "overall_health" in expected:
        check(
            f"overall_health={expected['overall_health']}",
            report.overall_health.value == expected["overall_health"],
            weight=2.0,
        )

    if "security_status" in expected:
        check(
            f"security_status={expected['security_status']}",
            report.security_status == expected["security_status"],
            weight=2.0,
        )

    if "incident_count" in expected:
        check(
            f"incident_count={expected['incident_count']}",
            len(report.incidents) == expected["incident_count"],
            weight=2.0,
        )

    if "min_incident_count" in expected:
        check(
            f"min_incident_count>={expected['min_incident_count']}",
            len(report.incidents) >= expected["min_incident_count"],
            weight=1.0,
        )

    if "categories" in expected:
        actual_cats = {i.category for i in report.incidents}
        for cat in expected["categories"]:
            check(f"has_{cat}_incident", cat in actual_cats, weight=1.5)

    if "severities" in expected:
        actual_sev = {i.severity.value for i in report.incidents}
        for sev in expected["severities"]:
            check(f"has_{sev}_severity", sev in actual_sev, weight=1.0)

    if "action_types" in expected:
        actual_actions = {
            i.recommended_action.action_type.value
            for i in report.incidents
            if i.recommended_action
        }
        for at in expected["action_types"]:
            check(f"recommends_{at}", at in actual_actions, weight=1.0)

    if "unknown_count" in expected:
        check(
            f"unknown_count={expected['unknown_count']}",
            len(report.unknown_devices) == expected["unknown_count"],
            weight=1.0,
        )

    if "root_cause_contains" in expected:
        text = " ".join(i.root_cause or "" for i in report.incidents).lower()
        for phrase in expected["root_cause_contains"]:
            check(f"root_cause mentions '{phrase}'", phrase.lower() in text, weight=1.0)

    score = points / total if total else 1.0
    return ScenarioResult(
        name=name,
        passed=score >= PASS_THRESHOLD and not failures,
        score=score,
        checks=checks,
        failures=failures,
    )


def run_all(scenarios_dir: Path = SCENARIOS_DIR) -> list[ScenarioResult]:
    paths = sorted(scenarios_dir.glob("*.json"))
    return [run_scenario(p) for p in paths]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run agent eval scenarios")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    parser.add_argument("--scenario", help="Run a single scenario by name")
    args = parser.parse_args()

    if args.scenario:
        path = SCENARIOS_DIR / f"{args.scenario}.json"
        results = [run_scenario(path)]
    else:
        results = run_all()

    avg = sum(r.score for r in results) / len(results) if results else 0.0
    passed = sum(1 for r in results if r.passed)

    if args.json:
        print(
            json.dumps(
                {
                    "passed": passed,
                    "total": len(results),
                    "average_score": round(avg, 3),
                    "pass_threshold": PASS_THRESHOLD,
                    "results": [
                        {
                            "name": r.name,
                            "passed": r.passed,
                            "score": round(r.score, 3),
                            "failures": r.failures,
                        }
                        for r in results
                    ],
                },
                indent=2,
            )
        )
        return

    print("=" * 60)
    print("AGENT EVAL RESULTS")
    print("=" * 60)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"\n[{status}] {r.name}  ({r.score:.0%})")
        for line in r.checks:
            print(f"  {line}")
        for line in r.failures:
            print(f"  {line}")
    print()
    print(f"Summary: {passed}/{len(results)} passed  |  avg score {avg:.0%}  |  threshold {PASS_THRESHOLD:.0%}")
    print("=" * 60)


if __name__ == "__main__":
    main()
