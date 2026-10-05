"""
HorNet agent loop — the core reasoning + tool execution engine.

Responsibilities:
  • Build system prompt with tool list scoped to current phase
  • Send user request to the model
  • Parse tool call / plain text response
  • Execute tool via risk gate
  • Feed result back → loop until resolved or max steps
  • Trigger escalation chain when no tool matches
  • Handle /ask inline queries without disrupting loop
"""

from __future__ import annotations

import time
from typing import Optional

from hornet import ui
from hornet.config import HNetConfig
from hornet.escalation import escalate
from hornet.model_client import ModelClient, system_msg, user_msg, assistant_msg, tool_result_msg
from hornet.risk_gate import check_and_gate
from hornet.state import SessionState, StateManager
from hornet.tools import ToolRegistry


# ── System prompt builder ────────────────────────────────────────────────────

def _build_system_prompt(state: SessionState, registry: ToolRegistry) -> str:
    tool_block = registry.tool_prompt_block(state.phase)
    return f"""You are HorNet, an expert CTF hacking assistant running on Kali Linux.

Current session state:
  Target : {state.target or "(not set — ask the user if needed)"}
  Phase  : {state.phase}
  Open ports : {', '.join(str(p) for p in state.open_ports) or 'none discovered yet'}
  Services   : {dict(state.services) or '{}'}
  Findings   : {len(state.findings)} recorded

Your job: reason step by step and call the right tool for each step of the CTF.

{tool_block}

Rules:
- Always call a tool when it applies — do NOT explain what you "would" do, just do it.
- If you need info not yet in state, call nmap_scan or curl_fetch first.
- When a tool result reveals something important (creds, CVE, path), state it explicitly.
- When the current phase is complete, say "Phase complete — advancing to <next phase>".
- If asked /ask questions by the user, answer from session state only.
- Never fabricate command outputs. Only report what tools return.
- For CONFIRM-tier tools, the user will be prompted — you just call the tool normally.
"""


# ── Agent loop ────────────────────────────────────────────────────────────────

class AgentLoop:
    def __init__(
        self,
        client: ModelClient,
        registry: ToolRegistry,
        state: SessionState,
        state_manager: StateManager,
        cfg: HNetConfig,
    ) -> None:
        self.client        = client
        self.registry      = registry
        self.state         = state
        self.state_manager = state_manager
        self.cfg           = cfg
        self._last_raw_output: str = ""

    def _conversation(self) -> list[dict]:
        """Return messages list: system + persisted conversation."""
        return [system_msg(_build_system_prompt(self.state, self.registry))] + \
               self.state.conversation

    def _save(self) -> None:
        self.state_manager.save(self.state)

    # ── /ask handler ─────────────────────────────────────────────────────────

    def handle_ask(self, question: str) -> None:
        """Answer a /ask query about session state without polluting the task loop."""
        msgs = self._conversation() + [
            user_msg(
                f"[/ask from user] {question}\n"
                "Answer from the session state above — be concise and factual."
            )
        ]
        ui.thinking("consulting session state")
        try:
            resp = self.client.chat(msgs)
            ui.result_block("ASK RESPONSE", resp.content)
        except Exception as exc:
            ui.error(f"Ask failed: {exc}")

    # ── Single model step ─────────────────────────────────────────────────────

    def _step(self, step_num: int) -> tuple[bool, str]:
        """
        Run one model → tool → result cycle.

        Returns
        -------
        (should_continue: bool, outcome: str)
        """
        ui.thinking(f"step {step_num} — reasoning")

        try:
            resp = self.client.chat(self._conversation())
        except Exception as exc:
            ui.error(f"LLM error: {exc}")
            return False, f"LLM error: {exc}"

        content = resp.content
        self.state.add_message("assistant", content)

        # ── Plain text (no tool call) ─────────────────────────────────────────
        if not resp.tool_call:
            ui.result_block("MODEL RESPONSE", content)

            # Check if model says task is complete
            done_signals = [
                "task complete", "phase complete", "no further action",
                "ctf complete", "flag found", "rooted", "finished"
            ]
            if any(sig in content.lower() for sig in done_signals):
                return False, "complete"

            # Escalation: model needs something we don't have a tool for
            ui.section("NO TOOL SELECTED", "Triggering escalation chain…")
            result = escalate(
                client=self.client,
                need_description=content,
                state=self.state,
                log_dir=self.cfg.log_dir,
                conversation=self._conversation(),
            )
            feedback = tool_result_msg(result)
            self.state.add_message("user", feedback["content"])
            self._save()
            return True, "escalated"

        # ── Tool call ─────────────────────────────────────────────────────────
        tool_name = resp.tool_call["tool"]
        args      = resp.tool_call.get("args", {})

        # Resolve default target from state
        if "target" in args and not args["target"]:
            args["target"] = self.state.target
        if "host" in args and not args["host"]:
            args["host"] = self.state.target

        tool_def = self.registry.get(tool_name)

        if not tool_def:
            # Unknown tool → escalation
            ui.warn(f"Unknown tool '{tool_name}' — escalating…")
            result = escalate(
                client=self.client,
                need_description=f"Execute '{tool_name}' with args {args}",
                state=self.state,
                log_dir=self.cfg.log_dir,
                conversation=self._conversation(),
            )
            feedback = tool_result_msg(result)
            self.state.add_message("user", feedback["content"])
            self._save()
            return True, f"unknown tool escalated: {tool_name}"

        # Display what we're about to do
        ui.tool_header(tool_name, tool_def.risk.value, args)

        # Risk gate
        approved, gate_reason = check_and_gate(tool_def, args, self.state)
        if not approved:
            ui.warn(f"Tool '{tool_name}' declined: {gate_reason}")
            self.state.add_message(
                "user",
                tool_result_msg(
                    f"Tool '{tool_name}' was declined by user. "
                    "Consider an alternative approach."
                )["content"],
            )
            self._save()
            return True, f"declined: {gate_reason}"

        # Execute
        ui.info("  Executing…")
        t0  = time.time()
        raw = tool_def.executor(args, self.state)
        elapsed = time.time() - t0
        self._last_raw_output = raw

        # Parse/summarise
        if tool_def.parser:
            summary = tool_def.parser(raw, self.state)
        else:
            # Default: cap at 3000 chars
            summary = raw[:3000] + ("…[truncated]" if len(raw) > 3000 else "")

        ui.result_block(f"RESULT: {tool_name} ({elapsed:.1f}s)", summary)

        # Record finding
        self.state.add_finding(tool_name, summary, raw)
        self.state.add_message("user", tool_result_msg(summary)["content"])
        self._save()
        return True, f"tool executed: {tool_name}"

    # ── Main task loop ────────────────────────────────────────────────────────

    def run_task(self, task: str) -> None:
        """
        Execute a user task through the full agent loop.

        Parameters
        ----------
        task : Natural-language task from the user.
        """
        ui.section("TASK", task[:100])
        self.state.task_stack.append(task)
        self.state.add_message("user", task)
        self._save()

        for step_num in range(1, self.cfg.max_loop_steps + 1):
            should_continue, outcome = self._step(step_num)
            if not should_continue:
                ui.success(f"Loop ended: {outcome}")
                break
        else:
            ui.warn(f"Reached max steps ({self.cfg.max_loop_steps}). Stopping loop.")

        self._save()
