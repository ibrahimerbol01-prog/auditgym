"""The four error types and the two interaction scenarios (plan §5.3, §5.3a, §5.5).

Every change goes through ``Mutator`` so it is logged as a replayable operation
(provenance). Each issue's expected amount is its own injection delta against the clean
baseline. Separation rule: date_or_fx changes only amounts, period_classification only
posting timestamps, payment_allocation only allocation rows, duplicate_invoice only adds a
record.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from ..seeding import Rng
from ..timeutil import tz
from ..version import ENV_VERSION
from .history import AR, REVENUE, UNAPPLIED, World, fx_id


class Mutator:
    def __init__(self, w: World) -> None:
        self.w = w
        self.ops: List[dict] = []

    def _find(self, table: str, key: str) -> dict:
        pk = {"ledger": "row_id", "invoices": "invoice_id", "payments": "payment_id"}[table]
        for r in getattr(self.w.tables, table):
            if r[pk] == key:
                return r
        raise KeyError(key)

    def set(self, table: str, key: str, fld: str, value: Any, why: str, stream: str) -> None:
        rec = self._find(table, key)
        before = copy.deepcopy(rec[fld])
        rec[fld] = value
        self.ops.append({"op": "set", "table": table, "key": key, "field": fld, "before": before,
                         "after": copy.deepcopy(value), "why": why, "rng_stream": stream})

    def add(self, table: str, record: dict, why: str, stream: str) -> None:
        if table == "documents":
            self.w.tables.documents[record["doc_id"]] = record
        else:
            getattr(self.w.tables, table).append(record)
        self.ops.append({"op": "add", "table": table, "record": copy.deepcopy(record), "why": why,
                         "rng_stream": stream})


def apply_ops(tables, ops: List[dict]) -> None:
    """Replay provenance operations on a copy of the clean tables (in place)."""
    pk = {"ledger": "row_id", "invoices": "invoice_id", "payments": "payment_id"}
    for op in ops:
        if op["op"] == "add":
            if op["table"] == "documents":
                tables.documents[op["record"]["doc_id"]] = copy.deepcopy(op["record"])
            else:
                getattr(tables, op["table"]).append(copy.deepcopy(op["record"]))
        elif op["op"] == "set":
            rows = getattr(tables, op["table"])
            rec = next(r for r in rows if r[pk[op["table"]]] == op["key"])
            if rec[op["field"]] != op["before"]:
                raise ValueError("provenance replay mismatch")
            rec[op["field"]] = copy.deepcopy(op["after"])
        else:
            raise ValueError("unknown op")


def _row(w: World, key: str) -> dict:
    return next(r for r in w.tables.ledger if r["row_id"] == key)


def _issue(**kw) -> dict:
    kw.setdefault("interacts_with", [])
    return kw


def inject_duplicate(w: World, m: Mutator, rng: Rng, inv: str, copy_day: date, stream: str) -> dict:
    src = next(i for i in w.tables.invoices if i["invoice_id"] == inv)
    new = w.next("I")
    doc = w.next("D")
    src_local = datetime.fromisoformat(src["issued_at"]).astimezone(tz(w.tz_name()))
    ts = w.ts(copy_day, rng.rand_int(9, 17), rng.rand_int(0, 59))
    rec = {"doc_id": doc, "invoice_id": new, "entity_id": src["entity_id"], "issued_at": ts,
           "due_at": (datetime.fromisoformat(ts) + timedelta(days=30)).isoformat(timespec="seconds"),
           "currency": src["currency"], "total_minor": src["total_minor"],
           "line_items": copy.deepcopy(src["line_items"])}
    m.add("invoices", rec, f"duplicate of {inv} re-issued {(copy_day - src_local.date()).days} days later", stream)
    sdoc = w.tables.documents[src["doc_id"]]
    m.add("documents", {**copy.deepcopy(sdoc), "doc_id": doc, "invoice_id": new, "date": copy_day.isoformat()},
          "document of the duplicate", stream)
    base = w.to_base(src["total_minor"], src["currency"], copy_day)
    ar_key, rv_key = w.next("L"), w.next("L")
    for key, acct, dr, cr in ((ar_key, AR, base, 0), (rv_key, REVENUE, 0, base)):
        m.add("ledger", {"row_id": key, "timestamp": ts, "account": acct, "debit_minor": dr, "credit_minor": cr,
                         "currency": w.base, "entity_id": src["entity_id"], "invoice_id": new, "payment_id": None},
              "posting of the duplicate", stream)
    w.meta[new] = {"date": copy_day, "entity": src["entity_id"], "currency": src["currency"],
                   "total": src["total_minor"], "ar_row": ar_key, "rev_row": rv_key, "base": base, "dup_of": inv}
    return _issue(type="duplicate_invoice", affected_ids=sorted([inv, new]), expected_amount_minor=src["total_minor"],
                  currency=src["currency"], acceptable_evidence_sets=[sorted([inv, new])], conversions=0,
                  detectability_tier="invoices")


def inject_allocation(w: World, m: Mutator, rng: Rng, pay: str, stream: str, fraction_pct: Optional[int] = None) -> dict:
    meta = w.meta[pay]
    inv = meta["allocs"][0][0]
    ar_key = meta["rows"]["ar"][0]
    row = _row(w, ar_key)
    pct = fraction_pct if fraction_pct is not None else rng.choice([100, rng.rand_int(30, 70)])
    moved = (row["credit_minor"] * pct) // 100
    if pct == 100 or row["credit_minor"] - moved <= 0:
        moved = row["credit_minor"]
        m.set("ledger", ar_key, "account", UNAPPLIED, f"receipt {pay} not applied to {inv}", stream)
        m.set("ledger", ar_key, "invoice_id", None, f"receipt {pay} not applied to {inv}", stream)
        unapplied_key = ar_key
    else:
        m.set("ledger", ar_key, "credit_minor", row["credit_minor"] - moved, f"receipt {pay} only partly applied", stream)
        unapplied_key = w.next("L")
        m.add("ledger", {"row_id": unapplied_key, "timestamp": row["timestamp"], "account": UNAPPLIED, "debit_minor": 0,
                         "credit_minor": moved, "currency": w.base, "entity_id": row["entity_id"], "invoice_id": None,
                         "payment_id": pay}, "unapplied remainder", stream)
    conv = 1 if meta["currency"] != w.base else 0
    return _issue(type="payment_allocation", affected_ids=sorted([pay, inv]), expected_amount_minor=moved,
                  currency=w.base, acceptable_evidence_sets=[sorted([pay, inv, unapplied_key])], conversions=conv,
                  detectability_tier="ledger+payments")


def _wrong_day(w: World, rng: Rng, inv: str, d: date, lo: date, hi: date) -> Optional[date]:
    ccy, total = w.meta[inv]["currency"], w.meta[inv]["total"]
    good = w.to_base(total, ccy, d)
    days = [k for k in range(-5, 6) if k != 0 and lo <= d + timedelta(days=k) <= hi]
    rng.shuffle(days)
    for k in days:
        nd = d + timedelta(days=k)
        if abs(w.to_base(total, ccy, nd) - good) >= 20:
            return nd
    return None


def inject_fx(w: World, m: Mutator, rng: Rng, inv: str, variant: str, stream: str,
              lo: Optional[date] = None, hi: Optional[date] = None) -> Optional[dict]:
    meta = w.meta[inv]
    d = meta["date"]
    lo = lo or (w.period_start + timedelta(days=1))
    hi = hi or (w.period_end - timedelta(days=1))
    nd = _wrong_day(w, rng, inv, d, lo, hi)
    if nd is None:
        return None
    good = w.to_base(meta["total"], meta["currency"], d)
    booked = w.to_base(meta["total"], meta["currency"], nd)
    ar, rv = meta["ar_row"], meta["rev_row"]
    why = f"rate of {nd.isoformat()} used instead of {d.isoformat()}"
    m.set("ledger", ar, "debit_minor", booked, why, stream)
    m.set("ledger", rv, "credit_minor", booked, why, stream)
    if variant == "b":
        old = _row(w, ar)["timestamp"]
        hhmm = datetime.fromisoformat(old).astimezone(tz(w.tz_name()))
        new_ts = w.ts(nd, hhmm.hour, hhmm.minute)
        m.set("ledger", ar, "timestamp", new_ts, f"posted with wrong date {nd.isoformat()}", stream)
        m.set("ledger", rv, "timestamp", new_ts, f"posted with wrong date {nd.isoformat()}", stream)
    meta["fx_wrong"] = nd
    return _issue(type="date_or_fx", affected_ids=[inv], expected_amount_minor=abs(booked - good), currency=w.base,
                  acceptable_evidence_sets=[sorted([inv, ar, fx_id(d, meta["currency"], w.base)])], conversions=1,
                  detectability_tier="ledger+fx", variant=variant)


def inject_period(w: World, m: Mutator, rng: Rng, inv: str, stream: str) -> dict:
    meta = w.meta[inv]
    d = meta["date"]
    if w.in_period(d):
        nd = w.period_end + timedelta(days=rng.rand_int(1, 4))
    else:
        nd = w.period_end - timedelta(days=rng.rand_int(0, 3)) if d > w.period_end else w.period_start + timedelta(days=rng.rand_int(0, 3))
    for key in (meta["ar_row"], meta["rev_row"]):
        old = _row(w, key)["timestamp"]
        hh = datetime.fromisoformat(old).astimezone(tz(w.tz_name()))
        m.set("ledger", key, "timestamp", w.ts(nd, hh.hour, hh.minute),
              f"posted in the wrong period ({nd.isoformat()} instead of {d.isoformat()})", stream)
    correct = w.to_base(meta["total"], meta["currency"], d)
    conv = 1 if meta["currency"] != w.base else 0
    ev = [inv, meta["ar_row"]]
    if meta["currency"] != w.base:  # the amount needs the policy-date rate to be provable from the set
        ev.append(fx_id(d, meta["currency"], w.base))
    return _issue(type="period_classification", affected_ids=[inv], expected_amount_minor=correct, currency=w.base,
                  acceptable_evidence_sets=[sorted(ev)], conversions=conv,
                  detectability_tier="ledger+invoices")


def inject_all(w: World) -> Dict[str, Any]:
    """Apply the configured errors to the world in place. Returns {'ops', 'issues'}."""
    cfg = w.cfg
    ch = cfg.content_hash()
    m = Mutator(w)
    issues: List[dict] = []
    if cfg.clean:
        return {"ops": [], "issues": []}
    for inv in w.hosts["duplicate_invoice"]:
        rng = Rng(w.seed, ch, ENV_VERSION, "inject.dup", inv)
        room = max(1, min(10, (w.period_end - w.meta[inv]["date"]).days))
        d = w.meta[inv]["date"] + timedelta(days=rng.rand_int(1, room))
        issues.append(inject_duplicate(w, m, rng, inv, d, f"inject.dup.{inv}"))
    for pay in w.hosts["payment_allocation"]:
        rng = Rng(w.seed, ch, ENV_VERSION, "inject.alloc", pay)
        issues.append(inject_allocation(w, m, rng, pay, f"inject.alloc.{pay}"))
    for i, inv in enumerate(w.hosts["date_or_fx"]):
        rng = Rng(w.seed, ch, ENV_VERSION, "inject.fx", inv)
        variant = "a" if i % 2 == 0 else "b"
        iss = inject_fx(w, m, rng, inv, variant, f"inject.fx.{inv}")
        if iss is None:  # flat rates around the date: fall back to the other variant window
            iss = inject_fx(w, m, rng, inv, "a", f"inject.fx.{inv}", w.period_start, w.period_end)
        if iss is None:
            raise RuntimeError("no distinguishable FX day for host invoice")
        issues.append(iss)
    for inv in w.hosts["period_classification"]:
        rng = Rng(w.seed, ch, ENV_VERSION, "inject.period", inv)
        issues.append(inject_period(w, m, rng, inv, f"inject.period.{inv}"))
    if w.hosts.get("A"):
        x, p = w.hosts["A"]
        rng = Rng(w.seed, ch, ENV_VERSION, "inject.A", x)
        a1 = inject_fx(w, m, rng, x, "a", f"inject.A.fx.{x}", w.period_start, w.period_end)
        if a1 is None:
            raise RuntimeError("no distinguishable FX day for scenario A")
        a2 = inject_period(w, m, rng, x, f"inject.A.period.{x}")
        a3 = inject_allocation(w, m, rng, p, f"inject.A.alloc.{p}", fraction_pct=rng.rand_int(30, 70))
        group = [a1, a2, a3]
        issues.extend(_link(group, "A"))
    if w.hosts.get("B"):
        x = w.hosts["B"][0]
        rng = Rng(w.seed, ch, ENV_VERSION, "inject.B", x)
        copy_day = w.period_end - timedelta(days=rng.rand_int(0, 2))
        b1 = inject_duplicate(w, m, rng, x, copy_day, f"inject.B.dup.{x}")
        y = [k for k in b1["affected_ids"] if k != x][0]
        b2 = inject_period(w, m, rng, y, f"inject.B.period.{y}")
        issues.extend(_link([b1, b2], "B"))
    for n, iss in enumerate(issues, 1):
        iss["issue_id"] = f"I-{n:02d}"
    for iss in issues:
        if "_group" in iss:
            iss["interacts_with"] = [o["issue_id"] for o in issues if o.get("_group") == iss["_group"] and o is not iss]
    for iss in issues:
        iss.pop("_group", None)
    return {"ops": m.ops, "issues": issues}


def _link(group: List[dict], name: str) -> List[dict]:
    for g in group:
        g["_group"] = name
        g["detectability_tier"] = "interacting"
        g["scenario"] = name
    return group
