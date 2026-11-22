"""Structure validation, normalization, matching, metrics and reward (brief §05, plan §7).

Published rules (also in policy.json, DESIGN.md):
- Invalid structure -> episode ends, reward -1, evaluator-side log entry.
- Matching follows the organizers' published conventions (fintech-checks, Nov 20 2026):
  IDs and currency are compared exactly (case and spaces matter, no NFKC, no trimming);
  affected_ids and evidence_ids are sets (order and repeats do not matter; limits are checked
  on the raw lists first).
- A finding matches an issue iff: same type, the same set of affected_ids, the same currency,
  |claimed - expected| <= tau, evidence_ids include one complete acceptable set, and every
  evidence id exists in the episode's public data (an unknown evidence id makes the finding a FP).
- tau: an explicit ``tolerance_minor`` in the issue if present (fixtures), else the rule published
  in every policy.json (1 + conversions), else 0 (the organizers' default). See ``tolerance``.
- One-to-one maximum matching; ties prefer the smaller amount error, then the lower finding index.
- The explanation is never parsed or scored.
"""
from __future__ import annotations

import json
import math
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

TYPES = ("duplicate_invoice", "payment_allocation", "date_or_fx", "period_classification")
FINDING_KEYS = {"type", "affected_ids", "claimed_amount_minor", "currency", "evidence_ids", "explanation"}
MAX_FINDINGS, MAX_EVIDENCE, MAX_EXPLANATION, MAX_AMOUNT = 30, 10, 1000, 10 ** 18
MAX_IDS, MAX_ID_LEN = 10, 64


class StructureError(ValueError):
    pass


def _str(x: Any, what: str, max_len: int = MAX_ID_LEN) -> str:
    if not isinstance(x, str) or not x.strip() or len(x) > max_len:
        raise StructureError(f"{what} must be a non-empty string up to {max_len} chars")
    return x


def validate_structure(sub: Any, episode_id: str) -> Dict[str, Any]:
    """Return the submission unchanged if valid, else raise StructureError (bounded message)."""
    if not isinstance(sub, dict):
        raise StructureError("submission must be an object")
    if set(sub) != {"episode_id", "findings"}:
        raise StructureError("submission keys must be exactly episode_id, findings")
    if sub["episode_id"] != episode_id:
        raise StructureError("episode_id mismatch")
    fs = sub["findings"]
    if not isinstance(fs, list):
        raise StructureError("findings must be a list")
    if len(fs) > MAX_FINDINGS:
        raise StructureError(f"at most {MAX_FINDINGS} findings")
    for i, f in enumerate(fs):
        if not isinstance(f, dict) or set(f) != FINDING_KEYS:
            raise StructureError(f"finding {i}: keys must be exactly {sorted(FINDING_KEYS)}")
        if f["type"] not in TYPES:
            raise StructureError(f"finding {i}: unknown type")
        amt = f["claimed_amount_minor"]
        if isinstance(amt, bool) or not isinstance(amt, int) or amt < 0 or amt > MAX_AMOUNT:
            raise StructureError(f"finding {i}: claimed_amount_minor must be an integer in [0, 1e18]")
        _str(f["currency"], f"finding {i}: currency", 8)
        for key, lim in (("affected_ids", MAX_IDS), ("evidence_ids", MAX_EVIDENCE)):
            ids = f[key]
            if not isinstance(ids, list) or len(ids) > lim or (key == "affected_ids" and not ids):
                raise StructureError(f"finding {i}: {key} must be a list of up to {lim} ids")
            for x in ids:
                _str(x, f"finding {i}: {key} item")
        if not isinstance(f["explanation"], str) or len(f["explanation"]) > MAX_EXPLANATION:
            raise StructureError(f"finding {i}: explanation must be a string up to {MAX_EXPLANATION} chars")
    return sub


def parse_submission(text: str) -> Any:
    """Strict JSON: NaN/Infinity are rejected."""
    def _bad(const: str) -> Any:
        raise StructureError(f"invalid JSON constant {const}")
    try:
        return json.loads(text, parse_constant=_bad)
    except json.JSONDecodeError as exc:
        raise StructureError("invalid JSON") from exc


def _norm_id(x: str) -> str:
    return x  # exact comparison (organizers' convention 1 and 5)


def _nonneg_int(x: Any) -> Optional[int]:
    return x if isinstance(x, int) and not isinstance(x, bool) and x >= 0 else None


def tolerance(iss: Dict[str, Any]) -> int:
    """tau for one issue, fixed by published rules and never by the agent's answer:
    1. an explicit ``tolerance_minor`` in the issue (fixtures use this, e.g. 0);
    2. else the rule published in every episode's policy.json: 1 + conversions;
    3. else 0, the organizers' default."""
    t = _nonneg_int(iss.get("tolerance_minor"))
    if t is not None:
        return t
    c = _nonneg_int(iss.get("conversions"))
    return 1 + c if c is not None else 0


def normalize_finding(f: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": f["type"],
            "affected_ids": sorted({_norm_id(x) for x in f["affected_ids"]}),
            "claimed_amount_minor": int(f["claimed_amount_minor"]),
            "currency": _norm_id(f["currency"]),
            "evidence_ids": sorted({_norm_id(x) for x in f["evidence_ids"]})}


def _norm_issue(iss: Dict[str, Any]) -> Dict[str, Any]:
    return {**iss, "affected_ids": sorted({_norm_id(x) for x in iss["affected_ids"]}),
            "currency": _norm_id(iss["currency"]),
            "acceptable_evidence_sets": [sorted({_norm_id(x) for x in s}) for s in iss["acceptable_evidence_sets"]]}


def amount_error(f: Dict[str, Any], iss: Dict[str, Any]) -> int:
    return abs(f["claimed_amount_minor"] - iss["expected_amount_minor"])


def is_compatible(f: Dict[str, Any], iss: Dict[str, Any], known_ids: Optional[set] = None) -> bool:
    if f["type"] != iss["type"] or f["affected_ids"] != iss["affected_ids"] or f["currency"] != iss["currency"]:
        return False
    if amount_error(f, iss) > tolerance(iss):
        return False
    ev = set(f["evidence_ids"])
    if known_ids is not None and not ev <= known_ids:
        return False
    return any(set(s) <= ev for s in iss["acceptable_evidence_sets"])


def near_miss(f: Dict[str, Any], iss: Dict[str, Any]) -> Optional[str]:
    if f["type"] != iss["type"] or f["affected_ids"] != iss["affected_ids"]:
        return None
    if f["currency"] != iss["currency"]:
        return "currency"
    if amount_error(f, iss) > tolerance(iss):
        return "amount outside tolerance"
    return "evidence set incomplete"


def match(findings: List[Dict[str, Any]], issues: List[Dict[str, Any]],
          known_ids: Optional[set] = None) -> List[Tuple[int, int]]:
    """Deterministic maximum one-to-one matching (Kuhn) with tie preferences."""
    nf = [normalize_finding(f) for f in findings]
    ni = [_norm_issue(i) for i in issues]
    adj: List[List[int]] = []
    for f in nf:
        cands = [j for j, iss in enumerate(ni) if is_compatible(f, iss, known_ids)]
        cands.sort(key=lambda j: (amount_error(f, ni[j]), j))
        adj.append(cands)
    owner: Dict[int, int] = {}

    def augment(i: int, seen: set) -> bool:
        for j in adj[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or augment(owner[j], seen):
                owner[j] = i
                return True
        return False

    order = sorted(range(len(nf)), key=lambda i: (min((amount_error(nf[i], ni[j]) for j in adj[i]), default=0), i))
    for i in order:
        augment(i, set())
    return sorted((i, j) for j, i in owner.items())


def prf1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    if tp == 0 and fp == 0 and fn == 0:
        f1 = 1.0  # both reference and findings empty
    else:
        f1 = (2 * tp) / (2 * tp + fp + fn)
    return precision, recall, f1


def terminal_reward(f1: float, inspection_steps: int) -> float:
    r = 2.0 * f1 - 1.0 - 0.002 * inspection_steps
    return max(-1.0, min(1.0, r))


def score(findings: List[Dict[str, Any]], issues: List[Dict[str, Any]], inspection_steps: int,
          known_ids: Optional[set] = None) -> Dict[str, Any]:
    pairs = match(findings, issues, known_ids)
    tp = len(pairs)
    fp = len(findings) - tp
    fn = len(issues) - tp
    p, r, f1 = prf1(tp, fp, fn)
    reward = terminal_reward(f1, inspection_steps)
    matched_f = {i for i, _ in pairs}
    nf = [normalize_finding(f) for f in findings]
    ni = [_norm_issue(i) for i in issues]
    per_finding = []
    for i, f in enumerate(nf):
        if i in matched_f:
            per_finding.append({"index": i, "matched": True})
        else:
            reason = next((near_miss(f, iss) for iss in ni if near_miss(f, iss)), None)
            per_finding.append({"index": i, "matched": False, "near_miss": reason})
    by_type: Dict[str, Dict[str, int]] = {}
    for j, iss in enumerate(issues):
        t = by_type.setdefault(iss["type"], {"issues": 0, "found": 0})
        t["issues"] += 1
        t["found"] += int(any(jj == j for _, jj in pairs))
    return {"tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r, "f1": f1,
            "inspection_steps": inspection_steps, "reward": reward, "per_finding": per_finding,
            "per_type": by_type, "matched_issue_ids": [issues[j]["issue_id"] for _, j in pairs]}


def is_finite_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
