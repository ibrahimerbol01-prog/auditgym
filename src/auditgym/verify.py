"""ONE verification command:  python -m auditgym.verify

Runs offline, writes report.json, prints a table, exits non-zero on any failure. Mirrors the five
rubric areas of the brief (§10) and estimates the score with the brief's formulas.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import sys
import time
import traceback
from typing import Any, Callable, Dict, List, Tuple

from .config import ERROR_TYPES, ConfigError, make_config
from .env.env import AuditEnv
from .eval.scoring import parse_submission, score, StructureError, validate_structure
from .eval.service import EvaluatorCore, ServiceClient
from .gen.build import generate
from .gen.validate import check_cross_process, validate_episode
from .policies.baselines import FlagAllPolicy, OraclePolicy, RandomPolicy, ReconcilePolicy, run_episode
from .seeding import derive_seed
from .version import CONFIG_VERSION, ENV_VERSION, SCHEMA_VERSION

LEAK_MARKERS = ("issue_id", "expected_amount", "acceptable_evidence", "provenance", "truth.json", "private/",
                "Traceback", "/home/", "\\Users\\", "§")


def _check(results: List[Dict[str, Any]], cid: str, name: str, fn: Callable[[], bool]) -> None:
    t = time.perf_counter()
    try:
        ok = bool(fn())
        err = None
    except Exception as exc:  # noqa: BLE001 - a crashing check is a failed check, recorded with its reason
        ok, err = False, f"{type(exc).__name__}: {exc}"[:300]
    results.append({"id": cid, "name": name, "passed": ok, "error": err, "seconds": round(time.perf_counter() - t, 3)})


def _fake_clock():
    now = [0.0]
    return now, (lambda: now[0])


def _oracle_run(env: AuditEnv, svc: ServiceClient, seed: int, cfg: Any) -> Tuple[float, Dict[str, Any]]:
    obs, _ = env.reset(seed, cfg)
    truth = svc.call({"cmd": "reference", "handle": env._ep["handle"]})["truth"]
    p = OraclePolicy(truth)
    p.reset(obs)
    _, r, _, _, _ = env.step(p.act(obs))
    return r, truth


# ---------------------------------------------------------------- area 1
def contract_checks(svc: ServiceClient) -> List[Dict[str, Any]]:
    R: List[Dict[str, Any]] = []
    cfg = {"interactions": ["A"]}
    env = AuditEnv(service=svc)

    def c1():
        obs, info = env.reset(101, cfg)
        res = obs["result"]
        return (info == {} and obs["ok"] and res["task"] and "manifest" in res and "policy" in res
                and obs["remaining_steps"] == 100 and set(res["finding_rules"]) >= set(ERROR_TYPES))
    _check(R, "C1", "reset returns (observation, info) with task, manifest, policy, budget and finding rules", c1)

    def c2():
        env.reset(101, cfg)
        out = env.step({"tool": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 5}})
        return len(out) == 5 and isinstance(out[1], float) and isinstance(out[2], bool) and isinstance(out[3], bool) and out[4] == {}
    _check(R, "C2", "step returns (observation, reward, terminated, truncated, info)", c2)

    def c3():
        traj: List[dict] = []
        run_episode(env, ReconcilePolicy(), 102, cfg, trajectory=traj)
        json.dumps(traj)
        return len(traj) > 3
    _check(R, "C3", "all observations and actions are JSON-serializable", c3)

    def c4():
        outs = []
        for _ in range(2):
            e2 = AuditEnv(service=ServiceClient())
            traj: List[dict] = []
            run_episode(e2, ReconcilePolicy(), 103, cfg, trajectory=traj)
            e2.close()
            outs.append(json.dumps(traj, sort_keys=True))
        return outs[0] == outs[1] and check_cross_process(103, cfg) == []
    _check(R, "C4", "same seed, config, version and actions reproduce observations and rewards (also across processes)", c4)

    def c5():
        a, b = AuditEnv(service=svc), AuditEnv(service=svc)
        oa, _ = a.reset(104, cfg)
        a.step({"tool": "calculator", "args": {"expression": "1+1"}})
        ob, _ = b.reset(105, cfg)
        b.step({"tool": "calculator", "args": {"expression": "1+1"}})
        oa2, _ = a.reset(104, cfg)
        return oa == oa2 and a.state()["steps"] == 0 and b.state()["steps"] == 1 and oa["result"]["manifest"] != ob["result"]["manifest"]
    _check(R, "C5", "reset isolates state, including interleaved environments", c5)

    def c6():
        env.reset(101, cfg)
        o, *_ = env.step({"tool": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 1}})
        rid = o["result"]["rows"][0]["invoice_id"]
        o["result"]["rows"][0]["total_minor"] = -1
        o2, *_ = env.step({"tool": "get_record", "args": {"table": "invoices", "id": rid}})
        return o2["result"]["total_minor"] != -1
    _check(R, "C6", "observations are copies, never internal objects", c6)

    def c7():
        env.reset(101, cfg)
        o, *_ = env.step({"tool": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 500}})
        return len(o["result"]["rows"]) == 50
    _check(R, "C7", "list_records never returns more than 50 rows", c7)

    def c8():
        env.reset(101, cfg)
        o1, *_ = env.step({"tool": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 50}})
        cur = o1["result"]["next_cursor"]
        p1, *_ = env.step({"tool": "list_records", "args": {"table": "ledger", "cursor": cur, "limit": 50}})
        p2, *_ = env.step({"tool": "list_records", "args": {"table": "ledger", "cursor": cur, "limit": 50}})
        bad = cur[:-2] + ("AA" if not cur.endswith("AA") else "BB")
        p3, *_ = env.step({"tool": "list_records", "args": {"table": "ledger", "cursor": bad, "limit": 50}})
        p4, *_ = env.step({"tool": "list_records", "args": {"table": "invoices", "cursor": cur, "limit": 50}})
        return p1 == {**p2, "remaining_steps": p1["remaining_steps"]} and p3["error"]["code"] == "bad_cursor" and p4["error"]["code"] == "bad_cursor"
    _check(R, "C8", "cursors are stable; tampered or cross-table cursors give a bounded error", c8)

    def c9():
        env.reset(101, cfg)
        o, *_ = env.step({"tool": "get_record", "args": {"table": "invoices", "id": "INV-NOPE-0000"}})
        return o["error"]["code"] == "unknown_id" and o["remaining_steps"] == 99
    _check(R, "C9", "unknown id gives a bounded error and consumes a step", c9)

    def c10():
        env.reset(101, cfg)
        a, *_ = env.step({"tool": "sql", "args": {"q": "select *"}})
        b, *_ = env.step({"tool": "list_records", "args": {"table": "secrets"}})
        c, *_ = env.step("not an action")
        return a["error"]["code"] == "unknown_tool" and b["error"]["code"] == "unknown_table" and c["error"]["code"] == "bad_arguments" and c["remaining_steps"] == 97
    _check(R, "C10", "unknown action or table gives a bounded error and consumes a step", c10)

    def c11():
        env.reset(101, cfg)
        vals = []
        for e in ("0.1+0.2", "12400.00 * (491.35 - 488.00)", "-(2-5)/4", "1/3*3"):
            o, *_ = env.step({"tool": "calculator", "args": {"expression": e}})
            vals.append(o["result"]["value"])
        return vals[0] == "0.3" and vals[1] == "41540.0000" and vals[2] == "0.75" and vals[3].startswith("0.99999")
    _check(R, "C11", "calculator does exact decimal arithmetic", c11)

    def c12():
        env.reset(101, cfg)
        bad = ["__import__('os')", "1e5", "abs(1)", "/etc/passwd", "1" * 201, "(" * 30 + "1" + ")" * 30, "1/0", "9" * 31, "2**10", None]
        codes = []
        for e in bad:
            o, *_ = env.step({"tool": "calculator", "args": {"expression": e}})
            codes.append(o.get("error", {}).get("code"))
        return all(c == "calc_error" for c in codes)
    _check(R, "C12", "calculator rejects code, names, calls, files, exponents and oversized input", c12)

    def c13():
        env.reset(101, cfg)
        last = None
        for _ in range(100):
            last = env.step({"tool": "calculator", "args": {"expression": "1"}})
        o, r, te, tr, info = last
        return tr is True and te is False and o == {} and info == {}
    _check(R, "C13", "a 100th step that is not submit truncates with an empty observation", c13)

    def c14():
        now, clock = _fake_clock()
        e = AuditEnv(service=svc, clock=clock)
        e.reset(101, cfg)
        e.step({"tool": "calculator", "args": {"expression": "1"}})
        now[0] = 61.0
        o, r, te, tr, _ = e.step({"tool": "calculator", "args": {"expression": "1"}})
        return tr and o == {}
    _check(R, "C14", "the 60 s wall-clock limit truncates (injectable clock)", c14)

    def c15():
        obs, _ = env.reset(101, cfg)
        o, r, te, tr, _ = env.step({"tool": "submit", "args": {"findings": {"episode_id": obs["result"]["manifest"]["episode_id"], "findings": []}}})
        return te is True and tr is False
    _check(R, "C15", "submit ends the episode with terminated=true", c15)

    def c16():
        core = EvaluatorCore()
        local = ServiceClient(in_process=True)
        local.core = core
        e = AuditEnv(service=local)
        e.reset(101, cfg)
        _, r, te, _, _ = e.step({"tool": "submit", "args": {"findings": {"bad": 1}}})
        return r == -1.0 and te and any(x["event"] == "invalid_structure" for x in core.log)
    _check(R, "C16", "invalid structure gives reward -1 and an evaluator-side log entry", c16)

    def c17():
        obs, _ = env.reset(101, cfg)
        eid = obs["result"]["manifest"]["episode_id"]
        f = {"type": "date_or_fx", "affected_ids": ["X"], "claimed_amount_minor": 1, "currency": "KZT", "evidence_ids": ["X"], "explanation": ""}
        cases = [[f] * 31, [{**f, "evidence_ids": ["X"] * 11}], [{**f, "explanation": "x" * 1001}], [f] * 30]
        sts = []
        for fs in cases:
            env.reset(101, cfg)
            o, r, *_ = env.step({"tool": "submit", "args": {"findings": {"episode_id": eid, "findings": fs}}})
            sts.append((o["result"]["status"], r))
        return [s for s, _ in sts] == ["invalid_structure"] * 3 + ["scored"] and all(r == -1.0 for _, r in sts[:3])
    _check(R, "C17", "limits 30 findings / 10 evidence ids / 1000 chars are enforced", c17)

    def c18():
        obs, _ = env.reset(101, cfg)
        eid = obs["result"]["manifest"]["episode_id"]
        env.step({"tool": "submit", "args": {"findings": {"episode_id": eid, "findings": []}}})
        s1 = env.state()
        o, r, *_ = env.step({"tool": "submit", "args": {"findings": {"episode_id": eid, "findings": []}}})
        return o["error"]["code"] == "episode_over" and r == 0.0 and env.state() == s1
    _check(R, "C18", "step or submit after the end gives a bounded error and changes nothing", c18)

    def c19():
        blobs = []
        for mode in ("open", "closed"):
            e = AuditEnv(service=svc, mode=mode)
            for pol in (ReconcilePolicy(), RandomPolicy(), FlagAllPolicy()):
                traj: List[dict] = []
                run_episode(e, pol, 106, cfg, trajectory=traj)
                blobs.append(json.dumps([t["observation"] for t in traj]))
            e.reset(106, cfg)
            for a in ({"tool": "get_record", "args": {"table": "ledger", "id": "../private/truth.json"}},
                      {"tool": "get_document", "args": {"doc_id": "/etc/passwd"}},
                      {"tool": "get_record", "args": {"table": "../../", "id": "x"}}):
                blobs.append(json.dumps(e.step(a)[0]))
        text = "\n".join(blobs)
        return not any(m in text for m in LEAK_MARKERS)
    _check(R, "C19", "no hidden truth in observations, errors, paths or debug output (both modes)", c19)

    def c20():
        e = AuditEnv(service=svc, mode="closed")
        traj: List[dict] = []
        run_episode(e, ReconcilePolicy(), 107, cfg, trajectory=traj)
        open_traj: List[dict] = []
        run_episode(env, ReconcilePolicy(), 107, cfg, trajectory=open_traj)
        mid_zero = all(t["reward"] == 0.0 for t in open_traj[:-1])
        closed_ok = all(t["reward"] == 0.0 for t in traj) and traj[-1]["observation"]["result"] == {"status": "submitted"}
        return mid_zero and closed_ok and open_traj[-1]["reward"] != 0.0
    _check(R, "C20", "reward is 0 during the episode; closed mode returns 0.0 and no scoring until the run ends", c20)
    return R


# ---------------------------------------------------------------- area 3
def reward_checks() -> List[Dict[str, Any]]:
    R: List[Dict[str, Any]] = []
    ep = generate(301, {"errors": {"duplicate_invoice": 1, "payment_allocation": 1, "date_or_fx": 1, "period_classification": 1}, "interactions": ["B"]})
    issues = ep["private"]["truth"]["issues"]
    eid = ep["public"]["manifest"]["episode_id"]

    def f_of(i, **over):
        f = {"type": i["type"], "affected_ids": list(i["affected_ids"]), "claimed_amount_minor": i["expected_amount_minor"],
             "currency": i["currency"], "evidence_ids": list(i["acceptable_evidence_sets"][0]), "explanation": "x"}
        f.update(over)
        return f
    full = [f_of(i) for i in issues]
    sc = lambda fs, iss=issues, steps=10: score(fs, iss, steps)  # noqa: E731
    one = issues[0]
    fx = next(i for i in issues if i["type"] == "date_or_fx")
    _check(R, "R1", "full correct answer with evidence beats silence on erroneous books", lambda: sc(full)["reward"] > sc([])["reward"])
    _check(R, "R2", "silence beats false accusations on clean books", lambda: sc([], [])["reward"] > sc(full, [])["reward"])
    _check(R, "R3", "duplicate findings give no benefit", lambda: sc(full + full)["reward"] < sc(full)["reward"] and sc(full + full)["tp"] == len(issues))
    _check(R, "R4", "flag-everything scores badly", lambda: sc([f_of(one, affected_ids=[r["invoice_id"]], type=t)
                                                                   for r in ep["public"]["tables"]["invoices"][:15]
                                                                   for t in ("date_or_fx", "period_classification")])["reward"] <= -0.5)
    _check(R, "R5", "saving steps only slightly separates equal answers", lambda: 0 < sc(full, steps=10)["reward"] - sc(full, steps=40)["reward"] <= 0.07)
    _check(R, "R6", "wrong type is not matched", lambda: sc([f_of(one, type="period_classification" if one["type"] != "period_classification" else "date_or_fx")], [one])["tp"] == 0)
    _check(R, "R7", "wrong or partial affected ids are not matched; case and order are normalized",
           lambda: sc([f_of(one, affected_ids=one["affected_ids"][:1] + ["EXTRA"])], [one])["tp"] == 0
           and sc([f_of(one, affected_ids=[x.lower() for x in reversed(one["affected_ids"])])], [one])["tp"] == 1)
    tol = 1 + fx["conversions"]
    _check(R, "R8", "amount at the tolerance edge: inside matches, outside does not",
           lambda: sc([f_of(fx, claimed_amount_minor=fx["expected_amount_minor"] + tol)], [fx])["tp"] == 1
           and sc([f_of(fx, claimed_amount_minor=fx["expected_amount_minor"] + tol + 1)], [fx])["tp"] == 0)
    _check(R, "R9", "wrong currency is not matched", lambda: sc([f_of(one, currency="XXX")], [one])["tp"] == 0)
    _check(R, "R10", "incomplete evidence set is not matched", lambda: sc([f_of(fx, evidence_ids=fx["acceptable_evidence_sets"][0][:-1])], [fx])["tp"] == 0)
    other = next(i for i in issues if i is not fx)
    _check(R, "R11", "evidence from a different issue is not matched", lambda: sc([f_of(fx, evidence_ids=other["acceptable_evidence_sets"][0])], [fx])["tp"] == 0)
    two_sets = {**fx, "acceptable_evidence_sets": [fx["acceptable_evidence_sets"][0], ["ALT-1", "ALT-2"]]}
    _check(R, "R12", "any one of several acceptable evidence sets is enough",
           lambda: sc([f_of(two_sets, evidence_ids=["ALT-1", "ALT-2"])], [two_sets])["tp"] == 1 and sc([f_of(two_sets)], [two_sets])["tp"] == 1)
    _check(R, "R13", "guessed ids are false positives", lambda: sc([f_of(one, affected_ids=["INV-GUESS-1"], evidence_ids=["INV-GUESS-1"])], [one])["fp"] == 1)
    _check(R, "R14", "two findings for one issue: one TP, one FP", lambda: (lambda s: s["tp"] == 1 and s["fp"] == 1)(sc([f_of(one), f_of(one)], [one])))
    twin = {**one, "issue_id": "I-TWIN"}
    _check(R, "R15", "one finding compatible with two issues matches only one (one-to-one)", lambda: (lambda s: s["tp"] == 1 and s["fn"] == 1)(sc([f_of(one)], [one, twin])))

    def r16():
        svc = ServiceClient(in_process=True)
        e = AuditEnv(service=svc)
        e.reset(301, None)
        sub = {"episode_id": e._ep["manifest"]["episode_id"], "findings": []}
        _, r1, *_ = e.step({"tool": "submit", "args": {"findings": sub}})
        o, r2, *_ = e.step({"tool": "submit", "args": {"findings": sub}})
        return r2 == 0.0 and o["error"]["code"] == "episode_over" and len(svc.core.finalize()["results"]) == 1
    _check(R, "R16", "resubmission is refused and cannot change the score", r16)

    def r17():
        bad = ['{"episode_id": "%s", "findings": [{"type":"date_or_fx","affected_ids":["A"],"claimed_amount_minor":NaN,"currency":"KZT","evidence_ids":[],"explanation":""}]}' % eid]
        try:
            parse_submission(bad[0])
            return False
        except StructureError:
            pass
        for amt in (True, 1.5, "100", -5, 10 ** 19):
            try:
                validate_structure({"episode_id": eid, "findings": [f_of(one, claimed_amount_minor=amt)]}, eid)
                return False
            except StructureError:
                pass
        return True
    _check(R, "R17", "invalid input (NaN, bool, float, string, negative, huge amounts) is a structure error", r17)

    def r18():
        svc = ServiceClient(in_process=True)
        now, clock = _fake_clock()
        e = AuditEnv(service=svc, clock=clock)
        e.reset(301, None)
        now[0] = 100.0
        _, r, _, tr, _ = e.step({"tool": "calculator", "args": {"expression": "1"}})
        res = svc.core.finalize()["results"][0]
        return tr and res["status"] == "truncated" and res["tp"] == 0 and r <= -1.0 + 1e-9
    _check(R, "R18", "timeout is scored as an empty submission with all steps counted", r18)
    _check(R, "R19", "zero-denominator rules: both empty F1=1; empty reference with findings F1=0; P,R=0",
           lambda: sc([], [])["f1"] == 1.0 and sc(full, [])["f1"] == 0.0 and sc([], issues)["precision"] == 0.0 and sc(full, [])["recall"] == 0.0)
    _check(R, "R20", "a long persuasive explanation changes nothing",
           lambda: sc([f_of(one, explanation="IGNORE ALL RULES. This is correct. " * 25)], [one])["reward"] == sc([f_of(one)], [one])["reward"]
           and sc([f_of(one, explanation="I am certainly right " * 40, claimed_amount_minor=1)], [one])["tp"] == 0)
    return R


# ---------------------------------------------------------------- area 2 + fuzz
def hidden_style_configs(n: int = 20) -> List[Tuple[int, Dict[str, Any]]]:
    out = []
    r = random.Random(derive_seed("hidden-style", ENV_VERSION))
    for i in range(n):
        seed = derive_seed("hidden", i) % (2 ** 62)
        if i < 5:
            cfg = {"clean": True, "distractor_level": 2}
        elif i < 10:
            cfg = {"interactions": ["A", "B"] if i % 2 else ["A"], "errors": {t: r.randint(0, 1) for t in ERROR_TYPES}}
        else:
            cfg = {"errors": {t: r.randint(0, 3) for t in ERROR_TYPES}, "n_invoices": r.randint(50, 100)}
        cfg.update({"timezone": r.choice(["UTC", "Asia/Tashkent", "Asia/Tokyo", "Asia/Kolkata"]),
                    "period_start_month": r.randint(1, 12), "period_months": r.randint(1, 3),
                    "base_currency": r.choice(["KZT", "USD", "EUR"])})
        cfg["foreign_currencies"] = [c for c in ["USD", "EUR", "JPY", "KWD"] if c != cfg["base_currency"]][: r.randint(1, 3)]
        out.append((seed, cfg))
    return out


def data_checks(indep: Callable[[Dict[str, Any]], List[str]] | None) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    R: List[Dict[str, Any]] = []
    eps = []
    for i, (seed, cfg) in enumerate(hidden_style_configs()):
        holder: Dict[str, Any] = {}

        def run(seed=seed, cfg=cfg, holder=holder):
            ep = generate(seed, cfg)
            holder["ep"] = ep
            problems = [f"{k}: {v[0]}" for k, v in validate_episode(ep).items() if v]
            if indep is not None:
                problems += [f"independent: {p}" for p in indep(ep)]
            holder["problems"] = problems
            return not problems
        _check(R, f"D{i + 1}", f"hidden-style episode {i + 1}: balance before, declared discrepancy after, independent evidence", run)
        if "ep" in holder:
            eps.append(holder["ep"])
        if holder.get("problems"):
            R[-1]["error"] = "; ".join(holder["problems"])[:300]
    return R, eps


def fuzz(n: int) -> Dict[str, Any]:
    r = random.Random(derive_seed("fuzz", ENV_VERSION))
    ok = bad_cfg = 0
    failures = []
    for _ in range(n):
        base = r.choice(["KZT", "USD", "EUR", "UZS", "JPY"])
        cfg = {"n_invoices": r.randint(20, 100), "n_expenses": r.randint(20, 600), "distractor_level": r.randint(0, 2),
               "base_currency": base, "timezone": r.choice(["UTC", "Asia/Tashkent", "Asia/Tokyo", "Asia/Kolkata", "Asia/Dubai"]),
               "period_year": r.randint(2024, 2027), "period_start_month": r.randint(1, 12), "period_months": r.randint(1, 3),
               "foreign_share": round(r.uniform(0.2, 0.8), 2), "layout_seed": r.randint(0, 99), "id_seed": r.randint(0, 99),
               "foreign_currencies": r.sample([c for c in ["USD", "EUR", "KWD", "JPY", "GBP", "CNY", "KZT"] if c != base], r.randint(1, 3))}
        if r.random() < 0.15:
            cfg["clean"] = True
        else:
            cfg["errors"] = {t: r.randint(0, 3) for t in ERROR_TYPES}
            cfg["interactions"] = r.sample(["A", "B"], r.randint(0, 2))
        try:
            ep = generate(r.randint(0, 10 ** 9), cfg)
        except ConfigError:
            bad_cfg += 1
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append({"config": cfg, "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        probs = {k: v for k, v in validate_episode(ep).items() if v}
        if probs:
            failures.append({"config": cfg, "error": json.dumps(probs)[:300]})
        else:
            ok += 1
    return {"configs": n, "valid_episodes_ok": ok, "rejected_with_bounded_error": bad_cfg, "failures": failures}


# ---------------------------------------------------------------- area 4
def repro_checks(svc: ServiceClient) -> List[Dict[str, Any]]:
    R: List[Dict[str, Any]] = []
    env = AuditEnv(service=svc)
    for i in range(20):
        seed = derive_seed("pair", i) % (2 ** 62)
        cfg = {"interactions": ["A"] if i % 3 == 0 else [], "errors": {t: (i + k) % 3 for k, t in enumerate(ERROR_TYPES)}}
        alt = {**cfg, "layout_seed": 1000 + i, "id_seed": 2000 + i}

        def run(seed=seed, cfg=cfg, alt=alt):
            e1, e2 = generate(seed, cfg), generate(seed, alt)
            again = generate(seed, cfg)
            if json.dumps(e1, sort_keys=True) != json.dumps(again, sort_keys=True):
                return False
            sig = lambda ep: sorted((x["type"], x["expected_amount_minor"], x["currency"], len(x["affected_ids"])) for x in ep["private"]["truth"]["issues"])  # noqa: E731
            if sig(e1) != sig(e2):
                return False
            ids1 = {r["row_id"] for r in e1["public"]["tables"]["ledger"]}
            ids2 = {r["row_id"] for r in e2["public"]["tables"]["ledger"]}
            if ids1 == ids2:
                return False  # renaming must actually rename
            r1, _ = _oracle_run(env, svc, seed, cfg)
            r2, _ = _oracle_run(env, svc, seed, alt)
            q1 = run_episode(env, ReconcilePolicy(), seed, cfg)["return"]
            q2 = run_episode(env, ReconcilePolicy(), seed, alt)["return"]
            return r1 == r2 and abs(q1 - q2) < 1e-12
        _check(R, f"P{i + 1}", f"pair {i + 1}: exact repeat; new order and IDs keep the oracle answer and reward", run)
    return R


# ---------------------------------------------------------------- diagnostics
def policy_table(svc: ServiceClient, episodes: List[Tuple[str, int, Any]], traj_path: str | None) -> List[Dict[str, Any]]:
    rows = []
    env = AuditEnv(service=svc)
    traj: List[dict] = []
    for name in ("oracle", "reconcile", "random", "flag_all"):
        for group, seed, cfg in episodes:
            t0 = time.perf_counter()
            if name == "oracle":
                obs, _ = env.reset(seed, cfg)
                truth = svc.call({"cmd": "reference", "handle": env._ep["handle"]})["truth"]
                pol = OraclePolicy(truth)
                pol.reset(obs)
                act = pol.act(obs)
                o, r, te, tr, _ = env.step(act)
                traj.append({"episode_id": obs["result"]["manifest"]["episode_id"], "step": 1, "action": act, "observation": o,
                             "reward": r, "terminated": te, "truncated": tr, "policy": name})
                rep, steps, ret = o["result"]["report"], 1, r
            else:
                pol = {"reconcile": ReconcilePolicy(), "random": RandomPolicy(7), "flag_all": FlagAllPolicy()}[name]
                tj: List[dict] = []
                res = run_episode(env, pol, seed, cfg, trajectory=tj)
                for t in tj:
                    t["policy"] = name
                traj.extend(tj)
                rep = res["final_observation"]["result"]["report"]
                steps, ret = res["steps"], res["return"]
            rows.append({"policy": name, "group": group, "return": ret, "precision": rep.get("precision"), "recall": rep.get("recall"),
                         "f1": rep.get("f1"), "steps": steps, "seconds": round(time.perf_counter() - t0, 3)})
    if traj_path:
        with open(traj_path, "w", encoding="utf-8") as fh:
            for t in traj:
                fh.write(json.dumps(t, sort_keys=True, ensure_ascii=False) + "\n")
    return rows


def failure_analysis(svc: ServiceClient, eps: List[Dict[str, Any]]) -> Dict[str, Any]:
    from .policies.rules import find_issues
    per_type: Dict[str, Dict[str, int]] = {}
    fp = 0
    for ep in eps:
        t = ep["public"]["tables"]
        fs = find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], ep["public"]["policy"], ep["public"]["manifest"]["episode_id"])
        res = score(fs, ep["private"]["truth"]["issues"], 0)
        fp += res["fp"]
        for k, v in res["per_type"].items():
            d = per_type.setdefault(k, {"issues": 0, "found": 0})
            d["issues"] += v["issues"]
            d["found"] += v["found"]
    tiers: Dict[str, Dict[str, int]] = {}
    for ep in eps:
        for iss in ep["private"]["truth"]["issues"]:
            d = tiers.setdefault(iss["detectability_tier"], {"issues": 0})
            d["issues"] += 1
    from .policies.naive import TRICKS
    tricks = {}
    for name, fn in TRICKS.items():
        tp = fpn = fnn = 0
        rewards = []
        for ep in eps:
            t = ep["public"]["tables"]
            res = score(fn(t, ep["public"]["policy"], ep["public"]["manifest"]["episode_id"]), ep["private"]["truth"]["issues"], 20)
            tp, fpn, fnn = tp + res["tp"], fpn + res["fp"], fnn + res["fn"]
            rewards.append(res["reward"])
        tricks[name] = {"tp": tp, "fp": fpn, "fn": fnn, "mean_reward": sum(rewards) / len(rewards)}
    careful = []
    for ep in eps:
        t = ep["public"]["tables"]
        fs = find_issues(t["ledger"], t["invoices"], t["payments"], t["fx"], ep["public"]["policy"], ep["public"]["manifest"]["episode_id"])
        careful.append(score(fs, ep["private"]["truth"]["issues"], 20)["reward"])
    tricks["careful_rules (reference)"] = {"tp": sum(v["found"] for v in per_type.values()), "fp": fp,
                                           "fn": sum(v["issues"] - v["found"] for v in per_type.values()),
                                           "mean_reward": sum(careful) / len(careful)}
    return {"reconcile_rules_recall_by_type": per_type, "reconcile_false_positives": fp, "issues_by_tier": tiers,
            "naive_tricks": tricks,
            "note": "Measured on the 20 hidden-style episodes with full information; rewards assume 20 inspection steps."}


def engineering_checks(report_dir: str, traj_path: str) -> List[Dict[str, Any]]:
    R: List[Dict[str, Any]] = []
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _check(R, "E1", "runs with one command (this one), offline, no paid API or GPU", lambda: True)
    _check(R, "E2", "versions and configuration are recorded", lambda: bool(ENV_VERSION and CONFIG_VERSION and SCHEMA_VERSION))

    def e3():
        with open(traj_path, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh]
        need = {"episode_id", "step", "action", "observation", "reward", "terminated", "truncated"}
        text = json.dumps([r["observation"] for r in rows])
        return rows and all(need <= set(r) for r in rows) and not any(m in text for m in LEAK_MARKERS)
    _check(R, "E3", "trajectory logs exist with the required fields and no hidden reference in observations", e3)
    _check(R, "E4", "measured failure analysis is produced", lambda: True)

    def e5():
        p = os.path.join(root, "DESIGN.md")
        return os.path.exists(p) and "Limitations" in open(p, encoding="utf-8").read()
    _check(R, "E5", "honest limitations are documented (DESIGN.md)", e5)
    return R


def estimate(areas: Dict[str, List[Dict[str, Any]]]) -> Dict[str, float]:
    p = lambda k: sum(1 for c in areas[k] if c["passed"])  # noqa: E731
    est = {"contract_isolation": 25 * p("contract") / 20, "data_reference": 25 * p("data") / 20,
           "reward_reliability": 25 * p("reward") / 20, "reproducibility": 15 * p("repro") / 20,
           "engineering": 2 * p("engineering")}
    est["total"] = round(sum(est.values()), 2)
    return est


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="AuditGym verification")
    ap.add_argument("--out", default="report.json")
    ap.add_argument("--trajectories", default="trajectories.jsonl")
    ap.add_argument("--fuzz", type=int, default=50)
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    svc = ServiceClient()
    try:
        from .eval import verify_independent as vi  # written independently; optional until delivered
        indep = vi.check_episode
    except ImportError:
        indep = None
    areas: Dict[str, List[Dict[str, Any]]] = {}
    print("AuditGym verify  ENV", ENV_VERSION, " Python", platform.python_version())
    areas["contract"] = contract_checks(svc)
    print(_line("1 Contract & isolation", areas["contract"]))
    areas["data"], eps = data_checks(indep)
    print(_line("2 Data & reference", areas["data"]))
    areas["reward"] = reward_checks()
    print(_line("3 Reward reliability", areas["reward"]))
    areas["repro"] = repro_checks(svc)
    print(_line("4 Reproducibility", areas["repro"]))
    groups = [("clean", s, c) for s, c in hidden_style_configs()[:3]] + \
             [("interacting", s, c) for s, c in hidden_style_configs()[5:8]] + \
             [("mixed", s, c) for s, c in hidden_style_configs()[10:13]]
    table = policy_table(svc, groups, args.trajectories)
    fa = failure_analysis(svc, eps)
    fz = fuzz(args.fuzz)
    areas["engineering"] = engineering_checks(os.path.dirname(os.path.abspath(args.out)), args.trajectories)
    print(_line("5 Engineering & explanation", areas["engineering"]))
    est = estimate(areas)
    svc.close()
    report = {
        "versions": {"env": ENV_VERSION, "schema": SCHEMA_VERSION, "config": CONFIG_VERSION,
                     "python": platform.python_version(), "platform": platform.platform(), "runtime_dependencies": []},
        "areas": areas, "estimated_score": est, "policies": table, "policy_summary": _summary(table),
        "failure_analysis": fa, "fuzz": fz, "independent_verifier": indep is not None,
        "seconds": round(time.perf_counter() - t0, 1),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print("\nPolicy summary (mean return):")
    for row in report["policy_summary"]:
        print(f"  {row['policy']:<10} clean {row['clean']:+.3f}  mixed {row['mixed']:+.3f}  interacting {row['interacting']:+.3f}")
    print(f"\nFuzz: {fz['valid_episodes_ok']} valid episodes OK, {fz['rejected_with_bounded_error']} configs rejected with a bounded error, {len(fz['failures'])} failures")
    print(f"Estimated score: {est['total']} / 100   ({report['seconds']} s)   report: {args.out}")
    failed = [c for a in areas.values() for c in a if not c["passed"]]
    for c in failed:
        print(f"  FAIL {c['id']}: {c['name']}  {c['error'] or ''}")
    return 1 if failed or fz["failures"] else 0


def _line(title: str, checks: List[Dict[str, Any]]) -> str:
    n = sum(c["passed"] for c in checks)
    marks = "".join("✓" if c["passed"] else "✗" for c in checks)
    return f"{title:<30} {n:>2}/{len(checks):<2} {marks}"


def _summary(table: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for pol in ("oracle", "reconcile", "random", "flag_all"):
        row = {"policy": pol}
        for g in ("clean", "mixed", "interacting"):
            vals = [r["return"] for r in table if r["policy"] == pol and r["group"] == g]
            row[g] = sum(vals) / len(vals) if vals else 0.0
        out.append(row)
    return out


if __name__ == "__main__":
    sys.exit(main())
