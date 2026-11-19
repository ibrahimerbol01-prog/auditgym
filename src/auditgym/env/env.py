"""AuditEnv: JSON-compatible, Gymnasium-style environment (brief §04, plan §6).

reset(seed, config) -> (observation, info); step(action) -> (observation, reward, terminated,
truncated, info). The environment holds only public data received from the evaluator service.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import time
from typing import Any, Callable, Dict, Optional, Tuple

from ..eval.service import ServiceClient
from .calculator import CalcError, evaluate

MAX_STEPS, MAX_SECONDS, PAGE = 100, 60.0, 50
TABLES = ("ledger", "invoices", "payments", "fx")
PK = {"ledger": "row_id", "invoices": "invoice_id", "payments": "payment_id"}
ERR = {
    "unknown_tool": "unknown tool",
    "unknown_table": "unknown table",
    "unknown_id": "record not found",
    "bad_arguments": "invalid arguments",
    "bad_cursor": "invalid cursor",
    "calc_error": "calculator error",
    "episode_over": "episode is over",
    "bad_config": "invalid seed or config",
}

TASK = ("You are auditing the books of a fictional company for one reporting period. Find real "
        "discrepancies of four types (duplicate_invoice, payment_allocation, date_or_fx, "
        "period_classification), prove each with record IDs, and submit once. Wrong accusations cost "
        "more than silence; every step costs 0.002 reward. You have 100 steps including submit.")

FINDING_RULES = {
    "duplicate_invoice": {"affected_ids": "both invoice IDs of the pair",
                          "amount": "invoice total_minor", "currency": "invoice currency",
                          "minimal_evidence": "both invoice IDs"},
    "payment_allocation": {"affected_ids": "[payment_id, invoice_id]",
                           "amount": "base amount left in unapplied cash (account 2350)", "currency": "base currency",
                           "minimal_evidence": "payment_id, invoice_id and the unapplied-cash ledger row"},
    "date_or_fx": {"affected_ids": "[invoice_id]",
                   "amount": "abs(booked base amount - foreign total x policy-date rate)", "currency": "base currency",
                   "minimal_evidence": "invoice_id, its accounts-receivable ledger row and the correct fx row id 'date|SRC|BASE'"},
    "period_classification": {"affected_ids": "[invoice_id]",
                              "amount": "the invoice's correct base amount (foreign total x policy-date rate)",
                              "currency": "base currency",
                              "minimal_evidence": "invoice_id, its accounts-receivable ledger row and, for a foreign invoice, the fx row of the policy date"},
    "tolerance": "|claimed - expected| <= 1 + conversions (0 for duplicates, 1 when a conversion is involved)",
    "matching": "one-to-one; duplicates and extra findings are false positives; the explanation is never scored",
}

TOOLS = {
    "list_records": {"table": "ledger|invoices|payments|fx", "cursor": "string|null", "limit": "int 1..50"},
    "get_record": {"table": "ledger|invoices|payments|fx", "id": "string (fx id = 'date|SRC|BASE')"},
    "get_document": {"doc_id": "string"},
    "calculator": {"expression": "string: decimals, + - * / ( ) only, max 200 chars"},
    "submit": {"findings": "{episode_id, findings:[{type, affected_ids, claimed_amount_minor, currency, evidence_ids, explanation}]}"},
}


def _fx_key(r: Dict[str, Any]) -> str:
    return f"{r['date']}|{r['source_currency']}|{r['target_currency']}"


class AuditEnv:
    def __init__(self, mode: str = "open", service: Optional[ServiceClient] = None,
                 clock: Callable[[], float] = time.monotonic, run_id: str = "default",
                 time_limit: Optional[float] = MAX_SECONDS) -> None:
        if mode not in ("open", "closed"):
            raise ValueError("mode must be 'open' or 'closed'")
        self.mode = mode
        self._own_service = service is None
        self.service = service or ServiceClient()
        self.clock = clock
        self.run_id = run_id
        self.time_limit = time_limit
        self._ep: Optional[Dict[str, Any]] = None
        self._done = True

    # ---------- lifecycle ----------
    def reset(self, seed: Any = None, config: Any = None, options: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        self._ep, self._done = None, True
        options = options or {}
        if "episode_dir" in options:
            resp = self.service.call({"cmd": "load", "dir": options["episode_dir"], "mode": self.mode, "run_id": self.run_id})
        else:
            resp = self.service.call({"cmd": "generate", "seed": seed, "config": config, "mode": self.mode, "run_id": self.run_id})
        if not resp.get("ok"):
            return {"ok": False, "error": {"code": "bad_config", "message": resp.get("error", {}).get("message", ERR["bad_config"])[:200]}}, {}
        pub = resp["public"]
        idx = {t: {} for t in TABLES}
        rows = {t: [] for t in TABLES}
        for t in ("ledger", "invoices", "payments"):
            rows[t] = sorted(pub["tables"][t], key=lambda r: r[PK[t]])
            idx[t] = {r[PK[t]]: r for r in rows[t]}
        rows["fx"] = sorted(pub["tables"]["fx"], key=_fx_key)
        idx["fx"] = {_fx_key(r): r for r in rows["fx"]}
        self._ep = {"handle": resp["handle"], "manifest": pub["manifest"], "policy": pub["policy"], "rows": rows,
                    "idx": idx, "docs": pub["tables"]["documents"], "steps": 0, "t0": self.clock()}
        self._done = False
        obs = {"ok": True, "result": {
            "task": TASK, "manifest": pub["manifest"], "policy": pub["policy"], "tools": TOOLS,
            "finding_schema": {"episode_id": pub["manifest"]["episode_id"], "findings": "list (max 30)",
                               "finding": {"type": "one of 4", "affected_ids": "list[str]",
                                           "claimed_amount_minor": "int >= 0", "currency": "str",
                                           "evidence_ids": "list[str] (max 10)", "explanation": "str (max 1000)"}},
            "finding_rules": FINDING_RULES}, "remaining_steps": MAX_STEPS}
        return copy.deepcopy(obs), {}

    def step(self, action: Any) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        ep = self._ep
        if ep is None or self._done:
            return self._err("episode_over", 0), 0.0, ep is not None, False, {}
        ep["steps"] += 1
        remaining = MAX_STEPS - ep["steps"]
        tool = action.get("tool") if isinstance(action, dict) else None
        args = action.get("args", {}) if isinstance(action, dict) else None
        timed_out = self.time_limit is not None and (self.clock() - ep["t0"]) > self.time_limit
        if tool == "submit" and not timed_out and isinstance(args, dict):
            return self._submit(args.get("findings"), remaining)
        if timed_out or remaining <= 0:
            return self._truncate()
        if not isinstance(action, dict) or not isinstance(tool, str):
            return self._err("bad_arguments", remaining), 0.0, False, False, {}
        if tool not in TOOLS or tool == "submit":
            code = "bad_arguments" if tool == "submit" else "unknown_tool"
            return self._err(code, remaining), 0.0, False, False, {}
        if not isinstance(args, dict):
            return self._err("bad_arguments", remaining), 0.0, False, False, {}
        try:
            result = getattr(self, "_t_" + tool)(**args)
        except _ToolError as exc:
            return self._err(exc.code, remaining), 0.0, False, False, {}
        except TypeError:
            return self._err("bad_arguments", remaining), 0.0, False, False, {}
        return {"ok": True, "result": copy.deepcopy(result), "remaining_steps": remaining}, 0.0, False, False, {}

    def state(self) -> Dict[str, Any]:
        if self._ep is None:
            return {"episode_id": None, "done": True}
        return {"episode_id": self._ep["manifest"]["episode_id"], "steps": self._ep["steps"],
                "remaining_steps": MAX_STEPS - self._ep["steps"], "done": self._done, "mode": self.mode}

    def close(self) -> None:
        if self._own_service:
            self.service.close()

    # ---------- internals ----------
    def _err(self, code: str, remaining: int) -> Dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": ERR[code]}, "remaining_steps": max(remaining, 0)}

    def _truncate(self):
        ep = self._ep
        self._done = True
        resp = self.service.call({"cmd": "score", "handle": ep["handle"], "submission": None,
                                  "inspection_steps": ep["steps"], "truncated": True})
        reward = float(resp.get("reward", 0.0)) if self.mode == "open" else 0.0
        return {}, reward, False, True, {}

    def _submit(self, findings: Any, remaining: int):
        ep = self._ep
        self._done = True
        resp = self.service.call({"cmd": "score", "handle": ep["handle"], "submission": findings,
                                  "inspection_steps": ep["steps"] - 1})
        if self.mode == "closed":
            return {"ok": True, "result": {"status": "submitted"}, "remaining_steps": remaining}, 0.0, True, False, {}
        report = resp.get("report", {})
        return ({"ok": True, "result": {"status": report.get("status", "submitted"), "report": report},
                 "remaining_steps": remaining}, float(resp.get("reward", 0.0)), True, False, {})

    def _table(self, table: Any) -> str:
        if not isinstance(table, str) or table not in TABLES:
            raise _ToolError("unknown_table")
        return table

    def _cursor(self, table: str, offset: int) -> str:
        dig = hashlib.sha256(f"{self._ep['manifest']['episode_id']}|{table}|{offset}".encode()).hexdigest()[:12]
        return base64.urlsafe_b64encode(f"{table}|{offset}|{dig}".encode()).decode().rstrip("=")

    def _parse_cursor(self, table: str, cursor: Any) -> int:
        if cursor is None:
            return 0
        if not isinstance(cursor, str) or len(cursor) > 200:
            raise _ToolError("bad_cursor")
        try:
            raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
            t, off, dig = raw.split("|")
            off_i = int(off)
        except (ValueError, UnicodeDecodeError):
            raise _ToolError("bad_cursor")
        if t != table or off_i < 0 or off_i > len(self._ep["rows"][table]) or self._cursor(table, off_i) != cursor:
            raise _ToolError("bad_cursor")
        return off_i

    def _t_list_records(self, table: Any = None, cursor: Any = None, limit: Any = PAGE) -> Dict[str, Any]:
        table = self._table(table)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise _ToolError("bad_arguments")
        limit = min(limit, PAGE)
        off = self._parse_cursor(table, cursor)
        rows = self._ep["rows"][table]
        page = rows[off:off + limit]
        nxt = self._cursor(table, off + limit) if off + limit < len(rows) else None
        return {"rows": page, "next_cursor": nxt}

    def _t_get_record(self, table: Any = None, id: Any = None) -> Dict[str, Any]:  # noqa: A002
        table = self._table(table)
        if not isinstance(id, str):
            raise _ToolError("bad_arguments")
        rec = self._ep["idx"][table].get(id)
        if rec is None:
            raise _ToolError("unknown_id")
        return rec

    def _t_get_document(self, doc_id: Any = None) -> Dict[str, Any]:
        if not isinstance(doc_id, str):
            raise _ToolError("bad_arguments")
        doc = self._ep["docs"].get(doc_id)
        if doc is None:
            raise _ToolError("unknown_id")
        return doc

    def _t_calculator(self, expression: Any = None) -> Dict[str, Any]:
        try:
            return {"value": evaluate(expression)}
        except CalcError:
            raise _ToolError("calc_error")


class _ToolError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
