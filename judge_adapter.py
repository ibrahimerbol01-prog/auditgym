"""AuditGym judge adapter — the single entry point described in the organizers' check definitions
("Genesis FinTech: определения проверок", published Nov 20 2026, section "Единый способ подключения").

Run from the repository root (or the container's /app) with ``PYTHONPATH=src``; standard library only.

    generate_episode(seed, config, output_dir)        -> writes one episode into output_dir
    make_env()                                         -> object with reset(seed, config) and step(action)
    score_episode(episode_dir, findings, inspection_steps) -> {"tp","fp","fn","precision","recall","f1","return"}

The adapter only translates names and envelopes; it never chooses actions and never changes the task.

Translation table (canonical -> AuditGym):
    action envelope   {"name": n, "args": a}           -> {"tool": n, "args": a}
    tables            ledger, invoices, payments, fx   -> same names (no translation needed)
    list_records      {"rows": [...], "next_cursor"}   -> {"records": [...], "next_cursor"}
    get_record        the record object                -> unchanged
    get_document      the document object              -> unchanged
    calculator        {"value": "<decimal string>"}    -> "<decimal string>"
    submit            closed: {"accepted": true}; train: {"accepted": true, "report": {...}}
    errors            {"code", "message"}              -> {"result": null, "error": {...}}
Record keys: ledger row_id, invoices invoice_id, payments payment_id, fx "<date>|<source>|<target>",
documents doc_id. Error types (type field): duplicate_invoice, payment_allocation, date_or_fx,
period_classification.

Isolation: the evaluator (truth, provenance, scoring) runs in a separate process (auditgym.eval.service).
The environment object talks to it through a restricted channel that cannot read the reference. In
closed mode every reward returned to the policy is 0, including the terminal one; the true reward is
computed and logged by the evaluator. Observations and info never contain seed, paths or truth.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
from typing import Any, Dict, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from auditgym.env.env import MAX_STEPS, AuditEnv  # noqa: E402
from auditgym.eval.service import EvaluatorCore  # noqa: E402
from auditgym.gen.build import generate  # noqa: E402
from auditgym.gen.export import write_episode  # noqa: E402

TASK = (
    "Audit the books of one fictional company for one reporting period. Tables: ledger, invoices, payments, "
    "fx; documents by doc_id. Actions: list_records{table,cursor,limit<=50}, get_record{table,id}, "
    "get_document{doc_id}, calculator{expression}, submit{findings}. findings = {\"episode_id\": str, "
    "\"findings\": [{\"type\": duplicate_invoice|payment_allocation|date_or_fx|period_classification, "
    "\"affected_ids\": [str], \"claimed_amount_minor\": int, \"currency\": str, \"evidence_ids\": [str] (<=10), "
    "\"explanation\": str (<=1000)}] (<=30)}. Budget: 100 actions including submit; 60 seconds."
)


# ---------------------------------------------------------------- generation (jury side only)
def generate_episode(seed: int, config: dict, output_dir: str) -> None:
    """Write one episode (public: manifest, ledger, invoices, payments, fx, policy, documents;
    private: truth, provenance, clean books) directly into ``output_dir``. Thin wrapper over the
    team generator; the same seed and config always give the same episode."""
    ep = generate(seed, dict(config or {}))
    os.makedirs(output_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="auditgym-gen-")
    try:
        produced = write_episode(tmp, ep)
        for name in os.listdir(produced):
            dst = os.path.join(output_dir, name)
            if os.path.isdir(dst):
                shutil.rmtree(dst)
            shutil.move(os.path.join(produced, name), dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- environment
class JudgeEnv:
    """reset(seed, config) -> (observation, info); step(action) -> (obs, reward, terminated, truncated, info)."""

    def __init__(self) -> None:
        self._env: Optional[AuditEnv] = None
        self._mode: Optional[str] = None
        self._remaining = MAX_STEPS
        self._over = False

    def _env_for(self, mode: str) -> AuditEnv:
        if self._env is None or self._mode != mode:
            if self._env is not None:
                self._env.close()
            self._env = AuditEnv(mode="closed" if mode == "closed" else "open")
            self._mode = mode
        return self._env

    def reset(self, seed: Any = None, config: Any = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        cfg = config if isinstance(config, dict) else {}
        mode = "closed" if cfg.get("mode") == "closed" else "train"
        env = self._env_for(mode)
        team_config = cfg.get("team_config") if isinstance(cfg.get("team_config"), dict) else {}
        if isinstance(cfg.get("episode_dir"), str):
            obs, _ = env.reset(options={"episode_dir": cfg["episode_dir"]})
        else:
            obs, _ = env.reset(seed=seed, config=team_config)
        self._over = False
        self._remaining = MAX_STEPS
        if not obs.get("ok"):
            self._over = True
            return {"task": TASK, "manifest": None, "policy": None, "remaining_steps": 0,
                    "error": {"code": "bad_config", "message": "episode could not be created or loaded"}}, {}
        res = obs["result"]
        return {"task": TASK, "manifest": copy.deepcopy(res["manifest"]), "policy": copy.deepcopy(res["policy"]),
                "remaining_steps": MAX_STEPS}, {}

    def step(self, action: Any) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        if self._env is None:
            return {"result": None, "error": {"code": "episode_over", "message": "call reset first"},
                    "remaining_steps": 0}, 0.0, True, False, {}
        name = action.get("name") if isinstance(action, dict) else None
        args = action.get("args", {}) if isinstance(action, dict) else None
        internal: Any = {"tool": name if isinstance(name, str) else None, "args": args}
        obs, reward, terminated, truncated, _ = self._env.step(internal)
        remaining = obs.get("remaining_steps", 0) if isinstance(obs, dict) and obs else 0
        reward = 0.0 if self._mode == "closed" else float(reward)
        if truncated:
            self._over = True
            return {"result": None, "error": None, "remaining_steps": 0}, reward, False, True, {}
        if not obs.get("ok", False):
            err = obs.get("error") or {"code": "bad_arguments", "message": "bad arguments"}
            return ({"result": None, "error": {"code": err.get("code"), "message": err.get("message")},
                     "remaining_steps": remaining}, 0.0, bool(terminated), False, {})
        result = obs.get("result")
        if terminated:  # submit
            self._over = True
            out: Dict[str, Any] = {"accepted": True}
            if self._mode != "closed" and isinstance(result, dict) and "report" in result:
                out["report"] = result["report"]
            return {"result": out, "error": None, "remaining_steps": remaining}, reward, True, False, {}
        tool = internal["tool"]
        if tool == "list_records":
            result = {"records": result["rows"], "next_cursor": result["next_cursor"]}
        elif tool == "calculator":
            result = result["value"]
        return {"result": result, "error": None, "remaining_steps": remaining}, 0.0, False, False, {}

    def close(self) -> None:
        if self._env is not None:
            self._env.close()
            self._env = None


def make_env() -> JudgeEnv:
    return JudgeEnv()


# ---------------------------------------------------------------- scoring (jury side only)
def score_episode(episode_dir: str, findings: dict, inspection_steps: int) -> dict:
    """Closed evaluator call: score one findings.json object against the episode's private truth.
    Invalid structure -> return -1 and every other field null (the error is in the evaluator log)."""
    core = EvaluatorCore(os.environ.get("AUDITGYM_EVAL_LOG"), "judge")
    loaded = core.dispatch({"cmd": "load", "dir": episode_dir, "mode": "open", "token": "judge"})
    if not loaded.get("ok"):
        raise ValueError("episode_dir could not be loaded")
    try:
        sub = json.loads(json.dumps(findings, allow_nan=False))
    except (TypeError, ValueError):
        sub = None
    steps = inspection_steps if isinstance(inspection_steps, int) and not isinstance(inspection_steps, bool) else -1
    steps = min(max(steps, 0), MAX_STEPS)
    res = core.score(loaded["handle"], sub, steps)
    rep = core._results["default"][-1]  # the full organizer-side result, never shown to a policy
    if rep.get("status") == "invalid_structure":
        return {"tp": None, "fp": None, "fn": None, "precision": None, "recall": None, "f1": None, "return": -1.0}
    return {"tp": rep["tp"], "fp": rep["fp"], "fn": rep["fn"], "precision": rep["precision"],
            "recall": rep["recall"], "f1": rep["f1"], "return": rep["reward"]}


__all__ = ["generate_episode", "make_env", "score_episode", "JudgeEnv"]
