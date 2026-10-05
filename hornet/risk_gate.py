"""
HorNet risk gate — intercepts CONFIRM-tier tool calls and gets explicit user approval.
"""

from __future__ import annotations

from hornet.tools import Risk, ToolDef
from hornet.state import SessionState
from hornet import ui


def check_and_gate(
    tool: ToolDef,
    args: dict,
    state: SessionState,
) -> tuple[bool, str]:
    """
    Check risk tier and, if CONFIRM, prompt user.

    Returns
    -------
    (approved: bool, reason: str)
    """
    if tool.risk == Risk.SAFE:
        return True, "auto-approved (SAFE)"

    # CONFIRM tier ─────────────────────────────────────────────────────────────
    ui.risk_banner(tool.name, tool.risk.value, args)
    answer = ui.prompt_confirm(
        f"  [{tool.risk.value}] Run '{tool.name}'? [p]roceed / [s]top : "
    )
    if answer == "proceed":
        return True, "user approved"
    else:
        reason = f"user declined to run {tool.name}"
        state.log_rejection(tool.name, args, reason)
        return False, reason
