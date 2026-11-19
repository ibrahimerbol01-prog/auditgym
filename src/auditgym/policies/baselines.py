"""The four baseline policies and the episode runner (plan §8).

All policies act only through the JSON action contract (section 6.2a). The oracle receives the
reference through the organizer interface (``reference``), never through the agent API.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from ..seeding import Rng
from .rules import find_issues

TYPES = ["duplicate_invoice", "payment_allocation", "date_or_fx", "period_classification"]


class Policy:
    name = "base"

    def reset(self, first_obs: Dict[str, Any]) -> None:
        self.first = first_obs
        self.episode_id = first_obs["result"]["manifest"]["episode_id"]

    def act(self, obs: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class OraclePolicy(Policy):
    """Evaluator-only: submits the reference with its first acceptable evidence set."""
    name = "oracle"

    def __init__(self, truth: Dict[str, Any]) -> None:
        self.truth = truth

    def act(self, obs):
        findings = [{"type": i["type"], "affected_ids": i["affected_ids"], "claimed_amount_minor": i["expected_amount_minor"],
                     "currency": i["currency"], "evidence_ids": i["acceptable_evidence_sets"][0],
                     "explanation": f"reference issue {i['issue_id']}"} for i in self.truth["issues"]]
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": findings[:30]}}}


class ReconcilePolicy(Policy):
    """Rule-based reconciliation using public tools only: page every table, then apply the rules."""
    name = "reconcile"
    ORDER = ["fx", "invoices", "payments", "ledger"]

    def reset(self, first_obs):
        super().reset(first_obs)
        self.data: Dict[str, List[dict]] = {t: [] for t in self.ORDER}
        self.table_i = 0
        self.cursor: Optional[str] = None
        self.last_table: Optional[str] = None

    def act(self, obs):
        if self.last_table and obs.get("ok"):
            self.data[self.last_table].extend(obs["result"]["rows"])
            self.cursor = obs["result"]["next_cursor"]
            if self.cursor is None:
                self.table_i += 1
        remaining = obs.get("remaining_steps", 0)
        if self.table_i < len(self.ORDER) and remaining > 1:
            self.last_table = self.ORDER[self.table_i]
            return {"tool": "list_records", "args": {"table": self.last_table, "cursor": self.cursor, "limit": 50}}
        pol = self.first["result"]["policy"]
        fs = find_issues(self.data["ledger"], self.data["invoices"], self.data["payments"], self.data["fx"],
                         pol, self.episode_id)
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": fs}}}


class RandomPolicy(Policy):
    """Seeded random investigator: random tool calls, then random findings over seen IDs."""
    name = "random"

    def __init__(self, seed: int = 7) -> None:
        self.seed = seed

    def reset(self, first_obs):
        super().reset(first_obs)
        self.rng = Rng("random-policy", self.seed, self.episode_id)
        self.seen: List[str] = []
        self.n = 0
        self.budget = self.rng.rand_int(3, 15)

    def act(self, obs):
        if obs.get("ok") and isinstance(obs.get("result"), dict) and "rows" in obs["result"]:
            for r in obs["result"]["rows"]:
                rid = r.get("row_id") or r.get("invoice_id") or r.get("payment_id")
                if rid:
                    self.seen.append(rid)
        self.n += 1
        if self.n <= self.budget:
            t = self.rng.choice(["ledger", "invoices", "payments", "fx"])
            return {"tool": "list_records", "args": {"table": t, "cursor": None, "limit": 50}}
        k = self.rng.rand_int(1, 5)
        fs = []
        for _ in range(k):
            ids = self.rng.sample(self.seen or ["X"], min(2, len(self.seen) or 1))
            fs.append({"type": self.rng.choice(TYPES), "affected_ids": ids,
                       "claimed_amount_minor": self.rng.rand_int(0, 10 ** 8), "currency": "KZT",
                       "evidence_ids": ids, "explanation": "random"})
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": fs}}}


class FlagAllPolicy(Policy):
    """Attack: reads invoices, then accuses every invoice of every applicable type (30 findings max)."""
    name = "flag_all"

    def reset(self, first_obs):
        super().reset(first_obs)
        self.invs: List[dict] = []
        self.started = False

    def act(self, obs):
        if not self.started:
            self.started = True
            return {"tool": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 50}}
        if obs.get("ok") and "rows" in obs.get("result", {}):
            self.invs = obs["result"]["rows"]
        base = self.first["result"]["manifest"]["base_currency"]
        fs = []
        for inv in self.invs:
            for t in ("date_or_fx", "period_classification"):
                fs.append({"type": t, "affected_ids": [inv["invoice_id"]], "claimed_amount_minor": inv["total_minor"],
                           "currency": base, "evidence_ids": [inv["invoice_id"]], "explanation": "everything is wrong"})
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": fs[:30]}}}


def run_episode(env, policy: Policy, seed: Any = None, config: Any = None, options: Optional[dict] = None,
                trajectory: Optional[List[dict]] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    obs, info = env.reset(seed=seed, config=config, options=options)
    if not obs.get("ok"):
        raise ValueError(obs["error"]["message"])
    policy.reset(obs)
    eid = obs["result"]["manifest"]["episode_id"]
    total, steps, last = 0.0, 0, obs
    terminated = truncated = False
    while not (terminated or truncated):
        action = policy.act(last)
        last, reward, terminated, truncated, info = env.step(action)
        steps += 1
        total += reward
        if trajectory is not None:
            trajectory.append({"episode_id": eid, "step": steps, "action": action, "observation": last,
                               "reward": reward, "terminated": terminated, "truncated": truncated})
    return {"episode_id": eid, "return": total, "steps": steps, "terminated": terminated, "truncated": truncated,
            "final_observation": last, "seconds": time.perf_counter() - t0}


def write_trajectories(path: str, rows: List[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
