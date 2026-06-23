from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class LatencyResult(BaseModel):
    target: str
    packets_sent: int
    packets_received: int
    packet_loss_pct: float
    rtt_min_ms: float | None = None
    rtt_avg_ms: float | None = None
    rtt_max_ms: float | None = None
    status: HealthStatus


class Metric(BaseModel):
    name: str
    value: float | str
    unit: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionType(str, Enum):
    NOTIFY = "notify"
    RATE_LIMIT = "rate_limit"
    BLOCK_DEVICE = "block_device"
    NONE = "none"


class Action(BaseModel):
    action_type: ActionType
    description: str
    target: str | None = None
    dry_run: bool = True
    approved: bool = False
    result: str | None = None


class Incident(BaseModel):
    id: str
    title: str
    summary: str
    severity: Severity
    category: str
    evidence: list[Metric] = Field(default_factory=list)
    recommended_action: Action | None = None
    root_cause: str | None = None


class AgentReport(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    overall_health: HealthStatus
    security_status: str = "clear"  # clear | alert
    latency_results: list[LatencyResult] = Field(default_factory=list)
    devices_on_lan: list[dict[str, Any]] = Field(default_factory=list)
    unknown_devices: list[dict[str, Any]] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    actions_taken: list[Action] = Field(default_factory=list)
    reasoning: str = ""
