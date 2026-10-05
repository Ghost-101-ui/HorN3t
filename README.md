# HorNet 🐝 — Kali Linux CTF AI Copilot

**`hnet`** is a terminal-native AI copilot for CTF work on Kali Linux.  
It drives an agentic reasoning loop over a registry of CTF tools, gates dangerous actions, and escalates to live web search when no tool covers the need.

---

## Features

| Capability | Detail |
|---|---|
| **Model backends** | Local Ollama · OpenRouter · any OpenAI-compatible endpoint |
| **Tool registry** | 16 tools across 4 CTF phases (recon → enum → exploit → post-exploit) |
| **Risk gating** | SAFE tools auto-run; CONFIRM tools (hydra, sqlmap, …) require explicit `[p]roceed` |
| **Escalation chain** | Web search → model proposes command → `[a]ccept` gate → run once → log |
| **Session persistence** | JSON state survives restarts; resume with `/load` or auto-prompt |
| **Zero runtime deps** | Pure Python 3 stdlib — only `urllib`, `subprocess`, `json` |

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/you/hornet.git
cd hornet
pip install -e .
```

This registers the `hnet` CLI entry point.

---

### 2A. Local — Ollama

```bash
# Install Ollama (https://ollama.ai)
ollama pull llama3          # or mistral, codellama, etc.

# Run HorNet (defaults to local Ollama)
hnet
```

Or with a config file (`hnet.config.json` in CWD or `~`):

```json
{
  "mode": "local",
  "local": {
    "base_url": "http://localhost:11434/v1",
    "model": "llama3"
  }
}
```

### 2B. Online — OpenRouter

```bash
export HNET_MODE=online
export HNET_API_KEY=sk-or-xxxx
export HNET_MODEL=anthropic/claude-3-haiku   # or any OpenRouter model

hnet
```

Or in `hnet.config.json`:

```json
{
  "mode": "online",
  "openrouter": {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "anthropic/claude-3-haiku",
    "api_key": "sk-or-xxxx"
  }
}
```

---

## CLI Flags

```
hnet                          interactive REPL (auto-resumes latest session)
hnet "scan 10.10.10.5"        one-shot task
hnet --target 10.10.10.5      pre-set target
hnet --local                  force local Ollama
hnet --online                 force OpenRouter
hnet --model llama3:70b       override model
hnet --phase exploitation     skip to a phase
hnet --load <session-id>      resume specific session
hnet --new                    force a fresh session
hnet --list-sessions          list all saved sessions
hnet --debug                  verbose output
```

---

## Interactive Commands

Once inside the REPL:

| Command | Description |
|---|---|
| `/ask <question>` | Query session state: ports, findings, why a tool was chosen |
| `/state` | Print full session summary |
| `/phase <name>` | Override CTF phase manually |
| `/raw` | Show full raw output of last tool run |
| `/findings` | List all tool findings so far |
| `/improvised` | Show web-search escalation log |
| `/history` | Show conversation history |
| `/sessions` | List saved sessions |
| `/load <id>` | Load a previous session |
| `/note <text>` | Add a freeform note |
| `/model` | Show current provider/model info |
| `/target <ip>` | Change target mid-session |
| `/clear` | Clear screen |
| `/exit` | Save & quit |

---

## Tool Registry

### Recon
| Tool | Risk | Description |
|---|---|---|
| `nmap_scan` | SAFE | Port scan + service detection |
| `whatweb_scan` | SAFE | Web technology fingerprinting |
| `netcat_banner` | SAFE | Service banner grab |

### Enumeration
| Tool | Risk | Description |
|---|---|---|
| `gobuster_dir` | SAFE | Directory/file brute-force |
| `ffuf_fuzz` | SAFE | Fast web fuzzer (FUZZ keyword) |
| `nikto_scan` | SAFE | Web vulnerability scan |
| `searchsploit` | SAFE | Exploit-DB search |
| `curl_fetch` | SAFE | HTTP requests |
| `enum4linux` | SAFE | SMB/NetBIOS enumeration |
| `smbclient_list` | SAFE | SMB share listing |
| `wfuzz_fuzz` | SAFE | Web fuzzer (alternative) |

### Exploitation
| Tool | Risk | Description |
|---|---|---|
| `ssh_try` | **CONFIRM** | Single SSH credential test |
| `hydra_bruteforce` | **CONFIRM** | Credential brute-force |
| `sqlmap_scan` | **CONFIRM** | SQL injection scanner |

### Post-Exploitation
| Tool | Risk | Description |
|---|---|---|
| `find_suid` | SAFE | Find SUID binaries |
| `linpeas_run` | **CONFIRM** | LinPEAS privilege escalation enum |

---

## Risk Gate

**SAFE tools** run immediately. **CONFIRM tools** pause with:

```
  [CONFIRM] Tool: hydra_bruteforce
    target = 10.10.10.5
    service = ssh
    passlist = /usr/share/wordlists/rockyou.txt

  [CONFIRM] Run 'hydra_bruteforce'? [p]roceed / [s]top :
```

Rejections are logged in state and fed back to the model, which then reasons about an alternative approach.

---

## Escalation Chain

When no registered tool covers the need:

1. Model drafts a search query
2. HorNet searches DuckDuckGo (no API key)
3. Model proposes one exact shell command
4. User prompted `[a]ccept / [n]ot`
5. On accept: runs once, logged to `~/.hornet/logs/session_improvised.log`
6. Raw material for future permanent tool registration (manual step)

---

## Session Persistence

Sessions are stored as JSON in `~/.hornet/sessions/session_<id>.json`.  
On next launch, HorNet asks to resume the latest session.

```bash
hnet --list-sessions
hnet --load abc12345
```

The improvised command log lives at `~/.hornet/logs/session_improvised.log`.

---

## Adding a New Tool

Open `hornet/tools.py` and add a `ToolDef` to `build_registry()`:

```python
reg.register(ToolDef(
    name="my_tool",
    description="What it does (shown to the model).",
    phase=["enumeration"],
    risk=Risk.SAFE,          # or Risk.CONFIRM
    schema={
        "target": {"type": "str", "description": "Target host", "required": True},
    },
    executor=lambda args, state: _run(["mytool", args["target"]]),
    parser=None,             # or a callable(raw, state) -> summary
))
```

No other file needs to change.

---

## Config Priority

1. CLI flags (`--model`, `--local`, `--online`)
2. Environment variables (`HNET_*`)
3. `hnet.config.json` in CWD or home dir
4. Built-in defaults (local Ollama, `llama3`)

---

## Project Layout

```
hornet/
  __init__.py       package + version
  cli.py            entry point, argparse, REPL, /commands
  agent.py          agentic loop (system prompt, step, escalation trigger)
  model_client.py   OpenAI-compatible HTTP client (stdlib urllib)
  config.py         multi-source config loader
  state.py          session state + JSON persistence
  tools.py          tool registry + all executors + parsers
  risk_gate.py      SAFE/CONFIRM gating logic
  escalation.py     web search → command proposal → execute-once flow
  ui.py             ANSI terminal output helpers
pyproject.toml
hnet.config.json    sample config
.env.example        sample env vars
```

---

## License

MIT
