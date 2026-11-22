"""LLM + audit tools: a local model as the auditor's judgement, with code doing the mechanical work.

A small local model that picks every action itself rarely gets past reading a few pages before the 60 s episode limit,
and invents ids it never saw (each one a false finding). Measured with Qwen2.5 0.5B/1.5B on CPU, it also keeps every
candidate when shown raw records. This agent splits the job the way tool-using agents do:

1. **read** — code pages through every table (about 20 steps, no model calls);
2. **propose** — a broad check (the open rules plus deliberately looser shortcuts from ``policies.naive``) flags
   candidates; the shortcuts also flag the brief's traps (legitimate recurring invoices, documented advances,
   time-zone edges), so the list mixes real errors with plausible non-errors;
3. **re-check** — the strict open rules (``policies.rules``) say for each candidate whether they confirm it: a tool
   result the model can weigh, like a second opinion (``strict_signal=False`` hides it, to measure the model alone);
4. **judge** — the model sees one compact line of facts per candidate and the company's legitimate patterns, and
   answers which to keep (JSON);
5. **guard** — only kept candidates are submitted, each with its own record ids and evidence (no invented ids, no
   malformed findings). A model failure or the time limit drops the unreviewed candidates instead of accepting them.

The score therefore mixes the tools and the model; the app labels the mode "LLM + tools" for that reason.

Measured (Nov 22, 20 test episodes, closed mode, CPU, Qwen2.5 GGUF via an Ollama-compatible server; silence −0.50,
Reconciler +0.96, submitting every candidate +0.16, an ideal judge +0.96):

    model   pure LLM (OllamaPolicy)        LLM + tools                          without the strict re-check
    1.5B    −0.60 (0 of 79 errors found)   −0.09 (22 found, precision 0.88)     −0.82
    0.5B    −0.50 (0 found)                −0.33 (22 found, precision 0.54)     −0.50

Tried and dropped (all worse on the same 20 episodes): asking for a short reason before each decision, separate
"which to drop" / "which to keep" questions (small models copy the whole list), and one yes/no question per candidate
(the 1.5B model answered yes to everything, the 0.5B model no). The model's own judgement is the limit: a larger local
model should do better, within the 60 s per episode.
Same transport and limits as ``OllamaPolicy`` (127.0.0.1 only, bounded requests, the env's 60 s limit).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

from .baselines import Policy
from .llm import MARGIN, MAX_SECONDS, ollama_url, valid_model_name, chat
from .naive import TRICKS
from .rules import find_issues

TABLES = ("fx", "invoices", "payments", "ledger")
BATCH = 14                # candidates per model call (one compact line each)
REQUEST_TIMEOUT = 40.0
WHY = {
    "duplicate_invoice": "possible duplicate: another invoice from the same customer looks the same",
    "payment_allocation": "possible misallocated, missing or partial payment application",
    "date_or_fx": "possible wrong date or exchange rate in a currency conversion",
    "period_classification": "possible posting in the wrong reporting period",
}
SYSTEM = ("You are a careful financial auditor reviewing candidate findings. A broad automatic check flagged each "
          "candidate; it is naive and also flags legitimate business patterns. A strict check then re-verified each one "
          "against the company's rules. Keep a candidate when the strict check confirms it and nothing in the facts "
          "shows a legitimate pattern; drop candidates the strict check does not confirm unless the facts clearly show "
          "an error. Decide every candidate separately. Reply with JSON only, one entry per candidate id: "
          "{\"c1\": \"keep\", \"c2\": \"drop\", ...}.")
SYSTEM_ALONE = ("You are a careful financial auditor reviewing candidate findings. A naive automatic check flagged each "
                "candidate and also flags legitimate business patterns. Keep a candidate only if the facts show a real "
                "error, not one of the company's legitimate patterns. Decide every candidate separately. Reply with JSON "
                "only, one entry per candidate id: {\"c1\": \"keep\", \"c2\": \"drop\", ...}.")


def _ids(row: Dict[str, Any]) -> List[str]:
    return [row[k] for k in ("row_id", "invoice_id", "payment_id", "doc_id") if isinstance(row.get(k), str)]


class OllamaAssistedPolicy(Policy):
    name = "llm-assist"

    def __init__(self, model: str, timeout: float = REQUEST_TIMEOUT, episode_seconds: Optional[float] = MAX_SECONDS,
                 batch: int = BATCH, strict_signal: bool = True) -> None:
        if not valid_model_name(model):
            raise ValueError("bad model name")
        self.model, self.timeout, self.episode_seconds, self.batch = model, timeout, episode_seconds, batch
        self.strict_signal = strict_signal
        self.last_error: Optional[str] = None
        self.stats: Dict[str, int] = {}

    def reset(self, first_obs):
        super().reset(first_obs)
        self.data: Dict[str, List[dict]] = {t: [] for t in TABLES}
        self.table_i, self.cursor, self.last_table = 0, None, None
        self.t0 = time.monotonic()
        self.url = ollama_url()
        res = first_obs.get("result") or {}
        self.policy_doc = res.get("policy") or {}
        self.base = (res.get("manifest") or {}).get("base_currency")

    # ---- 1. read every table in code
    def act(self, obs):
        if self.last_table and obs.get("ok") and isinstance(obs.get("result"), dict):
            self.data[self.last_table].extend(obs["result"].get("rows") or [])
            self.cursor = obs["result"].get("next_cursor")
            if self.cursor is None:
                self.table_i += 1
        if self.table_i < len(TABLES) and obs.get("remaining_steps", 0) > 1:
            self.last_table = TABLES[self.table_i]
            return {"tool": "list_records", "args": {"table": self.last_table, "cursor": self.cursor, "limit": 50}}
        return {"tool": "submit", "args": {"findings": {"episode_id": self.episode_id, "findings": self.judged()[:30]}}}

    # ---- 2. propose candidates with tools
    def candidates(self) -> List[dict]:
        t, pol, eid = self.data, self.policy_doc, self.episode_id
        out: Dict[Tuple[str, Tuple[str, ...]], dict] = {}
        try:
            strict = find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], pol, eid)
        except Exception:  # noqa: BLE001 - books the strict check cannot read: it confirms nothing
            strict = []
        self.strict_keys = {(f["type"], tuple(sorted(f["affected_ids"]))) for f in strict}
        for f in strict:
            out.setdefault((f["type"], tuple(sorted(f["affected_ids"]))), f)
        for name, fn in TRICKS.items():
            if name == "findings_without_evidence":
                continue
            try:
                found = fn(t, pol, eid)
            except Exception:  # noqa: BLE001 - a shortcut that cannot run on these books proposes nothing
                continue
            for f in found:
                out.setdefault((f["type"], tuple(sorted(f["affected_ids"]))), f)
        return sorted(out.values(), key=lambda f: (f["type"], sorted(f["affected_ids"])))

    def facts(self, f: dict) -> str:
        """One short line of facts about the records a candidate involves (no raw dumps: small models drown in them)."""
        by_id: Dict[str, dict] = {}
        for table in ("invoices", "payments"):
            for r in self.data[table]:
                for k in _ids(r):
                    by_id.setdefault(k, dict(r, _t=table))
        parts = []
        for rid in sorted(f.get("affected_ids") or [])[:3]:
            r = by_id.get(rid)
            if not r:
                continue
            if r["_t"] == "invoices":
                lines = r.get("line_items") or []
                period = sorted({str(x.get(k)) for x in lines for k in ("service_period", "period") if x.get(k)})
                parts.append(f"{rid}: invoice {r.get('issued_at', '')[:10]}, {r.get('total_minor')} {r.get('currency')}, "
                             f"{len(lines)} line(s)" + (f", service {'/'.join(period)}" if period else ""))
            else:
                parts.append(f"{rid}: payment {r.get('timestamp', '')[:10]}, {r.get('amount_minor')} {r.get('currency')}, "
                             f"refs {','.join(r.get('invoice_refs') or []) or 'none'}")
        return "; ".join(parts)[:300]

    # ---- 3. the model judges, 4. guarded submission
    def judged(self) -> List[dict]:
        cands = self.candidates()
        self.stats = {"candidates": len(cands), "kept": 0, "reviewed": 0}
        if not cands:
            return []
        patterns = self.policy_doc.get("legitimate_patterns") or []
        kept: List[dict] = []
        for start in range(0, len(cands), self.batch):
            left = (self.episode_seconds or 1e9) - MARGIN - (time.monotonic() - self.t0)
            if left < 2.0:
                self.last_error = "time limit: the remaining candidates were not reviewed (dropped)"
                break
            chunk = cands[start:start + self.batch]
            items = []
            for i, f in enumerate(chunk):
                item = {"id": f"c{start + i + 1}", "type": f["type"], "ids": sorted(f["affected_ids"]),
                        "amount": f"{f.get('claimed_amount_minor')} {f.get('currency')} (minor units)",
                        "broad_check": WHY.get(f["type"], f["type"]), "facts": self.facts(f)}
                if self.strict_signal:
                    item["strict_check"] = "confirms" if (f["type"], tuple(sorted(f["affected_ids"]))) in self.strict_keys else "does not confirm"
                items.append(item)
            user = json.dumps({"company": {"base_currency": self.base, "timezone": self.policy_doc.get("timezone"),
                                           "legitimate_patterns": patterns}, "candidates": items}, ensure_ascii=False)
            try:
                reply = chat(self.model, [{"role": "system", "content": SYSTEM if self.strict_signal else SYSTEM_ALONE},
                                          {"role": "user", "content": user}],
                             min(self.timeout, left), temperature=0.0, max_tokens=24 + 10 * len(chunk), url=self.url)
                answer = json.loads(reply)
                if not isinstance(answer, dict):
                    raise ValueError("the reply is not a JSON object")
            except Exception as exc:  # noqa: BLE001 - HTTP, timeout, bad JSON: this batch is dropped, honestly
                self.last_error = f"{type(exc).__name__}: {exc}"[:200]
                continue
            keep = answer.get("keep")                    # also accept the list form {"keep": ["c1", ...]}
            ids = {str(k).strip() for k in keep} if isinstance(keep, list) else set()
            ids |= {str(k).strip() for k, v in answer.items() if isinstance(v, str) and v.strip().lower() == "keep"}
            self.stats["reviewed"] += len(chunk)
            for i, f in enumerate(chunk):
                if f"c{start + i + 1}" in ids:
                    kept.append(self.clean(f))
        self.stats["kept"] = len(kept)
        return kept

    @staticmethod
    def clean(f: dict) -> dict:
        """A well-formed finding built only from the candidate's own record ids."""
        ev = sorted(set(f.get("evidence_ids") or []) | set(f["affected_ids"]))[:10]
        return {"type": f["type"], "affected_ids": sorted(f["affected_ids"]), "claimed_amount_minor": int(f["claimed_amount_minor"]),
                "currency": f["currency"], "evidence_ids": ev, "explanation": "flagged by a check, confirmed by the reviewer"[:1000]}
