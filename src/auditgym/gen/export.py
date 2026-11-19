"""Naming (id_seed), layout (layout_seed), episode identity and file export.

IDs are assigned AFTER injection by one canonical routine: ledger rows, invoices and payments
are numbered chronologically from a random start; documents and entities get a random
permutation. Injected records are therefore indistinguishable by ID format, range or rank
(anti-tell, plan §5.8). ``id_seed`` changes only names; ``layout_seed`` only file row order.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import os
from datetime import timezone
from typing import Any, Dict, List

from ..seeding import Rng
from ..timeutil import parse_ts
from ..version import ENV_VERSION, SCHEMA_VERSION
from .history import Tables, World

LEDGER_FIELDS = ["row_id", "timestamp", "account", "debit_minor", "credit_minor", "currency", "entity_id",
                 "invoice_id", "payment_id"]
INVOICE_FIELDS = ["doc_id", "invoice_id", "entity_id", "issued_at", "due_at", "currency", "total_minor", "line_items"]
PAYMENT_FIELDS = ["doc_id", "payment_id", "timestamp", "currency", "amount_minor", "invoice_refs"]
FX_FIELDS = ["date", "source_currency", "target_currency", "rate"]
PK = {"ledger": "row_id", "invoices": "invoice_id", "payments": "payment_id"}
_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_DIGITS = "23456789"


def _instant(ts: str) -> str:
    return parse_ts(ts).astimezone(timezone.utc).isoformat()


def build_name_map(w: World, tables: Tables, id_seed: int) -> Dict[str, str]:
    rng = Rng(w.seed, w.cfg.content_hash(), ENV_VERSION, "ids", id_seed)
    tag = rng.choice(_LETTERS) + rng.choice(_DIGITS)
    pfx = {"L": rng.choice(["L", "GL", "JE"]), "I": rng.choice(["INV", "IN", "BILL"]),
           "P": rng.choice(["PAY", "RCPT", "PMT"]), "D": rng.choice(["DOC", "SCAN", "ATT"]),
           "E": rng.choice(["E", "CUST", "PRT"])}
    tie = lambda k: hashlib.sha256(f"{w.seed}|{id_seed}|{k}".encode()).hexdigest()  # noqa: E731
    out: Dict[str, str] = {}

    def chrono(keys_ts: List[tuple], kind: str, width: int) -> None:
        start = rng.rand_int(10 ** (width - 1), 4 * 10 ** (width - 1))
        for i, (k, _) in enumerate(sorted(keys_ts, key=lambda kt: (kt[1], tie(kt[0])))):
            out[k] = f"{pfx[kind]}-{tag}-{start + i:0{width}d}"

    chrono([(r["row_id"], _instant(r["timestamp"])) for r in tables.ledger], "L", 5)
    chrono([(r["invoice_id"], _instant(r["issued_at"])) for r in tables.invoices], "I", 4)
    chrono([(r["payment_id"], _instant(r["timestamp"])) for r in tables.payments], "P", 4)
    docs = sorted(tables.documents, key=tie)
    nums = rng.sample(range(1000, 9999), len(docs))
    for k, n in zip(docs, nums):
        out[k] = f"{pfx['D']}-{tag}-{n}"
    ents = sorted(w.entities, key=tie)
    enums = rng.sample(range(100, 999), len(ents))
    for k, n in zip(ents, enums):
        out[k] = f"{pfx['E']}-{tag}-{n}"
    return out


def rename(obj: Any, names: Dict[str, str]) -> Any:
    if isinstance(obj, str):
        return names.get(obj, obj)
    if isinstance(obj, list):
        return [rename(x, names) for x in obj]
    if isinstance(obj, dict):
        return {rename(k, names) if isinstance(k, str) and k.startswith("§") else k: rename(v, names) for k, v in obj.items()}
    return obj


def tables_to_dict(t: Tables) -> Dict[str, Any]:
    return {"ledger": t.ledger, "invoices": t.invoices, "payments": t.payments, "fx": t.fx, "documents": t.documents}


def canonical_tables(d: Dict[str, Any]) -> Dict[str, Any]:
    """Rows sorted by primary key (fx by date, source); documents by id."""
    out = {}
    for name, pk in PK.items():
        out[name] = sorted((copy.deepcopy(r) for r in d[name]), key=lambda r: r[pk])
    out["fx"] = sorted((copy.deepcopy(r) for r in d["fx"]), key=lambda r: (r["date"], r["source_currency"]))
    out["documents"] = {k: copy.deepcopy(d["documents"][k]) for k in sorted(d["documents"])}
    return out


def content_id(public: Dict[str, Any], policy: Dict[str, Any]) -> str:
    blob = json.dumps({"tables": canonical_tables(public), "policy": policy}, sort_keys=True, separators=(",", ":"))
    return "ep_" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def assemble(w: World, clean: Tables, inj: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    """Return {'public': {...}, 'private': {...}} with final names and episode_id."""
    names = build_name_map(w, w.tables, w.cfg.id_seed)
    # Clean-table keys that disappear never exist (we only add or set), so one map covers both.
    pub = canonical_tables(rename(tables_to_dict(w.tables), names))
    cln = canonical_tables(rename(tables_to_dict(clean), names))
    ops = rename(inj["ops"], names)
    issues = rename(inj["issues"], names)
    for iss in issues:
        iss["affected_ids"] = sorted(iss["affected_ids"])
        iss["acceptable_evidence_sets"] = [sorted(s) for s in iss["acceptable_evidence_sets"]]
    entity_names = {names[k]: v for k, v in w.entities.items()}
    pol = rename(policy, names)
    pol["entities"] = {k: entity_names[k] for k in sorted(entity_names)}
    eid = content_id(pub, pol)
    manifest = {
        "schema_version": SCHEMA_VERSION, "episode_id": eid, "base_currency": w.base,
        "period_start": w.period_start.isoformat(), "period_end": w.period_end.isoformat(),
        "timezone": w.tz_name(),
        "counts": {"ledger": len(pub["ledger"]), "invoices": len(pub["invoices"]), "payments": len(pub["payments"]),
                   "fx": len(pub["fx"]), "documents": len(pub["documents"])},
        "rounding": {"mode": "half_even", "applies_to": "conversion_to_base"},
    }
    truth = {"episode_id": eid, "issues": issues}
    provenance = {"episode_id": eid, "env_version": ENV_VERSION, "seed": w.seed, "config": w.cfg.canonical(),
                  "clean_tables_sha256": hashlib.sha256(json.dumps(cln, sort_keys=True).encode()).hexdigest(),
                  "operations": ops}
    return {"public": {"manifest": manifest, "policy": pol, "tables": pub},
            "private": {"episode_id": eid, "truth": truth, "provenance": provenance, "clean": cln}}


# ---------- files ----------

def _csv(rows: List[dict], fields: List[str]) -> str:
    buf = io.StringIO()
    wr = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    wr.writeheader()
    for r in rows:
        wr.writerow({k: ("" if r[k] is None else r[k]) for k in fields})
    return buf.getvalue()


def _jsonl(rows: List[dict], fields: List[str]) -> str:
    return "".join(json.dumps({k: r[k] for k in fields}, ensure_ascii=False, sort_keys=False) + "\n" for r in rows)


def _layout(rows: List[dict], layout_seed: int, salt: str) -> List[dict]:
    rows = list(rows)
    if layout_seed:
        Rng("layout", layout_seed, salt).shuffle(rows)
    return rows


def write_tables(dirpath: str, tables: Dict[str, Any], layout_seed: int) -> None:
    os.makedirs(dirpath, exist_ok=True)
    files = {
        "ledger.csv": _csv(_layout(tables["ledger"], layout_seed, "ledger"), LEDGER_FIELDS),
        "invoices.jsonl": _jsonl(_layout(tables["invoices"], layout_seed, "inv"), INVOICE_FIELDS),
        "payments.jsonl": _jsonl(_layout(tables["payments"], layout_seed, "pay"), PAYMENT_FIELDS),
        "fx.csv": _csv(_layout(tables["fx"], layout_seed, "fx"), FX_FIELDS),
        "documents.jsonl": "".join(json.dumps(tables["documents"][k], ensure_ascii=False) + "\n"
                                   for k in [d["doc_id"] for d in _layout(list(tables["documents"].values()), layout_seed, "doc")]),
    }
    for name, text in files.items():
        with open(os.path.join(dirpath, name), "w", encoding="utf-8", newline="") as fh:
            fh.write(text)


def write_episode(root: str, ep: Dict[str, Any], layout_seed: int = 0) -> str:
    eid = ep["public"]["manifest"]["episode_id"]
    pub_dir = os.path.join(root, eid, "public")
    prv_dir = os.path.join(root, eid, "private")
    write_tables(pub_dir, ep["public"]["tables"], layout_seed)
    _dump(os.path.join(pub_dir, "manifest.json"), ep["public"]["manifest"])
    _dump(os.path.join(pub_dir, "policy.json"), ep["public"]["policy"])
    os.makedirs(prv_dir, exist_ok=True)
    _dump(os.path.join(prv_dir, "truth.json"), ep["private"]["truth"])
    _dump(os.path.join(prv_dir, "provenance.json"), ep["private"]["provenance"])
    write_tables(os.path.join(prv_dir, "clean"), ep["private"]["clean"], 0)
    return os.path.join(root, eid)


def _dump(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
