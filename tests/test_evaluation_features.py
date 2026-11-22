"""Fresh test split, failure analysis, evaluating a trained model, seed groups and report export (harness + learner)."""
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from auditgym import harness, learner  # noqa: E402


def wait(jobs):
    for _ in range(1200):
        if not jobs.busy():
            return
        time.sleep(0.1)
    raise AssertionError("job did not finish")


class TestSplit(unittest.TestCase):
    def test_twenty_fresh_valid_episodes_shaped_like_the_hidden_set(self):
        eps = learner.test_split()
        self.assertEqual(len(eps), 20)
        labels = [e["label"] for e in eps]
        self.assertEqual(sum(lab.startswith("чистая") for lab in labels), 5)
        self.assertEqual(sum(lab.startswith("взаимод") for lab in labels), 5)
        seeds = {e["seed"] for e in eps}
        self.assertEqual(len(seeds), 20)
        self.assertFalse(seeds & learner.forbidden_seeds(), "test seeds never overlap train or dev")
        self.assertEqual([e["seed"] for e in learner.test_split()], [e["seed"] for e in eps], "fixed for everyone")

    def test_never_drawn_by_the_trainer(self):
        test = {e["seed"] for e in learner.test_split()}
        drawn = {s for i in range(40) for s, _ in learner.episode_specs(1, i, 8, "mixed", learner.forbidden_seeds())}
        self.assertFalse(test & drawn)


class Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp()
        cls.jobs = harness.Jobs(base=cls.base)
        st, res = cls.jobs.post("/api/train", {"method": "cem", "iterations": 3, "population": 4, "episodes_per_candidate": 1,
                                                "eval_every": 1, "seeds": [1, 2]})
        assert st == 200 and res["ok"], res
        cls.group = res
        wait(cls.jobs)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_group_runs_each_seed_and_measures_on_test(self):
        runs = [r for r in harness.list_runs(self.base) if r.get("group") == self.group["group"]]
        self.assertEqual(sorted(r["seed"] for r in runs), [1, 2])
        for r in runs:
            full = harness.read_run(r["id"], self.base)
            self.assertEqual(full["test"]["episodes"], 20)
            self.assertIn("by_type", full["test"]["analysis"])
            self.assertGreater(full["test"]["reconcile"]["reward"], 0.9)
            self.assertIsNotNone(r["test_reward"])

    def test_trained_model_is_evaluated_like_any_agent_with_analysis(self):
        st, res = self.jobs.post("/api/runs", {"model": self.group["run"], "split": "dev", "limit": 3})
        self.assertEqual(st, 200, res)
        wait(self.jobs)
        ev = harness.read_run(res["run"], self.base)
        self.assertEqual((ev["status"], ev["model_run"], ev["mode"]), ("done", self.group["run"], "closed"))
        self.assertEqual(ev["analysis"]["episodes"], 3)
        self.assertIsNotNone(harness.read_steps(res["run"], 0, self.base), "the replay exists")
        self.assertEqual(self.jobs.post("/api/runs", {"model": "no-such-run", "split": "dev"})[0], 400)

    def test_export_writes_a_report_in_both_languages(self):
        for lang, word in (("en", "Honest limitations"), ("ru", "Честные ограничения")):
            st, res = self.jobs.post(f"/api/runs/{self.group['run']}/export", {"lang": lang})
            self.assertEqual(st, 200)
            self.assertIn(word, res["markdown"])
            self.assertTrue(os.path.isfile(res["path"]))
        self.assertEqual(self.jobs.post("/api/runs/nope/export", {})[0], 404)

    def test_bad_seed_lists_are_refused(self):
        for seeds in ([1], [1, 1], [1, 2, 3, 4, 5, 6], ["1", 2], [True, 2]):
            self.assertEqual(self.jobs.post("/api/train", {"seeds": seeds})[0], 400, seeds)


class AnalysisOnlyAtTheEnd(unittest.TestCase):
    def test_saved_analysis_has_no_near_miss_reasons_and_appears_after_the_run(self):
        base = tempfile.mkdtemp()
        seen_mid_run = []
        harness.run_split("reconcile", harness.BUILTIN["reconcile"], split="dev", limit=2, run_id="an-test", base=base,
                          on_event=lambda e: seen_mid_run.append("analysis" in (harness.read_run("an-test", base) or {}))
                          if e["type"] == "episode_end" else None)
        r = harness.read_run("an-test", base)
        self.assertFalse(any(seen_mid_run), "no diagnostics on disk while the run is going")
        self.assertIn("analysis", r)
        self.assertNotIn("near_miss", str(r))
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class ExternalAgentScoresStayHidden(unittest.TestCase):
    """Brief §04: in closed mode the reward stays with the evaluator until the run ends. An external program runs on
    the same machine, so run.json must not show its scores while the run is going."""

    def test_no_scores_on_disk_until_the_end(self):
        base = tempfile.mkdtemp()
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cmd = f'"{sys.executable}" "{os.path.join(root, "examples", "random_agent.py")}"'
        seen = []

        def on_event(e):
            if e["type"] == "episode_end":
                r = harness.read_run("ext-hidden", base)
                seen.append(any("score" in ep for ep in r["episodes"]) or bool(r["summary"].get("episodes_done")))
        harness.run_split("ext", harness.make_agent(cmd=cmd), split="dev", limit=2, run_id="ext-hidden", base=base, on_event=on_event)
        r = harness.read_run("ext-hidden", base)
        self.assertEqual(seen, [False, False], "no score or summary on disk during the run")
        self.assertTrue(all("score" in ep for ep in r["episodes"]))
        self.assertEqual(r["summary"]["episodes_done"], 2)
        self.assertNotIn("scores_hidden_until_end", r)
        shutil.rmtree(base, ignore_errors=True)


class CurrencyExponents(unittest.TestCase):
    """Brief §03: money is integer minor units with the currency's exponent; the manifest states every exponent."""

    def test_manifest_lists_the_exponent_of_every_currency_in_the_records(self):
        from auditgym.gen.build import generate
        from auditgym.money import exponent
        for split in ("train", "dev"):
            for e in harness.load_split(split):
                pub = generate(e["seed"], e["config"])["public"]
                used = {pub["manifest"]["base_currency"]}
                for t in ("ledger", "invoices", "payments"):
                    used |= {r["currency"] for r in pub["tables"][t]}
                for r in pub["tables"]["fx"]:
                    used |= {r["source_currency"], r["target_currency"]}
                ce = pub["manifest"]["currency_exponents"]
                self.assertEqual(set(ce), used, e["label"])
                self.assertTrue(all(ce[c] == exponent(c) for c in ce))


class CliVerifyArguments(unittest.TestCase):
    """The Docker image runs `auditgym.cli verify --out ... --trajectories ...`: every argument reaches the verifier."""

    def test_verify_options_are_passed_through(self):
        from auditgym import cli, verify
        seen = []
        real = verify.main
        verify.main = lambda argv=None: seen.append(argv) or 0
        try:
            self.assertEqual(cli.main(["verify", "--out", "/work/report.json", "--trajectories", "/work/t.jsonl"]), 0)
        finally:
            verify.main = real
        self.assertEqual(seen, [["--out", "/work/report.json", "--trajectories", "/work/t.jsonl"]])


class DevBaselines(unittest.TestCase):
    def test_training_charts_compare_with_the_reconciler_on_the_same_dev_split(self):
        st, res = harness.Jobs(base=tempfile.mkdtemp()).get("/api/baselines", {})
        self.assertEqual((st, res["split"]), (200, "dev"))
        dev = learner.evaluate_dev(learner.ReconcilePolicy)
        self.assertEqual(res["baselines"]["reconcile"], dev["reward"], "the same number the dev curve is measured with")
        self.assertEqual(res["baselines"]["random"], -1.0)


class NoiseRewardControl(unittest.TestCase):
    """Brief §01: no improvement claim without a controlled comparison. The same search on the same episodes, with
    seeded noise in place of the reward, must not learn; the real reward must."""

    def test_learning_comes_from_the_reward(self):
        cfg = {"iterations": 8, "population": 8, "episodes_per_candidate": 2, "eval_every": 2, "seed": 1}
        base = tempfile.mkdtemp()
        try:
            real = learner.train(cfg, run_id="real", base=base)
            ctrl = learner.train(cfg, run_id="ctrl", base=base, control="noise")
        finally:
            shutil.rmtree(base, ignore_errors=True)
        self.assertEqual(ctrl["control"], "noise_reward")
        self.assertNotIn("control", real)
        self.assertGreaterEqual(real["summary"]["dev_best"] - ctrl["summary"]["dev_best"], 0.3)
        self.assertGreaterEqual(real["test"]["auditor"]["reward"] - ctrl["test"]["auditor"]["reward"], 0.3)
        with self.assertRaises(ValueError):
            learner.train(cfg, base=tempfile.mkdtemp(), control="shuffle")


class InstalledAppPaths(unittest.TestCase):
    """The desktop app has no repository around it: training and the baselines must read the Jobs' own configs."""

    def test_training_uses_the_configs_it_was_given(self):
        cfg = tempfile.mkdtemp()
        for split in ("train", "dev"):
            shutil.copy(os.path.join(harness.ROOT, "configs", f"{split}.json"), cfg)
        root, harness.ROOT = harness.ROOT, os.path.join(cfg, "no-repository-here")
        base = tempfile.mkdtemp()
        try:
            with mock.patch.dict(os.environ, {"AUDITGYM_CONFIGS": ""}):
                jobs = harness.Jobs(base=base, configs=cfg)
                st, res = jobs.post("/api/train", {"iterations": 2, "population": 4, "episodes_per_candidate": 1})
                self.assertEqual(st, 200, res)
                for _ in range(1200):
                    if not jobs.busy():
                        break
                    time.sleep(0.05)
                run = harness.read_run(res["run"], base)
                self.assertEqual(run["status"], "done", run.get("error"))
                self.assertIn("auditor", run["test"])
                self.assertEqual(jobs.get("/api/baselines", {})[0], 200)
        finally:
            harness.ROOT = root
            harness._DEV_BASE.clear()
            shutil.rmtree(base, ignore_errors=True)
            shutil.rmtree(cfg, ignore_errors=True)


class WindowsFileRace(unittest.TestCase):
    def test_a_run_being_replaced_is_read_after_a_retry_not_reported_missing(self):
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, "r1"))
            harness._write_json(os.path.join(base, "r1", "run.json"), {"id": "r1"})
            real, calls = open, []

            def flaky(path, *a, **k):
                if str(path).endswith("run.json") and len(calls) < 3:
                    calls.append(1)
                    raise PermissionError(13, "being replaced")
                return real(path, *a, **k)
            with mock.patch("builtins.open", flaky):
                self.assertEqual(harness.read_run("r1", base), {"id": "r1"})
            self.assertEqual(len(calls), 3)
        finally:
            shutil.rmtree(base, ignore_errors=True)
