"""
HorNet session state — persisted to JSON so it survives restarts.

Tracks:
  • target info (IP, domain, ports, services)
  • phase (recon → enum → exploit → post)
  • findings (dict of tool → result summaries)
  • conversation history (list of chat messages)
  • improvised commands log
  • rejected tool attempts
"""

from __future__ import annotations

import json
import pathlib
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# ── CTF phases ───────────────────────────────────────────────────────────────

PHASES = ["recon", "enumeration", "exploitation", "post-exploitation"]


# ── State dataclass ──────────────────────────────────────────────────────────

@dataclass
class SessionState:
    session_id: str
    created_at: float
    target: str = ""                        # IP / hostname / URL
    phase: str  = "recon"
    open_ports: list[int]              = field(default_factory=list)
    services: dict[str, str]           = field(default_factory=dict)  # port → service
    findings: list[dict]               = field(default_factory=list)  # {tool, summary, ts}
    conversation: list[dict]           = field(default_factory=list)  # chat messages
    rejected_actions: list[dict]       = field(default_factory=list)  # risk-gated refusals
    improvised_commands: list[dict]    = field(default_factory=list)  # escalation log
    notes: list[str]                   = field(default_factory=list)  # free-form notes
    task_stack: list[str]              = field(default_factory=list)  # current task desc

    # ── Convenience mutators ─────────────────────────────────────────────────

    def add_finding(self, tool: str, summary: str, raw: str = "") -> None:
        self.findings.append({
            "tool": tool,
            "summary": summary,
            "raw": raw,
            "ts": time.time(),
        })

    def add_message(self, role: str, content: str) -> None:
        self.conversation.append({"role": role, "content": content})

    def log_rejection(self, tool: str, args: dict, reason: str) -> None:
        self.rejected_actions.append({
            "tool": tool,
            "args": args,
            "reason": reason,
            "ts": time.time(),
        })

    def log_improvised(
        self,
        command: str,
        rationale: str,
        output: str,
        context: str = "",
    ) -> None:
        self.improvised_commands.append({
            "command": command,
            "rationale": rationale,
            "context": context,
            "output": output[:2000],   # cap stored output
            "ts": time.time(),
        })

    def record_ports(self, ports: list[int]) -> None:
        self.open_ports = sorted(set(self.open_ports + ports))

    def record_service(self, port: int, service: str) -> None:
        self.services[str(port)] = service

    def advance_phase(self) -> str:
        idx = PHASES.index(self.phase) if self.phase in PHASES else 0
        if idx < len(PHASES) - 1:
            self.phase = PHASES[idx + 1]
        return self.phase

    def summary(self) -> str:
        """Return a human-readable state summary."""
        lines = [
            f"Target : {self.target or '(not set)'}",
            f"Phase  : {self.phase}",
            f"Ports  : {', '.join(str(p) for p in self.open_ports) or 'none yet'}",
        ]
        if self.services:
            lines.append("Services:")
            for p, s in self.services.items():
                lines.append(f"  {p} → {s}")
        if self.findings:
            lines.append(f"Findings: {len(self.findings)} recorded")
        if self.improvised_commands:
            lines.append(f"Improvised commands: {len(self.improvised_commands)}")
        return "\n".join(lines)

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SessionState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Manager ──────────────────────────────────────────────────────────────────

class StateManager:
    """Load, persist, and manage session state files."""

    def __init__(self, session_dir: pathlib.Path) -> None:
        self.session_dir = session_dir
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def new_session(self, target: str = "") -> SessionState:
        sid = str(uuid.uuid4())[:8]
        state = SessionState(
            session_id=sid,
            created_at=time.time(),
            target=target,
        )
        self._save(state)
        return state

    def _path(self, sid: str) -> pathlib.Path:
        return self.session_dir / f"session_{sid}.json"

    def _save(self, state: SessionState) -> None:
        with open(self._path(state.session_id), "w", encoding="utf-8") as fh:
            json.dump(state.to_dict(), fh, indent=2)

    def save(self, state: SessionState) -> None:
        self._save(state)

    def load(self, sid: str) -> Optional[SessionState]:
        p = self._path(sid)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as fh:
            return SessionState.from_dict(json.load(fh))

    def list_sessions(self) -> list[dict]:
        """Return metadata for all saved sessions, newest first."""
        results = []
        for p in sorted(self.session_dir.glob("session_*.json"), reverse=True):
            try:
                with open(p, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                results.append({
                    "id":      d["session_id"],
                    "target":  d.get("target", ""),
                    "phase":   d.get("phase", ""),
                    "created": d.get("created_at", 0),
                })
            except Exception:
                continue
        return results

    def latest_session(self) -> Optional[SessionState]:
        sessions = self.list_sessions()
        if not sessions:
            return None
        return self.load(sessions[0]["id"])
