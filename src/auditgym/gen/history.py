"""Consistent hidden company history and its derived public tables (plan §5.1-§5.4).

Everything uses internal tokens (``§I12``, ``§P3``, ``§L45``, ``§E2``, ``§D7``) that export.py
renames with ``id_seed``. The ledger is double-entry in the base currency and balances by
construction; validate.check_books_balance proves it for every episode.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Dict, List, Optional, Tuple

from ..config import EpisodeConfig
from ..money import convert
from ..seeding import Rng
from ..timeutil import iso, local_date, offset_str, tz
from ..version import ENV_VERSION

AR, REVENUE, RETURNS, BANK, UNAPPLIED, FXGL, AP = "1200", "4000", "4100", "1010", "2350", "7810", "2100"
EXPENSE_ACCOUNTS = ["6100", "6200", "6300", "6400", "6500"]
ACCOUNT_NAMES = {
    AR: "Accounts receivable", REVENUE: "Revenue", RETURNS: "Sales returns and allowances",
    BANK: "Bank", UNAPPLIED: "Unapplied cash", FXGL: "FX gain/loss", AP: "Accounts payable",
    "6100": "Freight costs", "6200": "Rent", "6300": "Software", "6400": "Utilities", "6500": "Contractors",
}
USD_VALUE = {"USD": "1", "EUR": "1.08", "GBP": "1.27", "KWD": "3.25", "CNY": "0.14",
             "JPY": "0.0066", "KZT": "0.00205", "UZS": "0.00008"}

_ADJ = ["Kestrel", "Orchard", "Nordvik", "Saffron", "Bluewing", "Quartzline", "Amberfield", "Cobalt",
        "Silverbirch", "Harbor", "Juniper", "Lumen", "Marlow", "Northgate", "Oakridge", "Pinecrest",
        "Redstone", "Stellar", "Tamarind", "Westbrook", "Yarrow", "Zephyr", "Brightwater", "Copperleaf"]
_NOUN = ["Freight", "Studio", "Polymers", "Foods", "Clinics", "Textiles", "Analytics", "Logistics",
         "Ceramics", "Robotics", "Optics", "Farms", "Print", "Labs", "Motors", "Media"]
_SUFFIX = ["LLP", "Ltd", "AS", "GmbH", "LLC", "SA", "Co"]
_SERVICES = ["Freight forwarding", "Warehouse storage", "Consulting hours", "Software licence",
             "Maintenance contract", "Customs brokerage", "Data processing", "Design services",
             "Equipment rental", "Training workshop", "Quality inspection", "Packaging supplies"]


def tok(kind: str, n: int) -> str:
    return f"§{kind}{n}"


def fx_id(d: date, src: str, dst: str) -> str:
    return f"{d.isoformat()}|{src}|{dst}"


@dataclass
class Tables:
    ledger: List[dict] = field(default_factory=list)
    invoices: List[dict] = field(default_factory=list)
    payments: List[dict] = field(default_factory=list)
    fx: List[dict] = field(default_factory=list)
    documents: Dict[str, dict] = field(default_factory=dict)

    def copy(self) -> "Tables":
        import copy as _c
        return _c.deepcopy(self)


@dataclass
class World:
    cfg: EpisodeConfig
    seed: int
    period_start: date
    period_end: date
    rates: Dict[Tuple[str, date], str]
    tables: Tables
    hosts: Dict[str, List[str]]
    counters: Dict[str, int]
    entities: Dict[str, str]
    meta: Dict[str, dict]  # per-record hidden facts (e.g. payment kind)

    @property
    def base(self) -> str:
        return self.cfg.base_currency

    def next(self, kind: str) -> str:
        self.counters[kind] = self.counters.get(kind, 0) + 1
        return tok(kind, self.counters[kind])

    def rate(self, ccy: str, d: date) -> str:
        if ccy == self.base:
            return "1"
        return self.rates[(ccy, d)]

    def to_base(self, amount: int, ccy: str, d: date) -> int:
        return convert(amount, ccy, self.base, self.rate(ccy, d))

    def tz_name(self) -> str:
        return self.cfg.timezone

    def in_period(self, d: date) -> bool:
        return self.period_start <= d <= self.period_end

    def ts(self, d: date, hour: int, minute: int, utc_form: bool = False) -> str:
        dt = datetime.combine(d, time(hour, minute), tz(self.tz_name()))
        if utc_form:
            from datetime import timezone as _tz
            dt = dt.astimezone(_tz.utc)
        return iso(dt)

    def ldate(self, ts: str) -> date:
        return local_date(ts, self.tz_name())

    def add_row(self, ts: str, account: str, debit: int, credit: int, entity: Optional[str],
                invoice: Optional[str], payment: Optional[str]) -> str:
        key = self.next("L")
        self.tables.ledger.append({
            "row_id": key, "timestamp": ts, "account": account, "debit_minor": debit,
            "credit_minor": credit, "currency": self.base, "entity_id": entity,
            "invoice_id": invoice, "payment_id": payment})
        return key


def _period(cfg: EpisodeConfig) -> Tuple[date, date]:
    y, m = cfg.period_year, cfg.period_start_month
    start = date(y, m, 1)
    em = m + cfg.period_months - 1
    ey = y + (em - 1) // 12
    em = (em - 1) % 12 + 1
    end = date(ey, em, calendar.monthrange(ey, em)[1])
    return start, end


def _rates(cfg: EpisodeConfig, rng: Rng, start: date, end: date) -> Dict[Tuple[str, date], str]:
    out: Dict[Tuple[str, date], str] = {}
    first, last = start - timedelta(days=12), end + timedelta(days=12)
    for ccy in cfg.foreign_currencies:
        level = Decimal(USD_VALUE[ccy]) / Decimal(USD_VALUE[cfg.base_currency])
        d = first
        while d <= last:
            step = Decimal(str(round((rng.random() - 0.5) * 0.012, 6)))
            if step == 0:
                step = Decimal("0.001")
            level = level * (Decimal(1) + step)
            out[(ccy, d)] = _sig(level, 6)
            d += timedelta(days=1)
    return out


def _sig(x: Decimal, digits: int) -> str:
    """Round to ``digits`` significant digits, as a plain decimal string."""
    if x == 0:
        return "0"
    exp = x.adjusted() - digits + 1
    q = x.quantize(Decimal(1).scaleb(exp), rounding=ROUND_HALF_EVEN)
    return format(q.normalize(), "f")


def _company_name(rng: Rng, used: set) -> str:
    for _ in range(200):
        n = f"{rng.choice(_ADJ)} {rng.choice(_NOUN)} {rng.choice(_SUFFIX)}"
        if n not in used:
            used.add(n)
            return n
    raise RuntimeError("name pool exhausted")


def _rand_day(rng: Rng, lo: date, hi: date) -> date:
    return lo + timedelta(days=rng.rand_int(0, (hi - lo).days))


def _money(rng: Rng, ccy: str, base: str) -> int:
    """A plausible line amount in minor units of ``ccy`` (about 300-9000 USD of value)."""
    usd = Decimal(rng.rand_int(300, 9000))
    value = usd / Decimal(USD_VALUE[ccy])
    from ..money import exponent
    exp = exponent(ccy)
    whole = int((value / Decimal(10)).quantize(Decimal(1))) * 10  # round to tens
    return max(whole, 10) * 10**exp


def build_world(seed: int, cfg: EpisodeConfig) -> World:
    """Build the clean, balanced history (no errors) plus reserved host records for injections."""
    ch = cfg.content_hash()
    rng = Rng(seed, ch, ENV_VERSION, "history")
    start, end = _period(cfg)
    w = World(cfg=cfg, seed=seed, period_start=start, period_end=end,
              rates=_rates(cfg, Rng(seed, ch, ENV_VERSION, "fx"), start, end),
              tables=Tables(), hosts={}, counters={}, entities={}, meta={})
    used_names: set = set()
    customers = [w.next("E") for _ in range(rng.rand_int(8, 14))]
    suppliers = [w.next("E") for _ in range(rng.rand_int(4, 7))]
    for e in customers + suppliers:
        w.entities[e] = _company_name(rng, used_names)
    w.meta["customers"] = {"list": customers}
    # Customers have a fixed billing currency (realistic and keeps lump sums single-currency).
    cust_ccy = {}
    for e in customers:
        cust_ccy[e] = rng.choice(cfg.foreign_currencies) if rng.random() < cfg.foreign_share else cfg.base_currency
    if all(c == cfg.base_currency for c in cust_ccy.values()):
        cust_ccy[customers[0]] = cfg.foreign_currencies[0]
    foreign_customers = [e for e in customers if cust_ccy[e] != cfg.base_currency]

    _fx_table(w)
    gen_rng = Rng(seed, ch, ENV_VERSION, "invoices")
    pay_rng = Rng(seed, ch, ENV_VERSION, "payments")

    # Reserved hosts so every configured issue has an unambiguous place (plan §5.3a).
    e = dict(cfg.errors) if not cfg.clean else {k: 0 for k in cfg.errors}
    inter = [] if cfg.clean else list(cfg.interactions)
    # Host dates follow (almost) the same distribution as ordinary invoices, so the date of a
    # record does not tell whether it hosts an error (red-team finding, plan §5.8 anti-tell).
    lo_all, hi_all = start - timedelta(days=4), end + timedelta(days=4)
    hosts: Dict[str, List[str]] = {"duplicate_invoice": [], "payment_allocation": [], "date_or_fx": [],
                                   "period_classification": [], "A": [], "B": []}
    for _ in range(e.get("duplicate_invoice", 0)):  # the copy must still fall inside the period
        hosts["duplicate_invoice"].append(_invoice(w, gen_rng, rng.choice(customers), cust_ccy, _rand_day(gen_rng, start, end - timedelta(days=1)), unique=True))
    for _ in range(e.get("payment_allocation", 0)):
        inv = _invoice(w, gen_rng, rng.choice(customers), cust_ccy, _rand_day(gen_rng, lo_all, hi_all))
        p = _payment(w, pay_rng, [inv], w.meta[inv]["date"] + timedelta(days=pay_rng.rand_int(2, 8)), kind="full")
        hosts["payment_allocation"].append(p)
    for _ in range(e.get("date_or_fx", 0)):  # the wrong day must stay inside the period
        hosts["date_or_fx"].append(_invoice(w, gen_rng, rng.choice(foreign_customers), cust_ccy, _rand_day(gen_rng, start + timedelta(days=1), end - timedelta(days=1))))
    for i in range(e.get("period_classification", 0)):
        if i % 2 == 0:  # issued in the last days of the period
            d = end - timedelta(days=gen_rng.rand_int(0, 3))
        else:  # issued just after the period (margin)
            d = end + timedelta(days=gen_rng.rand_int(1, 3))
        hosts["period_classification"].append(_invoice(w, gen_rng, rng.choice(customers), cust_ccy, d))
    if "A" in inter:
        x = _invoice(w, gen_rng, rng.choice(foreign_customers), cust_ccy, end - timedelta(days=gen_rng.rand_int(1, 3)))
        p = _payment(w, pay_rng, [x], end + timedelta(days=pay_rng.rand_int(1, 3)), kind="partial")
        hosts["A"] = [x, p]
    if "B" in inter:
        x = _invoice(w, gen_rng, rng.choice(customers), cust_ccy, end - timedelta(days=gen_rng.rand_int(5, 8)), unique=True)
        hosts["B"] = [x]
    w.hosts = hosts
    reserved = {k for v in hosts.values() for k in v}

    # Ordinary invoices across the period plus a small margin on both sides.
    n_regular = max(cfg.n_invoices - len([k for k in reserved if k.startswith("§I")]), 4)
    for _ in range(n_regular):
        d = _rand_day(gen_rng, start - timedelta(days=4), end + timedelta(days=4))
        _invoice(w, gen_rng, gen_rng.choice(customers), cust_ccy, d)

    # Distractors (plan §5.4).
    lvl = cfg.distractor_level
    if lvl >= 1:
        # Recurring invoices: same lines and amount, different service period.
        for _ in range(1 + lvl):
            cust = gen_rng.choice(customers)
            d1 = _rand_day(gen_rng, start, end - timedelta(days=31)) if (end - start).days > 40 else start
            first = _invoice(w, gen_rng, cust, cust_ccy, d1)
            d2 = d1 + timedelta(days=30)
            if d2 <= end + timedelta(days=4):
                _invoice(w, gen_rng, cust, cust_ccy, d2, copy_lines_from=first, shift_period_months=1)
        # Near-boundary timestamps written in UTC that resolve to the next local day.
        for _ in range(lvl):
            _invoice(w, gen_rng, gen_rng.choice(customers), cust_ccy, end + timedelta(days=1), utc_early=True)

    # Payments for ordinary invoices.
    # Hosts are paid like any other invoice (unpaid status must not be a tell), except those whose
    # payment is part of an allocation error or scenario A.
    no_pay = {w.meta[p]["allocs"][0][0] for p in hosts["payment_allocation"]} | set(hosts["A"][:1])
    regular = [k for k in w.meta if k.startswith("§I") and k not in no_pay and not w.meta[k].get("dup_of")]
    regular.sort(key=lambda k: (w.meta[k]["date"], int(k[2:])))
    paid = set()
    for inv in regular:
        if inv in paid:
            continue
        d_inv = w.meta[inv]["date"]
        if pay_rng.random() > 0.78:
            continue
        pay_day = d_inv + timedelta(days=pay_rng.rand_int(3, 24))
        if pay_day > end + timedelta(days=6):
            continue
        roll = pay_rng.random()
        if lvl >= 1 and roll < 0.10:
            _payment(w, pay_rng, [inv], pay_day, kind="split1")
            _payment(w, pay_rng, [inv], pay_day + timedelta(days=pay_rng.rand_int(1, 6)), kind="split2")
        elif lvl >= 1 and roll < 0.18:
            partner = next((o for o in regular if o not in paid and o != inv
                            and w.meta[o]["entity"] == w.meta[inv]["entity"]
                            and abs((w.meta[o]["date"] - d_inv).days) <= 20), None)
            if partner:
                _payment(w, pay_rng, [inv, partner], max(pay_day, w.meta[partner]["date"] + timedelta(days=2)), kind="lump")
                paid.add(partner)
            else:
                _payment(w, pay_rng, [inv], pay_day, kind="full")
        elif lvl >= 1 and roll < 0.24:
            _payment(w, pay_rng, [inv], pay_day, kind="shortpay")
        else:
            _payment(w, pay_rng, [inv], pay_day, kind="full")
        paid.add(inv)
    if lvl >= 1:
        for _ in range(lvl):
            cust = pay_rng.choice(customers)
            _advance(w, pay_rng, cust, cust_ccy[cust], _rand_day(pay_rng, start, end))

    # Expenses (suppliers, base currency) to give the ledger realistic volume.
    exp_rng = Rng(seed, ch, ENV_VERSION, "expenses")
    n_exp = cfg.n_expenses
    for _ in range(n_exp):
        sup = exp_rng.choice(suppliers)
        d = _rand_day(exp_rng, start - timedelta(days=4), end + timedelta(days=4))
        amt = _money(exp_rng, cfg.base_currency, cfg.base_currency) // 3 or 1000
        acct = exp_rng.choice(EXPENSE_ACCOUNTS)
        ts = w.ts(d, exp_rng.rand_int(9, 17), exp_rng.rand_int(0, 59))
        w.add_row(ts, acct, amt, 0, sup, None, None)
        w.add_row(ts, AP, 0, amt, sup, None, None)
        if exp_rng.random() < 0.7:
            d2 = d + timedelta(days=exp_rng.rand_int(5, 20))
            ts2 = w.ts(d2, exp_rng.rand_int(9, 17), exp_rng.rand_int(0, 59))
            w.add_row(ts2, AP, amt, 0, sup, None, None)
            w.add_row(ts2, BANK, 0, amt, sup, None, None)
    # Keep the ledger within 200-2000 rows (brief §03).
    while len(w.tables.ledger) < 200:
        sup = exp_rng.choice(suppliers)
        d = _rand_day(exp_rng, start, end)
        amt = _money(exp_rng, cfg.base_currency, cfg.base_currency) // 3 or 1000
        ts = w.ts(d, exp_rng.rand_int(9, 17), exp_rng.rand_int(0, 59))
        w.add_row(ts, exp_rng.choice(EXPENSE_ACCOUNTS), amt, 0, sup, None, None)
        w.add_row(ts, AP, 0, amt, sup, None, None)
    return w


def _fx_table(w: World) -> None:
    for (ccy, d), rate in sorted(w.rates.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        w.tables.fx.append({"date": d.isoformat(), "source_currency": ccy,
                            "target_currency": w.base, "rate": rate})


def _lines(w: World, rng: Rng, ccy: str, d: date) -> List[dict]:
    n = rng.rand_int(1, 3)
    ps = d.replace(day=1)
    pe = date(ps.year, ps.month, calendar.monthrange(ps.year, ps.month)[1])
    items = []
    for desc in rng.sample(_SERVICES, n):
        items.append({"description": desc, "service_period": {"start": ps.isoformat(), "end": pe.isoformat()},
                      "amount_minor": _money(rng, ccy, w.base)})
    return items


def _shift_month(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _invoice(w: World, rng: Rng, entity: str, cust_ccy: Dict[str, str], d: date, *, unique: bool = False,
             copy_lines_from: Optional[str] = None, shift_period_months: int = 0, utc_early: bool = False) -> str:
    ccy = cust_ccy[entity]
    if copy_lines_from:
        src = next(i for i in w.tables.invoices if i["invoice_id"] == copy_lines_from)
        lines = []
        for li in src["line_items"]:
            sp = li["service_period"]
            s = _shift_month(date.fromisoformat(sp["start"]), shift_period_months)
            e = date(s.year, s.month, calendar.monthrange(s.year, s.month)[1])
            lines.append({"description": li["description"], "service_period": {"start": s.isoformat(), "end": e.isoformat()},
                          "amount_minor": li["amount_minor"]})
        entity, ccy = src["entity_id"], src["currency"]
    else:
        lines = _lines(w, rng, ccy, d)
        if unique:  # make the line set unique so a later duplicate is unambiguous
            from ..money import exponent
            lines[0]["amount_minor"] += 10 ** exponent(ccy) * 10 * rng.rand_int(1, 9)
    if utc_early:
        ts = w.ts(d, 1, rng.rand_int(5, 50), utc_form=True)  # 01:xx local = previous day in UTC
    else:
        ts = w.ts(d, rng.rand_int(9, 17), rng.rand_int(0, 59))
    key = w.next("I")
    doc = w.next("D")
    total = sum(li["amount_minor"] for li in lines)
    ld = w.ldate(ts)
    w.tables.invoices.append({
        "doc_id": doc, "invoice_id": key, "entity_id": entity, "issued_at": ts,
        "due_at": iso(datetime.fromisoformat(ts) + timedelta(days=30)), "currency": ccy,
        "total_minor": total, "line_items": lines})
    w.tables.documents[doc] = {"doc_id": doc, "kind": "invoice", "invoice_id": key, "issuer": "Company",
                               "customer": w.entities[entity], "entity_id": entity, "date": ld.isoformat(),
                               "currency": ccy, "total_minor": total, "line_items": lines, "memo": ""}
    base_amt = w.to_base(total, ccy, ld)
    post_ts = w.ts(ld, datetime.fromisoformat(ts).astimezone(tz(w.tz_name())).hour,
                   datetime.fromisoformat(ts).astimezone(tz(w.tz_name())).minute)
    ar = w.add_row(post_ts, AR, base_amt, 0, entity, key, None)
    rv = w.add_row(post_ts, REVENUE, 0, base_amt, entity, key, None)
    w.meta[key] = {"date": ld, "entity": entity, "currency": ccy, "total": total, "ar_row": ar, "rev_row": rv,
                   "base": base_amt}
    return key


def _payment(w: World, rng: Rng, invoices: List[str], d: date, kind: str) -> str:
    ent = w.meta[invoices[0]]["entity"]
    ccy = w.meta[invoices[0]]["currency"]
    allocs: List[Tuple[str, int]] = []
    deduction = 0
    if kind in ("full", "lump"):
        allocs = [(i, w.meta[i]["total"]) for i in invoices]
    elif kind == "split1":
        part = (w.meta[invoices[0]]["total"] * rng.rand_int(30, 70)) // 100
        w.meta[invoices[0]]["split_first"] = part
        allocs = [(invoices[0], part)]
    elif kind == "split2":
        allocs = [(invoices[0], w.meta[invoices[0]]["total"] - w.meta[invoices[0]]["split_first"])]
    elif kind == "partial":
        allocs = [(invoices[0], (w.meta[invoices[0]]["total"] * rng.rand_int(40, 60)) // 100)]
    elif kind == "shortpay":
        tot = w.meta[invoices[0]]["total"]
        deduction = (tot * rng.rand_int(2, 6)) // 100
        allocs = [(invoices[0], tot - deduction)]
    amount = sum(a for _, a in allocs)
    ts = w.ts(d, rng.rand_int(9, 17), rng.rand_int(0, 59))
    key = w.next("P")
    doc = w.next("D")
    memo = {"full": "Payment in full", "lump": "Payment for several invoices", "split1": "Part payment",
            "split2": "Balance payment", "partial": "Part payment, balance to follow",
            "shortpay": ""}[kind]
    if kind == "shortpay":
        memo = f"Deduction agreed with supplier (damaged goods): {deduction} minor units, credit note issued"
    w.tables.payments.append({"doc_id": doc, "payment_id": key, "timestamp": ts, "currency": ccy,
                              "amount_minor": amount, "invoice_refs": list(invoices)})
    w.tables.documents[doc] = {"doc_id": doc, "kind": "remittance", "payment_id": key, "payer": w.entities[ent],
                               "entity_id": ent, "date": d.isoformat(), "currency": ccy, "amount_minor": amount,
                               "references": list(invoices),
                               "allocations": [{"invoice_id": i, "amount_minor": a} for i, a in allocs],
                               "memo": memo}
    bank_base = w.to_base(amount, ccy, d)
    rows = {"bank": w.add_row(ts, BANK, bank_base, 0, ent, None, key), "ar": []}
    ar_total = 0
    for inv, a in allocs:
        ar_base = w.to_base(a, ccy, w.meta[inv]["date"])
        ar_total += ar_base
        rows["ar"].append(w.add_row(ts, AR, 0, ar_base, ent, inv, key))
    diff = bank_base - ar_total
    if diff > 0:
        rows["fx"] = w.add_row(ts, FXGL, 0, diff, ent, None, key)
    elif diff < 0:
        rows["fx"] = w.add_row(ts, FXGL, -diff, 0, ent, None, key)
    if deduction:
        inv = invoices[0]
        ded_base = w.to_base(deduction, ccy, w.meta[inv]["date"])
        rows["cn_dr"] = w.add_row(ts, RETURNS, ded_base, 0, ent, inv, None)
        rows["cn_cr"] = w.add_row(ts, AR, 0, ded_base, ent, inv, None)
    w.meta[key] = {"date": d, "entity": ent, "currency": ccy, "kind": kind, "rows": rows, "allocs": allocs,
                   "amount": amount}
    return key


def _advance(w: World, rng: Rng, ent: str, ccy: str, d: date) -> str:
    amount = _money(rng, ccy, w.base)
    ts = w.ts(d, rng.rand_int(9, 17), rng.rand_int(0, 59))
    key = w.next("P")
    doc = w.next("D")
    w.tables.payments.append({"doc_id": doc, "payment_id": key, "timestamp": ts, "currency": ccy,
                              "amount_minor": amount, "invoice_refs": None})
    w.tables.documents[doc] = {"doc_id": doc, "kind": "remittance", "payment_id": key, "payer": w.entities[ent],
                               "entity_id": ent, "date": d.isoformat(), "currency": ccy, "amount_minor": amount,
                               "references": [], "allocations": [],
                               "memo": "Advance payment for future orders (held as unapplied cash)"}
    base = w.to_base(amount, ccy, d)
    b = w.add_row(ts, BANK, base, 0, ent, None, key)
    u = w.add_row(ts, UNAPPLIED, 0, base, ent, None, key)
    w.meta[key] = {"date": d, "entity": ent, "currency": ccy, "kind": "advance", "rows": {"bank": b, "unapplied": u},
                   "allocs": [], "amount": amount}
    return key


def policy_doc(w: World) -> dict:
    return {
        "schema_version": "1.0",
        "base_currency": w.base,
        "timezone": w.tz_name(),
        "timezone_offset": offset_str(w.tz_name()),
        "period": {"start": w.period_start.isoformat(), "end": w.period_end.isoformat(),
                   "rule": "A record belongs to the period of its policy date, taken in the company time zone."},
        "policy_date": {"invoice": "issued_at", "payment": "timestamp",
                        "note": "If a ledger posting and the document disagree on a date, the document date wins."},
        "fx": {"direction": "1 source_currency = rate target_currency; target is always the base currency",
               "rate_date": "the policy date of the record, in the company time zone (spot rate of that day)",
               "partial_payments": "each payment settles at its own date's rate; differences go to account 7810",
               "rounding": "half_even, once, when converting to base minor units"},
        "rounding": {"mode": "half_even", "applies_to": "conversion_to_base"},
        "accounts": ACCOUNT_NAMES,
        "legitimate_patterns": [
            "split payments and lump-sum payments covering several invoices",
            "short payment with a documented deduction and a credit note (accounts 4100/1200)",
            "advance payments with no invoice reference held in 2350 Unapplied cash",
            "recurring invoices with the same lines and amount but a different service period",
            "timestamps written with other UTC offsets; always convert to the company time zone"],
        "tolerance": {"rule": "|claimed - expected| <= 1 + conversions (minor units of the claimed currency)",
                      "conversions": {"duplicate_invoice": 0, "payment_allocation": "1 if the payment is foreign else 0",
                                      "date_or_fx": 1, "period_classification": "1 if the invoice is foreign else 0"}},
    }
