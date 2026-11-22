"""LLM + audit tools (policies/llm_assist.py) against a scripted fake Ollama: code reads and proposes, the model judges.

No real model and no network: the fake judge keeps every candidate, none, or answers garbage.
"""
import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from auditgym import harness  # noqa: E402
from auditgym.policies.llm_assist import OllamaAssistedPolicy  # noqa: E402


class FakeJudge(BaseHTTPRequestHandler):
    prompts = []

    def log_message(self, *args):
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"models": [{"name": n} for n in ("judge-all:1b", "judge-none:1b", "judge-garbage:1b")]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = body["messages"][-1]["content"]
        FakeJudge.prompts.append(user)
        ids = sorted(set(re.findall(r'"id": "(c\d+)"', user)))
        reply = {"judge-all:1b": json.dumps({i: "keep" for i in ids}), "judge-none:1b": json.dumps({i: "drop" for i in ids})}.get(body["model"], "no JSON here")
        self._send({"message": {"role": "assistant", "content": reply}, "done": True})


class AssistedRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeJudge)
        threading.Thread(target=cls.fake.serve_forever, daemon=True).start()
        cls.env = mock.patch.dict(os.environ, {"AUDITGYM_OLLAMA_URL": f"http://127.0.0.1:{cls.fake.server_address[1]}"})
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.fake.shutdown()
        cls.fake.server_close()

    def run_model(self, model, limit=3):
        base = tempfile.mkdtemp()
        jobs = harness.Jobs(base=base)
        st, res = jobs.post("/api/runs", {"policy": "llm", "llm_model": model, "assist": True, "split": "dev", "limit": limit})
        self.assertEqual(st, 200, res)
        for _ in range(600):
            if not jobs.busy():
                break
            time.sleep(0.1)
        return harness.read_run(res["run"], base)

    def test_the_judge_decides_and_only_real_records_are_submitted(self):
        FakeJudge.prompts = []
        r = self.run_model("judge-all:1b")
        self.assertEqual((r["status"], r["mode"], r["llm_assist"]), ("done", "closed", True))
        self.assertTrue(r["agent"].endswith("-assist"))
        self.assertTrue(FakeJudge.prompts, "the model was asked")
        prompt = json.loads(FakeJudge.prompts[0])
        self.assertIn("legitimate_patterns", prompt["company"])
        self.assertTrue(all({"facts", "broad_check", "strict_check", "type", "ids"} <= set(c) for c in prompt["candidates"]))
        self.assertEqual(r["summary"]["not_scored"], 0, "every submission is well formed")
        self.assertGreater(r["summary"]["tp"], 0, "keeping every candidate finds the real errors (and the traps)")

    def test_keeping_nothing_is_silence_and_garbage_is_dropped_not_accepted(self):
        none = self.run_model("judge-none:1b")
        bad = self.run_model("judge-garbage:1b")
        for r in (none, bad):
            self.assertEqual(r["summary"]["tp"], 0)
            self.assertEqual(r["summary"]["fp"], 0, "a failed or empty review never submits unreviewed candidates")

    def test_candidates_mix_real_errors_and_traps(self):
        pol = OllamaAssistedPolicy("judge-all:1b")
        self.assertEqual(pol.clean({"type": "date_or_fx", "affected_ids": ["B", "A"], "claimed_amount_minor": 12.0,
                                    "currency": "USD", "evidence_ids": ["R1"]})["affected_ids"], ["A", "B"])
        with self.assertRaises(ValueError):
            OllamaAssistedPolicy("bad name with spaces")


if __name__ == "__main__":
    unittest.main()
