"""Public reconciliation rules: detect the four error types from public records only.

Used by the reconciliation baseline (through the tools) and by the generator self-check
(every injected issue must be found and nothing on a clean episode may fire). The
independent verifier (eval/verify_independent.py) is written separately and does not use it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, List

from ..money import convert
from ..timeutil import local_date

AR, REVENUE, UNAPPLIED, RETURNS = "1200", "4000", "2350", "4100"


def _canon_lines(lines: List[dict]) -> str:
    import json
    return json.dumps(sorted(lines, key=lambda li: (li["description"], li["amount_minor"])), sort_keys=True)


def find_issues(ledger: List[dict], invoices: List[dict], payments: List[dict], fx: List[dict],
                policy: Dict[str, Any], episode_id: str) -> List[dict]:
    tzn = policy["timezone"]
    base = policy["base_currency"]
    p_start = date.fromisoformat(policy["period"]["start"])
    p_end = date.fromisoformat(policy["period"]["end"])
    rates = {(r["date"], r["source_currency"]): r["rate"] for r in fx}
    by_inv: Dict[str, List[dict]] = defaultdict(list)
    by_pay: Dict[str, List[dict]] = defaultdict(list)
    for r in ledger:
        if r["invoice_id"]:
            by_inv[r["invoice_id"]].append(r)
        if r["payment_id"]:
            by_pay[r["payment_id"]].append(r)
    findings: List[dict] = []

    def in_period(d: date) -> bool:
        return p_start <= d <= p_end

    # duplicate_invoice: same entity, currency, total and identical lines incl. service period.
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for inv in invoices:
        groups[(inv["entity_id"], inv["currency"], inv["total_minor"], _canon_lines(inv["line_items"]))].append(inv)
    for (ent, ccy, tot, _), invs in groups.items():
        if len(invs) < 2:
            continue
        invs = sorted(invs, key=lambda i: i["issued_at"])
        for later in invs[1:]:
            ids = sorted([invs[0]["invoice_id"], later["invoice_id"]])
            findings.append({"type": "duplicate_invoice", "affected_ids": ids, "claimed_amount_minor": tot,
                             "currency": ccy, "evidence_ids": ids,
                             "explanation": "Same entity, line items and service period invoiced twice."})

    for inv in invoices:
        iid, ccy = inv["invoice_id"], inv["currency"]
        d_policy = local_date(inv["issued_at"], tzn)
        ar_rows = [r for r in by_inv[iid] if r["account"] == AR and r["debit_minor"] > 0 and not r["payment_id"]]
        if not ar_rows:
            continue
        ar = ar_rows[0]
        rate = "1" if ccy == base else rates.get((d_policy.isoformat(), ccy))
        if rate is None:
            continue
        expected = convert(inv["total_minor"], ccy, base, rate)
        # date_or_fx: booked base amount differs from foreign amount x policy rate.
        if ccy != base and abs(ar["debit_minor"] - expected) > 2:
            findings.append({"type": "date_or_fx", "affected_ids": [iid],
                             "claimed_amount_minor": abs(ar["debit_minor"] - expected), "currency": base,
                             "evidence_ids": sorted([iid, ar["row_id"], f"{d_policy.isoformat()}|{ccy}|{base}"]),
                             "explanation": "Booked at a rate other than the policy-date rate."})
        # period_classification: posting period differs from the policy-date period.
        d_post = local_date(ar["timestamp"], tzn)
        if in_period(d_policy) != in_period(d_post):
            ev = [iid, ar["row_id"]] + ([f"{d_policy.isoformat()}|{ccy}|{base}"] if ccy != base else [])
            findings.append({"type": "period_classification", "affected_ids": [iid], "claimed_amount_minor": expected,
                             "currency": base, "evidence_ids": sorted(ev),
                             "explanation": "Posted outside the period of its issue date."})

    # payment_allocation: referenced invoice exists but part of the receipt sits in unapplied cash.
    for p in payments:
        refs = p["invoice_refs"]
        if not refs:
            continue
        un = [r for r in by_pay[p["payment_id"]] if r["account"] == UNAPPLIED and r["credit_minor"] > 0]
        if not un or len(refs) != 1:
            continue
        amount = sum(r["credit_minor"] for r in un)
        findings.append({"type": "payment_allocation", "affected_ids": sorted([p["payment_id"], refs[0]]),
                         "claimed_amount_minor": amount, "currency": base,
                         "evidence_ids": sorted([p["payment_id"], refs[0]] + [r["row_id"] for r in un]),
                         "explanation": "Receipt references the invoice but was left in unapplied cash."})
    findings.sort(key=lambda f: (f["type"], f["affected_ids"]))
    return findings[:30]


def submission(episode_id: str, findings: List[dict]) -> Dict[str, Any]:
    return {"episode_id": episode_id, "findings": findings}
