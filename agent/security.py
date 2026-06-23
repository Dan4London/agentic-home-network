"""Security analysis: unknown devices and LAN inventory."""

from __future__ import annotations

import uuid
from dataclasses import asdict

from agent.config import settings
from agent.schemas import Action, ActionType, Incident, Metric, Severity
from probes.device_baseline import security_snapshot
from probes.device_identity import DeviceIdentity


def gather_security_metrics() -> tuple[list[DeviceIdentity], list[DeviceIdentity]]:
    return security_snapshot()


def security_incidents(unknown: list[DeviceIdentity]) -> list[Incident]:
    incidents: list[Incident] = []
    for device in unknown:
        label = device.suggested_name()
        identity_hint = _describe_device(device)
        incidents.append(
            Incident(
                id=str(uuid.uuid4())[:8],
                title=f"Unknown device on LAN: {label}",
                summary=(
                    f"Unrecognised device at {device.ip} (MAC {device.mac}). {identity_hint}"
                ),
                severity=Severity.WARNING,
                category="security",
                evidence=[
                    Metric(name="ip", value=device.ip),
                    Metric(name="mac", value=device.mac),
                    Metric(name="hostname", value=device.hostname or "unknown"),
                    Metric(name="vendor", value=device.vendor or "unknown"),
                ],
                root_cause=(
                    "Device MAC is not in the known_devices baseline. "
                    "Could be a new guest, IoT gadget, or unauthorised join."
                ),
                recommended_action=Action(
                    action_type=ActionType.NOTIFY,
                    description=f"Review unknown device {device.ip} ({device.mac})",
                    target=device.ip,
                    dry_run=settings.dry_run,
                ),
            )
        )
    return incidents


def _describe_device(device: DeviceIdentity) -> str:
    parts: list[str] = []
    if device.hostname:
        parts.append(f"Hostname: {device.hostname}")
    if device.vendor:
        parts.append(f"Vendor: {device.vendor}")
    if device.device_type:
        parts.append(f"Type: {device.device_type}")
    if device.notes:
        parts.append(device.notes)
    return " ".join(parts) if parts else "Could not identify device type."


def devices_to_dict(devices: list[DeviceIdentity]) -> list[dict]:
    return [asdict(d) for d in devices]
