"""
HorNet tool registry.

Each tool is a ToolDef with:
  name         – unique slug
  description  – shown to the model in the system prompt
  phase        – CTF phase tag(s): recon | enumeration | exploitation | post-exploitation
  risk         – SAFE (auto-run) | CONFIRM (requires user gate)
  schema       – input field definitions {field: {type, description, required}}
  executor     – callable(args: dict, state: SessionState) -> str (raw output)
  parser       – optional callable(raw: str, state: SessionState) -> str (summary)
"""

from __future__ import annotations

import subprocess
import shlex
import re
import textwrap
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from hornet.state import SessionState


# ── Risk tiers ───────────────────────────────────────────────────────────────

class Risk(str, Enum):
    SAFE    = "SAFE"
    CONFIRM = "CONFIRM"


# ── ToolDef ──────────────────────────────────────────────────────────────────

@dataclass
class ToolDef:
    name: str
    description: str
    phase: list[str]                          # e.g. ["recon", "enumeration"]
    risk: Risk
    schema: dict[str, dict]                   # field → {type, description, required}
    executor: Callable[[dict, SessionState], str]
    parser: Optional[Callable[[str, SessionState], str]] = None


# ── Registry ─────────────────────────────────────────────────────────────────

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, tool: ToolDef) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDef]:
        return self._tools.get(name)

    def list_for_phase(self, phase: str) -> list[ToolDef]:
        """Return all tools applicable to the given phase (plus 'any')."""
        return [
            t for t in self._tools.values()
            if phase in t.phase or "any" in t.phase
        ]

    def all_tools(self) -> list[ToolDef]:
        return list(self._tools.values())

    def tool_prompt_block(self, phase: str) -> str:
        """Build the tool-listing section injected into the system prompt."""
        tools = self.list_for_phase(phase)
        lines = ["Available tools for phase «" + phase + "»:\n"]
        for t in tools:
            required_fields = [
                f"{k} ({v['type']}{'*' if v.get('required') else '?'})"
                for k, v in t.schema.items()
            ]
            lines.append(
                f"  [{t.risk.value}] {t.name}({', '.join(required_fields)})\n"
                f"    {t.description}\n"
            )
        lines.append(
            "\nTo invoke a tool, reply with ONLY this JSON (nothing else):\n"
            '```json\n{"tool": "<name>", "args": {<key: value>}}\n```\n'
            "If no tool fits, reply with plain text — the escalation chain handles it."
        )
        return "\n".join(lines)


# ── Shared subprocess helper ──────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 180) -> str:
    """Run a subprocess and return combined stdout+stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout + result.stderr
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT after {timeout}s — try narrowing scope]"
    except FileNotFoundError:
        return f"[ERROR] Command not found: {cmd[0]!r} — is it installed?"
    except Exception as exc:
        return f"[ERROR] {exc}"


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_nmap(raw: str, state: SessionState) -> str:
    """Extract open ports + services from nmap output, update state."""
    ports: list[int] = []
    lines: list[str] = []
    for line in raw.splitlines():
        m = re.match(r"(\d+)/tcp\s+open\s+(\S+)", line)
        if m:
            port, svc = int(m.group(1)), m.group(2)
            ports.append(port)
            state.record_service(port, svc)
            lines.append(f"  {port}/tcp → {svc}")
    if ports:
        state.record_ports(ports)
    summary = f"Open ports ({len(ports)}):\n" + "\n".join(lines) if lines else "No open ports detected."
    return summary


def _parse_gobuster(raw: str, state: SessionState) -> str:
    """Extract discovered paths from gobuster output."""
    found = [ln for ln in raw.splitlines() if ln.strip().startswith("/")]
    if not found:
        return "No paths discovered (or wordlist exhausted)."
    return f"Discovered {len(found)} path(s):\n" + "\n".join(f"  {p}" for p in found[:40])


def _parse_nikto(raw: str, state: SessionState) -> str:
    """Summarise nikto findings."""
    findings = [ln for ln in raw.splitlines() if "+ " in ln]
    if not findings:
        return "No significant findings from nikto."
    top = findings[:20]
    summary = f"Nikto findings ({len(findings)} total, showing {len(top)}):\n"
    return summary + "\n".join(f"  {f.strip()}" for f in top)


def _parse_searchsploit(raw: str, state: SessionState) -> str:
    """Extract exploit titles from searchsploit output."""
    lines = [ln for ln in raw.splitlines() if "|" in ln and "Title" not in ln]
    if not lines:
        return "No exploits found."
    return f"Exploits found ({len(lines)}):\n" + "\n".join(f"  {ln.strip()}" for ln in lines[:20])


def _parse_hydra(raw: str, state: SessionState) -> str:
    """Extract cracked credentials from hydra output."""
    creds = [ln for ln in raw.splitlines() if "[" in ln and "host:" in ln.lower()]
    if not creds:
        # also check for the summary line
        for ln in raw.splitlines():
            if "valid password" in ln.lower() or "login:" in ln.lower():
                creds.append(ln.strip())
    if not creds:
        return "No credentials cracked."
    return "Cracked credentials:\n" + "\n".join(f"  {c.strip()}" for c in creds)


# ── Tool executors ─────────────────────────────────────────────────────────────

def _exec_nmap(args: dict, state: SessionState) -> str:
    target  = args.get("target") or state.target
    ports   = args.get("ports", "")
    flags   = args.get("flags", "-sV -T4")
    cmd = ["nmap"] + shlex.split(flags)
    if ports:
        cmd += ["-p", str(ports)]
    cmd.append(target)
    return _run(cmd, timeout=300)


def _exec_gobuster(args: dict, state: SessionState) -> str:
    target    = args.get("target") or state.target
    wordlist  = args.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
    ext       = args.get("extensions", "")
    cmd = ["gobuster", "dir", "-u", target, "-w", wordlist, "-q", "--no-error"]
    if ext:
        cmd += ["-x", ext]
    return _run(cmd, timeout=600)


def _exec_nikto(args: dict, state: SessionState) -> str:
    target = args.get("target") or state.target
    port   = args.get("port", "")
    cmd = ["nikto", "-h", target]
    if port:
        cmd += ["-p", str(port)]
    return _run(cmd, timeout=300)


def _exec_searchsploit(args: dict, state: SessionState) -> str:
    query = args.get("query", "")
    cmd   = ["searchsploit", "--colour", query]
    return _run(cmd, timeout=30)


def _exec_curl(args: dict, state: SessionState) -> str:
    url     = args.get("url", "")
    method  = args.get("method", "GET")
    headers = args.get("headers", {})
    data    = args.get("data", "")
    cmd = ["curl", "-s", "-L", "-X", method]
    for k, v in (headers.items() if isinstance(headers, dict) else []):
        cmd += ["-H", f"{k}: {v}"]
    if data:
        cmd += ["-d", data]
    cmd.append(url)
    return _run(cmd, timeout=30)


def _exec_ssh_try(args: dict, state: SessionState) -> str:
    host     = args.get("host") or state.target
    user     = args.get("username", "root")
    password = args.get("password", "")
    port     = args.get("port", 22)
    # Use sshpass for password-based attempts
    cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-p", str(port),
        f"{user}@{host}",
        "id",
    ]
    return _run(cmd, timeout=20)


def _exec_hydra(args: dict, state: SessionState) -> str:
    target   = args.get("target") or state.target
    service  = args.get("service", "ssh")
    user     = args.get("username", "")
    userlist = args.get("userlist", "")
    passlist = args.get("passlist", "/usr/share/wordlists/rockyou.txt")
    port     = args.get("port", "")
    cmd      = ["hydra", "-t", "4", "-f"]
    if user:
        cmd += ["-l", user]
    elif userlist:
        cmd += ["-L", userlist]
    if passlist:
        cmd += ["-P", passlist]
    if port:
        cmd += ["-s", str(port)]
    cmd.append(target)
    cmd.append(service)
    return _run(cmd, timeout=600)


def _exec_sqlmap(args: dict, state: SessionState) -> str:
    url    = args.get("url", "")
    data   = args.get("data", "")
    level  = args.get("level", 1)
    risk   = args.get("risk", 1)
    cmd    = ["sqlmap", "-u", url, "--batch", f"--level={level}", f"--risk={risk}", "--output-dir=/tmp/sqlmap"]
    if data:
        cmd += ["--data", data]
    return _run(cmd, timeout=300)


def _exec_wfuzz(args: dict, state: SessionState) -> str:
    url      = args.get("url", "")
    wordlist = args.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
    hc       = args.get("hide_codes", "404")
    cmd = ["wfuzz", "-c", "-z", f"file,{wordlist}", "--hc", str(hc), url]
    return _run(cmd, timeout=300)


def _exec_enum4linux(args: dict, state: SessionState) -> str:
    target = args.get("target") or state.target
    flags  = args.get("flags", "-a")
    cmd    = ["enum4linux", flags, target]
    return _run(cmd, timeout=120)


def _exec_smbclient(args: dict, state: SessionState) -> str:
    target = args.get("target") or state.target
    share  = args.get("share", "")
    cmd    = ["smbclient", "-L", f"//{target}", "-N"]
    if share:
        cmd = ["smbclient", f"//{target}/{share}", "-N", "-c", "ls"]
    return _run(cmd, timeout=30)


def _exec_ffuf(args: dict, state: SessionState) -> str:
    url      = args.get("url", "")
    wordlist = args.get("wordlist", "/usr/share/wordlists/dirb/common.txt")
    ext      = args.get("extensions", "")
    mc       = args.get("match_codes", "200,301,302,403")
    cmd      = ["ffuf", "-w", wordlist, "-u", url, "-mc", str(mc), "-s"]
    if ext:
        cmd += ["-e", ext]
    return _run(cmd, timeout=300)


def _exec_whatweb(args: dict, state: SessionState) -> str:
    target = args.get("target") or state.target
    cmd    = ["whatweb", "-a", "3", target]
    return _run(cmd, timeout=30)


def _exec_linpeas(args: dict, state: SessionState) -> str:
    """Run linpeas.sh if available locally."""
    path = args.get("path", "/tmp/linpeas.sh")
    cmd  = ["bash", path]
    return _run(cmd, timeout=300)


def _exec_find_suid(args: dict, state: SessionState) -> str:
    path = args.get("path", "/")
    cmd  = ["find", path, "-perm", "-u=s", "-type", "f", "2>/dev/null"]
    # subprocess needs a real list — use shell=True for redirection
    result = subprocess.run(
        f"find {path} -perm -u=s -type f 2>/dev/null",
        shell=True, capture_output=True, text=True, timeout=60,
    )
    return (result.stdout + result.stderr).strip() or "No SUID binaries found."


def _exec_netcat_banner(args: dict, state: SessionState) -> str:
    host = args.get("host") or state.target
    port = args.get("port", 80)
    cmd  = ["bash", "-c", f"echo '' | nc -w 3 {host} {port}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    return (result.stdout + result.stderr).strip() or "(no banner)"


# ── Build & return registry ───────────────────────────────────────────────────

def build_registry() -> ToolRegistry:
    reg = ToolRegistry()

    # ── RECON ────────────────────────────────────────────────────────────────

    reg.register(ToolDef(
        name="nmap_scan",
        description=(
            "Port scan a target with nmap. Use for initial recon and service discovery. "
            "flags default to '-sV -T4'. Specify ports='1-1000' to narrow scope."
        ),
        phase=["recon", "enumeration"],
        risk=Risk.SAFE,
        schema={
            "target":  {"type": "str", "description": "IP or hostname (defaults to session target)", "required": False},
            "ports":   {"type": "str", "description": "Port range e.g. '22,80,443' or '1-65535'",   "required": False},
            "flags":   {"type": "str", "description": "Extra nmap flags",                             "required": False},
        },
        executor=_exec_nmap,
        parser=_parse_nmap,
    ))

    reg.register(ToolDef(
        name="whatweb_scan",
        description="Fingerprint web technologies on a target URL/IP.",
        phase=["recon", "enumeration"],
        risk=Risk.SAFE,
        schema={
            "target": {"type": "str", "description": "URL or IP", "required": True},
        },
        executor=_exec_whatweb,
        parser=None,
    ))

    reg.register(ToolDef(
        name="netcat_banner",
        description="Grab a service banner from a host:port using netcat.",
        phase=["recon"],
        risk=Risk.SAFE,
        schema={
            "host": {"type": "str", "description": "Target host", "required": True},
            "port": {"type": "int", "description": "Port number",  "required": True},
        },
        executor=_exec_netcat_banner,
        parser=None,
    ))

    # ── ENUMERATION ──────────────────────────────────────────────────────────

    reg.register(ToolDef(
        name="gobuster_dir",
        description=(
            "Directory/file brute-force on a web server. "
            "Provide a full URL (http://...). Optionally specify extensions like 'php,html'."
        ),
        phase=["enumeration"],
        risk=Risk.SAFE,
        schema={
            "target":     {"type": "str", "description": "Full URL to scan",         "required": True},
            "wordlist":   {"type": "str", "description": "Wordlist path",            "required": False},
            "extensions": {"type": "str", "description": "File extensions to fuzz",  "required": False},
        },
        executor=_exec_gobuster,
        parser=_parse_gobuster,
    ))

    reg.register(ToolDef(
        name="ffuf_fuzz",
        description=(
            "Fast web fuzzer. Use FUZZ keyword in URL. "
            "Example: url='http://10.0.0.1/FUZZ'"
        ),
        phase=["enumeration"],
        risk=Risk.SAFE,
        schema={
            "url":          {"type": "str", "description": "URL with FUZZ placeholder", "required": True},
            "wordlist":     {"type": "str", "description": "Wordlist path",              "required": False},
            "extensions":   {"type": "str", "description": "e.g. 'php,txt'",            "required": False},
            "match_codes":  {"type": "str", "description": "HTTP codes to match",       "required": False},
        },
        executor=_exec_ffuf,
        parser=None,
    ))

    reg.register(ToolDef(
        name="nikto_scan",
        description="Web server vulnerability scanner. Checks for misconfigs, outdated software, dangerous files.",
        phase=["enumeration"],
        risk=Risk.SAFE,
        schema={
            "target": {"type": "str", "description": "IP or hostname", "required": True},
            "port":   {"type": "int", "description": "HTTP port",      "required": False},
        },
        executor=_exec_nikto,
        parser=_parse_nikto,
    ))

    reg.register(ToolDef(
        name="searchsploit",
        description="Search Exploit-DB for known CVEs/exploits matching a keyword (e.g. 'vsftpd 2.3.4', 'OpenSSH 7.2').",
        phase=["enumeration", "exploitation"],
        risk=Risk.SAFE,
        schema={
            "query": {"type": "str", "description": "Software name + version to search", "required": True},
        },
        executor=_exec_searchsploit,
        parser=_parse_searchsploit,
    ))

    reg.register(ToolDef(
        name="curl_fetch",
        description="HTTP request with curl. Use for testing endpoints, grabbing pages, uploading data.",
        phase=["enumeration", "exploitation", "any"],
        risk=Risk.SAFE,
        schema={
            "url":     {"type": "str",  "description": "Full URL",                          "required": True},
            "method":  {"type": "str",  "description": "HTTP method (GET/POST/PUT/DELETE)", "required": False},
            "headers": {"type": "dict", "description": "HTTP headers dict",                 "required": False},
            "data":    {"type": "str",  "description": "POST body",                        "required": False},
        },
        executor=_exec_curl,
        parser=None,
    ))

    reg.register(ToolDef(
        name="enum4linux",
        description="SMB/NetBIOS enumeration for Windows/Samba hosts. Extracts shares, users, password policy.",
        phase=["enumeration"],
        risk=Risk.SAFE,
        schema={
            "target": {"type": "str", "description": "IP of SMB host",   "required": True},
            "flags":  {"type": "str", "description": "enum4linux flags", "required": False},
        },
        executor=_exec_enum4linux,
        parser=None,
    ))

    reg.register(ToolDef(
        name="smbclient_list",
        description="List or browse SMB shares on a target host.",
        phase=["enumeration"],
        risk=Risk.SAFE,
        schema={
            "target": {"type": "str", "description": "IP or hostname",    "required": True},
            "share":  {"type": "str", "description": "Share name to list", "required": False},
        },
        executor=_exec_smbclient,
        parser=None,
    ))

    reg.register(ToolDef(
        name="wfuzz_fuzz",
        description="Web fuzzer with flexible payload injection. Use FUZZ keyword in URL.",
        phase=["enumeration"],
        risk=Risk.SAFE,
        schema={
            "url":        {"type": "str", "description": "URL with FUZZ keyword",     "required": True},
            "wordlist":   {"type": "str", "description": "Wordlist path",             "required": False},
            "hide_codes": {"type": "str", "description": "HTTP codes to hide (e.g. 404)", "required": False},
        },
        executor=_exec_wfuzz,
        parser=None,
    ))

    # ── EXPLOITATION ─────────────────────────────────────────────────────────

    reg.register(ToolDef(
        name="ssh_try",
        description="Try a single SSH login with username/password. For brute-forcing use hydra_bruteforce.",
        phase=["exploitation"],
        risk=Risk.CONFIRM,
        schema={
            "host":     {"type": "str", "description": "Target host",      "required": True},
            "username": {"type": "str", "description": "SSH username",     "required": True},
            "password": {"type": "str", "description": "SSH password",     "required": True},
            "port":     {"type": "int", "description": "SSH port (def 22)","required": False},
        },
        executor=_exec_ssh_try,
        parser=None,
    ))

    reg.register(ToolDef(
        name="hydra_bruteforce",
        description=(
            "Credential brute-force with Hydra. Supports ssh, ftp, http-post-form, etc. "
            "Provide either username or userlist, and a password list."
        ),
        phase=["exploitation"],
        risk=Risk.CONFIRM,
        schema={
            "target":   {"type": "str", "description": "Target IP/host",         "required": True},
            "service":  {"type": "str", "description": "Protocol (ssh/ftp/...)", "required": True},
            "username": {"type": "str", "description": "Single username",        "required": False},
            "userlist": {"type": "str", "description": "Username list file",     "required": False},
            "passlist": {"type": "str", "description": "Password list file",     "required": False},
            "port":     {"type": "int", "description": "Service port",           "required": False},
        },
        executor=_exec_hydra,
        parser=_parse_hydra,
    ))

    reg.register(ToolDef(
        name="sqlmap_scan",
        description=(
            "Automated SQL injection scanner. Use on a URL with parameter. "
            "CONFIRM tier — sends active payloads."
        ),
        phase=["exploitation"],
        risk=Risk.CONFIRM,
        schema={
            "url":   {"type": "str", "description": "Target URL with params (e.g. ?id=1)", "required": True},
            "data":  {"type": "str", "description": "POST data string",                    "required": False},
            "level": {"type": "int", "description": "Test level 1-5",                     "required": False},
            "risk":  {"type": "int", "description": "Risk level 1-3",                     "required": False},
        },
        executor=_exec_sqlmap,
        parser=None,
    ))

    # ── POST-EXPLOITATION ────────────────────────────────────────────────────

    reg.register(ToolDef(
        name="find_suid",
        description="Find SUID binaries on the local system — useful for privilege escalation.",
        phase=["post-exploitation"],
        risk=Risk.SAFE,
        schema={
            "path": {"type": "str", "description": "Search root (default /)", "required": False},
        },
        executor=_exec_find_suid,
        parser=None,
    ))

    reg.register(ToolDef(
        name="linpeas_run",
        description="Run linpeas.sh for Linux privilege escalation enumeration. Script must exist at path.",
        phase=["post-exploitation"],
        risk=Risk.CONFIRM,
        schema={
            "path": {"type": "str", "description": "Path to linpeas.sh", "required": False},
        },
        executor=_exec_linpeas,
        parser=None,
    ))

    return reg
