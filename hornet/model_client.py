"""
HorNet model client — thin OpenAI-compatible wrapper (stdlib urllib only).

Supports:
  • Local Ollama  (base_url=http://localhost:11434/v1, api_key="ollama")
  • OpenRouter    (base_url=https://openrouter.ai/api/v1, api_key=<key>)
  • Any OpenAI-compatible endpoint
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from hornet.config import ProviderConfig


# ── Message helpers ──────────────────────────────────────────────────────────

def system_msg(content: str) -> dict:
    return {"role": "system", "content": content}


def user_msg(content: str) -> dict:
    return {"role": "user", "content": content}


def assistant_msg(content: str) -> dict:
    return {"role": "assistant", "content": content}


def tool_result_msg(content: str) -> dict:
    """Injects tool results as a user-turn message (works across providers)."""
    return {"role": "user", "content": f"[TOOL RESULT]\n{content}"}


# ── Response dataclass ───────────────────────────────────────────────────────

@dataclass
class ModelResponse:
    content: str            # raw text from the model
    tool_call: Optional[dict] = None   # parsed {"tool": ..., "args": {...}} or None
    raw: Optional[dict] = None         # full JSON response for debug


# ── Client ───────────────────────────────────────────────────────────────────

class ModelClient:
    """Minimal OpenAI-compatible chat client using stdlib urllib."""

    def __init__(self, cfg: ProviderConfig) -> None:
        self.cfg = cfg
        self._endpoint = cfg.base_url.rstrip("/") + "/chat/completions"

    # ── Low-level HTTP ───────────────────────────────────────────────────────

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key or 'none'}",
        }
        # OpenRouter specific headers (ignored by other providers)
        if "openrouter" in self.cfg.base_url:
            headers["HTTP-Referer"] = "https://github.com/hornet-ctf"
            headers["X-Title"]      = "HorNet CTF Copilot"

        req = urllib.request.Request(
            self._endpoint,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"LLM API error {exc.code}: {err_body[:400]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach LLM endpoint {self._endpoint!r}: {exc.reason}"
            ) from exc

    # ── Tool-call parsing ────────────────────────────────────────────────────

    @staticmethod
    def _parse_tool_call(text: str) -> Optional[dict]:
        """
        Extract a JSON tool call from model output.

        Accepts:
          • Fenced code block:  ```json\n{"tool": ..., "args": {...}}\n```
          • Bare JSON object starting with {"tool":
        """
        import re

        # Try fenced block first
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if fence:
            raw_json = fence.group(1)
        else:
            # Try bare JSON — find first { ... } that has a "tool" key
            bare = re.search(r"(\{[^{}]*\"tool\"[^{}]*\})", text, re.DOTALL)
            if not bare:
                return None
            raw_json = bare.group(1)

        try:
            obj = json.loads(raw_json)
        except json.JSONDecodeError:
            return None

        if isinstance(obj, dict) and "tool" in obj:
            obj.setdefault("args", {})
            return obj
        return None

    # ── Public API ───────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        *,
        stop_sequences: Optional[list[str]] = None,
    ) -> ModelResponse:
        """Send a chat request and return a parsed ModelResponse."""
        payload: dict[str, Any] = {
            "model":       self.cfg.model,
            "messages":    messages,
            "max_tokens":  self.cfg.max_tokens,
            "temperature": self.cfg.temperature,
        }
        if stop_sequences:
            payload["stop"] = stop_sequences

        raw = self._post(payload)
        content = raw["choices"][0]["message"]["content"] or ""
        tool_call = self._parse_tool_call(content)

        return ModelResponse(content=content, tool_call=tool_call, raw=raw)

    def ping(self) -> bool:
        """Check if the endpoint is reachable with a minimal request."""
        try:
            self.chat([user_msg("ping")])
            return True
        except Exception:
            return False

    # ── Streaming (optional, for long outputs) ───────────────────────────────

    def stream_chat(
        self,
        messages: list[dict],
    ) -> Iterator[str]:
        """Yield text chunks as they arrive (SSE streaming)."""
        payload: dict[str, Any] = {
            "model":       self.cfg.model,
            "messages":    messages,
            "max_tokens":  self.cfg.max_tokens,
            "temperature": self.cfg.temperature,
            "stream":      True,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key or 'none'}",
        }
        req = urllib.request.Request(
            self._endpoint, data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.cfg.timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError):
                        continue
