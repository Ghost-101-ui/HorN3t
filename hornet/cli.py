"""
HorNet CLI entry point — `hnet` command.

Usage:
  hnet [OPTIONS] [TASK]
  hnet                         # interactive REPL
  hnet "scan 10.10.10.5"       # one-shot task
  hnet --local                 # force local Ollama
  hnet --online                # force OpenRouter
  hnet --model llama3          # override model
  hnet --load <session-id>     # resume a session
  hnet --target 10.10.10.5     # pre-set target
  hnet --phase exploitation    # pre-set phase
  hnet --list-sessions         # list saved sessions
  hnet --new                   # force a new session
"""

from __future__ import annotations

import argparse
import os
import sys
import pathlib

# ── Bootstrap sys.path so `hornet` package is importable ────────────────────
_ROOT = pathlib.Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from hornet import ui
from hornet.agent import AgentLoop
from hornet.config import load_config
from hornet.model_client import ModelClient
from hornet.state import StateManager
from hornet.tools import build_registry


# ── Argument parser ───────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="hnet",
        description="HorNet — Kali Linux CTF AI Copilot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("task", nargs="?", default="", help="One-shot task (skips interactive loop)")
    p.add_argument("--local",   action="store_true", help="Force local Ollama backend")
    p.add_argument("--online",  action="store_true", help="Force online (OpenRouter) backend")
    p.add_argument("--model",   default="",          help="Override model name")
    p.add_argument("--base-url","--base_url", default="", help="Override API base URL", dest="base_url")
    p.add_argument("--target",  default="",          help="Pre-set CTF target IP/host")
    p.add_argument("--phase",   default="",          help="Pre-set phase (recon/enumeration/...)")
    p.add_argument("--load",    default="",          help="Load session by ID")
    p.add_argument("--new",     action="store_true", help="Force new session (don't resume latest)")
    p.add_argument("--list-sessions", action="store_true", help="List saved sessions and exit")
    p.add_argument("--debug",   action="store_true", help="Enable debug output")
    p.add_argument("--version", action="version", version="hnet 0.1.0")
    return p


# ── Session helpers ───────────────────────────────────────────────────────────

def _pick_or_create_session(args: argparse.Namespace, sm: StateManager):
    from hornet.state import SessionState, PHASES
    import time

    if args.load:
        state = sm.load(args.load)
        if not state:
            ui.error(f"Session '{args.load}' not found.")
            sys.exit(1)
        ui.success(f"Resumed session {state.session_id} (target={state.target}, phase={state.phase})")
        return state

    if not args.new:
        latest = sm.latest_session()
        if latest:
            ans = ui.ask_inline(
                f"Resume latest session {latest.session_id} "
                f"[target={latest.target or '?'}, phase={latest.phase}]? [y/n]"
            )
            if ans.lower() in ("y", "yes", ""):
                ui.success(f"Resumed session {latest.session_id}")
                return latest

    state = sm.new_session(target=args.target)
    if args.phase and args.phase in PHASES:
        state.phase = args.phase
    elif args.target:
        state.target = args.target
    ui.success(f"New session {state.session_id}" + (f" | target={state.target}" if state.target else ""))
    return state


# ── /command dispatch ─────────────────────────────────────────────────────────

def _handle_slash(
    cmd: str,
    loop: AgentLoop,
    sm: StateManager,
    cfg,
) -> bool:
    """
    Handle a slash command.
    Returns True if execution should continue, False to exit.
    """
    import os as _os
    parts = cmd.split(None, 1)
    verb  = parts[0].lower()
    arg   = parts[1] if len(parts) > 1 else ""

    if verb == "/exit" or verb == "/quit":
        ui.info("Saving session… bye!")
        sm.save(loop.state)
        return False

    elif verb == "/help":
        ui.print_help()

    elif verb == "/ask":
        if not arg:
            arg = ui.ask_inline("What do you want to ask?")
        if arg:
            loop.handle_ask(arg)

    elif verb == "/state":
        ui.result_block("SESSION STATE", loop.state.summary())

    elif verb == "/raw":
        raw = loop._last_raw_output
        if raw:
            ui.result_block("RAW OUTPUT", raw, max_lines=200)
        else:
            ui.info("No tool has been run yet.")

    elif verb == "/phase":
        from hornet.state import PHASES
        if arg in PHASES:
            loop.state.phase = arg
            sm.save(loop.state)
            ui.success(f"Phase set to '{arg}'")
        else:
            ui.warn(f"Unknown phase. Valid: {', '.join(PHASES)}")

    elif verb == "/history":
        hist = loop.state.conversation
        if not hist:
            ui.info("No conversation history yet.")
        else:
            lines = []
            for m in hist[-20:]:   # last 20 messages
                role = m["role"].upper()
                content = m["content"][:200].replace("\n", " ")
                lines.append(f"[{role}] {content}")
            ui.result_block("CONVERSATION HISTORY (last 20)", "\n".join(lines))

    elif verb == "/sessions":
        sessions = sm.list_sessions()
        if not sessions:
            ui.info("No saved sessions.")
        else:
            import datetime
            lines = []
            for s in sessions:
                dt = datetime.datetime.fromtimestamp(s["created"]).strftime("%Y-%m-%d %H:%M")
                lines.append(f"  {s['id']}  {dt}  target={s['target'] or '?'}  phase={s['phase']}")
            ui.result_block("SAVED SESSIONS", "\n".join(lines))

    elif verb == "/load":
        if not arg:
            ui.warn("Usage: /load <session-id>")
        else:
            new_state = sm.load(arg)
            if new_state:
                loop.state = new_state
                ui.success(f"Loaded session {arg}")
            else:
                ui.error(f"Session '{arg}' not found.")

    elif verb == "/note":
        if arg:
            loop.state.notes.append(arg)
            sm.save(loop.state)
            ui.success("Note saved.")
        else:
            ui.warn("Usage: /note <text>")

    elif verb == "/findings":
        findings = loop.state.findings
        if not findings:
            ui.info("No findings recorded yet.")
        else:
            lines = []
            for f in findings:
                import datetime
                dt = datetime.datetime.fromtimestamp(f["ts"]).strftime("%H:%M:%S")
                lines.append(f"[{dt}] {f['tool']}: {f['summary'][:120]}")
            ui.result_block("FINDINGS", "\n".join(lines))

    elif verb == "/improvised":
        cmds = loop.state.improvised_commands
        if not cmds:
            ui.info("No improvised commands logged.")
        else:
            import datetime
            lines = []
            for c in cmds:
                dt = datetime.datetime.fromtimestamp(c["ts"]).strftime("%H:%M:%S")
                lines.append(
                    f"[{dt}] {c['command']}\n"
                    f"  rationale: {c.get('rationale', '')}\n"
                    f"  output: {c.get('output', '')[:100]}…"
                )
            ui.result_block("IMPROVISED COMMANDS", "\n\n".join(lines))

    elif verb == "/model":
        p = cfg.provider
        ui.result_block(
            "MODEL INFO",
            f"Provider : {p.name}\nModel    : {p.model}\nBase URL : {p.base_url}\nTimeout  : {p.timeout}s",
        )

    elif verb == "/clear":
        _os.system("clear" if _os.name != "nt" else "cls")

    elif verb == "/target":
        if arg:
            loop.state.target = arg
            sm.save(loop.state)
            ui.success(f"Target set to '{arg}'")
        else:
            ui.info(f"Current target: {loop.state.target or '(not set)'}")

    else:
        ui.warn(f"Unknown command: {verb}  — type /help")

    return True


# ── Main entry point ──────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    cfg = load_config(
        force_local=args.local,
        force_online=args.online,
        override_model=args.model or None,
        override_base_url=args.base_url or None,
    )
    if args.debug:
        cfg.debug = True

    # ── Setup dirs ────────────────────────────────────────────────────────────
    cfg.session_dir.mkdir(parents=True, exist_ok=True)
    cfg.log_dir.mkdir(parents=True, exist_ok=True)

    # ── Print banner ──────────────────────────────────────────────────────────
    ui.print_banner()
    ui.dim(f"  Provider : {cfg.provider.name}  │  Model : {cfg.provider.model}")
    ui.dim(f"  Base URL : {cfg.provider.base_url}")

    # ── Build components ──────────────────────────────────────────────────────
    client   = ModelClient(cfg.provider)
    registry = build_registry()
    sm       = StateManager(cfg.session_dir)

    # ── --list-sessions shortcut ──────────────────────────────────────────────
    if args.list_sessions:
        sessions = sm.list_sessions()
        if not sessions:
            ui.info("No saved sessions.")
        else:
            import datetime
            for s in sessions:
                dt = datetime.datetime.fromtimestamp(s["created"]).strftime("%Y-%m-%d %H:%M")
                print(f"  {s['id']}  {dt}  target={s['target'] or '?'}  phase={s['phase']}")
        sys.exit(0)

    # ── Pick session ──────────────────────────────────────────────────────────
    state = _pick_or_create_session(args, sm)
    if args.target and not state.target:
        state.target = args.target
    if args.phase and state.phase == "recon":
        from hornet.state import PHASES
        if args.phase in PHASES:
            state.phase = args.phase

    # ── Build agent loop ──────────────────────────────────────────────────────
    loop = AgentLoop(
        client=client,
        registry=registry,
        state=state,
        state_manager=sm,
        cfg=cfg,
    )

    # ── One-shot mode ─────────────────────────────────────────────────────────
    if args.task:
        loop.run_task(args.task)
        sm.save(state)
        return

    # ── Interactive REPL ──────────────────────────────────────────────────────
    ui.print_help()

    if not state.target:
        target = ui.ask_inline("Enter CTF target (IP / hostname / URL) — or press Enter to skip")
        if target:
            state.target = target
            sm.save(state)

    while True:
        try:
            raw_input = ui.prompt_user(f"hnet [{state.phase}]> ")
        except (KeyboardInterrupt, EOFError):
            ui.info("\nCtrl+C — type /exit to quit.")
            continue

        if not raw_input:
            continue

        if raw_input.startswith("/"):
            should_continue = _handle_slash(raw_input, loop, sm, cfg)
            if not should_continue:
                break
        else:
            loop.run_task(raw_input)


if __name__ == "__main__":
    main()
