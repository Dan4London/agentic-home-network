"""MCP server: guarded remediation actions."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from agent.actuator import execute_action, propose_action, rollback_block
from agent.config import Settings
from agent.schemas import Action, ActionType
from agent.policies import action_allowed

mcp = FastMCP("actuator")


def _action(action_type: str, description: str, target: str | None) -> Action:
    return Action(
        action_type=ActionType(action_type),
        description=description,
        target=target,
    )


@mcp.tool()
def propose_action_tool(action_type: str, description: str, target: str | None = None) -> str:
    """Propose a remediation action (dry-run). Does not apply changes."""
    if not action_allowed(action_type):
        return json.dumps({"error": f"Action '{action_type}' not in allow-list"})
    action = _action(action_type, description, target)
    result = propose_action(action)
    return json.dumps(
        {
            "proposed": result.success,
            "action_type": action_type,
            "description": description,
            "target": target,
            "dry_run": True,
            "message": result.message,
            "rollback_hint": result.rollback_hint,
        }
    )


@mcp.tool()
def apply_action(
    action_type: str,
    description: str,
    target: str | None = None,
    approved: bool = False,
) -> str:
    """Apply a guarded action. Requires approved=true; respects DRY_RUN env."""
    if not action_allowed(action_type):
        return json.dumps({"error": f"Action '{action_type}' not in allow-list"})
    settings = Settings()
    action = _action(action_type, description, target)
    result = execute_action(action, approved=approved)
    return json.dumps(
        {
            "applied": result.success and not result.dry_run,
            "dry_run": result.dry_run or settings.dry_run,
            "message": result.message,
            "rollback_hint": result.rollback_hint,
        }
    )


@mcp.tool()
def rollback_block_tool(target: str) -> str:
    """Remove a probe-side iptables block for the given IP."""
    result = rollback_block(target)
    return json.dumps({"success": result.success, "message": result.message})


if __name__ == "__main__":
    mcp.run()
