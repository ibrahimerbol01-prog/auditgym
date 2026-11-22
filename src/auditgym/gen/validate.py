"""Generator-side self-checks (plan §5.8). Each returns a list of problems (empty = pass)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import defaultdict
from typing import Any, Dict, List

from ..eval.scoring import score
from ..money import convert
from ..policies.rules import find_issues
from ..timeutil import local_date
from .export import canonical_tables
from .history import Tables
from .inject import apply_ops


def _rates(fx: List[dict]) -> Dict[tuple, str]:
    return {(r["date"], r["source_currency"]): r["rate"] for r in fx}


def check_books_balance(t: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    """Before injection: double entry balances, totals equal lines, base amounts equal foreign x rate."""
    p: List[str] = []
    dr = sum(r["debit_minor"] for r in t["ledger"])
    cr = sum(r["credit_minor"] for r in t["ledger"])
    if dr != cr:
        p.append(f"ledger does not balance: debit {dr} != credit {cr}")
    if any(r["currency"] != policy["base_currency"] for r in t["ledger"]):
        p.append("ledger row not in base currency")
    base, tzn, rates = policy["base_currency"], policy["timezone"], _rates(t["fx"])
    rows_by_inv = defaultdict(list)
    rows_by_pay = defaultdict(list)
    for r in t["ledger"]:
        if r["invoice_id"]:
            rows_by_inv[r["invoice_id"]].append(r)
        if r["payment_id"]:
            rows_by_pay[r["payment_id"]].append(r)
    for inv in t["invoices"]:
        if inv["total_minor"] != sum(li["amount_minor"] for li in inv["line_items"]):
            p.append(f"{inv['invoice_id']}: total != sum of lines")
        d = local_date(inv["issued_at"], tzn).isoformat()
        rate = "1" if inv["currency"] == base else rates[(d, inv["currency"])]
        exp = convert(inv["total_minor"], inv["currency"], base, rate)
        ar = [r for r in rows_by_inv[inv["invoice_id"]] if r["account"] == "1200" and r["debit_minor"] > 0]
        if len(ar) != 1 or ar[0]["debit_minor"] != exp:
            p.append(f"{inv['invoice_id']}: AR posting != total x rate")
        elif local_date(ar[0]["timestamp"], tzn) != local_date(inv["issued_at"], tzn):
            p.append(f"{inv['invoice_id']}: posted on another date than issued")
    for pay in t["payments"]:
        d = local_date(pay["timestamp"], tzn).isoformat()
        rate = "1" if pay["currency"] == base else rates[(d, pay["currency"])]
        bank = [r for r in rows_by_pay[pay["payment_id"]] if r["account"] == "1010"]
        if len(bank) != 1 or bank[0]["debit_minor"] != convert(pay["amount_minor"], pay["currency"], base, rate):
            p.append(f"{pay['payment_id']}: bank receipt != amount x rate")
        doc = t["documents"][pay["doc_id"]]
        if pay["invoice_refs"] and sum(a["amount_minor"] for a in doc["allocations"]) != pay["amount_minor"]:
            p.append(f"{pay['payment_id']}: allocations != amount")
    return p


def check_replay(clean: Dict[str, Any], ops: List[dict], public: Dict[str, Any]) -> List[str]:
    t = Tables(ledger=json.loads(json.dumps(clean["ledger"])), invoices=json.loads(json.dumps(clean["invoices"])),
               payments=json.loads(json.dumps(clean["payments"])), fx=json.loads(json.dumps(clean["fx"])),
               documents=json.loads(json.dumps(clean["documents"])))
    try:
        apply_ops(t, ops)
    except (ValueError, StopIteration) as exc:
        return [f"replay failed: {exc}"]
    got = canonical_tables({"ledger": t.ledger, "invoices": t.invoices, "payments": t.payments, "fx": t.fx,
                            "documents": t.documents})
    want = canonical_tables(public)
    return [] if json.dumps(got, sort_keys=True) == json.dumps(want, sort_keys=True) else ["replay != public tables"]


def check_declared_discrepancy(ep: Dict[str, Any]) -> List[str]:
    """Clean books show nothing; public books show exactly the declared issues (rules engine)."""
    p: List[str] = []
    pol = ep["public"]["policy"]
    eid = ep["public"]["manifest"]["episode_id"]
    c = ep["private"]["clean"]
    if find_issues(c["ledger"], c["invoices"], c["payments"], c["fx"], pol, eid):
        p.append("rules fire on the clean books (contradictory distractor)")
    t = ep["public"]["tables"]
    fs = find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], pol, eid)
    res = score(fs, ep["private"]["truth"]["issues"], 0)
    if res["f1"] != 1.0:
        p.append(f"public books do not show exactly the declared issues (tp={res['tp']} fp={res['fp']} fn={res['fn']})")
    return p


def check_evidence_reachable(ep: Dict[str, Any]) -> List[str]:
    t = ep["public"]["tables"]
    ids = {r["row_id"] for r in t["ledger"]} | {r["invoice_id"] for r in t["invoices"]} | \
          {r["payment_id"] for r in t["payments"]} | set(t["documents"]) | \
          {f"{r['date']}|{r['source_currency']}|{r['target_currency']}" for r in t["fx"]}
    p = []
    for iss in ep["private"]["truth"]["issues"]:
        for s in iss["acceptable_evidence_sets"]:
            for x in s:
                if x not in ids:
                    p.append(f"{iss['issue_id']}: evidence {x} not reachable")
        for x in iss["affected_ids"]:
            if x not in ids:
                p.append(f"{iss['issue_id']}: affected id {x} not reachable")
    return p


def check_no_leaks(ep: Dict[str, Any]) -> List[str]:
    blob = json.dumps(ep["public"], ensure_ascii=False)
    bad = [s for s in ("issue_id", "truth", "provenance", "expected_amount", "§", "acceptable_evidence", "inject")
           if s in blob]
    return [f"public data contains '{s}'" for s in bad]


def check_separation(ep: Dict[str, Any]) -> List[str]:
    """Each issue's affected invoice differs from clean only in the fields its type may change."""
    c = {r["row_id"]: r for r in ep["private"]["clean"]["ledger"]}
    pub = {r["row_id"]: r for r in ep["public"]["tables"]["ledger"]}
    p = []
    groups = defaultdict(set)
    for iss in ep["private"]["truth"]["issues"]:
        groups[iss["type"]].add(tuple(iss["affected_ids"]))
    for rid, r in pub.items():
        if rid not in c:
            continue
        diff = {k for k in r if r[k] != c[rid][k]}
        if diff - {"debit_minor", "credit_minor", "timestamp", "account", "invoice_id"}:
            p.append(f"{rid}: unexpected changed fields {sorted(diff)}")
        if {"debit_minor", "credit_minor"} & diff and "timestamp" in diff and r["account"] in ("1200", "4000"):
            # date_or_fx variant b changes both on purpose; any other combination is a violation.
            inv = r["invoice_id"]
            if not any(inv in ids for ids in groups["date_or_fx"]):
                p.append(f"{rid}: amount and date changed without a date_or_fx issue")
    return p


def check_cross_process(seed: int, config: Any) -> List[str]:
    from . import crossproc  # the child's code; imported here so packaged builds include it
    src = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    outs = []
    for hs in ("1", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=hs, PYTHONPATH=src)
        r = subprocess.run([sys.executable, "-m", crossproc.__name__, str(seed), json.dumps(config)], capture_output=True,
                           text=True, env=env, timeout=120)
        outs.append(r.stdout.strip())
    return [] if outs[0] and outs[0] == outs[1] else ["generation differs across processes"]


def validate_episode(ep: Dict[str, Any]) -> Dict[str, List[str]]:
    pol = ep["public"]["policy"]
    return {
        "books_balance_before": check_books_balance(ep["private"]["clean"], pol),
        "replay": check_replay(ep["private"]["clean"], ep["private"]["provenance"]["operations"], ep["public"]["tables"]),
        "declared_discrepancy": check_declared_discrepancy(ep),
        "evidence_reachable": check_evidence_reachable(ep),
        "no_leaks": check_no_leaks(ep),
        "separation": check_separation(ep),
        "ledger_after_balances": [] if sum(r["debit_minor"] for r in ep["public"]["tables"]["ledger"]) ==
        sum(r["credit_minor"] for r in ep["public"]["tables"]["ledger"]) else ["public ledger does not balance"],
    }
