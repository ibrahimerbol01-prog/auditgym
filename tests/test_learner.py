"""Trainer (T10): run.json contract, closed-mode dev evaluation, determinism, seed hygiene, careful theta."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest

from auditgym import harness, learner
from auditgym.gen.build import generate
from auditgym.policies.rules import find_issues

TINY = {"iterations": 3, "population": 4, "episodes_per_candidate": 1, "eval_every": 1, "seed": 3}
STRIP = ("seconds", "eps_per_sec", "cpu_seconds")


def _points(run):
    return [{k: v for k, v in p.items() if k not in STRIP} for p in run["points"]]


class TestLearner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp()
        cls.events = []
        cls.trained = learner.train(dict(TINY), run_id="t-learner-a", base=cls.base, on_event=cls.events.append)

    def test_run_json_schema(self):
        with open(os.path.join(self.base, "t-learner-a", "run.json"), encoding="utf-8") as fh:
            r = json.load(fh)
        for k in ("id", "kind", "model", "method", "status", "config", "env_version", "started", "finished",
                  "iterations", "at", "points", "best", "summary"):
            self.assertIn(k, r)
        self.assertEqual((r["kind"], r["model"], r["method"], r["status"]), ("training", "auditor-cem", "cem", "done"))
        self.assertEqual((r["iterations"], r["at"], len(r["points"])), (3, 3, 3))
        for p in r["points"]:
            for k in ("i", "train_mean", "train_best", "train_elite", "sigma", "episodes", "seconds", "eps_per_sec", "dev"):
                self.assertIn(k, p)
            self.assertEqual(p["episodes"], 4)
        self.assertEqual(len(r["best"]["theta"]), learner.N_PARAMS)
        for k in ("dev_start", "dev_best", "dev_last", "episodes", "seconds"):
            self.assertIn(k, r["summary"])
        self.assertEqual([e["type"] for e in self.events], ["iteration"] * 3 + ["run_end"])

    def test_switch_on_variants_turn_a_whole_check_on(self):
        """On a plateau the trainer tries the champion with one check that cannot work turned fully on. A check works
        only with all its settings on: the payment check without the payments table finds nothing (seeds 4 and 14)."""
        on = list(learner.CAREFUL_THETA)
        self.assertEqual(learner.switch_on_variants(on), [], "every check already works: nothing to try")
        champ = list(on)
        champ[learner._IDX["read_payments"]] = -3.0              # the check is on, but it never reads the payments
        vs = learner.switch_on_variants(champ)
        self.assertEqual(len(vs), 2)                              # the mode setting both ways
        for v in vs:
            for n in ("read_payments", "pages_payments", "check_payment"):
                self.assertGreater(v[learner._IDX[n]], 0, n)
            for n in learner.PARAM_NAMES:                         # nothing outside the payment group changes
                if n not in ("read_payments", "pages_payments", "read_invoices", "read_ledger", "pages_ledger",
                             "check_payment", "payment_strict"):
                    self.assertEqual(v[learner._IDX[n]], champ[learner._IDX[n]], n)
        self.assertEqual(sorted(v[learner._IDX["payment_strict"]] > 0 for v in vs), [False, True])

    def test_cem_keeps_the_mean_of_theta_bounded(self):
        """Unbounded, the CEM mean drifted to +-10: every candidate then behaved alike and the search was stuck (seed 5
        of the Standard size ended with duplicates only). The bound keeps every setting able to flip."""
        for p in self.trained["points"]:
            self.assertTrue(all(abs(x) <= learner.MU_BOUND + 1e-9 for x in p["mu"]), p["mu"])

    def test_live_view_is_the_real_search(self):
        """The "model at work" panel shows the search itself: every candidate's score, the elite the update used,
        the mean of theta after the update, and a replay of the best candidate scored by the evaluator."""
        r, cfg = self.trained, learner.normalize_config(TINY)
        for p in r["points"]:
            self.assertEqual(len(p["scores"]), cfg["population"])
            self.assertEqual(len(p["mu"]), learner.N_PARAMS)
            self.assertEqual(len(p["elite"]), max(1, round(cfg["population"] * cfg["elite_frac"])))
            self.assertAlmostEqual(max(p["scores"]), p["train_best"], places=3)
            self.assertAlmostEqual(sum(p["scores"]) / len(p["scores"]), p["train_mean"], places=3)
            self.assertGreaterEqual(p["cpu_seconds"], 0)
        L = r["live"]
        self.assertEqual(L["i"], len(r["points"]) - 1)
        self.assertNotIn("error", L)
        self.assertIsInstance(L["seed"], str)          # 64-bit seeds do not survive JSON numbers in a browser
        for k in ("candidate", "episode_id", "steps", "reward", "pages", "rows", "issues", "clean", "tp", "fp", "fn", "findings"):
            self.assertIn(k, L)
        self.assertEqual(set(L["pages"]), set(learner.TABLE_ORDER))
        self.assertEqual(sum(1 for f in L["findings"] if f["matched"]), L["tp"])
        self.assertEqual(sum(1 for f in L["findings"] if not f["matched"]), L["fp"])
        self.assertEqual(L["tp"] + L["fn"], L["issues"])
        self.assertEqual(r["pid"], os.getpid())

    def test_live_audit_replays_the_scored_episode(self):
        """The replay is the same episode the trainer scored: the careful theta gets the reward run_episode gives it."""
        from auditgym.env.env import AuditEnv
        from auditgym.policies.baselines import run_episode
        spec = learner.episode_specs(5, 0, 1, "mixed", learner.forbidden_seeds())[0]
        env = AuditEnv(mode="open", service=learner._Service(), run_id="t-live")
        want = run_episode(env, learner.AuditorPolicy(learner.CAREFUL_THETA), seed=spec[0], config=spec[1])["return"]
        got = learner.live_audit(env, learner.CAREFUL_THETA, spec, 0)
        env.close()
        self.assertAlmostEqual(got["reward"], round(want, 4), places=4)
        self.assertEqual(got["fp"], 0)
        self.assertTrue(all(f["matched"] for f in got["findings"]))

    def test_live_audit_of_a_clean_company(self):
        """A clean company ignores the error counts of its config: the live view must say 0 issues, as the evaluator does."""
        from auditgym.env.env import AuditEnv
        specs = [sp for i in range(40) for sp in learner.episode_specs(9, i, 4, "mixed", learner.forbidden_seeds())]
        spec = next(sp for sp in specs if sp[1].get("clean"))
        env = AuditEnv(mode="open", service=learner._Service(), run_id="t-live-clean")
        got = learner.live_audit(env, learner.CAREFUL_THETA, spec, 0)
        env.close()
        self.assertEqual((got["issues"], got["clean"], got["tp"], got["fn"], got["findings"]), (0, True, 0, 0, []))
        self.assertGreater(got["reward"], 0.9)

    def test_dev_points_and_closed_mode(self):
        pts = self.trained["points"]
        self.assertIsNotNone(pts[0]["dev"])
        self.assertIsNotNone(pts[-1]["dev"])
        for k in ("reward", "f1", "precision", "recall", "fp", "steps"):
            self.assertIn(k, pts[0]["dev"])
        self.assertEqual(pts[0]["dev"]["episodes"], 10)
        # The dev evaluator plays in closed mode: every step reward is 0, the submit answer carries no report,
        # and the score still comes back (through finalize).
        orig = learner.AuditEnv
        modes, rewards, finals = [], [], []

        class Env(orig):
            def __init__(self, *a, **kw):
                modes.append(kw.get("mode"))
                super().__init__(*a, **kw)

            def step(self, action):
                out = super().step(action)
                rewards.append(out[1])
                if out[2]:
                    finals.append(out[0])
                return out
        learner.AuditEnv = Env
        try:
            dev = learner.evaluate_dev(lambda: learner.AuditorPolicy(learner.CAREFUL_THETA), limit=2)
        finally:
            learner.AuditEnv = orig
        self.assertEqual(modes, ["closed"])
        self.assertTrue(rewards and all(r == 0.0 for r in rewards))
        self.assertEqual([f["result"] for f in finals], [{"status": "submitted"}] * 2)
        self.assertGreater(dev["reward"], 0.9)

    def test_deterministic(self):
        again = learner.train(dict(TINY), run_id="t-learner-b", base=self.base)
        self.assertEqual(_points(self.trained), _points(again))
        self.assertEqual(self.trained["best"]["theta"], again["best"]["theta"])

    def test_training_seeds_avoid_splits(self):
        forbidden = {e["seed"] for s in ("train", "dev") for e in harness.load_split(s)}
        self.assertTrue(forbidden <= learner.forbidden_seeds())
        for preset in learner.PRESETS:
            for i in range(5):
                for s, cfg in learner.episode_specs(1, i, 8, preset, learner.forbidden_seeds()):
                    self.assertNotIn(s, forbidden)
                    self.assertTrue(0 <= s < 2 ** 63)
                    learner.make_config(cfg)
                    if preset == "simple":
                        self.assertEqual(cfg.get("interactions"), [])
                    if preset == "interacting":
                        self.assertTrue(cfg["interactions"])

    def test_careful_theta(self):
        k = learner.decode(learner.CAREFUL_THETA)
        for seed, cfg in ((7001, {}), (7002, {"interactions": ["A", "B"], "n_invoices": 60})):
            t = generate(seed, cfg)["public"]
            tb, pol = t["tables"], t["policy"]
            self.assertEqual(find_issues(tb["ledger"], tb["invoices"], tb["payments"], tb["fx"], pol, "x"),
                             learner.find_issues_param(tb["ledger"], tb["invoices"], tb["payments"], tb["fx"], pol, k))
        dev = learner.evaluate_dev(lambda: learner.AuditorPolicy(learner.CAREFUL_THETA), limit=3)
        self.assertGreater(dev["reward"], 0.9)

    def test_any_theta_is_valid(self):
        for th in ([0.0] * learner.N_PARAMS, [50.0] * learner.N_PARAMS, [-1e9] * learner.N_PARAMS):
            learner.decode(th)
        with self.assertRaises(ValueError):
            learner.decode([0.0])

    def test_describe(self):
        d = learner.describe(learner.CAREFUL_THETA)
        self.assertEqual([x["key"] for x in d], learner.PARAM_NAMES)
        self.assertEqual(len(learner.PARAM_NAMES), learner.N_PARAMS)
        for x in d:
            self.assertEqual(set(x), {"key", "label", "value", "on"})
            self.assertTrue(x["label"] and isinstance(x["value"], str) and isinstance(x["on"], bool))
        fx = next(x for x in d if x["key"] == "check_fx")
        self.assertEqual((fx["label"], fx["value"]), ("Проверка курсов", "вкл · допуск 2 · местное время"))

    def test_stop_and_bad_config(self):
        ev = threading.Event()
        ev.set()
        r = learner.train(dict(TINY), run_id="t-learner-stop", base=self.base, stop=ev)
        self.assertEqual((r["status"], r["at"]), ("stopped", 0))
        self.assertIsNotNone(r["finished"])
        for bad in ({"method": "x"}, {"iterations": 0}, {"dataset": {"preset": "?"}}, {"nope": 1}):
            with self.assertRaises(ValueError):
                learner.train(bad, run_id="t-learner-bad", base=self.base)

    def test_source_hygiene(self):
        with open(learner.__file__, encoding="utf-8") as fh:
            src = fh.read()
        for word in ("truth", "private/", '"reference"'):
            self.assertNotIn(word, src)


if __name__ == "__main__":
    unittest.main()
