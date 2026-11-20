"""Gymnasium adapter for AuditGym (optional dependency — never imported by src/).

Spaces
------
- ``observation_space``: ``gymnasium.spaces.Text`` containing the canonical ASCII-safe
  JSON serialization of the ``AuditEnv`` observation dict.
- ``action_space``:
  - ``action_mode="text"`` (default): ``gymnasium.spaces.Text`` containing a JSON-encoded
    tool call, e.g. ``{"tool": "list_records", "args": {"table": "ledger", "limit": 50}}``.
    Malformed JSON strings are forwarded as an unknown tool so ``AuditEnv`` answers with a
    bounded error instead of raising.
  - ``action_mode="discrete"``: ``gymnasium.spaces.Discrete(6)`` mapping six canonical
    actions (0..3 list each table, 4 calculator, 5 submit empty findings) for quick
    RL-framework smoke tests.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - optional dependency
    gym = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]

from auditgym.env.env import AuditEnv

# Printable ASCII (0x20..0x7E) matches json.dumps(..., ensure_ascii=True).
_ASCII_CHARSET = "".join(chr(c) for c in range(32, 127))

_DISCRETE_ACTIONS = (
    {"tool": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 50}},
    {"tool": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 50}},
    {"tool": "list_records", "args": {"table": "payments", "cursor": None, "limit": 50}},
    {"tool": "list_records", "args": {"table": "fx", "cursor": None, "limit": 50}},
    {"tool": "calculator", "args": {"expression": "1 + 1"}},
    None,  # 5 -> submit empty findings for the current episode_id
)

_BaseEnv = gym.Env if gym is not None else object


class AuditGymEnv(_BaseEnv):  # type: ignore[misc]
    """Gymnasium-compatible wrapper around :class:`auditgym.env.env.AuditEnv`."""

    metadata = {"render_modes": ["ansi"], "render_fps": 1}

    def __init__(
        self,
        mode: str = "open",
        action_mode: str = "text",
        default_config: Optional[Dict[str, Any]] = None,
        render_mode: Optional[str] = None,
    ) -> None:
        if gym is None or spaces is None:
            raise ImportError(
                "gymnasium is required for AuditGymEnv; install it with `pip install gymnasium`"
            )
        if action_mode not in ("text", "discrete"):
            raise ValueError("action_mode must be 'text' or 'discrete'")
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(f"unsupported render_mode: {render_mode!r}")

        super().__init__()
        self.action_mode = action_mode
        self.render_mode = render_mode
        self._default_config = dict(default_config) if default_config is not None else {}
        self._env = AuditEnv(mode=mode)
        self._episode_id: Optional[str] = None
        self._last_obs: str = "{}"

        self.observation_space = spaces.Text(
            min_length=2,
            max_length=2_000_000,
            charset=_ASCII_CHARSET,
        )
        if action_mode == "discrete":
            self.action_space = spaces.Discrete(len(_DISCRETE_ACTIONS))
        else:
            self.action_space = spaces.Text(
                min_length=2,
                max_length=100_000,
                charset=_ASCII_CHARSET,
            )

    def _encode_obs(self, obs: Dict[str, Any]) -> str:
        text = json.dumps(obs, ensure_ascii=True, sort_keys=True)
        self._last_obs = text
        return text

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, Dict[str, Any]]:
        super().reset(seed=seed)
        ep_seed = int(seed) if seed is not None else int(self.np_random.integers(0, 2**31 - 1))
        cfg = (options or {}).get("config", self._default_config)
        obs, info = self._env.reset(seed=ep_seed, config=cfg)
        self._episode_id = (
            obs.get("result", {}).get("manifest", {}).get("episode_id")
            if isinstance(obs, dict)
            else None
        )
        return self._encode_obs(obs), dict(info)

    def step(self, action: Any) -> Tuple[str, float, bool, bool, Dict[str, Any]]:
        if self.action_mode == "discrete":
            idx = int(action)
            if idx == len(_DISCRETE_ACTIONS) - 1:
                act: Any = {
                    "tool": "submit",
                    "args": {"findings": {"episode_id": self._episode_id or "", "findings": []}},
                }
            elif 0 <= idx < len(_DISCRETE_ACTIONS):
                act = _DISCRETE_ACTIONS[idx]
            else:
                act = {"tool": "__invalid__", "args": {}}
        else:
            if isinstance(action, str):
                try:
                    act = json.loads(action)
                except ValueError:
                    act = {"tool": "__invalid__", "args": {}}
            else:
                act = action

        obs, reward, terminated, truncated, info = self._env.step(act)
        return self._encode_obs(obs), float(reward), bool(terminated), bool(truncated), dict(info)

    def render(self) -> Optional[str]:
        if self.render_mode == "ansi":
            return self._last_obs
        return None

    def close(self) -> None:
        self._env.close()


__all__ = ["AuditGymEnv"]
