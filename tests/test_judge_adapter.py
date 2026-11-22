"""The organizers' published checks (fintech-checks, Nov 20 2026), run through judge_adapter.py.

Block 1 contract tests C01-C17 and C19, Block 3 matcher tests 1-20, the open examples M01-M12 and
Block 4 paired checks (row permutation and one-to-one ID renaming done on a copy, like the jury does).
"""
import csv
import io
import json
import os
import random
import re
import shutil
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import judge_adapter as J  # noqa: E402

TOL = 1e-9


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="judge-")
        cls.ep = os.path.join(cls.tmp, "E")
        J.generate_episode(1001, {}, cls.ep)
        cls.manifest = json.loads(_read(os.path.join(cls.ep, "public", "manifest.json")))
        cls.truth = json.loads(_read(os.path.join(cls.ep, "private", "truth.json")))
        cls.eid = cls.manifest["episode_id"]
        cls.ledger = list(csv.DictReader(io.StringIO(_read(os.path.join(cls.ep, "public", "ledger.csv")))))
        cls.invoices = [json.loads(l) for l in _read(os.path.join(cls.ep, "public", "invoices.jsonl")).splitlines() if l]
        cls.docs = [json.loads(l) for l in _read(os.path.join(cls.ep, "public", "documents.jsonl")).splitlines() if l]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def env(self, episode_dir=None, mode="closed"):
        e = J.make_env()
        self.addCleanup(e.close)
        obs, info = e.reset(1, {"mode": mode, "episode_dir": episode_dir or self.ep, "team_config": {}})
        return e, obs, info

    @staticmethod
    def act(name, **args):
        return {"name": name, "args": args}


class TestContract(Base):
    def test_c01_c02_c03_first_observation(self):
        e, obs, info = self.env()
        json.dumps(obs), json.dumps(info)
        self.assertEqual(set(obs), {"task", "manifest", "policy", "remaining_steps"})
        self.assertEqual(obs["remaining_steps"], 100)
        m = obs["manifest"]
        for k in ("schema_version", "episode_id", "base_currency", "period_start", "period_end", "timezone", "counts", "rounding"):
            self.assertIn(k, m)
        self.assertEqual(m["counts"]["ledger"], len(self.ledger))
        self.assertEqual(m["counts"]["documents"], len(self.docs))
        blob = json.dumps(obs)
        self.assertNotIn("truth", blob.lower().replace("truthful", ""))
        self.assertNotIn("expected_amount_minor", blob)

    def test_c04_c05_c06_paging(self):
        e, obs, _ = self.env()
        seen, cursor, first = [], None, None
        while True:
            o, r, term, trunc, info = e.step(self.act("list_records", table="ledger", cursor=cursor, limit=50))
            self.assertIsInstance(term, bool), self.assertIsInstance(trunc, bool)
            self.assertEqual(r, 0.0), self.assertEqual(info, {})
            recs = o["result"]["records"]
            self.assertLessEqual(len(recs), 50)
            seen += [x["row_id"] for x in recs]
            if first is None:
                first = (o["result"]["next_cursor"], recs)
            cursor = o["result"]["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(set(seen), {r["row_id"] for r in self.ledger})
        a = e.step(self.act("list_records", table="ledger", cursor=first[0], limit=50))[0]
        b = e.step(self.act("list_records", table="ledger", cursor=first[0], limit=50))[0]
        self.assertEqual(a["result"], b["result"])
        self.assertEqual(a["remaining_steps"] - 1, b["remaining_steps"])

    def test_c07_c08_record_and_document(self):
        e, _, _ = self.env()
        r1 = self.invoices[0]["invoice_id"]
        o = e.step(self.act("get_record", table="invoices", id=r1))[0]
        self.assertEqual(o["result"]["invoice_id"], r1)
        d1 = self.docs[0]["doc_id"]
        o = e.step(self.act("get_document", doc_id=d1))[0]
        self.assertIsNone(o["error"])
        self.assertIsInstance(o["result"], dict)

    def test_c09_c10_calculator(self):
        e, _, _ = self.env()
        self.assertEqual(e.step(self.act("calculator", expression="0.1+0.2"))[0]["result"], "0.3")
        for bad in ("open('/etc/passwd').read()", "__import__('os').system('id')", "1+x"):
            o = e.step(self.act("calculator", expression=bad))[0]
            self.assertIsNone(o["result"]), self.assertEqual(o["error"]["code"], "calc_error")

    def test_c11_c12_c13_c14_errors_spend_a_step(self):
        e, _, _ = self.env()
        ids = {r["row_id"] for r in self.ledger} | {d["doc_id"] for d in self.docs}
        u = "U-" + "9" * 12
        self.assertNotIn(u, ids)
        steps = []
        for a in (self.act("get_record", table="ledger", id=u), self.act("get_document", doc_id=u), self.act("no_such_action")):
            o = e.step(a)[0]
            self.assertIsNone(o["result"]), self.assertIsInstance(o["error"]["code"], str)
            self.assertNotIn("/", o["error"]["message"])
            steps.append(o["remaining_steps"])
        self.assertEqual(steps, [99, 98, 97])
        o = e.step(self.act("get_record", table="ledger", id=self.ledger[0]["row_id"]))[0]
        self.assertEqual(o["remaining_steps"], 96)
        self.assertEqual(o["result"]["row_id"], self.ledger[0]["row_id"])

    def test_c15_submit_is_final_and_c19_closed_rewards_are_zero(self):
        e, _, _ = self.env()
        e.step(self.act("list_records", table="ledger", cursor=None, limit=5))
        o, r, term, trunc, info = e.step(self.act("submit", findings={"episode_id": self.eid, "findings": []}))
        self.assertEqual((o["result"], r, term, trunc, info), ({"accepted": True}, 0.0, True, False, {}))
        o2, r2, term2, _, _ = e.step(self.act("submit", findings={"episode_id": self.eid, "findings": []}))
        self.assertTrue(term2), self.assertEqual(r2, 0.0), self.assertIsNone(o2["result"])

    def test_c16_submit_as_action_100(self):
        e, _, _ = self.env()
        for _ in range(99):
            e.step(self.act("calculator", expression="1"))
        o, r, term, trunc, _ = e.step(self.act("submit", findings={"episode_id": self.eid, "findings": []}))
        self.assertTrue(term), self.assertFalse(trunc), self.assertEqual(o["result"], {"accepted": True})

    def test_c17_hundred_actions_truncate(self):
        e, _, _ = self.env()
        for i in range(100):
            o, r, term, trunc, _ = e.step(self.act("calculator", expression="1"))
        self.assertTrue(trunc), self.assertFalse(term)
        o, r, term, trunc, _ = e.step(self.act("submit", findings={"episode_id": self.eid, "findings": []}))
        self.assertIsNone(o["result"])

    def test_train_mode_returns_the_terminal_reward(self):
        e, _, _ = self.env(mode="train")
        o, r, term, _, _ = e.step(self.act("submit", findings={"episode_id": self.eid, "findings": []}))
        self.assertTrue(term)
        expected = -1.0 if self.truth["issues"] else 1.0
        self.assertAlmostEqual(r, expected, delta=TOL)


def fixture(base_dir, out_dir, issues):
    shutil.copytree(base_dir, out_dir)
    truth = json.loads(_read(os.path.join(out_dir, "private", "truth.json")))
    truth["issues"] = issues
    _write(os.path.join(out_dir, "private", "truth.json"), json.dumps(truth))
    return out_dir


class TestMatcher(Base):
    """Block 3: one issue A, type T, record R1, 10000 KZT, evidence {D1, D2}, tau = 0."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.R1, cls.R2, cls.R3 = (cls.invoices[i]["invoice_id"] for i in range(3))
        cls.D1, cls.D2, cls.D3 = (cls.ledger[i]["row_id"] for i in range(3))
        cls.A = {"issue_id": "A", "type": "duplicate_invoice", "affected_ids": [cls.R1], "expected_amount_minor": 10000,
                 "currency": "KZT", "acceptable_evidence_sets": [[cls.D1, cls.D2]], "tolerance_minor": 0}
        cls.B = {**cls.A, "issue_id": "B", "affected_ids": [cls.R2]}
        cls.fx_a = fixture(cls.ep, os.path.join(cls.tmp, "A"), [cls.A])
        cls.fx_ab = fixture(cls.ep, os.path.join(cls.tmp, "AB"), [cls.A, cls.B])
        cls.fx_0 = fixture(cls.ep, os.path.join(cls.tmp, "Z"), [])

    def F(self, **kw):
        f = {"type": "duplicate_invoice", "affected_ids": [self.R1], "claimed_amount_minor": 10000, "currency": "KZT",
             "evidence_ids": [self.D1, self.D2], "explanation": "short"}
        f.update(kw)
        return f

    def s(self, d, fs, steps=10):
        return J.score_episode(d, {"episode_id": self.eid, "findings": fs}, steps)

    def check(self, res, tp, fp, fn, ret):
        self.assertEqual((res["tp"], res["fp"], res["fn"]), (tp, fp, fn))
        self.assertAlmostEqual(res["return"], float(ret), delta=TOL)

    def test_01_to_17(self):
        a, ab, z = self.fx_a, self.fx_ab, self.fx_0
        self.check(self.s(a, [self.F()]), 1, 0, 0, 0.98)
        self.check(self.s(a, []), 0, 0, 1, -1)
        r = self.s(z, []); self.check(r, 0, 0, 0, 0.98); self.assertEqual(r["f1"], 1.0)
        self.check(self.s(z, [self.F()]), 0, 1, 0, -1)
        r = self.s(a, [self.F(), self.F()]); self.check(r, 1, 1, 0, Fraction(47, 150))
        self.assertAlmostEqual(r["f1"], 2 / 3, delta=TOL)
        self.check(self.s(a, [self.F(type="date_or_fx")]), 0, 1, 1, -1)
        self.check(self.s(a, [self.F(affected_ids=[self.R3])]), 0, 1, 1, -1)
        self.check(self.s(a, [self.F(claimed_amount_minor=10001)]), 0, 1, 1, -1)
        self.check(self.s(a, [self.F(currency="USD")]), 0, 1, 1, -1)
        self.check(self.s(a, [self.F(evidence_ids=[self.D1])]), 0, 1, 1, -1)
        self.check(self.s(a, [self.F(evidence_ids=[self.D1, "U-NOT-THERE-1"])]), 0, 1, 1, -1)
        recs = [self.R1, self.R2, self.R3, self.invoices[3]["invoice_id"], self.invoices[4]["invoice_id"]]
        flag = [self.F(type=t, affected_ids=[x]) for x in recs
                for t in ("duplicate_invoice", "payment_allocation", "date_or_fx", "period_classification")]
        self.check(self.s(a, flag), 1, 19, 0, Fraction(-871, 1050))
        self.check(self.s(ab, [self.F()]), 1, 0, 1, Fraction(47, 150))
        self.check(self.s(ab, [self.F(), self.F(affected_ids=[self.R3])]), 1, 1, 1, -0.02)
        self.check(self.s(a, [self.F()], 0), 1, 0, 0, 1.0)
        self.check(self.s(a, [self.F()], 50), 1, 0, 0, 0.90)
        self.check(self.s(a, [self.F()], 100), 1, 0, 0, 0.80)

    def test_18_19_20_structure_limits(self):
        for fs in ([self.F()] * 31, [self.F(evidence_ids=[f"E{i}" for i in range(11)])], [self.F(explanation="x" * 1001)]):
            r = self.s(self.fx_a, fs)
            self.assertEqual(r["return"], -1.0)
            self.assertIsNone(r["tp"])

    def test_m01_to_m12(self):
        d1, d2, d3 = self.D1, self.D2, self.D3
        two = fixture(self.ep, os.path.join(self.tmp, "M"), [{**self.A, "affected_ids": [self.R1, self.R2]}])
        G = lambda **kw: self.F(**{"affected_ids": [self.R1, self.R2], **kw})  # noqa: E731
        self.assertEqual(self.s(two, [G(affected_ids=[self.R2, self.R1, self.R1])])["tp"], 1)       # M01
        self.check(self.s(two, [G(affected_ids=[self.R1, self.R2, self.R3])]), 0, 1, 1, -1)          # M02
        self.assertEqual(self.s(two, [G(evidence_ids=[d2, d1, d3])])["tp"], 1)                      # M03
        self.check(self.s(two, [G(evidence_ids=[d1, d2, "U-NOT-THERE-1"])]), 0, 1, 1, -1)            # M04
        self.assertEqual(self.s(two, [G(evidence_ids=[d1] * 10 + [d2])])["return"], -1.0)           # M05
        self.check(self.s(two, [G(currency="kzt")]), 0, 1, 1, -1)                                    # M06
        self.check(self.s(two, [G(currency="KZT ")]), 0, 1, 1, -1)
        self.check(self.s(two, [G(claimed_amount_minor=10001)]), 0, 1, 1, -1)                        # M07
        t1 = fixture(self.ep, os.path.join(self.tmp, "M8"), [{**self.A, "affected_ids": [self.R1, self.R2], "tolerance_minor": 1}])
        self.assertEqual(self.s(t1, [G(claimed_amount_minor=10001)])["tp"], 1)                      # M08
        self.assertEqual(self.s(t1, [G(claimed_amount_minor=10002)])["tp"], 0)
        self.assertEqual(self.s(two, [G(claimed_amount_minor="10000")])["return"], -1.0)            # M09
        self.assertEqual(self.s(two, [G(claimed_amount_minor=True)])["return"], -1.0)
        # M10/M11: F0 fits A and B, F1 fits only A -> a maximum matching, never greedy
        both = fixture(self.ep, os.path.join(self.tmp, "M10"), [
            {**self.A, "acceptable_evidence_sets": [[d1, d2]]},
            {**self.A, "issue_id": "B", "acceptable_evidence_sets": [[d1, d3]], "affected_ids": [self.R1]}])
        f0, f1 = self.F(evidence_ids=[d1, d2, d3]), self.F(evidence_ids=[d1, d2])
        self.check(self.s(both, [f0, f1]), 2, 0, 0, 0.98)
        self.check(self.s(both, [f1, f0]), 2, 0, 0, 0.98)
        r = self.s(self.fx_a, [self.F(), self.F()]); self.check(r, 1, 1, 0, Fraction(47, 150))     # M12


class TestPaired(Base):
    """Block 4: the jury permutes rows and renames ids consistently in a copy (truth and provenance too)."""

    def transformed(self, name, permute, rename, seed=7):
        out = os.path.join(self.tmp, name)
        shutil.copytree(self.ep, out)
        rng = random.Random(seed)
        mapping = {}
        if rename:
            ids = [r["row_id"] for r in self.ledger] + [r["invoice_id"] for r in self.invoices]
            ids += [json.loads(l)["payment_id"] for l in _read(os.path.join(out, "public", "payments.jsonl")).splitlines() if l]
            ids += [d["doc_id"] for d in self.docs]
            mapping = {x: f"Z{i:05d}-{x.split('-')[0]}" for i, x in enumerate(ids)}
            pat = re.compile(r"(?<![\w-])(" + "|".join(re.escape(x) for x in sorted(mapping, key=len, reverse=True)) + r")(?![\w-])")
            for dp, _, fns in os.walk(out):
                for fn in fns:
                    p = os.path.join(dp, fn)
                    _write(p, pat.sub(lambda m: mapping[m.group(1)], _read(p)))
        if permute:
            pub = os.path.join(out, "public")
            for fn in ("ledger.csv", "fx.csv"):
                lines = _read(os.path.join(pub, fn)).splitlines(keepends=True)
                body = lines[1:]
                rng.shuffle(body)
                _write(os.path.join(pub, fn), lines[0] + "".join(body))
            for fn in ("invoices.jsonl", "payments.jsonl", "documents.jsonl"):
                lines = [l for l in _read(os.path.join(pub, fn)).splitlines() if l]
                rng.shuffle(lines)
                _write(os.path.join(pub, fn), "\n".join(lines) + "\n")
        return out, mapping

    def oracle(self, truth, mapping):
        m = lambda x: mapping.get(x, x)  # noqa: E731
        return [{"type": i["type"], "affected_ids": [m(x) for x in i["affected_ids"]],
                 "claimed_amount_minor": i["expected_amount_minor"], "currency": i["currency"],
                 "evidence_ids": [m(x) for x in i["acceptable_evidence_sets"][0]], "explanation": ""} for i in truth["issues"]]

    def test_pairs_keep_metrics_and_reward(self):
        base = J.score_episode(self.ep, {"episode_id": self.eid, "findings": self.oracle(self.truth, {})}, 12)
        self.assertEqual(base["fn"], 0)
        for name, perm, ren in (("P-order", True, False), ("P-ids", False, True), ("P-both", True, True)):
            d, mapping = self.transformed(name, perm, ren)
            got = J.score_episode(d, {"episode_id": self.eid, "findings": self.oracle(self.truth, mapping)}, 12)
            self.assertEqual(got, base, name)
            e = J.make_env()
            self.addCleanup(e.close)
            obs, _ = e.reset(1, {"mode": "closed", "episode_dir": d})
            self.assertEqual(obs["manifest"]["episode_id"], self.eid, name)

    def test_reset_replays_exactly(self):
        def run():
            e, obs, _ = self.env()
            out = [obs]
            for a in (self.act("list_records", table="invoices", cursor=None, limit=50), self.act("calculator", expression="2*3"),
                      self.act("get_record", table="ledger", id=self.ledger[0]["row_id"])):
                out.append(e.step(a))
            return json.dumps(out, sort_keys=True)
        self.assertEqual(run(), run())


if __name__ == "__main__":
    unittest.main()
