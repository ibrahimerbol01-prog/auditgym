"""Preloaded models (models/, src/auditgym/models.py): the catalogue matches its files, installs are checked, and an
installed model is an ordinary training the app can evaluate. No network: the catalogue is read from the checkout."""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from auditgym import cli, harness, learner, models  # noqa: E402

MODELS = os.path.join(ROOT, "models") + os.sep


class Catalogue(unittest.TestCase):
    def test_every_auditor_file_matches_the_catalogue(self):
        cat = models.catalogue(MODELS)
        auditors = [m for m in cat if m["kind"] == "auditor"]
        self.assertGreaterEqual(len(auditors), 3)
        listed = {m["file"] for m in auditors}
        on_disk = {f for f in os.listdir(MODELS) if f.endswith(".json") and f != "index.json"}
        self.assertEqual(listed, on_disk, "every model file is listed, and every listed file exists")
        for m in auditors:
            with open(os.path.join(MODELS, m["file"]), "rb") as fh:
                data = fh.read()
            self.assertEqual(hashlib.sha256(data).hexdigest(), m["sha256"], m["name"])
            run = models._valid_run(json.loads(data), m["name"])
            self.assertEqual(run["test"]["auditor"]["reward"], m["test_reward"], "the catalogue states the measured result")
            self.assertEqual(run["env_version"], learner.ENV_VERSION, "trained on this version of the environment")
        for m in cat:
            if m["kind"] == "ollama":
                from auditgym.policies.llm import valid_model_name
                self.assertTrue(valid_model_name(m["ollama"]))

    def test_the_recommended_model_is_actually_good_and_the_control_is_not(self):
        by = {m["name"]: m for m in models.catalogue(MODELS)}
        self.assertGreater(by["auditor-cem"]["test_reward"], 0.9)
        self.assertLess(by["auditor-noise-control"]["test_reward"], 0.5)


class Install(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.src = tempfile.mkdtemp() + os.sep
        for f in os.listdir(MODELS):
            shutil.copy(os.path.join(MODELS, f), self.src)
        self.cat = {m["name"]: m for m in models.catalogue(self.src)}

    def tearDown(self):
        shutil.rmtree(self.base, ignore_errors=True)
        shutil.rmtree(self.src, ignore_errors=True)

    def test_an_installed_model_is_listed_and_can_be_evaluated(self):
        self.assertTrue(models.install(self.cat["auditor-cem"], base=self.base, src=self.src, say=lambda s: None))
        row = next(r for r in harness.list_runs(self.base) if r["id"] == "preloaded-auditor-cem")
        self.assertEqual((row["kind"], row["status"]), ("training", "done"))
        self.assertTrue(row["preloaded"])
        jobs = harness.Jobs(base=self.base)
        st, res = jobs.post("/api/runs", {"model": "preloaded-auditor-cem", "split": "dev", "limit": 2})
        self.assertEqual(st, 200, res)
        for _ in range(600):
            if not jobs.busy():
                break
            time.sleep(0.05)
        run = harness.read_run(res["run"], self.base)
        self.assertEqual(run["status"], "done")
        self.assertGreater(run["summary"]["reward"], 0.5)

    def test_a_tampered_or_mislabelled_file_is_refused(self):
        path = os.path.join(self.src, "auditor-cem.json")
        with open(path, "rb") as fh:
            good = fh.read()
        with open(path, "wb") as fh:
            fh.write(good.replace(b'"status": "done"', b'"status": "done" '))
        with self.assertRaisesRegex(models.ModelError, "checksum"):
            models.install(self.cat["auditor-cem"], base=self.base, src=self.src, say=lambda s: None)
        run = json.loads(good)
        run["best"]["theta"] = run["best"]["theta"][:5]
        with self.assertRaises(models.ModelError):
            models._valid_run(run, "auditor-cem")
        with self.assertRaises(models.ModelError):
            models._valid_run(dict(json.loads(good), id="../escape"), "auditor-cem")
        with self.assertRaises(models.ModelError):
            models._fetch("../index.json", self.src)
        self.assertFalse(os.listdir(self.base), "nothing was written")

    def test_ollama_models_are_skipped_without_ollama(self):
        said = []
        with mock.patch("shutil.which", return_value=None):
            self.assertFalse(models.install(self.cat["qwen2.5-0.5b"], base=self.base, src=self.src, say=said.append))
        self.assertIn("ollama pull qwen2.5:0.5b", said[0])


class Choices(unittest.TestCase):
    def test_answers(self):
        cat = models.catalogue(MODELS)
        names = lambda xs: [m["name"] for m in xs]  # noqa: E731
        self.assertEqual(len(models.choose("a", cat)), len(cat))
        self.assertTrue(all(m["kind"] == "auditor" for m in models.choose("s", cat)))
        self.assertEqual(names(models.choose("1, 3", cat)), [cat[0]["name"], cat[2]["name"]])
        self.assertEqual(models.choose("", cat), [])
        self.assertEqual(models.choose("99 x", cat), [])

    def test_cli_list_and_ask(self):
        base = tempfile.mkdtemp()
        try:
            with mock.patch.dict(os.environ, {"AUDITGYM_MODELS_URL": MODELS, "AUDITGYM_RUNS": base}):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(cli.main(["models"]), 0)
                self.assertIn("General auditor", out.getvalue())
                with mock.patch("builtins.input", return_value="1"), redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(["models", "--ask"]), 0)
                self.assertTrue(os.path.isfile(os.path.join(base, "preloaded-auditor-cem", "run.json")))
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(["models", "install", "nope"]), 2)
            with mock.patch.dict(os.environ, {"AUDITGYM_MODELS_URL": os.path.join(base, "missing") + os.sep}), \
                    redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertEqual(cli.main(["models", "--ask"]), 0, "an unreachable catalogue never fails an install")
        finally:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
