"""A local LLM as an agent, in-process, through the Ollama server on this machine (inference only, no training).

Same prompting as ``examples/llm_agent.py`` (the stdin/stdout version), but a ``Policy`` the harness can run
directly, so it also works in the frozen desktop build. Standard library only.

Bounds: the server is always http://127.0.0.1:11434 (``AUDITGYM_OLLAMA_URL`` may move it, for tests, but only to
another port on 127.0.0.1 / localhost); every request has a timeout no longer than the time the episode has
left; the env's own step and time limits stay in force. Any HTTP or JSON failure, or an answer that is not one
JSON action, ends the episode with an empty (valid) submission: an honest result, never a crash.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..env.env import MAX_SECONDS
from .baselines import Policy

DEFAULT_URL = "http://127.0.0.1:11434"
LOCAL_HOSTS = ("127.0.0.1", "localhost")
# Ollama names: "qwen2.5:1.5b", "llama3.2:latest", "hf.co/user/Model-GGUF:Q4_K_M". Nothing else gets through.
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(/[A-Za-z0-9][A-Za-z0-9._-]{0,63}){0,3}(:[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$")
MAX_NAME = 120

SYSTEM = ("You are a financial audit agent in a sandbox. Investigate the books with the tools and then submit "
          "findings. Reply with ONE JSON object only, exactly {\"tool\": <name>, \"args\": {...}}. No prose.")
TEMPERATURE = 0.2
MAX_TOKENS = 512
HISTORY = 6            # recent steps the model sees
REQUEST_TIMEOUT = 45.0  # seconds per request, and never past the episode's own time limit
MARGIN = 3.0            # submit this long before the env's time limit, so the submission still counts


def ollama_url() -> str:
    """The local Ollama base URL. ``AUDITGYM_OLLAMA_URL`` is honoured only for http on 127.0.0.1 / localhost."""
    raw = os.environ.get("AUDITGYM_OLLAMA_URL")
    if not raw:
        return DEFAULT_URL
    try:
        u = urllib.parse.urlsplit(raw)
        port = u.port
    except ValueError:
        return DEFAULT_URL
    if u.scheme != "http" or u.hostname not in LOCAL_HOSTS or u.username or u.password or u.path not in ("", "/") \
            or u.query or u.fragment:
        return DEFAULT_URL
    return f"http://{u.hostname}" + (f":{port}" if port else "")


def _opener() -> urllib.request.OpenerDirector:
    # Ollama is local: never route it through an HTTP(S)_PROXY from the environment.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def valid_model_name(name: Any) -> bool:
    return isinstance(name, str) and len(name) <= MAX_NAME and ".." not in name and bool(MODEL_NAME.fullmatch(name))


def agent_name(model: str) -> str:
    """Agent name recorded in the run: ``llm-<model>`` with everything but [a-z0-9.] turned into '-'."""
    slug = re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-.")[:48] or "model"
    return "llm-" + slug


def list_models(timeout: float = 1.0) -> Dict[str, Any]:
    """{"available": bool, "models": [names]} from the local server's /api/tags (short timeout, never raises)."""
    from ..scout import ollama_info  # the scout's probe: same parsing, same no-proxy opener
    info = ollama_info(ollama_url(), timeout)
    names = [m["name"] for m in info.get("models") or [] if valid_model_name(m.get("name"))]
    return {"available": bool(info.get("available")), "models": names}


def resolve_model(name: str, installed: List[str]) -> Optional[str]:
    """The installed name ``name`` refers to (exact, or with Ollama's implicit ":latest"), else None."""
    if name in installed:
        return name
    if ":" not in name and name + ":latest" in installed:
        return name + ":latest"
    return None


def chat(model: str, messages: List[Dict[str, str]], timeout: float, temperature: float = TEMPERATURE,
         max_tokens: int = MAX_TOKENS, url: Optional[str] = None) -> str:
    """One non-streaming /api/chat call in JSON mode; returns the reply text. Raises on any failure."""
    body = {"model": model, "messages": messages, "stream": False, "format": "json",
            "options": {"temperature": temperature, "num_predict": max_tokens, "seed": 0}}
    req = urllib.request.Request((url or ollama_url()) + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with _opener().open(req, timeout=timeout) as resp:
        text = json.loads(resp.read(4_000_000).decode("utf-8"))["message"]["content"]
    if not isinstance(text, str):
        raise ValueError("no text in the reply")
    return text


def short(obs: Any, limit: int = 2500) -> str:
    text = json.dumps(obs, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " …(truncated)"


def intro_of(first_obs: Dict[str, Any]) -> str:
    res = first_obs.get("result") if isinstance(first_obs.get("result"), dict) else {}
    return json.dumps({k: res.get(k) for k in ("task", "tools", "policy", "finding_schema", "finding_rules", "manifest")},
                      ensure_ascii=False)


def fix_submit(action: Dict[str, Any], episode_id: Any) -> Dict[str, Any]:
    """Put the episode id into a submit action (the model often forgets or garbles it)."""
    if action.get("tool") == "submit":
        args = action.get("args")
        if not isinstance(args, dict):
            args = action["args"] = {}
        f = args.get("findings")
        if isinstance(f, dict):
            f["episode_id"] = episode_id
        elif isinstance(f, list):
            args["findings"] = {"episode_id": episode_id, "findings": f}
    return action


class OllamaPolicy(Policy):
    """The local model picks every action; the harness and the env enforce the rules as for any agent."""
    name = "llm"

    def __init__(self, model: str, temperature: float = TEMPERATURE, max_tokens: int = MAX_TOKENS,
                 history: int = HISTORY, timeout: float = REQUEST_TIMEOUT,
                 episode_seconds: Optional[float] = MAX_SECONDS) -> None:
        if not valid_model_name(model):
            raise ValueError("bad model name")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.history_n = history
        self.timeout = timeout
        self.episode_seconds = episode_seconds
        self.last_error: Optional[str] = None

    def reset(self, first_obs):
        super().reset(first_obs)
        self.intro = intro_of(first_obs)
        self.history: List[Dict[str, str]] = []
        self.t0 = time.monotonic()
        self.url = ollama_url()

    def empty(self) -> Dict[str, Any]:
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": []}}}

    def act(self, obs):
        if obs is not self.first:
            self.history.append({"role": "user", "content": "Observation: " + short(obs)})
        left = obs.get("remaining_steps", 100) if isinstance(obs, dict) else 0
        left = left if isinstance(left, int) and not isinstance(left, bool) else 0
        time_left = float("inf")
        if self.episode_seconds is not None:
            time_left = self.episode_seconds - MARGIN - (time.monotonic() - self.t0)
        if left <= 2 or time_left < 1.0:
            return self.empty()
        timeout = min(self.timeout, time_left)
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"Episode setup: {self.intro}\nSteps left: {left}. episode_id = {self.episode_id}"}]
        messages += self.history[-2 * self.history_n:] if self.history_n > 0 else []
        try:
            reply = chat(self.model, messages, timeout, self.temperature, self.max_tokens, self.url)
            cand = json.loads(reply)
        except Exception as exc:  # noqa: BLE001 - HTTP, timeout, bad JSON: end the episode honestly
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return self.empty()
        if not (isinstance(cand, dict) and isinstance(cand.get("tool"), str)):
            self.last_error = "the reply is not a JSON action"
            return self.empty()
        self.history.append({"role": "assistant", "content": reply})
        return fix_submit(cand, self.episode_id)
