"""
HorNet escalation chain.

Triggered when the model's tool call names an unregistered tool
or the model emits plain text indicating it can't proceed.

Flow:
  1. Model drafts a web search query.
  2. HorNet performs the search (DuckDuckGo HTML scrape — no API key needed).
  3. Results fed back to model → it proposes an exact shell command.
  4. User prompted [a]ccept / [n]ot.
  5. On accept: run once, log to session_improvised.log.
  6. On reject: log rejection, return explanation to model.
"""

from __future__ import annotations

import subprocess
import time
import urllib.parse
import urllib.request
import re
import pathlib

from hornet import ui
from hornet.model_client import ModelClient, user_msg, tool_result_msg
from hornet.state import SessionState


# ── Web search (DuckDuckGo HTML — stdlib only) ────────────────────────────────

def _ddg_search(query: str, max_results: int = 5) -> str:
    """Scrape DuckDuckGo HTML results, return plain-text snippet list."""
    url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"[Search failed: {exc}]"

    # Extract result snippets from HTML
    snippets: list[str] = []
    # DuckDuckGo result pattern
    for m in re.finditer(
        r'class="result__snippet">(.*?)</a>',
        html,
        re.DOTALL,
    ):
        text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        if text:
            snippets.append(text)
        if len(snippets) >= max_results:
            break

    if not snippets:
        # Fallback: grab any visible text blocks
        clean = re.sub(r"<[^>]+>", " ", html)
        clean = re.sub(r"\s+", " ", clean)
        snippets = [clean[500:1500]]  # grab a middle chunk

    return "\n---\n".join(snippets[:max_results])


# ── Improvised command log ───────────────────────────────────────────────────

def _write_improvised_log(log_dir: pathlib.Path, entry: dict) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "session_improvised.log"
    with open(log_path, "a", encoding="utf-8") as fh:
        import json
        fh.write(json.dumps(entry) + "\n")


# ── Main escalation function ─────────────────────────────────────────────────

def escalate(
    client: ModelClient,
    need_description: str,
    state: SessionState,
    log_dir: pathlib.Path,
    conversation: list[dict],
) -> str:
    """
    Run the escalation chain for an unresolved need.

    Parameters
    ----------
    need_description : What the model said it needs (plain text).

    Returns
    -------
    A string result to feed back into the conversation.
    """
    ui.section("ESCALATION", "No registered tool covers this need — searching the web…")

    # Step 1: Ask the model to draft a search query ────────────────────────────
    search_prompt = conversation + [
        user_msg(
            f"You said: {need_description}\n\n"
            "No HorNet tool covers this. Draft a concise DuckDuckGo search query "
            "(max 10 words) to find the exact shell command or technique needed. "
            "Reply with ONLY the search query, no explanation."
        )
    ]
    try:
        query_resp = client.chat(search_prompt)
        search_query = query_resp.content.strip().strip('"').strip("'")
    except Exception as exc:
        search_query = need_description[:80]
        ui.warn(f"Could not get search query from model: {exc}. Using raw description.")

    ui.info(f"  Searching: {search_query!r}")

    # Step 2: Perform web search ───────────────────────────────────────────────
    search_results = _ddg_search(search_query)
    ui.dim(f"  Got {len(search_results)} chars of results.")

    # Step 3: Ask model to propose a concrete command ─────────────────────────
    propose_prompt = conversation + [
        user_msg(
            f"Web search results for '{search_query}':\n\n{search_results}\n\n"
            "Based on these results, propose EXACTLY ONE shell command that solves "
            f"the need: '{need_description}'.\n"
            "Reply in this exact format:\n"
            "COMMAND: <exact command here>\n"
            "RATIONALE: <one sentence why>\n"
            "If you cannot determine a safe, specific command, reply: NO_COMMAND"
        )
    ]
    try:
        propose_resp = client.chat(propose_prompt)
        proposal = propose_resp.content.strip()
    except Exception as exc:
        return f"[Escalation failed at proposal step: {exc}]"

    if "NO_COMMAND" in proposal:
        msg = "Web search did not yield a concrete command. Manual investigation needed."
        ui.warn(msg)
        return msg

    # Parse COMMAND / RATIONALE
    cmd_line  = ""
    rationale = ""
    for line in proposal.splitlines():
        if line.startswith("COMMAND:"):
            cmd_line  = line[len("COMMAND:"):].strip()
        elif line.startswith("RATIONALE:"):
            rationale = line[len("RATIONALE:"):].strip()

    if not cmd_line:
        # Try to extract any plausible command
        cmd_match = re.search(r"`([^`]+)`", proposal)
        if cmd_match:
            cmd_line = cmd_match.group(1)
        else:
            return f"Model did not return a parseable command.\nFull response:\n{proposal}"

    # Step 4: Present to user and gate ────────────────────────────────────────
    ui.section("IMPROVISED COMMAND PROPOSAL", "")
    ui.info(f"  Command  : {cmd_line}")
    ui.info(f"  Rationale: {rationale or '(not provided)'}")
    answer = ui.prompt_confirm(
        "  Run this command? [a]ccept / [n]ot : ",
        accept_key="a",
        reject_key="n",
    )

    if answer != "accept":
        msg = f"User declined improvised command: {cmd_line!r}"
        state.log_rejection("improvised", {"command": cmd_line}, msg)
        _write_improvised_log(log_dir, {
            "ts": time.time(), "command": cmd_line, "rationale": rationale,
            "outcome": "declined", "search_query": search_query,
        })
        return "Command declined by user. Try a different approach."

    # Step 5: Execute once ─────────────────────────────────────────────────────
    ui.info("  Running…")
    try:
        result = subprocess.run(
            cmd_line,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (result.stdout + result.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        output = "[TIMEOUT after 120s]"
    except Exception as exc:
        output = f"[ERROR] {exc}"

    output_preview = output[:2000]
    ui.result_block("IMPROVISED COMMAND OUTPUT", output_preview)

    # Step 6: Log to improvised log ────────────────────────────────────────────
    state.log_improvised(
        command=cmd_line,
        rationale=rationale,
        output=output,
        context=need_description,
    )
    _write_improvised_log(log_dir, {
        "ts":           time.time(),
        "command":      cmd_line,
        "rationale":    rationale,
        "output":       output_preview,
        "search_query": search_query,
        "outcome":      "accepted",
    })

    return f"Improvised command executed.\nCommand: {cmd_line}\nOutput:\n{output_preview}"
