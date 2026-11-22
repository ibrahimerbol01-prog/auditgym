"""Load and validate exported episode directories (public, and private for the evaluator only)."""
from __future__ import annotations

import csv
import json
import os
from typing import Any, Dict

from ..gen.export import FX_FIELDS, INVOICE_FIELDS, LEDGER_FIELDS, PAYMENT_FIELDS, canonical_tables

_INT = {"debit_minor", "credit_minor", "total_minor", "amount_minor"}


def _read_csv(path: str, fields) -> list:
    with open(path, encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        if rd.fieldnames != list(fields):
            raise ValueError(f"{os.path.basename(path)}: unexpected columns")
        out = []
        for row in rd:
            rec = {}
            for k in fields:
                v = row[k]
                rec[k] = None if v == "" else (int(v) if k in _INT else v)
            out.append(rec)
        return out


def _read_jsonl(path: str, fields=None) -> list:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                if fields is not None and list(rec) != list(fields):
                    raise ValueError(f"{os.path.basename(path)}: unexpected fields")
                out.append(rec)
    return out


def read_tables(d: str) -> Dict[str, Any]:
    docs = _read_jsonl(os.path.join(d, "documents.jsonl"))
    return canonical_tables({
        "ledger": _read_csv(os.path.join(d, "ledger.csv"), LEDGER_FIELDS),
        "invoices": _read_jsonl(os.path.join(d, "invoices.jsonl"), INVOICE_FIELDS),
        "payments": _read_jsonl(os.path.join(d, "payments.jsonl"), PAYMENT_FIELDS),
        "fx": _read_csv(os.path.join(d, "fx.csv"), FX_FIELDS),
        "documents": {x["doc_id"]: x for x in docs},
    })


def _load(path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_episode_dir(ep_dir: str, with_private: bool = False) -> Dict[str, Any]:
    pub = os.path.join(ep_dir, "public")
    out: Dict[str, Any] = {"public": {"manifest": _load(os.path.join(pub, "manifest.json")),
                                      "policy": _load(os.path.join(pub, "policy.json")),
                                      "tables": read_tables(pub)}}
    if with_private:
        prv = os.path.join(ep_dir, "private")
        out["private"] = {"episode_id": out["public"]["manifest"]["episode_id"],
                          "truth": _load(os.path.join(prv, "truth.json")),
                          "provenance": _load(os.path.join(prv, "provenance.json")),
                          "clean": read_tables(os.path.join(prv, "clean")) if os.path.isdir(os.path.join(prv, "clean")) else {}}
    return out


def validate_episode_dir(ep_dir: str) -> None:
    ep = load_episode_dir(ep_dir)
    m = ep["public"]["manifest"]
    for k, n in m["counts"].items():
        got = len(ep["public"]["tables"][k])
        if got != n:
            raise ValueError(f"count mismatch for {k}")
