"""Learnable auditor and a pure-Python trainer (task T10, contract in docs/TRAINING_API.md section 1).

``AuditorPolicy(theta)`` is an ordinary agent: it acts only through the public tool contract, exactly like
``ReconcilePolicy``. A parameter vector ``theta`` (any real numbers; each one goes through a sigmoid) decides which
tables it reads and how many pages, which of the four checks it runs, how strict they are, local or UTC dates,
which evidence IDs it cites and how many findings it submits. The checks are a parametric copy of the careful
rules in ``policies/rules.py`` with the shortcuts of ``policies/naive.py`` as the other settings, so one ``theta``
reproduces the careful rules and a random one behaves like the naive tricks.

``train(config)`` searches ``theta`` with the cross-entropy method or REINFORCE (a Gaussian search distribution
with a reward baseline) on freshly generated episodes in open mode (the reward comes from the evaluator only),
and every ``eval_every`` iterations measures the current policy on the 10 held-out dev episodes in closed mode,
exactly as ``harness.run_split`` does (finalize, public score fields only). CPU only, standard library only,
deterministic for a given config.
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import harness
from .config import ConfigError, make_config
from .env.env import AuditEnv
from .eval.service import EvaluatorCore, ServiceClient
from .gen.build import generate
from .money import convert
from .policies.baselines import Policy, RandomPolicy, ReconcilePolicy, run_episode
from .policies.rules import AR, UNAPPLIED, _canon_lines
from .seeding import Rng, derive_seed
from .timeutil import TZ_OFFSETS_MIN, local_date
from .version import ENV_VERSION

TABLE_ORDER = ("fx", "invoices", "payments", "ledger")
MAX_PAGES = 30          # a page budget of 30 means "the whole table" for every valid config
MAX_CAP = 30            # the evaluator accepts at most 30 findings
TOL_DECADES = 6         # FX tolerance spans 0 .. 10^6 - 1 minor units on a log scale
DUP_LEVELS = ("amount", "entity", "lines")

# name, Russian label. Order is the layout of theta.
PARAMS: List[Tuple[str, str]] = [
    ("read_fx", "Читать курсы валют"),
    ("read_invoices", "Читать счета"),
    ("read_payments", "Читать платежи"),
    ("read_ledger", "Читать главную книгу"),
    ("pages_fx", "Страниц курсов"),
    ("pages_invoices", "Страниц счетов"),
    ("pages_payments", "Страниц платежей"),
    ("pages_ledger", "Страниц главной книги"),
    ("check_duplicate", "Проверка дублей счетов"),
    ("check_payment", "Проверка разноски платежей"),
    ("check_fx", "Проверка курсов"),
    ("check_period", "Проверка периода"),
    ("dup_match", "Критерий дубля"),
    ("fx_tolerance", "Допуск по курсу"),
    ("fx_local_time", "Дата курса"),
    ("period_local_time", "Дата для периода"),
    ("payment_strict", "Строгость разноски"),
    ("evidence_rich", "Доказательства"),
    ("min_amount", "Порог суммы"),
    ("max_findings", "Предел находок"),
]
PARAM_NAMES: List[str] = [p for p, _ in PARAMS]
LABELS: Dict[str, str] = dict(PARAMS)
N_PARAMS: int = len(PARAMS)
_IDX = {n: i for i, n in enumerate(PARAM_NAMES)}

# A hand-set theta that reproduces policies/rules.find_issues exactly (the reconcile baseline).
CAREFUL = {n: 4.0 for n in PARAM_NAMES}
CAREFUL["fx_tolerance"] = -2.45          # sigmoid -> 10^(0.0794*6) - 1 = 2 minor units, as in the careful rule
CAREFUL["min_amount"] = -6.0             # 0: never abstains
CAREFUL_THETA: List[float] = [CAREFUL[n] for n in PARAM_NAMES]


def _sig(x: float) -> float:
    x = max(-60.0, min(60.0, float(x)))
    return 1.0 / (1.0 + math.exp(-x))


def decode(theta: Sequence[float]) -> Dict[str, Any]:
    """Map any real vector to concrete settings (pure function, no state)."""
    if len(theta) != N_PARAMS:
        raise ValueError(f"theta must have {N_PARAMS} numbers")
    s = {n: _sig(theta[i]) for i, n in enumerate(PARAM_NAMES)}
    on = lambda n: s[n] > 0.5  # noqa: E731
    pages = {t: (min(MAX_PAGES, 1 + int(s["pages_" + t] * MAX_PAGES)) if on("read_" + t) else 0) for t in TABLE_ORDER}
    return {
        "pages": pages,
        "check_duplicate": on("check_duplicate"), "check_payment": on("check_payment"),
        "check_fx": on("check_fx"), "check_period": on("check_period"),
        "dup_match": DUP_LEVELS[min(2, int(s["dup_match"] * 3))],
        "fx_tolerance": int(round(10 ** (s["fx_tolerance"] * TOL_DECADES))) - 1,
        "fx_local_time": on("fx_local_time"), "period_local_time": on("period_local_time"),
        "payment_strict": on("payment_strict"),
        "evidence_rich": on("evidence_rich"),
        "min_amount": int(round(10 ** (s["min_amount"] * TOL_DECADES))) - 1,
        "max_findings": min(MAX_CAP, int(s["max_findings"] * (MAX_CAP + 1))),
    }


# ------------------------------------------------------------------------------------------ the checks
def _utc_date(ts: str) -> date:
    return datetime.fromisoformat(ts).astimezone(timezone.utc).date()


def find_issues_param(ledger: List[dict], invoices: List[dict], payments: List[dict], fx: List[dict],
                      policy: Dict[str, Any], k: Dict[str, Any]) -> List[dict]:
    """Parametric copy of ``rules.find_issues``; with the careful settings the output is identical.

    The other settings are the shortcuts of ``policies/naive.py``: duplicates by amount (with or without the
    entity), UTC dates, any unapplied cash, findings without evidence; plus a minimum amount
    below which it abstains and a cap on the number of findings."""
    tzn, base = policy["timezone"], policy["base_currency"]
    p_start = date.fromisoformat(policy["period"]["start"])
    p_end = date.fromisoformat(policy["period"]["end"])
    fx_date = (lambda ts: local_date(ts, tzn)) if k["fx_local_time"] else _utc_date
    per_date = (lambda ts: local_date(ts, tzn)) if k["period_local_time"] else _utc_date
    rates = {(r["date"], r["source_currency"]): r["rate"] for r in fx}
    by_inv: Dict[str, List[dict]] = defaultdict(list)
    by_pay: Dict[str, List[dict]] = defaultdict(list)
    for r in ledger:
        if r["invoice_id"]:
            by_inv[r["invoice_id"]].append(r)
        if r["payment_id"]:
            by_pay[r["payment_id"]].append(r)
    ev_l = ev_f = k["evidence_rich"]
    findings: List[dict] = []

    def in_period(d: date) -> bool:
        return p_start <= d <= p_end

    if k["check_duplicate"]:
        groups: Dict[tuple, List[dict]] = defaultdict(list)
        for inv in invoices:
            key: tuple = (inv["currency"], inv["total_minor"])
            if k["dup_match"] != "amount":
                key = (inv["entity_id"],) + key
            if k["dup_match"] == "lines":
                key = key + (_canon_lines(inv["line_items"]),)
            groups[key].append(inv)
        for invs in groups.values():
            if len(invs) < 2:
                continue
            invs = sorted(invs, key=lambda i: i["issued_at"])
            for later in invs[1:]:
                ids = sorted([invs[0]["invoice_id"], later["invoice_id"]])
                findings.append({"type": "duplicate_invoice", "affected_ids": ids, "claimed_amount_minor": later["total_minor"],
                                 "currency": later["currency"], "evidence_ids": ids,
                                 "explanation": "Same entity, line items and service period invoiced twice."})

    if k["check_fx"] or k["check_period"]:
        for inv in invoices:
            iid, ccy = inv["invoice_id"], inv["currency"]
            ar_rows = [r for r in by_inv[iid] if r["account"] == AR and r["debit_minor"] > 0 and not r["payment_id"]]
            if not ar_rows:
                continue
            ar = ar_rows[0]
            d_rate = fx_date(inv["issued_at"])
            rate = "1" if ccy == base else rates.get((d_rate.isoformat(), ccy))
            if rate is None:
                continue
            expected = convert(inv["total_minor"], ccy, base, rate)
            fx_key = f"{d_rate.isoformat()}|{ccy}|{base}"
            if k["check_fx"] and ccy != base and abs(ar["debit_minor"] - expected) > k["fx_tolerance"]:
                ev = [iid] + ([ar["row_id"]] if ev_l else []) + ([fx_key] if ev_f else [])
                findings.append({"type": "date_or_fx", "affected_ids": [iid],
                                 "claimed_amount_minor": abs(ar["debit_minor"] - expected),
                                 "currency": base, "evidence_ids": sorted(ev),
                                 "explanation": "Booked at a rate other than the policy-date rate."})
            if k["check_period"] and in_period(per_date(inv["issued_at"])) != in_period(per_date(ar["timestamp"])):
                ev = [iid] + ([ar["row_id"]] if ev_l else []) + ([fx_key] if ev_f and ccy != base else [])
                findings.append({"type": "period_classification", "affected_ids": [iid], "claimed_amount_minor": expected,
                                 "currency": base, "evidence_ids": sorted(ev),
                                 "explanation": "Posted outside the period of its issue date."})

    if k["check_payment"]:
        if k["payment_strict"]:
            for p in payments:
                refs = p["invoice_refs"]
                if not refs:
                    continue
                un = [r for r in by_pay[p["payment_id"]] if r["account"] == UNAPPLIED and r["credit_minor"] > 0]
                if not un or len(refs) != 1:
                    continue
                ids = sorted([p["payment_id"], refs[0]])
                findings.append({"type": "payment_allocation", "affected_ids": ids,
                                 "claimed_amount_minor": sum(r["credit_minor"] for r in un), "currency": base,
                                 "evidence_ids": sorted(ids + ([r["row_id"] for r in un] if ev_l else [])),
                                 "explanation": "Receipt references the invoice but was left in unapplied cash."})
        else:  # naive: any cash in unapplied is an allocation error (ignores documented advances)
            pays = {p["payment_id"]: p for p in payments}
            for r in ledger:
                p = pays.get(r["payment_id"]) if r["payment_id"] else None
                if r["account"] == UNAPPLIED and r["credit_minor"] > 0 and p is not None:
                    ids = sorted([p["payment_id"], (p["invoice_refs"] or ["?"])[0]])
                    findings.append({"type": "payment_allocation", "affected_ids": ids,
                                     "claimed_amount_minor": r["credit_minor"], "currency": base,
                                     "evidence_ids": sorted(ids + ([r["row_id"]] if ev_l else [])),
                                     "explanation": "Cash left in unapplied."})
    findings = [f for f in findings if f["claimed_amount_minor"] >= k["min_amount"]]
    findings.sort(key=lambda f: (f["type"], f["affected_ids"]))
    return findings[:k["max_findings"]]


class AuditorPolicy(Policy):
    """Parametric auditor: pages the chosen tables (fx, invoices, payments, ledger) within its page budgets,
    then submits the findings of the enabled checks. Public tools only, like ``ReconcilePolicy``."""
    name = "auditor"

    def __init__(self, theta: Sequence[float]) -> None:
        self.theta = [float(x) for x in theta]
        self.k = decode(self.theta)

    def reset(self, first_obs):
        super().reset(first_obs)
        self.data: Dict[str, List[dict]] = {t: [] for t in TABLE_ORDER}
        self.queue = [t for t in TABLE_ORDER if self.k["pages"][t] > 0]
        self.pages_read = 0
        self.cursor: Optional[str] = None
        self.last_table: Optional[str] = None

    def act(self, obs):
        if self.last_table and obs.get("ok"):
            self.data[self.last_table].extend(obs["result"]["rows"])
            self.cursor = obs["result"]["next_cursor"]
            self.pages_read += 1
            if self.cursor is None or self.pages_read >= self.k["pages"][self.last_table]:
                self.queue.pop(0)
                self.cursor, self.pages_read = None, 0
        self.last_table = None
        if self.queue and obs.get("remaining_steps", 0) > 1:
            self.last_table = self.queue[0]
            return {"tool": "list_records", "args": {"table": self.last_table, "cursor": self.cursor, "limit": 50}}
        pol = self.first["result"]["policy"]
        fs = find_issues_param(self.data["ledger"], self.data["invoices"], self.data["payments"], self.data["fx"], pol, self.k)
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": fs}}}


def describe(theta: Sequence[float]) -> List[Dict[str, Any]]:
    """Human-readable learned policy: one entry per parameter, in Russian."""
    k = decode(theta)
    yn = lambda b: "вкл" if b else "выкл"  # noqa: E731
    tz = lambda b: "местное время" if b else "UTC"  # noqa: E731
    dup = {"amount": "только сумма", "entity": "контрагент + валюта + сумма", "lines": "полное совпадение строк"}
    out: List[Dict[str, Any]] = []

    def add(key: str, value: str, on: bool) -> None:
        out.append({"key": key, "label": LABELS[key], "value": value, "on": bool(on)})

    for t in TABLE_ORDER:
        add("read_" + t, "да" if k["pages"][t] else "нет", k["pages"][t] > 0)
    for t in TABLE_ORDER:
        n = k["pages"][t]
        add("pages_" + t, ("все" if n >= MAX_PAGES else f"до {n}") if n else "—", n > 0)
    add("check_duplicate", f"{yn(k['check_duplicate'])} · {dup[k['dup_match']]}", k["check_duplicate"])
    add("check_payment", f"{yn(k['check_payment'])} · " + ("только по ссылке на один счёт" if k["payment_strict"]
                                                          else "любые неразнесённые деньги"), k["check_payment"])
    add("check_fx", f"{yn(k['check_fx'])} · допуск {k['fx_tolerance']} · {tz(k['fx_local_time'])}", k["check_fx"])
    add("check_period", f"{yn(k['check_period'])} · {tz(k['period_local_time'])}", k["check_period"])
    add("dup_match", dup[k["dup_match"]], k["check_duplicate"])
    add("fx_tolerance", f"{k['fx_tolerance']} мин. ед.", k["check_fx"])
    add("fx_local_time", tz(k["fx_local_time"]), k["check_fx"] or k["check_period"])
    add("period_local_time", tz(k["period_local_time"]), k["check_period"])
    add("payment_strict", "строго" if k["payment_strict"] else "любые неразнесённые", k["check_payment"])
    add("evidence_rich", "строка книги и курс" if k["evidence_rich"] else "только id документов", k["evidence_rich"])
    add("min_amount", f"от {k['min_amount']} мин. ед." if k["min_amount"] else "любая сумма", True)
    add("max_findings", str(k["max_findings"]), k["max_findings"] > 0)
    return out


# ------------------------------------------------------------------------------------------ evaluator plumbing
class _CachingCore(EvaluatorCore):
    """Evaluator core that generates each (seed, config) once: every candidate of an iteration plays the same
    episodes (common random numbers) without paying for generation again. Scoring is unchanged."""

    def __init__(self, token: str, cache: Dict[str, Any]) -> None:
        super().__init__(None, token)
        self.cache = cache

    def generate(self, seed, config, mode="open", run_id="default"):
        if mode not in ("open", "closed"):
            return super().generate(seed, config, mode, run_id)
        key = json.dumps([seed, config], sort_keys=True)
        ep = self.cache.get(key)
        if ep is None:
            try:
                ep = generate(seed, config)
            except ConfigError as exc:
                return {"ok": False, "error": {"code": "bad_config", "message": str(exc)[:200]}}
            self.cache[key] = ep
        return self._register(ep, mode, run_id)


class _Service(ServiceClient):
    """In-process organizer client over a caching core."""

    def __init__(self, cache: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(in_process=True)
        self.core = _CachingCore(self._token, {} if cache is None else cache)


# ------------------------------------------------------------------------------------------ episodes
PRESETS = ("mixed", "simple", "interacting")
ERROR_TYPES = ("duplicate_invoice", "payment_allocation", "date_or_fx", "period_classification")
_CURRENCY_SETS = [("KZT", ["USD", "EUR"]), ("KZT", ["USD", "EUR", "CNY"]), ("USD", ["EUR", "JPY"]),
                  ("EUR", ["USD", "KWD", "GBP"]), ("UZS", ["USD"]), ("KZT", ["USD", "JPY"])]
_TZS = sorted(TZ_OFFSETS_MIN)


def forbidden_seeds(configs: Optional[str] = None) -> set:
    """Seeds of the train and dev splits: training never uses them."""
    out = set(range(1000, 1010)) | set(range(2000, 2010))
    for split in harness.SPLITS:
        try:
            out |= {e["seed"] for e in harness.load_split(split, configs)}
        except (OSError, ValueError, KeyError):
            pass
    return out


def episode_config(preset: str, rng: Rng) -> Dict[str, Any]:
    """A random but valid episode config for a training preset (mirrors the variety of configs/train.json)."""
    clean = preset == "mixed" and rng.chance(0.2)
    inter: List[str] = []
    if preset == "interacting" or (preset == "mixed" and not clean and rng.chance(0.35)):
        inter = rng.choice([["A"], ["B"], ["A", "B"]])
    errors = {t: rng.rand_int(0, 2) for t in ERROR_TYPES}
    if not clean and not inter and sum(errors.values()) == 0:
        errors[rng.choice(ERROR_TYPES)] = 1
    cfg: Dict[str, Any] = {"layout_seed": rng.rand_int(0, 10 ** 6), "id_seed": rng.rand_int(0, 10 ** 6),
                           "errors": errors, "clean": clean, "interactions": inter,
                           "distractor_level": rng.rand_int(0, 2), "period_start_month": rng.rand_int(1, 12),
                           "period_months": rng.rand_int(1, 3), "n_expenses": rng.choice([40, 80, 80, 120, 200])}
    if preset == "mixed" and rng.chance(0.35):
        base, foreign = rng.choice(_CURRENCY_SETS)
        cfg.update(base_currency=base, foreign_currencies=list(foreign), timezone=rng.choice(_TZS))
    issues = 0 if clean else sum(errors.values()) + 3 * ("A" in inter) + 2 * ("B" in inter)
    if issues > 12:
        cfg["errors"] = {t: min(v, 1) for t, v in errors.items()}
        issues = 0 if clean else sum(cfg["errors"].values()) + 3 * ("A" in inter) + 2 * ("B" in inter)
    cfg["n_invoices"] = min(100, max(rng.rand_int(40, 80), 4 * issues))
    try:
        make_config(cfg)
    except ConfigError:
        cfg = {"layout_seed": cfg["layout_seed"], "id_seed": cfg["id_seed"]}
    return cfg


def episode_specs(seed: int, iteration: int, n: int, preset: str, forbidden: set) -> List[Tuple[int, Dict[str, Any]]]:
    out = []
    for j in range(n):
        s, salt = -1, 0
        while s < 0 or s in forbidden:
            s = derive_seed("auditgym-learner-episode", seed, preset, iteration, j, salt) % (2 ** 63)
            salt += 1
        out.append((s, episode_config(preset, Rng("auditgym-learner-config", seed, preset, iteration, j))))
    return out


# ------------------------------------------------------------------------------------------ dev evaluation
def evaluate_dev(make: Callable[[], Policy], limit: Optional[int] = None, configs: Optional[str] = None,
                 cache: Optional[Dict[str, Any]] = None, run_id: str = "learner-dev") -> Dict[str, Any]:
    """Held-out dev split in CLOSED mode, the way ``harness.run_split`` does it: a separate evaluator client,
    no reward in the observations, ``finalize`` per episode, public score fields only."""
    eps = harness.load_split("dev", configs)[: limit or None]
    svc = _Service(cache)
    env = AuditEnv(mode="closed", service=svc, run_id=run_id)
    rows = []
    for e in eps:
        t0 = time.perf_counter()
        obs, _ = env.reset(seed=e["seed"], config=e["config"])
        if not obs.get("ok"):
            continue
        policy = make()
        policy.reset(obs)
        last, n, done = obs, 0, False
        while not done:
            last, _r, terminated, truncated, _i = env.step(policy.act(last))
            n += 1
            done = terminated or truncated
        res = svc.call({"cmd": "finalize", "run_id": run_id}).get("results") or [{}]
        rows.append({"steps": n, "seconds": time.perf_counter() - t0,
                     "score": {k: res[-1][k] for k in harness.PUBLIC_SCORE if k in res[-1]}})
    env.close()
    s = harness.summarize(rows)
    if not s.get("episodes_done"):
        return {"reward": -1.0, "f1": 0.0, "precision": 0.0, "recall": 0.0, "fp": 0.0, "steps": 0.0, "episodes": 0}
    return {"reward": s["reward"], "f1": s["f1"], "precision": s["precision"], "recall": s["recall"],
            "fp": round(s["fp"] / s["episodes_done"], 3), "steps": s["steps"], "episodes": s["episodes_done"]}


def dev_baselines(configs: Optional[str] = None) -> Dict[str, Any]:
    """Reference policies on the same dev split (reconcile = careful rules, random seed 7)."""
    cache: Dict[str, Any] = {}
    return {"reconcile": evaluate_dev(ReconcilePolicy, configs=configs, cache=cache),
            "random": evaluate_dev(RandomPolicy, configs=configs, cache=cache)}


# ------------------------------------------------------------------------------------------ training
DEFAULTS: Dict[str, Any] = {"method": "cem", "iterations": 30, "population": 16, "episodes_per_candidate": 4,
                            "elite_frac": 0.25, "seed": 1, "dataset": {"preset": "mixed"}, "eval_every": 2, "pace": 0.0}
SIGMA0, SIGMA_FLOOR = 2.0, 0.1
CEM_SMOOTH = 0.3
EXTRA0, EXTRA_FRAC = 1.0, 1.0    # CEM extra noise (variance), decays to 0 at EXTRA_FRAC of the iterations
RF_LR_MU, RF_LR_SIGMA = 1.5, 0.15


def normalize_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    c = dict(config or {})
    unknown = sorted(set(c) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"unknown training key: {unknown[0][:40]}")
    out = {**DEFAULTS, **c}
    ds = out["dataset"] if isinstance(out["dataset"], dict) else None
    if ds is None or set(ds) - {"preset"} or ds.get("preset", "mixed") not in PRESETS:
        raise ValueError("dataset must be {\"preset\": mixed|simple|interacting}")
    out["dataset"] = {"preset": ds.get("preset", "mixed")}
    if out["method"] not in ("cem", "reinforce"):
        raise ValueError("method must be cem or reinforce")

    def integer(key, lo, hi):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not float(v).is_integer() or not lo <= v <= hi:
            raise ValueError(f"{key} must be an integer in {lo}..{hi}")
        out[key] = int(v)

    def number(key, lo, hi):
        v = out[key]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"{key} must be a number in {lo}..{hi}")
        out[key] = float(v)

    integer("iterations", 1, 1000)
    integer("population", 2, 256)
    integer("episodes_per_candidate", 1, 64)
    integer("seed", 0, 2 ** 31)
    integer("eval_every", 1, 1000)
    number("elite_frac", 0.01, 1.0)
    number("pace", 0.0, 5.0)
    return out


def _gauss(rng: Rng) -> float:
    u1 = 1.0 - rng.random()
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * rng.random())


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def train(config: Optional[Dict[str, Any]] = None, run_id: Optional[str] = None, base: Optional[str] = None,
          on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
          stop: Optional[threading.Event] = None, configs: Optional[str] = None) -> Dict[str, Any]:
    """Run a training job, write ``<runs>/<run_id>/run.json`` after every iteration and return the run."""
    cfg = normalize_config(config)
    method, n_iter, pop = cfg["method"], cfg["iterations"], cfg["population"]
    n_eps, seed, preset = cfg["episodes_per_candidate"], cfg["seed"], cfg["dataset"]["preset"]
    n_elite = max(1, min(pop, int(round(pop * cfg["elite_frac"]))))
    model = f"auditor-{method}"
    root = base or harness.runs_dir()
    if run_id is None:
        run_id = harness.new_run_id(model, "train")
        n = 1
        while os.path.exists(os.path.join(root, run_id)):
            n += 1
            run_id = f"{harness.new_run_id(model, 'train')}-{n}"
    if not harness.RUN_ID.match(run_id):
        raise ValueError("bad run id")
    folder = os.path.join(root, run_id)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "run.json")
    emit = on_event or (lambda e: None)
    run: Dict[str, Any] = {"id": run_id, "kind": "training", "model": model, "method": method, "status": "running",
                           "config": cfg, "env_version": ENV_VERSION, "started": time.time(), "finished": None,
                           "iterations": n_iter, "at": 0, "points": [],
                           "best": {"theta": None, "describe": None, "dev": None, "i": None},
                           "summary": {"dev_start": None, "dev_best": None, "dev_last": None, "episodes": 0, "seconds": 0.0}}
    harness._write_json(path, run)

    rng = Rng("auditgym-learner-search", seed, method)
    mu = [0.0] * N_PARAMS
    sig = [SIGMA0] * N_PARAMS
    forbidden = forbidden_seeds(configs)
    dev_cache: Dict[str, Any] = {}
    total_eps, total_sec = 0, 0.0
    try:
        for i in range(n_iter):
            if stop is not None and stop.is_set():
                run["status"] = "stopped"
                break
            t0 = time.perf_counter()
            specs = episode_specs(seed, i, n_eps, preset, forbidden)
            svc = _Service()
            env = AuditEnv(mode="open", service=svc, run_id="learner-train")
            eps_noise = [[_gauss(rng) for _ in range(N_PARAMS)] for _ in range(pop)]
            cands = [[mu[d] + sig[d] * e[d] for d in range(N_PARAMS)] for e in eps_noise]
            scores: List[float] = []
            aborted = False
            for th in cands:
                if stop is not None and stop.is_set():
                    aborted = True
                    break
                rs = [run_episode(env, AuditorPolicy(th), seed=s, config=c)["return"] for s, c in specs]
                scores.append(_mean(rs))
            env.close()
            if aborted:
                run["status"] = "stopped"
                break
            order = sorted(range(pop), key=lambda k: (-scores[k], k))
            elite = order[:n_elite]
            if method == "cem":
                extra = EXTRA0 * max(0.0, 1.0 - i / max(1.0, EXTRA_FRAC * n_iter))
                for d in range(N_PARAMS):
                    vals = [cands[k][d] for k in elite]
                    m = _mean(vals)
                    var = _mean([(v - m) ** 2 for v in vals])
                    mu[d] = CEM_SMOOTH * m + (1 - CEM_SMOOTH) * mu[d]
                    sig[d] = max(SIGMA_FLOOR, math.sqrt(CEM_SMOOTH * var + (1 - CEM_SMOOTH) * sig[d] ** 2 + extra))
            else:  # REINFORCE with a Gaussian policy over theta and the population mean as baseline
                b = _mean(scores)
                sd = math.sqrt(_mean([(r - b) ** 2 for r in scores])) or 1.0
                adv = [(r - b) / sd for r in scores]
                for d in range(N_PARAMS):
                    g_mu = _mean([adv[k] * eps_noise[k][d] for k in range(pop)])
                    g_ls = _mean([adv[k] * (eps_noise[k][d] ** 2 - 1.0) for k in range(pop)])
                    mu[d] += RF_LR_MU * sig[d] * g_mu
                    sig[d] = max(SIGMA_FLOOR, sig[d] * math.exp(0.5 * RF_LR_SIGMA * g_ls))
            train_sec = time.perf_counter() - t0
            dev = None
            if i == 0 or i == n_iter - 1 or i % cfg["eval_every"] == 0:
                cur = list(mu)
                dev = evaluate_dev(lambda: AuditorPolicy(cur), configs=configs, cache=dev_cache,
                                   run_id=f"learner-dev-{i}")
                if run["best"]["dev"] is None or dev["reward"] > run["best"]["dev"]["reward"]:
                    run["best"] = {"theta": [round(x, 4) for x in cur], "describe": describe(cur), "dev": dev, "i": i}
            seconds = time.perf_counter() - t0
            n_played = pop * n_eps
            total_eps += n_played
            total_sec += seconds
            point = {"i": i, "train_mean": round(_mean(scores), 4), "train_best": round(scores[order[0]], 4),
                     "train_elite": round(_mean([scores[k] for k in elite]), 4), "sigma": round(_mean(sig), 4),
                     "episodes": n_played, "seconds": round(seconds, 3),
                     "eps_per_sec": round(n_played / train_sec, 1) if train_sec > 0 else None, "dev": dev}
            run["points"].append(point)
            run["at"] = i + 1
            devs = [p["dev"]["reward"] for p in run["points"] if p["dev"]]
            run["summary"] = {"dev_start": devs[0] if devs else None, "dev_best": max(devs) if devs else None,
                              "dev_last": devs[-1] if devs else None, "episodes": total_eps, "seconds": round(total_sec, 2)}
            harness._write_json(path, run)
            emit({"type": "iteration", "point": point})
            if cfg["pace"] and i < n_iter - 1:
                if stop is not None:
                    stop.wait(cfg["pace"])
                else:
                    time.sleep(cfg["pace"])
        else:
            run["status"] = "done"
    except Exception as exc:  # noqa: BLE001 - a failed job ends with a readable status, like evaluation runs
        run["status"] = "error"
        run["error"] = str(exc)[:200]
    finally:
        run["finished"] = time.time()
        harness._write_json(path, run)
        emit({"type": "run_end", "run": run})
    return run
