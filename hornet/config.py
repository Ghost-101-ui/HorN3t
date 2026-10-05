"""
HorNet configuration loader.

Priority (highest → lowest):
  1. CLI flags (--model, --local, --online)
  2. Environment variables (HNET_* prefix)
  3. hnet.config.json in CWD or home dir
  4. Baked-in defaults (local Ollama)
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, field
from typing import Optional

# ── Defaults ────────────────────────────────────────────────────────────────

_DEFAULT_LOCAL_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_LOCAL_MODEL    = "llama3"
_DEFAULT_ONLINE_PROVIDER = "openrouter"
_DEFAULT_ONLINE_MODEL   = "anthropic/claude-3-haiku"
_CONFIG_FILENAME        = "hnet.config.json"


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    name: str                        # "ollama" | "openrouter" | custom
    base_url: str
    model: str
    api_key: Optional[str] = None
    timeout: int = 120
    max_tokens: int = 2048
    temperature: float = 0.2


@dataclass
class HNetConfig:
    provider: ProviderConfig
    session_dir: pathlib.Path = field(default_factory=lambda: pathlib.Path.home() / ".hornet" / "sessions")
    log_dir: pathlib.Path     = field(default_factory=lambda: pathlib.Path.home() / ".hornet" / "logs")
    max_loop_steps: int = 20
    debug: bool = False


# ── Loader ───────────────────────────────────────────────────────────────────

def _find_config_file() -> Optional[pathlib.Path]:
    """Search CWD then home for hnet.config.json."""
    for base in (pathlib.Path.cwd(), pathlib.Path.home()):
        p = base / _CONFIG_FILENAME
        if p.exists():
            return p
    return None


def _load_json_config(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_config(
    *,
    force_local: bool = False,
    force_online: bool = False,
    override_model: Optional[str] = None,
    override_base_url: Optional[str] = None,
) -> HNetConfig:
    """
    Build and return a HNetConfig, merging all sources.

    Parameters
    ----------
    force_local   : If True, use local Ollama regardless of config.
    force_online  : If True, use the configured online provider.
    override_model: Model name from --model CLI flag.
    """
    raw: dict = {}
    cfg_path = _find_config_file()
    if cfg_path:
        raw = _load_json_config(cfg_path)

    # ── Determine provider mode ──────────────────────────────────────────────
    if force_local:
        mode = "local"
    elif force_online:
        mode = "online"
    else:
        mode = os.environ.get(
            "HNET_MODE",
            raw.get("mode", "local"),
        )

    if mode == "local":
        prov_raw = raw.get("local", {})
        base_url = (
            override_base_url
            or os.environ.get("HNET_BASE_URL")
            or prov_raw.get("base_url", _DEFAULT_LOCAL_BASE_URL)
        )
        model = (
            override_model
            or os.environ.get("HNET_MODEL")
            or prov_raw.get("model", _DEFAULT_LOCAL_MODEL)
        )
        api_key = os.environ.get("HNET_API_KEY") or prov_raw.get("api_key", "ollama")
        provider = ProviderConfig(
            name="ollama",
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=int(prov_raw.get("timeout", 120)),
            max_tokens=int(prov_raw.get("max_tokens", 2048)),
            temperature=float(prov_raw.get("temperature", 0.2)),
        )
    else:
        # online — default to OpenRouter
        prov_name = os.environ.get("HNET_PROVIDER") or raw.get("provider", _DEFAULT_ONLINE_PROVIDER)
        prov_raw  = raw.get(prov_name, raw.get("online", {}))

        # OpenRouter base_url
        default_url = "https://openrouter.ai/api/v1"
        base_url = (
            override_base_url
            or os.environ.get("HNET_BASE_URL")
            or prov_raw.get("base_url", default_url)
        )
        model = (
            override_model
            or os.environ.get("HNET_MODEL")
            or prov_raw.get("model", _DEFAULT_ONLINE_MODEL)
        )
        api_key = os.environ.get("HNET_API_KEY") or prov_raw.get("api_key", "")
        provider = ProviderConfig(
            name=prov_name,
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout=int(prov_raw.get("timeout", 60)),
            max_tokens=int(prov_raw.get("max_tokens", 2048)),
            temperature=float(prov_raw.get("temperature", 0.2)),
        )

    # ── Misc config ──────────────────────────────────────────────────────────
    session_dir = pathlib.Path(
        os.environ.get("HNET_SESSION_DIR")
        or raw.get("session_dir", str(pathlib.Path.home() / ".hornet" / "sessions"))
    )
    log_dir = pathlib.Path(
        os.environ.get("HNET_LOG_DIR")
        or raw.get("log_dir", str(pathlib.Path.home() / ".hornet" / "logs"))
    )

    return HNetConfig(
        provider=provider,
        session_dir=session_dir,
        log_dir=log_dir,
        max_loop_steps=int(raw.get("max_loop_steps", 20)),
        debug=bool(os.environ.get("HNET_DEBUG") or raw.get("debug", False)),
    )
