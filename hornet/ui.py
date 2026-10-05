"""
HorNet terminal UI helpers.

Rich ANSI color output, prompts, and formatted blocks.
No external dependencies — pure stdlib.
"""

from __future__ import annotations

import sys
import os

# ── Force UTF-8 output on Windows ────────────────────────────────────────────
if sys.platform == "win32":
    import io
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    except Exception:
        pass

# ── ANSI codes ────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

RED     = "\033[91m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
BLUE    = "\033[94m"
MAGENTA = "\033[95m"
CYAN    = "\033[96m"
WHITE   = "\033[97m"
ORANGE  = "\033[38;5;214m"

BG_RED   = "\033[41m"
BG_DARK  = "\033[48;5;235m"

_WIDTH = 72


def _bar(char: str = "-", color: str = DIM) -> str:
    return f"{color}{char * _WIDTH}{RESET}"


# ── Banner ────────────────────────────────────────────────────────────────────

_BANNER_UTF8 = (
    "\n"
    + CYAN + BOLD + "\n"
    + "  \u2588\u2588\u2557  \u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2557   \u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\n"
    + "  \u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2557  \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d\u255a\u2550\u2550\u2588\u2588\u2554\u2550\u2550\u255d\n"
    + "  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2554\u2588\u2588\u2557 \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2557     \u2588\u2588\u2551\n"
    + "  \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2551\u255a\u2588\u2588\u2557\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u255d     \u2588\u2588\u2551\n"
    + "  \u2588\u2588\u2551  \u2588\u2588\u2551\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2551 \u255a\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557   \u2588\u2588\u2551\n"
    + "  \u255a\u2550\u255d  \u255a\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u2550\u2550\u255d\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d   \u255a\u2550\u255d\n"
    + RESET + MAGENTA + "  Kali Linux CTF AI Copilot  .  hnet" + RESET + "\n"
)

_BANNER_ASCII = (
    "\n"
    + CYAN + BOLD + "\n"
    + "  #     #  ####  ####  #    # ###### #####\n"
    + "  #     # #    # #   # ##   # #        #  \n"
    + "  ####### #    # ####  # #  # #####    #  \n"
    + "  #     # #    # #   # #  # # #        #  \n"
    + "  #     # #    # #   # #   ## #        #  \n"
    + "  #     #  ####  ####  #    # ######   #  \n"
    + RESET + MAGENTA + "  Kali Linux CTF AI Copilot  .  hnet" + RESET + "\n"
)


def print_banner() -> None:
    """Print the HorNet banner, falling back to ASCII on narrow/non-UTF8 terminals."""
    try:
        print(_BANNER_UTF8)
    except (UnicodeEncodeError, UnicodeDecodeError):
        print(_BANNER_ASCII)


# ── Styled printers ───────────────────────────────────────────────────────────

def section(title: str, subtitle: str = "") -> None:
    print(f"\n{_bar('=', CYAN)}")
    print(f"{CYAN}{BOLD}  >> {title}{RESET}" + (f"  {DIM}{subtitle}{RESET}" if subtitle else ""))
    print(_bar("-", DIM))


def info(msg: str) -> None:
    print(f"{BLUE}[i]{RESET} {msg}")


def success(msg: str) -> None:
    print(f"{GREEN}[+]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}[!]{RESET} {msg}", file=sys.stderr)


def error(msg: str) -> None:
    print(f"{RED}[x]{RESET} {msg}", file=sys.stderr)


def dim(msg: str) -> None:
    print(f"{DIM}{msg}{RESET}")


def step(icon: str, label: str, value: str = "") -> None:
    print(f"  {CYAN}{icon}{RESET} {BOLD}{label}{RESET}" + (f" -> {value}" if value else ""))


def result_block(title: str, content: str, max_lines: int = 30) -> None:
    lines = content.splitlines()
    if len(lines) > max_lines:
        shown = lines[:max_lines]
        omitted = len(lines) - max_lines
        content = "\n".join(shown) + f"\n{DIM}... {omitted} more lines (use /raw to see all){RESET}"
    print(f"\n{BG_DARK}{BOLD}  {title}  {RESET}")
    print(_bar("-", DIM))
    for line in content.splitlines():
        print(f"  {line}")
    print(_bar("-", DIM))


def risk_banner(tool_name: str, risk: str, args: dict) -> None:
    color = RED if risk == "CONFIRM" else GREEN
    print(f"\n  {color}{BOLD}[{risk}]{RESET} Tool: {BOLD}{tool_name}{RESET}")
    for k, v in args.items():
        val_str = str(v)
        if len(val_str) > 60:
            val_str = val_str[:57] + "..."
        print(f"    {DIM}{k}{RESET} = {val_str}")


def tool_header(tool_name: str, risk: str, args: dict) -> None:
    color = ORANGE if risk == "CONFIRM" else CYAN
    print(f"\n{_bar('-', DIM)}")
    print(f"  {color}> TOOL:{RESET} {BOLD}{tool_name}{RESET}  {DIM}[{risk}]{RESET}")
    for k, v in args.items():
        val_str = str(v)
        if len(val_str) > 80:
            val_str = val_str[:77] + "..."
        print(f"    {DIM}{k}{RESET}: {val_str}")


def thinking(msg: str) -> None:
    print(f"  {MAGENTA}~{RESET} {DIM}{msg}...{RESET}")


# ── Prompts ───────────────────────────────────────────────────────────────────

def prompt_user(prompt_text: str = "hnet> ") -> str:
    try:
        return input(f"\n{CYAN}{BOLD}{prompt_text}{RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        return "/exit"


def prompt_confirm(
    text: str,
    accept_key: str = "p",
    reject_key: str = "s",
) -> str:
    """
    Prompt until user types one of the expected keys.
    Returns 'proceed'/'accept' on accept key, 'stop'/'reject' on reject key.
    """
    accept_words = {accept_key.lower(), accept_key.upper(), "proceed", "accept", "yes", "y"}
    reject_words = {reject_key.lower(), reject_key.upper(), "stop", "reject", "no", "n", "skip"}
    while True:
        try:
            ans = input(f"\n{YELLOW}{BOLD}{text}{RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            return "stop"
        if ans in accept_words:
            return "proceed" if accept_key == "p" else "accept"
        if ans in reject_words:
            return "stop"
        print(f"  {DIM}Please enter '{accept_key}' or '{reject_key}'.{RESET}")


def ask_inline(question: str) -> str:
    """Ask a follow-up question inline (for /ask command, phase override, etc.)."""
    try:
        return input(f"  {CYAN}?{RESET} {question}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


# ── Inline help ───────────────────────────────────────────────────────────────

HELP_TEXT = f"""
{BOLD}HorNet -- Interactive Commands{RESET}

  {CYAN}/ask <question>{RESET}    Query session state (ports, findings, tool choices)
  {CYAN}/state{RESET}             Show current session state summary
  {CYAN}/phase <name>{RESET}      Override current CTF phase manually
                      (recon | enumeration | exploitation | post-exploitation)
  {CYAN}/target <ip>{RESET}       Change target IP/host mid-session
  {CYAN}/raw{RESET}               Show full raw output of the last tool run
  {CYAN}/history{RESET}           Show conversation history
  {CYAN}/findings{RESET}          Show all recorded findings
  {CYAN}/improvised{RESET}        Show improvised command log
  {CYAN}/note <text>{RESET}       Add a free-form note to the session
  {CYAN}/sessions{RESET}          List saved sessions
  {CYAN}/load <id>{RESET}         Load a previous session
  {CYAN}/model{RESET}             Show current model/provider info
  {CYAN}/clear{RESET}             Clear the screen
  {CYAN}/help{RESET}              Show this help
  {CYAN}/exit{RESET} or Ctrl+C   Exit HorNet

{DIM}Type your CTF task in plain English to start the agent loop.{RESET}
"""


def print_help() -> None:
    print(HELP_TEXT)
