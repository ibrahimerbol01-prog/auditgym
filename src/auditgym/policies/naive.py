"""Naive heuristics used only for the measured failure analysis.

Each trick replaces ONE careful rule with the shortcut a simple solver would take. Scoring them
against the truth shows which legitimate distractors defeat which shortcut (brief §02: difficulty
must defeat simple tricks without making the task unsolvable).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from .rules import find_issues


def _utc_date(ts: str) -> date:
    return datetime.fromisoformat(ts).astimezone(timezone.utc).date()


def trick_duplicates_by_amount(t: Dict[str, Any], pol: Dict[str, Any], eid: str) -> List[dict]:
    """Duplicates = same entity and same total (ignores line items and service period)."""
    out = [f for f in find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], pol, eid) if f["type"] != "duplicate_invoice"]
    groups = defaultdict(list)
    for inv in t["invoices"]:
        groups[(inv["entity_id"], inv["currency"], inv["total_minor"])].append(inv)
    for (_, ccy, tot), invs in groups.items():
        invs = sorted(invs, key=lambda i: i["issued_at"])
        for later in invs[1:]:
            ids = sorted([invs[0]["invoice_id"], later["invoice_id"]])
            out.append({"type": "duplicate_invoice", "affected_ids": ids, "claimed_amount_minor": tot, "currency": ccy,
                        "evidence_ids": ids, "explanation": ""})
    return out[:30]


def trick_utc_dates(t: Dict[str, Any], pol: Dict[str, Any], eid: str) -> List[dict]:
    """Uses the UTC calendar date instead of the company time zone for periods and rates."""
    pol2 = dict(pol, timezone="UTC")
    return find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], pol2, eid)


def trick_any_unapplied(t: Dict[str, Any], pol: Dict[str, Any], eid: str) -> List[dict]:
    """Any cash in 2350 Unapplied is an allocation error (ignores documented advances)."""
    out = [f for f in find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], pol, eid) if f["type"] != "payment_allocation"]
    pays = {p["payment_id"]: p for p in t["payments"]}
    for r in t["ledger"]:
        if r["account"] == "2350" and r["credit_minor"] > 0 and r["payment_id"]:
            p = pays[r["payment_id"]]
            inv = (p["invoice_refs"] or ["?"])[0]
            out.append({"type": "payment_allocation", "affected_ids": sorted([p["payment_id"], inv]),
                        "claimed_amount_minor": r["credit_minor"], "currency": pol["base_currency"],
                        "evidence_ids": sorted([p["payment_id"], inv, r["row_id"]]), "explanation": ""})
    return out[:30]


def trick_no_evidence(t: Dict[str, Any], pol: Dict[str, Any], eid: str) -> List[dict]:
    """Right findings, but cites only the affected ids (no proof)."""
    fs = find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], pol, eid)
    return [dict(f, evidence_ids=list(f["affected_ids"])) for f in fs]


TRICKS = {
    "duplicates_by_amount_only": trick_duplicates_by_amount,
    "utc_dates_instead_of_company_tz": trick_utc_dates,
    "any_unapplied_cash_is_an_error": trick_any_unapplied,
    "findings_without_evidence": trick_no_evidence,
}
