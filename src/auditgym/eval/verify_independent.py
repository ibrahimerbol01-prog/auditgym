#!/usr/bin/env python3.11
"""Independent verifier for AuditGym episodes.

Written only from the specification (PLAN.md sections 4, 5.3, 5.3a, 5.4, 5.7,
7.2) and the public episode files. It imports nothing from the generator.

For every issue declared in private/truth.json it re-proves, from the PUBLIC
records and policy.json only:
  1. every affected id and every evidence id exists in the public records;
  2. the discrepancy is real and its amount is right
     (|expected - recomputed| <= 1 + conversions);
  3. at least one acceptable evidence set is sufficient on its own: the same
     per-type proof is re-run on a view of the episode that contains ONLY the
     records named in that set (plus policy.json).
It also checks the ledger balances, runs the per-type detectors over the whole
episode and reports every detection that the truth does not declare.

Usage: python3.11 verify_independent.py <episodes_root | episode_dir>
Exit status is non-zero if any episode fails.

Standard library only. Money is integer minor units; conversions use
decimal.Decimal and round half-even once, when converting to base minor units.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, getcontext

getcontext().prec = 50

EXPONENTS = {"KZT": 2, "USD": 2, "EUR": 2, "UZS": 2, "GBP": 2, "CNY": 2,
             "JPY": 0, "KWD": 3}

ACC_BANK, ACC_AR, ACC_AP, ACC_UNAPPLIED = "1010", "1200", "2100", "2350"
ACC_REVENUE, ACC_RETURNS, ACC_FX = "4000", "4100", "7810"

TYPES = ("duplicate_invoice", "payment_allocation", "date_or_fx",
         "period_classification")


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def _parse_offset(s: str) -> timezone:
    m = re.fullmatch(r"([+-])(\d{2}):(\d{2})", s.strip())
    if not m:
        raise ValueError(f"bad timezone_offset {s!r}")
    sign = 1 if m.group(1) == "+" else -1
    return timezone(sign * timedelta(hours=int(m.group(2)),
                                     minutes=int(m.group(3))))


def _int_or_none(v):
    if v is None or v == "":
        return None
    return int(v)


def _str_or_none(v):
    return None if v is None or v == "" else v


class Episode:
    """Public records of one episode, optionally restricted to a set of ids."""

    def __init__(self, policy, manifest, ledger, invoices, payments, docs, fx):
        self.policy = policy
        self.manifest = manifest
        self.ledger = ledger            # list of dict rows
        self.invoices = invoices        # invoice_id -> record
        self.payments = payments        # payment_id -> record
        self.docs = docs                # doc_id -> document
        self.fx = fx                    # "date|SRC|TGT" -> Decimal rate
        self.rows = {r["row_id"]: r for r in ledger}
        self.base = policy["base_currency"]
        self.tz = _parse_offset(policy["timezone_offset"])
        self.p_start = date.fromisoformat(policy["period"]["start"])
        self.p_end = date.fromisoformat(policy["period"]["end"])

    # ---- construction ----------------------------------------------------
    @classmethod
    def load(cls, ep_dir: str) -> "Episode":
        pub = os.path.join(ep_dir, "public")
        with open(os.path.join(pub, "policy.json"), encoding="utf-8") as f:
            policy = json.load(f)
        manifest = {}
        mp = os.path.join(pub, "manifest.json")
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as f:
                manifest = json.load(f)
        ledger = []
        with open(os.path.join(pub, "ledger.csv"), encoding="utf-8",
                  newline="") as f:
            for r in csv.DictReader(f):
                ledger.append({
                    "row_id": r["row_id"],
                    "timestamp": r["timestamp"],
                    "account": r["account"],
                    "debit_minor": _int_or_none(r["debit_minor"]) or 0,
                    "credit_minor": _int_or_none(r["credit_minor"]) or 0,
                    "currency": r["currency"],
                    "entity_id": _str_or_none(r["entity_id"]),
                    "invoice_id": _str_or_none(r["invoice_id"]),
                    "payment_id": _str_or_none(r["payment_id"]),
                })

        def jl(name):
            out = []
            p = os.path.join(pub, name)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            out.append(json.loads(line))
            return out

        invoices = {r["invoice_id"]: r for r in jl("invoices.jsonl")}
        payments = {r["payment_id"]: r for r in jl("payments.jsonl")}
        docs = {r["doc_id"]: r for r in jl("documents.jsonl")}
        fx = {}
        with open(os.path.join(pub, "fx.csv"), encoding="utf-8",
                  newline="") as f:
            for r in csv.DictReader(f):
                fid = f'{r["date"]}|{r["source_currency"]}|{r["target_currency"]}'
                fx[fid] = Decimal(r["rate"])
        return cls(policy, manifest, ledger, invoices, payments, docs, fx)

    def all_ids(self) -> set:
        return (set(self.rows) | set(self.invoices) | set(self.payments)
                | set(self.docs) | set(self.fx))

    def restrict(self, ids) -> "Episode":
        """A view holding only the records whose ids are in `ids`."""
        ids = set(ids)
        return Episode(
            self.policy, self.manifest,
            [r for r in self.ledger if r["row_id"] in ids],
            {k: v for k, v in self.invoices.items() if k in ids},
            {k: v for k, v in self.payments.items() if k in ids},
            {k: v for k, v in self.docs.items() if k in ids},
            {k: v for k, v in self.fx.items() if k in ids},
        )

    # ---- time and money ---------------------------------------------------
    def company_dt(self, ts: str) -> datetime:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            raise ValueError(f"timestamp without offset: {ts}")
        return dt.astimezone(self.tz)

    def company_date(self, ts: str) -> date:
        return self.company_dt(ts).date()

    def in_period(self, d: date) -> bool:
        return self.p_start <= d <= self.p_end

    def fx_id(self, d: date, cur: str) -> str:
        return f"{d.isoformat()}|{cur}|{self.base}"

    def rate(self, d: date, cur: str):
        if cur == self.base:
            return Decimal(1)
        return self.fx.get(self.fx_id(d, cur))

    def to_base(self, amount_minor: int, cur: str, d: date):
        """None if the needed fx row is not available in this view."""
        if cur == self.base:
            return amount_minor
        r = self.rate(d, cur)
        if r is None:
            return None
        return to_base_with_rate(amount_minor, cur, self.base, r)

    # ---- record helpers ---------------------------------------------------
    def invoice_policy_date(self, inv):
        """Policy date of an invoice: issued_at in company time; if the
        invoice's document carries a different date, the document wins.
        Returns (date, notes)."""
        notes = []
        d = self.company_date(inv["issued_at"])
        doc = self.docs.get(inv.get("doc_id")) if inv.get("doc_id") else None
        if doc is not None and doc.get("date"):
            dd = date.fromisoformat(doc["date"])
            if dd != d:
                notes.append(f"invoice {inv['invoice_id']}: document date "
                             f"{dd} != issued_at company date {d}; "
                             f"document date wins")
                d = dd
        return d, notes

    def payment_policy_date(self, pay):
        notes = []
        d = self.company_date(pay["timestamp"])
        doc = self.docs.get(pay.get("doc_id")) if pay.get("doc_id") else None
        if doc is not None and doc.get("date"):
            dd = date.fromisoformat(doc["date"])
            if dd != d:
                notes.append(f"payment {pay['payment_id']}: document date "
                             f"{dd} != timestamp company date {d}; "
                             f"document date wins")
                d = dd
        return d, notes

    def ar_postings(self, invoice_id):
        """AR (1200) debit rows that post the invoice itself (no payment)."""
        return [r for r in self.ledger
                if r["account"] == ACC_AR and r["invoice_id"] == invoice_id
                and r["payment_id"] is None and r["debit_minor"] > 0]

    def rows_of(self, account=None, invoice_id=None, payment_id=None):
        out = []
        for r in self.ledger:
            if account is not None and r["account"] != account:
                continue
            if invoice_id is not None and r["invoice_id"] != invoice_id:
                continue
            if payment_id is not None and r["payment_id"] != payment_id:
                continue
            out.append(r)
        return out

    def find_rate_dates(self, amount_minor, cur, booked):
        """All fx dates whose rate reproduces `booked` exactly."""
        hits = []
        for fid, r in self.fx.items():
            d, s, t = fid.split("|")
            if s == cur and t == self.base and \
                    to_base_with_rate(amount_minor, cur, self.base, r) == booked:
                hits.append(d)
        return sorted(hits)


def to_base_with_rate(amount_minor: int, cur: str, base: str, rate) -> int:
    shift = EXPONENTS[base] - EXPONENTS[cur]
    v = Decimal(amount_minor) * Decimal(rate) * (Decimal(10) ** shift)
    return int(v.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def canon_items(items):
    return json.dumps(items, sort_keys=True, separators=(",", ":"))


# --------------------------------------------------------------------------
# Per-type proofs. Each returns (problems, warnings, amount, facts).
# `full` = True when running on the whole episode: then contextual checks
# (credit notes, competing explanations, document consistency) are also run.
# On a restricted view (evidence sufficiency) only facts derivable from the
# records in the set are used.
# --------------------------------------------------------------------------

def prove_duplicate(ep: Episode, issue, full: bool):
    P, W, facts = [], [], {}
    ids = issue["affected_ids"]
    if len(ids) != 2:
        return [f"duplicate_invoice needs 2 affected ids, got {ids}"], W, None, facts
    invs = [ep.invoices.get(i) for i in ids]
    for i, inv in zip(ids, invs):
        if inv is None:
            P.append(f"invoice {i} not available")
    if P:
        return P, W, None, facts
    a, b = invs
    for fld in ("entity_id", "currency", "total_minor"):
        if a[fld] != b[fld]:
            P.append(f"{fld} differs: {a[fld]!r} vs {b[fld]!r}")
    if canon_items(a["line_items"]) != canon_items(b["line_items"]):
        P.append("line_items (incl. service_period) differ")
    for inv in invs:
        s = sum(li["amount_minor"] for li in inv["line_items"])
        if s != inv["total_minor"]:
            P.append(f"{inv['invoice_id']}: total_minor {inv['total_minor']} "
                     f"!= sum(line_items) {s}")
    amount = a["total_minor"]
    facts["currency"] = a["currency"]
    if full:
        # both posted to AR, and no credit note cancelling one of them
        for inv in invs:
            iid = inv["invoice_id"]
            posts = ep.ar_postings(iid)
            if not posts:
                P.append(f"{iid} is not posted to AR (no 1200 debit row)")
            cancel = sum(r["credit_minor"] for r in ep.rows_of(ACC_AR, invoice_id=iid)
                         if r["payment_id"] is None)
            ret = sum(r["debit_minor"] for r in ep.rows_of(ACC_RETURNS, invoice_id=iid))
            if cancel or ret:
                booked = sum(r["debit_minor"] for r in posts)
                msg = (f"{iid}: credit-note style rows found "
                       f"(AR credit w/o payment {cancel}, 4100 debit {ret})")
                if booked and cancel >= booked:
                    P.append(msg + " that cancel the invoice in full")
                else:
                    W.append(msg)
        # documents must agree with the records
        for inv in invs:
            doc = ep.docs.get(inv.get("doc_id"))
            if doc is not None:
                for fld in ("entity_id", "currency", "total_minor"):
                    if doc.get(fld) != inv[fld]:
                        P.append(f"{inv['invoice_id']}: document {fld} "
                                 f"{doc.get(fld)!r} != record {inv[fld]!r}")
                if canon_items(doc.get("line_items")) != canon_items(inv["line_items"]):
                    P.append(f"{inv['invoice_id']}: document line_items differ from record")
    return P, W, amount, facts


def _remit_refs(ep: Episode, pay):
    doc = ep.docs.get(pay.get("doc_id")) if pay.get("doc_id") else None
    refs = set(pay.get("invoice_refs") or [])
    if doc is not None:
        refs |= set(doc.get("references") or [])
        refs |= {a.get("invoice_id") for a in (doc.get("allocations") or [])}
    refs.discard(None)
    return refs, doc


def prove_payment_allocation(ep: Episode, issue, full: bool):
    P, W, facts = [], [], {}
    ids = issue["affected_ids"]
    pay_ids = [i for i in ids if i in ep.payments]
    inv_ids = [i for i in ids if i in ep.invoices]
    if len(ids) != 2 or len(pay_ids) != 1 or len(inv_ids) != 1:
        return ([f"need [payment_id, invoice_id] available, got {ids} "
                 f"(payments found {pay_ids}, invoices found {inv_ids})"],
                W, None, facts)
    pid, iid = pay_ids[0], inv_ids[0]
    pay, inv = ep.payments[pid], ep.invoices[iid]
    refs, doc = _remit_refs(ep, pay)
    if iid not in refs:
        P.append(f"{pid}: neither invoice_refs nor remittance names {iid}")
    if pay.get("invoice_refs") is None and (doc is None or not doc.get("references")):
        P.append(f"{pid}: invoice_refs null -> legitimate advance pattern")
    if len(refs) > 1:
        # lump sum: the under-applied invoice must be identifiable
        if doc is None or not doc.get("allocations"):
            P.append(f"{pid} references several invoices {sorted(refs)} and "
                     f"no allocation breakdown is available -> ambiguous")
    unapplied = [r for r in ep.rows_of(ACC_UNAPPLIED, payment_id=pid)]
    amt = sum(r["credit_minor"] - r["debit_minor"] for r in unapplied)
    facts["unapplied_rows"] = [r["row_id"] for r in unapplied]
    if not unapplied or amt <= 0:
        P.append(f"no unapplied-cash (2350) credit for {pid} available")
    if pay["currency"] == inv["currency"] and pay["amount_minor"] > inv["total_minor"]:
        W.append(f"{pid} ({pay['amount_minor']}) exceeds invoice total "
                 f"({inv['total_minor']}): part could be legitimate overpayment")
    facts["payment_foreign"] = pay["currency"] != ep.base
    if full:
        if doc is not None:
            memo = (doc.get("memo") or "").lower()
            if "advance" in memo or "unapplied" in memo:
                P.append(f"{pid}: remittance memo documents the unapplied cash: {doc.get('memo')!r}")
            if "deduction" in memo or "credit note" in memo:
                W.append(f"{pid}: remittance memo mentions a deduction: {doc.get('memo')!r}")
            if doc.get("amount_minor") != pay["amount_minor"] or doc.get("currency") != pay["currency"]:
                P.append(f"{pid}: remittance amount/currency disagrees with payment record")
        # bank receipt vs. AR application
        bank = sum(r["debit_minor"] - r["credit_minor"] for r in ep.rows_of(ACC_BANK, payment_id=pid))
        applied = sum(r["credit_minor"] - r["debit_minor"]
                      for r in ep.rows_of(ACC_AR, invoice_id=iid, payment_id=pid))
        facts.update(bank=bank, applied_to_invoice=applied)
        # open AR balance on the invoice: unapplied cash could have been applied
        ar_bal = sum(r["debit_minor"] - r["credit_minor"] for r in ep.rows_of(ACC_AR, invoice_id=iid))
        facts["invoice_ar_open"] = ar_bal
        if ar_bal <= 0:
            P.append(f"{iid}: AR fully cleared ({ar_bal}); unapplied cash is not owed to it")
        elif ar_bal + 1 < amt and len(refs) == 1:
            W.append(f"{iid}: open AR {ar_bal} smaller than unapplied {amt}")
        # sanity: payment rows balance
        prow = ep.rows_of(payment_id=pid)
        if sum(r["debit_minor"] for r in prow) != sum(r["credit_minor"] for r in prow):
            P.append(f"{pid}: payment journal rows do not balance")
        # foreign amount check of the bank receipt at the payment date rate
        pd, notes = ep.payment_policy_date(pay)
        W.extend(notes)
        exp_bank = ep.to_base(pay["amount_minor"], pay["currency"], pd)
        if exp_bank is not None and exp_bank != bank:
            W.append(f"{pid}: bank debit {bank} != amount x rate({pd}) {exp_bank}")
    return P, W, amt if unapplied else None, facts


def prove_date_or_fx(ep: Episode, issue, full: bool):
    P, W, facts = [], [], {}
    ids = issue["affected_ids"]
    if len(ids) != 1:
        return [f"date_or_fx expects one affected id, got {ids}"], W, None, facts
    rid = ids[0]
    if rid in ep.invoices:
        rec = ep.invoices[rid]
        cur, amt_f = rec["currency"], rec["total_minor"]
        pdate, notes = ep.invoice_policy_date(rec)
        posts = ep.ar_postings(rid)
        booked = sum(r["debit_minor"] for r in posts) if posts else None
    elif rid in ep.payments:
        rec = ep.payments[rid]
        cur, amt_f = rec["currency"], rec["amount_minor"]
        pdate, notes = ep.payment_policy_date(rec)
        posts = ep.rows_of(ACC_BANK, payment_id=rid)
        booked = sum(r["debit_minor"] - r["credit_minor"] for r in posts) if posts else None
    else:
        return [f"record {rid} not available"], W, None, facts
    W.extend(notes)
    if cur == ep.base:
        P.append(f"{rid} is in base currency {cur}; date_or_fx applies to foreign records only")
        return P, W, None, facts
    if not posts:
        P.append(f"booked ledger row for {rid} not available")
        return P, W, None, facts
    correct = ep.to_base(amt_f, cur, pdate)
    facts.update(policy_date=str(pdate), booked=booked, correct=correct,
                 fx_row=ep.fx_id(pdate, cur))
    if correct is None:
        P.append(f"fx row {ep.fx_id(pdate, cur)} (policy date) not available")
        return P, W, None, facts
    if booked == correct:
        P.append(f"booked {booked} equals amount x rate(policy date) -> no discrepancy")
        return P, W, 0, facts
    posting_dates = sorted({ep.company_date(r["timestamp"]) for r in posts})
    facts["posting_dates"] = [str(d) for d in posting_dates]
    if full:
        hits = ep.find_rate_dates(amt_f, cur, booked)
        facts["booked_matches_rate_of"] = hits
        if not hits:
            W.append(f"booked {booked} does not match the rate of any fx date")
        variant = issue.get("variant")
        pd_in = [d for d in posting_dates if d != pdate]
        if variant == "b":
            if not pd_in:
                P.append("variant b: ledger posting date equals the document date")
            elif not any(str(d) in hits for d in posting_dates):
                P.append(f"variant b: booked amount does not match rate of posting date {posting_dates}")
            for d in posting_dates:
                if ep.in_period(d) != ep.in_period(pdate):
                    P.append("variant b: wrong date crosses the period boundary")
        elif variant == "a":
            if pd_in:
                W.append(f"variant a but posting date {posting_dates} != policy date {pdate}"
                         " (expected only if an interacting period issue moved it)")
        doc = ep.docs.get(rec.get("doc_id")) if rec.get("doc_id") else None
        if doc is None:
            W.append(f"{rid}: no document to confirm the date")
    return P, W, abs(booked - correct), facts


def prove_period(ep: Episode, issue, full: bool):
    P, W, facts = [], [], {}
    ids = issue["affected_ids"]
    if len(ids) != 1:
        return [f"period_classification expects one affected id, got {ids}"], W, None, facts
    rid = ids[0]
    if rid in ep.invoices:
        rec = ep.invoices[rid]
        cur, amt_f = rec["currency"], rec["total_minor"]
        pdate, notes = ep.invoice_policy_date(rec)
        posts = ep.ar_postings(rid)
        booked = sum(r["debit_minor"] for r in posts)
    elif rid in ep.payments:
        rec = ep.payments[rid]
        cur, amt_f = rec["currency"], rec["amount_minor"]
        pdate, notes = ep.payment_policy_date(rec)
        posts = ep.rows_of(ACC_BANK, payment_id=rid)
        booked = sum(r["debit_minor"] - r["credit_minor"] for r in posts)
    else:
        return [f"record {rid} not available"], W, None, facts
    W.extend(notes)
    if not posts:
        return [f"posting ledger row for {rid} not available"], W, None, facts
    pin = ep.in_period(pdate)
    post_dates = sorted({ep.company_date(r["timestamp"]) for r in posts})
    facts.update(policy_date=str(pdate), policy_in_period=pin,
                 posting_dates=[str(d) for d in post_dates], booked=booked)
    mism = [d for d in post_dates if ep.in_period(d) != pin]
    if not mism:
        P.append(f"posting {post_dates} and policy date {pdate} are in the same period")
    correct = ep.to_base(amt_f, cur, pdate)
    facts["foreign"] = cur != ep.base
    if correct is None:
        # amount needs the fx row of the policy date; it is not available
        facts["amount_source"] = "booked ledger row (fx row not available)"
        return P, W, None, facts
    facts["correct"] = correct
    if full and booked != correct:
        W.append(f"booked {booked} != correct {correct} (amount also wrong; "
                 "expected only if an interacting date_or_fx issue exists)")
    return P, W, correct, facts


PROVERS = {
    "duplicate_invoice": prove_duplicate,
    "payment_allocation": prove_payment_allocation,
    "date_or_fx": prove_date_or_fx,
    "period_classification": prove_period,
}


def expected_conversions(ep: Episode, issue):
    t = issue["type"]
    if t == "date_or_fx":
        return 1
    if t == "duplicate_invoice":
        return 0
    if t == "payment_allocation":
        p = next((ep.payments[i] for i in issue["affected_ids"] if i in ep.payments), None)
        return None if p is None else int(p["currency"] != ep.base)
    if t == "period_classification":
        r = issue["affected_ids"][0]
        rec = ep.invoices.get(r) or ep.payments.get(r)
        return None if rec is None else int(rec["currency"] != ep.base)
    return None


def expected_currency(ep: Episode, issue):
    if issue["type"] == "duplicate_invoice":
        inv = ep.invoices.get(issue["affected_ids"][0])
        return inv["currency"] if inv else None
    return ep.base


# --------------------------------------------------------------------------
# Detectors (whole episode)
# --------------------------------------------------------------------------

def detect_all(ep: Episode):
    """Returns list of detections: dict(type, affected_ids, amount, detail)."""
    out = []
    # duplicate invoices
    groups = {}
    for inv in ep.invoices.values():
        key = (inv["entity_id"], inv["currency"], inv["total_minor"],
               canon_items(inv["line_items"]))
        groups.setdefault(key, []).append(inv["invoice_id"])
    for key, g in groups.items():
        if len(g) < 2:
            continue
        g = sorted(g)
        for i in range(len(g)):
            for j in range(i + 1, len(g)):
                pair = [g[i], g[j]]
                # cancelled by a credit note? then legitimate
                cancelled = False
                for iid in pair:
                    booked = sum(r["debit_minor"] for r in ep.ar_postings(iid))
                    cn = sum(r["credit_minor"] for r in ep.rows_of(ACC_AR, invoice_id=iid)
                             if r["payment_id"] is None)
                    if booked and cn >= booked:
                        cancelled = True
                if not cancelled:
                    out.append(dict(type="duplicate_invoice", affected_ids=pair,
                                    amount=key[2], currency=key[1], detail=""))
    # payment allocation: unapplied cash on a payment that names an invoice
    for pid, pay in ep.payments.items():
        un = ep.rows_of(ACC_UNAPPLIED, payment_id=pid)
        amt = sum(r["credit_minor"] - r["debit_minor"] for r in un)
        if amt <= 0:
            continue
        refs, doc = _remit_refs(ep, pay)
        if not refs:
            continue  # advance payment without reference: legitimate
        memo = ((doc or {}).get("memo") or "").lower()
        if "advance" in memo or "unapplied" in memo:
            continue
        cands = []
        for iid in sorted(refs):
            ar_bal = sum(r["debit_minor"] - r["credit_minor"]
                         for r in ep.rows_of(ACC_AR, invoice_id=iid))
            if ar_bal > 0:
                cands.append(iid)
        if len(cands) == 1:
            out.append(dict(type="payment_allocation", affected_ids=sorted([pid, cands[0]]),
                            amount=amt, currency=ep.base, detail=""))
        else:
            out.append(dict(type="payment_allocation", affected_ids=[pid],
                            amount=amt, currency=ep.base,
                            detail=f"ambiguous: open referenced invoices {cands}"))
    # date_or_fx on foreign invoices
    for iid, inv in ep.invoices.items():
        if inv["currency"] == ep.base:
            continue
        posts = ep.ar_postings(iid)
        if not posts:
            continue
        pdate, _ = ep.invoice_policy_date(inv)
        correct = ep.to_base(inv["total_minor"], inv["currency"], pdate)
        booked = sum(r["debit_minor"] for r in posts)
        if correct is None:
            out.append(dict(type="date_or_fx", affected_ids=[iid], amount=None,
                            currency=ep.base, detail=f"no fx row for {pdate}"))
        elif booked != correct:
            out.append(dict(type="date_or_fx", affected_ids=[iid],
                            amount=abs(booked - correct), currency=ep.base, detail=""))
    # date_or_fx on foreign payments (bank receipt vs amount x rate)
    for pid, pay in ep.payments.items():
        if pay["currency"] == ep.base:
            continue
        bank = ep.rows_of(ACC_BANK, payment_id=pid)
        if not bank:
            continue
        pdate, _ = ep.payment_policy_date(pay)
        correct = ep.to_base(pay["amount_minor"], pay["currency"], pdate)
        booked = sum(r["debit_minor"] - r["credit_minor"] for r in bank)
        if correct is not None and booked != correct:
            out.append(dict(type="date_or_fx", affected_ids=[pid],
                            amount=abs(booked - correct), currency=ep.base,
                            detail="payment bank receipt"))
    # period classification on invoices and payments
    for iid, inv in ep.invoices.items():
        posts = ep.ar_postings(iid)
        if not posts:
            continue
        pdate, _ = ep.invoice_policy_date(inv)
        if any(ep.in_period(ep.company_date(r["timestamp"])) != ep.in_period(pdate)
               for r in posts):
            out.append(dict(type="period_classification", affected_ids=[iid],
                            amount=ep.to_base(inv["total_minor"], inv["currency"], pdate),
                            currency=ep.base, detail=""))
    for pid, pay in ep.payments.items():
        bank = ep.rows_of(ACC_BANK, payment_id=pid)
        if not bank:
            continue
        pdate, _ = ep.payment_policy_date(pay)
        if any(ep.in_period(ep.company_date(r["timestamp"])) != ep.in_period(pdate)
               for r in bank):
            out.append(dict(type="period_classification", affected_ids=[pid],
                            amount=ep.to_base(pay["amount_minor"], pay["currency"], pdate),
                            currency=ep.base, detail="payment"))
    return out


def informational_scan(ep: Episode):
    """Non-type observations: posting date != document date with no
    amount/period consequence, records without postings, etc."""
    notes = []
    for iid, inv in ep.invoices.items():
        pdate, n = ep.invoice_policy_date(inv)
        notes.extend(n)
        for r in ep.ar_postings(iid):
            d = ep.company_date(r["timestamp"])
            if d != pdate:
                notes.append(f"{iid}: AR posting {r['row_id']} on {d}, policy date {pdate}")
        if not ep.ar_postings(iid):
            notes.append(f"{iid}: invoice has no AR posting")
    return notes


# --------------------------------------------------------------------------
# Episode verification
# --------------------------------------------------------------------------

def verify_episode(ep_dir: str) -> dict:
    ep = Episode.load(ep_dir)
    with open(os.path.join(ep_dir, "private", "truth.json"), encoding="utf-8") as f:
        truth = json.load(f)
    episode_id = truth.get("episode_id") or os.path.basename(ep_dir.rstrip("/"))
    gp, gwarn = [], []

    # ---- global equalities --------------------------------------------
    if ep.manifest.get("episode_id") and ep.manifest["episode_id"] != episode_id:
        gp.append(f"manifest episode_id {ep.manifest['episode_id']} != truth {episode_id}")
    td = sum(r["debit_minor"] for r in ep.ledger)
    tc = sum(r["credit_minor"] for r in ep.ledger)
    if td != tc:
        gp.append(f"ledger does not balance: debit {td} != credit {tc}")
    for r in ep.ledger:
        if r["currency"] != ep.base:
            gp.append(f"{r['row_id']}: ledger currency {r['currency']} != base {ep.base}")
        if (r["debit_minor"] > 0) == (r["credit_minor"] > 0):
            gp.append(f"{r['row_id']}: row must have exactly one of debit/credit")
        if r["debit_minor"] < 0 or r["credit_minor"] < 0:
            gp.append(f"{r['row_id']}: negative amount")
    for iid, inv in ep.invoices.items():
        s = sum(li["amount_minor"] for li in inv["line_items"])
        if s != inv["total_minor"]:
            gp.append(f"{iid}: total {inv['total_minor']} != sum(line_items) {s}")
        if inv["currency"] not in EXPONENTS:
            gp.append(f"{iid}: unknown currency {inv['currency']}")
    # per-transaction balance: rows grouped by payment, and invoice postings
    by_pay = {}
    for r in ep.ledger:
        if r["payment_id"]:
            by_pay.setdefault(r["payment_id"], []).append(r)
    for pid, rows in by_pay.items():
        if sum(r["debit_minor"] for r in rows) != sum(r["credit_minor"] for r in rows):
            gp.append(f"payment {pid}: its ledger rows do not balance")
    for iid in ep.invoices:
        ar = sum(r["debit_minor"] for r in ep.ar_postings(iid))
        rev = sum(r["credit_minor"] for r in ep.rows_of(ACC_REVENUE, invoice_id=iid))
        if ar != rev:
            gwarn.append(f"{iid}: AR posting {ar} != revenue {rev}")
    # counts
    cnt = ep.manifest.get("counts") or {}
    actual = {"ledger": len(ep.ledger), "invoices": len(ep.invoices),
              "payments": len(ep.payments), "fx": len(ep.fx), "documents": len(ep.docs)}
    for k, v in cnt.items():
        if actual.get(k) != v:
            gp.append(f"manifest count {k}={v} but found {actual.get(k)}")
    # id uniqueness across tables
    seen = {}
    for name, keys in (("ledger", [r["row_id"] for r in ep.ledger]),
                       ("invoices", list(ep.invoices)), ("payments", list(ep.payments)),
                       ("documents", list(ep.docs)), ("fx", list(ep.fx))):
        for k in keys:
            if k in seen and seen[k] != name:
                gp.append(f"id {k} appears in {seen[k]} and {name}")
            seen[k] = name
    # documents agree with records
    for iid, inv in ep.invoices.items():
        doc = ep.docs.get(inv.get("doc_id")) if inv.get("doc_id") else None
        if inv.get("doc_id") and doc is None:
            gp.append(f"{iid}: doc_id {inv['doc_id']} not found")
        if doc is not None:
            for fld in ("invoice_id", "entity_id", "currency", "total_minor"):
                if doc.get(fld) != inv[fld]:
                    gp.append(f"{iid}: document {fld} {doc.get(fld)!r} != {inv[fld]!r}")
            if canon_items(doc.get("line_items")) != canon_items(inv["line_items"]):
                gp.append(f"{iid}: document line_items differ")
    for pid, pay in ep.payments.items():
        doc = ep.docs.get(pay.get("doc_id")) if pay.get("doc_id") else None
        if pay.get("doc_id") and doc is None:
            gp.append(f"{pid}: doc_id {pay['doc_id']} not found")
        if doc is not None:
            for fld in ("payment_id", "currency", "amount_minor"):
                if doc.get(fld) != pay[fld]:
                    gp.append(f"{pid}: document {fld} {doc.get(fld)!r} != {pay[fld]!r}")
            if sorted(doc.get("references") or []) != sorted(pay.get("invoice_refs") or []):
                gwarn.append(f"{pid}: document references {doc.get('references')} "
                             f"!= invoice_refs {pay.get('invoice_refs')}")
            alloc = sum(a.get("amount_minor", 0) for a in doc.get("allocations") or [])
            if doc.get("allocations") and alloc != pay["amount_minor"]:
                gwarn.append(f"{pid}: remittance allocations sum {alloc} != amount {pay['amount_minor']}")

    # ---- issues ---------------------------------------------------------
    all_ids = ep.all_ids()
    issue_ids = {i["issue_id"] for i in truth.get("issues", [])}
    results = []
    for issue in truth.get("issues", []):
        prob, warn = [], []
        t = issue.get("type")
        if t not in PROVERS:
            results.append(dict(issue_id=issue.get("issue_id"), type=t, ok=False,
                                problems=[f"unknown type {t}"], warnings=[]))
            continue
        # 1. existence
        for i in issue["affected_ids"]:
            if i not in all_ids:
                prob.append(f"affected id {i} not in public records")
        for s in issue["acceptable_evidence_sets"]:
            for i in s:
                if i not in all_ids:
                    prob.append(f"evidence id {i} not in public records")
        for j in issue.get("interacts_with", []):
            if j not in issue_ids:
                prob.append(f"interacts_with {j} is not a declared issue")
        # currency / conversions fields vs policy tolerance table
        ec = expected_currency(ep, issue)
        if ec is not None and issue["currency"] != ec:
            prob.append(f"currency {issue['currency']} but should be {ec}")
        econv = expected_conversions(ep, issue)
        if econv is not None and issue.get("conversions") != econv:
            prob.append(f"conversions {issue.get('conversions')} but policy table gives {econv}")
        tol = 1 + int(issue.get("conversions") or 0)
        exp = issue["expected_amount_minor"]
        if not isinstance(exp, int) or isinstance(exp, bool) or exp <= 0:
            prob.append(f"expected_amount_minor {exp!r} must be a positive integer")
        # 2. reality and amount on the whole episode
        P, W, amt, facts = PROVERS[t](ep, issue, True)
        prob.extend(f"[full] {p}" for p in P)
        warn.extend(f"[full] {w}" for w in W)
        if amt is None:
            prob.append("[full] amount could not be recomputed")
        elif abs(amt - exp) > tol:
            prob.append(f"[full] amount: recomputed {amt}, declared {exp}, tolerance {tol}")
        # 3. sufficiency of evidence sets
        suff = []
        for s in issue["acceptable_evidence_sets"]:
            view = ep.restrict(s)
            sP, sW, samt, sfacts = PROVERS[t](view, issue, False)
            why = list(sP)
            if not why:
                if samt is None and t == "period_classification":
                    # amount needs the policy-date fx row; fall back to the
                    # booked ledger row in the set, which is only trustworthy
                    # if it equals the correct amount (not provable here).
                    b = sfacts.get("booked")
                    if b is not None and abs(b - exp) <= tol:
                        warn.append(f"set {s}: period mismatch proven; amount {exp} is only "
                                    f"readable from the booked ledger row; its correctness "
                                    f"needs fx row {view.fx_id(date.fromisoformat(sfacts['policy_date']), ep.invoices.get(issue['affected_ids'][0], {}).get('currency', '?'))} "
                                    f"which is not in the set")
                    else:
                        why.append(f"expected amount {exp} cannot be derived from the set "
                                   f"(booked row shows {b}; fx row of policy date "
                                   f"{sfacts.get('policy_date')} not in set)")
                elif samt is None:
                    why.append("amount not derivable from the set")
                elif abs(samt - exp) > tol:
                    why.append(f"amount from set {samt} != declared {exp}")
            if t == "date_or_fx" and issue.get("variant") == "b":
                rec = ep.invoices.get(issue["affected_ids"][0]) or ep.payments.get(issue["affected_ids"][0])
                if rec and rec.get("doc_id") and rec["doc_id"] not in s:
                    warn.append(f"set {s}: variant b set omits doc_id {rec['doc_id']} that "
                                f"PLAN 5.3a lists in the minimum set (still provable via the "
                                f"record's issued_at)")
            if t == "duplicate_invoice":
                if not any(i in ep.rows for i in s):
                    warn.append(f"set {s}: AR postings of the pair are not in the set "
                                f"(PLAN 5.3a minimum is both invoice ids; posting checked on full data)")
            suff.append((s, why))
        if not any(not why for _, why in suff):
            for s, why in suff:
                prob.append(f"evidence set {s} insufficient: " + "; ".join(why))
        results.append(dict(issue_id=issue["issue_id"], type=t, ok=not prob,
                            problems=prob, warnings=warn, recomputed=amt,
                            expected=exp, facts=facts))

    # ---- detectors vs truth ---------------------------------------------
    dets = detect_all(ep)
    declared = {(i["type"], tuple(sorted(i["affected_ids"]))) for i in truth.get("issues", [])}
    undeclared = []
    for d in dets:
        key = (d["type"], tuple(sorted(d["affected_ids"])))
        if key not in declared:
            undeclared.append(d)
            gp.append(f"undeclared detection: {d['type']} {d['affected_ids']} "
                      f"amount={d['amount']} {d['detail']}".rstrip())
    detected_keys = {(d["type"], tuple(sorted(d["affected_ids"]))) for d in dets}
    for i in truth.get("issues", []):
        if (i["type"], tuple(sorted(i["affected_ids"]))) not in detected_keys:
            for r in results:
                if r["issue_id"] == i["issue_id"]:
                    r["problems"].append("detector did not fire on this declared issue")
                    r["ok"] = False

    ok = not gp and all(r["ok"] for r in results)
    return dict(episode_id=episode_id, ok=ok, issues=results,
                global_problems=gp, global_warnings=gwarn,
                info=informational_scan(ep))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _episode_dirs(root):
    if os.path.isdir(os.path.join(root, "public")):
        return [root]
    return sorted(os.path.join(root, d) for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d, "public")))


def main(argv):
    if len(argv) != 2:
        print("usage: verify_independent.py <episodes_root>", file=sys.stderr)
        return 2
    verbose = os.environ.get("VERIFY_VERBOSE") == "1"
    any_fail = False
    rows = []
    reports = []
    for d in _episode_dirs(argv[1]):
        try:
            rep = verify_episode(d)
        except Exception as e:  # never crash the table
            rep = dict(episode_id=os.path.basename(d), ok=False, issues=[],
                       global_problems=[f"verifier error: {type(e).__name__}: {e}"],
                       global_warnings=[], info=[])
        reports.append(rep)
        any_fail |= not rep["ok"]
        if not rep["issues"]:
            rows.append((rep["episode_id"], "-", "(no issues)", "", "",
                         "PASS" if rep["ok"] else "FAIL"))
        for r in rep["issues"]:
            rows.append((rep["episode_id"], r["issue_id"], r["type"],
                         str(r.get("expected", "")), str(r.get("recomputed", "")),
                         "PASS" if r["ok"] else "FAIL"))
        rows.append((rep["episode_id"], "GLOBAL", "balance/detectors/consistency", "", "",
                     "PASS" if not rep["global_problems"] else "FAIL"))
    hdr = ("episode", "issue", "type", "declared", "recomputed", "result")
    w = [max(len(str(x[i])) for x in rows + [hdr]) for i in range(len(hdr))]
    line = "  ".join(h.ljust(w[i]) for i, h in enumerate(hdr))
    print(line)
    print("-" * len(line))
    for r in rows:
        print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))
    print()
    for rep in reports:
        msgs = []
        for r in rep["issues"]:
            for p in r["problems"]:
                msgs.append(f"  FAIL {r['issue_id']}: {p}")
            for x in r.get("warnings", []):
                msgs.append(f"  warn {r['issue_id']}: {x}")
        for p in rep["global_problems"]:
            msgs.append(f"  FAIL global: {p}")
        for x in rep.get("global_warnings", []):
            msgs.append(f"  warn global: {x}")
        if verbose:
            for x in rep.get("info", []):
                msgs.append(f"  info: {x}")
        if msgs:
            print(f"{rep['episode_id']}:")
            print("\n".join(msgs))
    print()
    print("OVERALL:", "FAIL" if any_fail else "PASS")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


# --------------------------------------------------------------------------
# Adapter used by `python -m auditgym.verify` (area 2). Writes the episode's PUBLIC files and the
# truth CLAIMS to a temporary directory and runs the independent verifier on them. The
# verifier itself imports nothing from auditgym.gen (enforced by tests/test_independence.py).
# --------------------------------------------------------------------------
def check_episode(ep_obj: dict) -> list:
    import tempfile
    from ..gen.export import write_tables  # file writer only; no generation logic

    with tempfile.TemporaryDirectory() as d:
        root = os.path.join(d, ep_obj["public"]["manifest"]["episode_id"])
        write_tables(os.path.join(root, "public"), ep_obj["public"]["tables"], 0)
        for name in ("manifest", "policy"):
            with open(os.path.join(root, "public", f"{name}.json"), "w", encoding="utf-8") as fh:
                json.dump(ep_obj["public"][name], fh)
        os.makedirs(os.path.join(root, "private"))
        with open(os.path.join(root, "private", "truth.json"), "w", encoding="utf-8") as fh:
            json.dump(ep_obj["private"]["truth"], fh)
        res = verify_episode(root)
    problems = list(res["global_problems"])
    for r in res["issues"]:
        if not r["ok"]:
            problems += [f"{r['issue_id']}: {p}" for p in r["problems"]]
    return problems
