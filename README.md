<div align="center">

# 🐝 HorN3t

**Kali Linux Terminal AI Copilot for CTF Work**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Kali%20Linux-purple?style=for-the-badge&logo=linux)](https://kali.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Zero Deps](https://img.shields.io/badge/Dependencies-Zero-brightgreen?style=for-the-badge)](pyproject.toml)

> AI-powered terminal copilot that drives nmap, gobuster, hydra, sqlmap and more — with risk gating, session persistence, and a web-search escalation chain.

</div>

---

## ⚡ Install (Kali Linux)

### Option A — Git clone (recommended)

```bash
# 1. Clone the repo
git clone https://github.com/Ghost-101-ui/HorN3t.git
cd HorN3t

# 2. Install (zero runtime dependencies — pure Python stdlib)
pip install -e .

# 3. Run
hnet
```

> If `hnet` is not found after install, run it as:
> ```bash
> python -m hornet.cli
> ```
> Or add pip's script dir to PATH:
> ```bash
> echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
> ```

---

### Option B — One-liner setup

```bash
git clone https://github.com/Ghost-101-ui/HorN3t.git && cd HorN3t && pip install -e . && hnet
```

---

## 🔧 Backend Setup

HorN3t works with **local Ollama** (free, offline) or **OpenRouter** (cloud models).  
Pick one — no other dependencies needed.

---

### 🖥️ Local — Ollama (Free, runs on your machine)

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull a model (choose one)
ollama pull llama3          # recommended — fast + smart
ollama pull mistral         # lighter alternative
ollama pull codellama       # code-focused

# 3. Start Ollama (auto-starts on most systems, or run manually)
ollama serve &

# 4. Run HorN3t in local mode (default)
hnet --local --target 10.10.10.5
```

**Config file** — create `hnet.config.json` in your project folder:
```json
{
  "mode": "local",
  "local": {
    "base_url": "http://localhost:11434/v1",
    "model": "llama3"
  }
}
```

---

### 🌐 Online — OpenRouter (Cloud, smarter models)

```bash
# 1. Get a free API key → https://openrouter.ai/keys

# 2. Set env vars
export HNET_MODE=online
export HNET_API_KEY=sk-or-xxxxxxxxxxxxxxxxxxxxxxxx
export HNET_MODEL=anthropic/claude-3-haiku    # or: meta-llama/llama-3-8b-instruct:free

# 3. Run
hnet --online --target 10.10.10.5
```

**Or** add to `hnet.config.json`:
```json
{
  "mode": "online",
  "openrouter": {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "anthropic/claude-3-haiku",
    "api_key": "sk-or-xxxxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

---

## 🚀 Usage

```bash
# Interactive mode (auto-resumes last session)
hnet

# Set target and start
hnet --target 10.10.10.5

# Force a new session
hnet --new --target 10.10.10.5

# Skip to a specific phase
hnet --target 10.10.10.5 --phase exploitation

# One-shot task (non-interactive)
hnet --target 10.10.10.5 "scan all ports and find web services"

# Resume a previous session
hnet --list-sessions
hnet --load <session-id>

# Force local or online backend
hnet --local
hnet --online

# Override model at runtime
hnet --model llama3:70b
```

---

## 💬 Interactive Commands

Once inside the HorN3t shell, type these anytime:

| Command | What it does |
|---|---|
| `/ask <question>` | Ask about findings, ports, why a tool was chosen |
| `/state` | Full session summary (target, phase, ports, services) |
| `/findings` | List all tool results recorded so far |
| `/raw` | Show full raw output of the last tool run |
| `/phase <name>` | Jump to a phase: `recon` / `enumeration` / `exploitation` / `post-exploitation` |
| `/target <ip>` | Change the target mid-session |
| `/improvised` | Show log of web-search escalation commands |
| `/sessions` | List all saved sessions |
| `/load <id>` | Load a previous session |
| `/history` | Show conversation history |
| `/note <text>` | Save a free-form note |
| `/model` | Show current provider + model info |
| `/clear` | Clear the screen |
| `/help` | Show help |
| `/exit` | Save session and quit |

---

## 🧰 Built-in CTF Tool Registry

### 🔍 Recon
| Tool | Risk | Description |
|---|---|---|
| `nmap_scan` | ✅ SAFE | Port scan + service detection |
| `whatweb_scan` | ✅ SAFE | Web technology fingerprinting |
| `netcat_banner` | ✅ SAFE | Grab service banners |

### 🗂️ Enumeration
| Tool | Risk | Description |
|---|---|---|
| `gobuster_dir` | ✅ SAFE | Directory/file brute-force |
| `ffuf_fuzz` | ✅ SAFE | Fast web fuzzer (FUZZ keyword in URL) |
| `nikto_scan` | ✅ SAFE | Web vulnerability scanner |
| `searchsploit` | ✅ SAFE | Search Exploit-DB for CVEs |
| `curl_fetch` | ✅ SAFE | Custom HTTP requests |
| `enum4linux` | ✅ SAFE | SMB/NetBIOS enumeration |
| `smbclient_list` | ✅ SAFE | Browse SMB shares |
| `wfuzz_fuzz` | ✅ SAFE | Web fuzzer (alternative) |

### 💥 Exploitation
| Tool | Risk | Description |
|---|---|---|
| `ssh_try` | ⚠️ CONFIRM | Single SSH credential attempt |
| `hydra_bruteforce` | ⚠️ CONFIRM | Credential brute-force |
| `sqlmap_scan` | ⚠️ CONFIRM | SQL injection scanner |

### 🏴 Post-Exploitation
| Tool | Risk | Description |
|---|---|---|
| `find_suid` | ✅ SAFE | Find SUID binaries for privesc |
| `linpeas_run` | ⚠️ CONFIRM | LinPEAS privilege escalation enum |

> ⚠️ **CONFIRM** tools pause the loop and ask `[p]roceed / [s]top` before running. Rejections are fed back to the model so it reasons about an alternative.

---

## 🛡️ Risk Gate

```
  [CONFIRM] Tool: hydra_bruteforce
    target  = 10.10.10.5
    service = ssh
    passlist = /usr/share/wordlists/rockyou.txt

  [CONFIRM] Run 'hydra_bruteforce'? [p]roceed / [s]top :
```

---

## 🔁 Escalation Chain

When no registered tool covers the need:

```
1.  Model drafts a search query
2.  HorN3t searches DuckDuckGo (no API key needed)
3.  Model reads results and proposes ONE exact shell command
4.  You are prompted: [a]ccept / [n]ot
5.  On accept → runs once → logged to ~/.hornet/logs/session_improvised.log
6.  NOT auto-registered — stays a manual, reviewed promotion step
```

---

## 📁 Session Persistence

Sessions are saved to `~/.hornet/sessions/session_<id>.json`.  
On next launch HorN3t asks to resume the latest session.

```bash
# List sessions
hnet --list-sessions

# Load specific session
hnet --load abc12345
```

---

## ⚙️ Config Priority

```
1. CLI flags        --model, --local, --online, --target
2. Env variables    HNET_MODE, HNET_API_KEY, HNET_MODEL, HNET_BASE_URL
3. hnet.config.json (in CWD or home dir)
4. Defaults         local Ollama on localhost:11434, model=llama3
```

---

## 📦 Project Layout

```
HorN3t/
├── hornet/
│   ├── cli.py            → hnet entry point + REPL + /commands
│   ├── agent.py          → agentic reasoning loop
│   ├── model_client.py   → OpenAI-compatible HTTP client (stdlib only)
│   ├── config.py         → multi-source config loader
│   ├── state.py          → session state + JSON persistence
│   ├── tools.py          → CTF tool registry (16 tools + parsers)
│   ├── risk_gate.py      → SAFE / CONFIRM gating logic
│   ├── escalation.py     → web search → propose → run-once chain
│   └── ui.py             → ANSI terminal output helpers
├── hnet.config.json      → sample config (edit this)
├── .env.example          → env var reference
└── pyproject.toml        → pip package (zero runtime deps)
```

---

## ➕ Adding a Custom Tool

Open [`hornet/tools.py`](hornet/tools.py) and add to `build_registry()`:

```python
from hornet.tools import ToolDef, Risk

reg.register(ToolDef(
    name="my_tool",
    description="What it does — shown to the AI for tool selection.",
    phase=["enumeration"],           # recon / enumeration / exploitation / post-exploitation
    risk=Risk.SAFE,                  # or Risk.CONFIRM
    schema={
        "target": {"type": "str", "description": "Target host", "required": True},
    },
    executor=lambda args, state: _run(["mytool", args["target"]]),
    parser=None,                     # optional: callable(raw, state) -> summary string
))
```

No other file needs to change.

---

## 📜 License

MIT — free to use, modify, and distribute.

---

<div align="center">

**Made for CTF players on Kali Linux 🐉**  
[Ghost-101-ui](https://github.com/Ghost-101-ui) · [HorN3t](https://github.com/Ghost-101-ui/HorN3t)

</div>
