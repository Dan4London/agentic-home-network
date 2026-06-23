"""Guarded remediation: propose → confirm → act with rollback hints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from agent.config import settings
from agent.policies import (
    ALLOWED_ACTIONS,
    AUTO_EXECUTABLE_ACTIONS,
    DESTRUCTIVE_ACTIONS,
    action_allowed,
)
from agent.schemas import Action, ActionType
from probes.ssh_runner import SSHConfig, run_remote_command

VAR_DIR = Path(__file__).resolve().parent.parent / "var"
NOTIFICATIONS_LOG = VAR_DIR / "notifications.jsonl"
BLOCKS_FILE = VAR_DIR / "blocked_devices.json"
ACTION_LOG = VAR_DIR / "action_log.jsonl"


class ActionResult:
    def __init__(
        self,
        *,
        success: bool,
        message: str,
        dry_run: bool,
        rollback_hint: str | None = None,
    ):
        self.success = success
        self.message = message
        self.dry_run = dry_run
        self.rollback_hint = rollback_hint


def _ensure_var_dir() -> None:
    VAR_DIR.mkdir(parents=True, exist_ok=True)


def _ssh() -> SSHConfig:
    return SSHConfig(
        host=settings.probe_host,
        user=settings.probe_user,
        password=settings.probe_password,
        key_path=settings.probe_ssh_key,
    )


def _log_action(action: Action, result: ActionResult) -> None:
    _ensure_var_dir()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action_type": action.action_type.value,
        "target": action.target,
        "description": action.description,
        "approved": action.approved,
        "dry_run": result.dry_run,
        "success": result.success,
        "message": result.message,
    }
    with ACTION_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def propose_action(action: Action) -> ActionResult:
    """Dry-run preview — never mutates network state."""
    if not action_allowed(action.action_type.value):
        return ActionResult(success=False, message=f"Action '{action.action_type.value}' not allow-listed", dry_run=True)

    preview = _preview(action)
    return ActionResult(
        success=True,
        message=f"Proposed: {preview}",
        dry_run=True,
        rollback_hint=_rollback_hint(action),
    )


def execute_action(action: Action, *, approved: bool) -> ActionResult:
    """Execute a guarded action. Requires approved=True."""
    if not action_allowed(action.action_type.value):
        return ActionResult(success=False, message="Action not allow-listed", dry_run=settings.dry_run)

    if not approved:
        return ActionResult(success=False, message="Refused: human approval required", dry_run=True)

    proposal = propose_action(action)
    if not proposal.success:
        return proposal

    if settings.dry_run:
        result = ActionResult(
            success=True,
            message=f"DRY_RUN: would execute — {proposal.message}",
            dry_run=True,
            rollback_hint=proposal.rollback_hint,
        )
        _log_action(action, result)
        return result

    if action.action_type == ActionType.NOTIFY:
        result = _execute_notify(action)
    elif action.action_type == ActionType.BLOCK_DEVICE:
        result = _execute_block(action)
    elif action.action_type == ActionType.RATE_LIMIT:
        result = _execute_rate_limit(action)
    else:
        result = ActionResult(success=False, message="Unknown action type", dry_run=False)

    _log_action(action, result)
    return result


def _preview(action: Action) -> str:
    target = action.target or "n/a"
    if action.action_type == ActionType.NOTIFY:
        return f"send operator alert about {target}"
    if action.action_type == ActionType.BLOCK_DEVICE:
        return f"block LAN traffic from {target} at probe (iptables FORWARD DROP)"
    if action.action_type == ActionType.RATE_LIMIT:
        return f"rate-limit traffic from {target} at probe (iptables hashlimit)"
    return action.description


def _rollback_hint(action: Action) -> str | None:
    target = action.target or ""
    if action.action_type == ActionType.BLOCK_DEVICE:
        return f"Run rollback_block(target='{target}') or delete var/blocked_devices.json entry"
    if action.action_type == ActionType.RATE_LIMIT:
        return f"Remove iptables hashlimit rule for {target} on probe"
    return None


def _execute_notify(action: Action) -> ActionResult:
    _ensure_var_dir()
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": action.target,
        "message": action.description,
    }
    with NOTIFICATIONS_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return ActionResult(
        success=True,
        message=f"Notification logged for {action.target}",
        dry_run=False,
    )


def _execute_block(action: Action) -> ActionResult:
    target = action.target
    if not target:
        return ActionResult(success=False, message="block_device requires a target IP", dry_run=False)

    rule = f"iptables -C FORWARD -s {target} -j DROP 2>/dev/null || iptables -A FORWARD -s {target} -j DROP"
    code, out, err = run_remote_command(_ssh(), f"sudo {rule}")
    if code != 0:
        return ActionResult(
            success=False,
            message=f"iptables block failed (sudo may be required on probe): {err or out}",
            dry_run=False,
            rollback_hint=_rollback_hint(action),
        )

    _ensure_var_dir()
    blocks: list[dict] = []
    if BLOCKS_FILE.exists():
        blocks = json.loads(BLOCKS_FILE.read_text())
    blocks.append({"ip": target, "blocked_at": datetime.now(timezone.utc).isoformat()})
    BLOCKS_FILE.write_text(json.dumps(blocks, indent=2))

    return ActionResult(
        success=True,
        message=f"Blocked forward traffic from {target} at probe",
        dry_run=False,
        rollback_hint=_rollback_hint(action),
    )


def _execute_rate_limit(action: Action) -> ActionResult:
    target = action.target
    if not target:
        return ActionResult(success=False, message="rate_limit requires a target IP", dry_run=False)

    rule = (
        f"iptables -C FORWARD -s {target} -m hashlimit "
        f"--hashlimit-above 1mb/s --hashlimit-mode srcip --hashlimit-name rl_{target.replace('.', '_')} "
        f"-j DROP 2>/dev/null || iptables -A FORWARD -s {target} -m hashlimit "
        f"--hashlimit-above 1mb/s --hashlimit-mode srcip --hashlimit-name rl_{target.replace('.', '_')} -j DROP"
    )
    code, out, err = run_remote_command(_ssh(), f"sudo {rule}")
    if code != 0:
        return ActionResult(
            success=False,
            message=f"iptables rate-limit failed: {err or out}",
            dry_run=False,
            rollback_hint=_rollback_hint(action),
        )
    return ActionResult(
        success=True,
        message=f"Rate-limited traffic from {target} at probe (~1 MB/s cap)",
        dry_run=False,
        rollback_hint=_rollback_hint(action),
    )


def rollback_block(target: str) -> ActionResult:
    """Remove a probe-side block for target IP."""
    rule = f"sudo iptables -D FORWARD -s {target} -j DROP"
    code, out, err = run_remote_command(_ssh(), rule)
    if BLOCKS_FILE.exists():
        blocks = [b for b in json.loads(BLOCKS_FILE.read_text()) if b.get("ip") != target]
        BLOCKS_FILE.write_text(json.dumps(blocks, indent=2))
    if code != 0:
        return ActionResult(success=False, message=f"Rollback failed: {err or out}", dry_run=False)
    return ActionResult(success=True, message=f"Unblocked {target} at probe", dry_run=False)


def should_auto_execute(action: Action, *, approve_all: bool, allow_block: bool) -> bool:
    if approve_all:
        if action.action_type in DESTRUCTIVE_ACTIONS and not allow_block:
            return False
        return True
    return action.action_type in AUTO_EXECUTABLE_ACTIONS
