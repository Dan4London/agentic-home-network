from __future__ import annotations

from dataclasses import dataclass

from agent.schemas import HealthStatus, LatencyResult, Severity, ActionType


@dataclass(frozen=True)
class LatencyThresholds:
    """Latency policy thresholds (milliseconds)."""

    degraded_rtt_ms: float = 50.0
    critical_rtt_ms: float = 200.0
    degraded_loss_pct: float = 5.0
    critical_loss_pct: float = 50.0


LATENCY_THRESHOLDS = LatencyThresholds()


def classify_latency(result: LatencyResult, thresholds: LatencyThresholds = LATENCY_THRESHOLDS) -> HealthStatus:
    if result.packet_loss_pct >= thresholds.critical_loss_pct:
        return HealthStatus.DOWN
    if result.rtt_avg_ms is not None and result.rtt_avg_ms >= thresholds.critical_rtt_ms:
        return HealthStatus.DOWN
    if result.packet_loss_pct >= thresholds.degraded_loss_pct:
        return HealthStatus.DEGRADED
    if result.rtt_avg_ms is not None and result.rtt_avg_ms >= thresholds.degraded_rtt_ms:
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY


def severity_for_status(status: HealthStatus) -> Severity:
    if status == HealthStatus.DOWN:
        return Severity.CRITICAL
    if status == HealthStatus.DEGRADED:
        return Severity.WARNING
    return Severity.INFO


ALLOWED_ACTIONS: frozenset[str] = frozenset({"notify", "rate_limit", "block_device"})

# Safe to run with --approve (no network mutation when DRY_RUN=true)
AUTO_EXECUTABLE_ACTIONS: frozenset[ActionType] = frozenset({ActionType.NOTIFY})

# Never auto-run without --allow-block
DESTRUCTIVE_ACTIONS: frozenset[ActionType] = frozenset({ActionType.BLOCK_DEVICE, ActionType.RATE_LIMIT})


def action_allowed(action_type: str) -> bool:
    return action_type in ALLOWED_ACTIONS
