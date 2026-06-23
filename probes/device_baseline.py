"""Baseline allow-list and unknown-device detection."""

from __future__ import annotations

from pathlib import Path

import yaml

from probes.device_identity import DeviceIdentity, discover_devices

BASELINE_PATH = Path(__file__).resolve().parent.parent / "baseline" / "known_devices.yaml"


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {"devices": []}
    return yaml.safe_load(BASELINE_PATH.read_text()) or {"devices": []}


def known_mac_addresses() -> set[str]:
    baseline = load_baseline()
    return {d["mac"].lower() for d in baseline.get("devices", []) if d.get("mac")}


def diff_unknown_devices(identities: list[DeviceIdentity]) -> list[DeviceIdentity]:
    known = known_mac_addresses()
    return [d for d in identities if d.mac.lower() not in known]


def security_snapshot() -> tuple[list[DeviceIdentity], list[DeviceIdentity]]:
    """Return (all_devices, unknown_devices)."""
    all_devices = discover_devices()
    unknown = diff_unknown_devices(all_devices)
    return all_devices, unknown
