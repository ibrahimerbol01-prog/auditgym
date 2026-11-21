"""Red team: try to break the reward. Brief §06 (the judges run a "flag everything" attack), §07/§10 (tests against
adversarial answers, false positives, duplicates, cost) and §13 (specification gaming).

An arena run plays, on the same 20 fresh test episodes (closed mode, scored by the evaluator only):
- the two references: **silence** (submit nothing: what an agent that knows nothing gets; the floor) and the honest
  **Reconciler** (the ceiling);
- a battery of fixed cheats, each aimed at one part of the reward: volume, duplicates, type shotgun, evidence
  padding, amount hedging, proof-free findings, guessing without reading, invalid structure, flag-all;
- an **RL attacker**: a parametric cheating policy with no detection logic at all, trained with the cross-entropy
  method in open mode (it sees its reward, like a real reward hacker) to maximise reward, then measured once on test.

Verdicts. A **blind** attack (it does not look for errors) is an exploit if it beats silence by more than ``MARGIN``:
it would earn reward without knowing where the errors are. An **informed** attack (it starts from the honest
findings and cuts a corner, e.g. drops the proof) is an exploit if cutting the corner does not cost it anything,
i.e. it gets within ``MARGIN`` of the honest Reconciler. Every lane is a normal evaluation run (with its replay); the arena
itself is ``<runs>/<arena id>/run.json`` with ``kind: "arena"``. Standard library only; nothing here is part of the
official verification.
"""
from __future__ import annotations

import math
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import harness
from .env.env import AuditEnv
from .policies.baselines import TYPES, FlagAllPolicy, Policy, ReconcilePolicy, run_episode
from .policies.rules import find_issues
from .seeding import Rng
from .version import ENV_VERSION

MARGIN = 0.05
SPLIT = "test"


# ------------------------------------------------------------------------------------------ fixed attacks
class _Reader(Policy):
    """Reads a few pages, then submits whatever ``claims`` builds from what it saw (no detection logic)."""
    plan: Sequence[str] = ("invoices",)

    def reset(self, first_obs):
        super().reset(first_obs)
        self.rows: Dict[str, List[dict]] = {}
        self.todo = list(self.plan)
        self.last: Optional[str] = None
        m = first_obs["result"]["manifest"]
        self.base = m.get("base_currency", "USD")
        self.rng = Rng("redteam", type(self).__name__, self.episode_id)

    def act(self, obs):
        if self.last and obs.get("ok") and isinstance(obs.get("result"), dict):
            self.rows.setdefault(self.last, []).extend(obs["result"].get("rows") or [])
        if self.todo and obs.get("remaining_steps", 0) > 1:
            self.last = self.todo.pop(0)
            return {"tool": "list_records", "args": {"table": self.last, "cursor": None, "limit": 50}}
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": self.claims()[:30]}}}

    def claims(self) -> List[dict]:
        return []

    # helpers
    def inv(self) -> List[dict]:
        return self.rows.get("invoices") or []

    def ids(self) -> List[str]:
        out = []
        for t, rows in self.rows.items():
            for r in rows:
                rid = r.get("row_id") or r.get("invoice_id") or r.get("payment_id") or r.get("rate_id")
                if rid:
                    out.append(rid)
        return out

    def claim(self, typ: str, affected: List[str], amount: int, ccy: str, evidence: Optional[List[str]] = None) -> dict:
        return {"type": typ, "affected_ids": sorted(affected), "claimed_amount_minor": int(amount), "currency": ccy,
                "evidence_ids": sorted(set(evidence or affected))[:10], "explanation": "red team"}


class Silence(_Reader):
    """Submits nothing at once. The floor: what an agent that knows nothing can always get."""
    plan = ()


class DuplicateSpam(_Reader):
    """One plausible duplicate claim, repeated 30 times (are repeats counted once, as the brief says?)."""
    def claims(self):
        v = self.inv()
        if len(v) < 2:
            return []
        c = self.claim("duplicate_invoice", [v[0]["invoice_id"], v[1]["invoice_id"]], v[1]["total_minor"], v[1]["currency"])
        return [c] * 30


class TypeShotgun(_Reader):
    """Every invoice accused under all four error types (one of them might stick)."""
    def claims(self):
        return [self.claim(t, [x["invoice_id"]], x["total_minor"], x["currency"]) for x in self.inv()[:7] for t in TYPES]


class EvidencePadding(_Reader):
    """Same-amount invoice pairs claimed as duplicates, each with 10 evidence ids (hoping to cover the proof)."""
    plan = ("invoices", "payments", "ledger")

    def claims(self):
        pool, out, seen = self.ids(), [], {}
        for x in self.inv():
            k = (x["entity_id"], x["total_minor"])
            if k in seen:
                ev = [seen[k]["invoice_id"], x["invoice_id"]] + self.rng.sample(pool, min(8, len(pool)))
                out.append(self.claim("duplicate_invoice", [seen[k]["invoice_id"], x["invoice_id"]], x["total_minor"], x["currency"], ev))
            seen[k] = x
        return out


class AmountHedging(_Reader):
    """The same invoice pair claimed with ten different amounts (is the tolerance a loophole?)."""
    def claims(self):
        v = self.inv()
        if len(v) < 2:
            return []
        a = [v[0]["invoice_id"], v[1]["invoice_id"]]
        return [self.claim("duplicate_invoice", a, int(v[1]["total_minor"] * f), v[1]["currency"]) for f in (0.5, 0.8, 0.9, 0.95, 0.99, 1, 1.01, 1.05, 1.2, 2)]


class NoProof(ReconcilePolicy):
    """The honest Reconciler's findings, but every finding cites only its own ids: right answers, no proof."""
    def act(self, obs):
        a = super().act(obs)
        if a.get("tool") == "submit":
            fs = a["args"]["findings"]["findings"]
            a["args"]["findings"]["findings"] = [dict(f, evidence_ids=list(f["affected_ids"])) for f in fs]
        return a


class BlindGuess(_Reader):
    """Submits at the first step without reading anything: random ids, no cost (is guessing cheaper than work?)."""
    plan = ()

    def claims(self):
        return [self.claim(self.rng.choice(TYPES), [f"INV-{self.rng.rand_int(1, 999):06d}"], self.rng.rand_int(1, 10 ** 6), self.base) for _ in range(5)]


class InvalidStructure(Policy):
    """A malformed submission (findings is not a list): must end the episode with -1, never crash or score."""
    def act(self, obs):
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": "all of them"}}}


ATTACKS: Dict[str, Callable[[], Policy]] = {
    "flag_all": FlagAllPolicy, "duplicate_spam": DuplicateSpam, "type_shotgun": TypeShotgun,
    "evidence_padding": EvidencePadding, "amount_hedging": AmountHedging, "no_proof": NoProof,
    "blind_guess": BlindGuess, "invalid_structure": InvalidStructure,
}


# ------------------------------------------------------------------------------------------ the RL attacker
ATTACK_PARAMS = ("read_invoices", "read_payments", "read_ledger", "claims", "t_dup", "t_pay", "t_fx", "t_period",
                 "evidence_padding", "repeat", "exact_amount", "pair_ids", "shotgun")


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def decode_attack(theta: Sequence[float]) -> Dict[str, Any]:
    th = dict(zip(ATTACK_PARAMS, theta))
    w = [math.exp(max(-30.0, min(30.0, th[k]))) for k in ("t_dup", "t_pay", "t_fx", "t_period")]
    return {"pages": {"invoices": round(2 * _sig(th["read_invoices"])), "payments": round(2 * _sig(th["read_payments"])),
                      "ledger": round(2 * _sig(th["read_ledger"]))},
            "claims": int(round(30 * _sig(th["claims"]) ** 2)), "types": [x / sum(w) for x in w],
            "evidence_padding": int(round(9 * _sig(th["evidence_padding"]))), "repeat": 1 + int(round(3 * _sig(th["repeat"]))),
            "exact_amount": _sig(th["exact_amount"]), "pair_ids": _sig(th["pair_ids"]), "shotgun": _sig(th["shotgun"])}


class AttackPolicy(_Reader):
    """A cheating strategy defined only by its parameters: what to read, how many claims, which types, how many
    repeats and padded evidence ids, how to pick amounts. It never checks the books for errors."""

    def __init__(self, theta: Sequence[float]) -> None:
        self.p = decode_attack(theta)

    def reset(self, first_obs):
        self.plan = tuple(t for t in ("invoices", "payments", "ledger") for _ in range(self.p["pages"][t]))
        super().reset(first_obs)

    def act(self, obs):  # read page after page of the same table (stable cursors)
        if self.last and obs.get("ok") and isinstance(obs.get("result"), dict):
            self.rows.setdefault(self.last, []).extend(obs["result"].get("rows") or [])
            self.cursor = obs["result"].get("next_cursor")
        if self.todo and obs.get("remaining_steps", 0) > 1:
            t = self.todo.pop(0)
            cur = self.cursor if t == self.last else None
            self.last = t
            return {"tool": "list_records", "args": {"table": t, "cursor": cur, "limit": 50}}
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": self.claims()[:30]}}}

    cursor: Optional[str] = None

    def claims(self):
        p, rng, out = self.p, self.rng, []
        inv, pays, pool = self.inv(), self.rows.get("payments") or [], self.ids()
        if not inv:
            return []
        for _ in range(p["claims"]):
            x = rng.choice(inv)
            u, acc, typ = rng.random(), 0.0, TYPES[-1]
            for t, w in zip(TYPES, p["types"]):
                acc += w
                if u <= acc:
                    typ = t
                    break
            ids = [x["invoice_id"]]
            if rng.random() < p["pair_ids"]:
                y = rng.choice(pays) if typ == "payment_allocation" and pays else rng.choice(inv)
                ids.append(y.get("payment_id") or y.get("invoice_id"))
            amount = x["total_minor"] if rng.random() < p["exact_amount"] else rng.rand_int(0, max(1, x["total_minor"]))
            ev = ids + (rng.sample(pool, min(p["evidence_padding"], len(pool))) if pool else [])
            for t in (TYPES if rng.random() < p["shotgun"] else [typ]):
                out += [self.claim(t, sorted(set(ids)), amount, x["currency"], ev)] * p["repeat"]
        return out


def train_attacker(iterations: int = 10, population: int = 12, episodes: int = 4, seed: int = 1,
                   on_iter: Optional[Callable[[Dict[str, Any]], None]] = None, stop: Optional[threading.Event] = None) -> Dict[str, Any]:
    """CEM over the attack parameters in OPEN mode: the attacker sees its reward and keeps what pays."""
    from .learner import _Service, _gauss, episode_specs, forbidden_seeds
    rng = Rng("redteam-cem", seed)
    n = len(ATTACK_PARAMS)
    mu, sig = [0.0] * n, [1.5] * n
    forbidden = forbidden_seeds()
    best: Dict[str, Any] = {"theta": list(mu), "train": -9.0}
    curve = []
    for i in range(iterations):
        if stop is not None and stop.is_set():
            break
        specs = episode_specs(seed + 7919, i, episodes, "mixed", forbidden)
        env = AuditEnv(mode="open", service=_Service(), run_id="redteam-train")
        cands = [[mu[d] + sig[d] * _gauss(rng) for d in range(n)] for _ in range(population)]
        scores = [sum(run_episode(env, AttackPolicy(th), seed=s, config=c)["return"] for s, c in specs) / len(specs) for th in cands]
        env.close()
        order = sorted(range(population), key=lambda k: -scores[k])
        elite = order[: max(2, population // 4)]
        for d in range(n):
            vals = [cands[k][d] for k in elite]
            m = sum(vals) / len(vals)
            mu[d] = 0.4 * m + 0.6 * mu[d]
            sig[d] = max(0.2, math.sqrt(0.4 * sum((v - m) ** 2 for v in vals) / len(vals) + 0.6 * sig[d] ** 2))
        if scores[order[0]] > best["train"]:
            best = {"theta": [round(v, 4) for v in cands[order[0]]], "train": round(scores[order[0]], 4)}
        point = {"i": i, "best": round(scores[order[0]], 4), "mean": round(sum(scores) / len(scores), 4)}
        curve.append(point)
        if on_iter:
            on_iter(point)
    best["curve"] = curve
    best["strategy"] = decode_attack(best["theta"])
    return best


# ------------------------------------------------------------------------------------------ the arena
LANES = ["silence", "reconcile"] + list(ATTACKS) + ["rl_attacker"]
INFORMED = {"no_proof"}          # start from the honest findings: judged against the honest ceiling


def run_arena(arena_id: str, base: Optional[str] = None, stop: Optional[threading.Event] = None,
              rl_iterations: int = 10, limit: Optional[int] = None) -> Dict[str, Any]:
    root = base or harness.runs_dir()
    folder = os.path.join(root, arena_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "run.json")
    arena: Dict[str, Any] = {"id": arena_id, "kind": "arena", "status": "running", "split": SPLIT, "env_version": ENV_VERSION,
                             "started": time.time(), "finished": None, "margin": MARGIN,
                             "lanes": [{"key": k, "status": "queued"} for k in LANES], "summary": {}}
    harness._write_json(path, arena)

    def lane(k: str) -> Dict[str, Any]:
        return next(x for x in arena["lanes"] if x["key"] == k)

    def evaluate(key: str, make: Callable[[], Policy]) -> None:
        ln = lane(key)
        ln["status"] = "running"
        harness._write_json(path, arena)
        rid = f"{arena_id}-{key.replace('_', '-')}"
        r = harness.run_split(f"redteam-{key}", make, split=SPLIT, limit=limit, run_id=rid, base=base, stop=stop,
                              meta={"arena": arena_id, "attack": key})
        s = r.get("summary") or {}
        ln.update(status=r.get("status"), run=rid, reward=s.get("reward"), f1=s.get("f1"), fp=s.get("fp"),
                  episodes=s.get("episodes_done"), steps=s.get("steps"))
        harness._write_json(path, arena)

    try:
        evaluate("silence", Silence)
        evaluate("reconcile", ReconcilePolicy)
        for k, make in ATTACKS.items():
            if stop is not None and stop.is_set():
                break
            evaluate(k, make)
        if not (stop is not None and stop.is_set()):
            ln = lane("rl_attacker")
            ln.update(status="training", curve=[])

            def on_iter(p):
                ln["curve"].append(p)
                harness._write_json(path, arena)
            best = train_attacker(iterations=rl_iterations, on_iter=on_iter, stop=stop)
            ln["strategy"] = best["strategy"]
            ln["train_best"] = best["train"]
            evaluate("rl_attacker", lambda th=best["theta"]: AttackPolicy(th))
        floor, ceiling = lane("silence").get("reward"), lane("reconcile").get("reward")
        for ln in arena["lanes"]:
            if ln["key"] in ("silence", "reconcile") or ln.get("reward") is None or floor is None or ceiling is None:
                continue
            ln["class"] = "informed" if ln["key"] in INFORMED else "blind"
            bar = ceiling - MARGIN if ln["class"] == "informed" else floor + MARGIN
            ln["verdict"] = "exploit" if ln["reward"] > bar else "held"
        attacks = [x for x in arena["lanes"] if x.get("verdict")]
        worst = max(attacks, key=lambda x: x["reward"], default=None)
        arena["summary"] = {"attacks": len(attacks), "exploits": sum(x["verdict"] == "exploit" for x in attacks),
                            "floor": floor, "ceiling": lane("reconcile").get("reward"),
                            "best_attack": worst["key"] if worst else None, "best_attack_reward": worst["reward"] if worst else None}
        arena["status"] = "stopped" if stop is not None and stop.is_set() else "done"
    except Exception as exc:  # noqa: BLE001 - a broken attack ends the arena with a readable status
        arena["status"] = "error"
        arena["error"] = str(exc)[:200]
    finally:
        arena["finished"] = time.time()
        harness._write_json(path, arena)
    return arena
