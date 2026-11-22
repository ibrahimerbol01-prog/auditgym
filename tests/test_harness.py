"""Local harness (auditgym.harness), the terminal view (run-agent) and the runs API behind /runs.html.

Standard library only. Runs use a temporary runs folder (AUDITGYM_RUNS) and only 1-2 dev episodes.
"""
import http.client
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from auditgym import harness
from auditgym.env.adapters import make_http_server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_WORDS = ("acceptable_evidence", "expected_amount", "issue_id", "truth", "provenance", "near_miss")


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_reconcile_run_is_scored_in_closed_mode_and_saved(self):
        events = []
        run = harness.run_split("reconcile", harness.BUILTIN["reconcile"], "dev", limit=2, base=self.base, on_event=events.append)
        self.assertEqual(run["status"], "done")
        self.assertEqual(run["mode"], "closed")
        self.assertEqual(run["summary"]["episodes_done"], 2)
        self.assertGreater(run["summary"]["reward"], 0.9)
        self.assertEqual([e["type"] for e in events][:2], ["run_start", "episode_start"])
        self.assertEqual(events[-1]["type"], "run_end")
        self.assertEqual(harness.list_runs(self.base)[0]["id"], run["id"])
        steps = harness.read_steps(run["id"], 0, self.base)
        self.assertEqual(steps[-1]["tool"], "submit")
        self.assertEqual(len(steps), run["episodes"][0]["steps"])
        folder = os.path.join(self.base, run["id"])
        for name in ("run.json", "steps.jsonl"):
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                text = fh.read()
            for word in SECRET_WORDS:
                self.assertNotIn(word, text, f"{name} must not contain {word}")

    def test_episode_labels_come_from_the_public_config(self):
        labels = [e["label"] for e in harness.load_split("dev")]
        self.assertEqual(len(labels), 10)
        self.assertIn("чистая", labels)

    def test_harness_never_asks_for_the_reference(self):
        with open(os.path.join(ROOT, "src", "auditgym", "harness.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn('"reference"', src)
        self.assertNotIn("truth.json", src)
        self.assertNotIn("private/", src)

    def test_external_program_agent(self):
        cmd = f'"{sys.executable}" "{os.path.join(ROOT, "examples", "random_agent.py")}"'
        run = harness.run_split("random", harness.make_agent(cmd=cmd), "dev", limit=1, base=self.base)
        self.assertEqual(run["status"], "done")
        self.assertLessEqual(run["episodes"][0]["score"]["reward"], 0.0)

    def test_broken_agent_scores_honestly_and_does_not_crash(self):
        cmd = f'"{sys.executable}" -c "print(123)"'
        run = harness.run_split("broken", harness.make_agent(cmd=cmd), "dev", limit=1, base=self.base)
        self.assertEqual(run["status"], "done")
        self.assertEqual(run["summary"]["not_scored"], 1)
        self.assertEqual(run["summary"]["f1"], 0.0)
        self.assertEqual(run["episodes"][0]["score"]["reward"], -1.0)

    def test_bad_ids_are_rejected(self):
        for bad in ("../x", "..", "a/b", "", "A" * 100):
            self.assertIsNone(harness.read_run(bad, self.base))
            self.assertIsNone(harness.read_steps(bad, 0, self.base))
        with self.assertRaises(ValueError):
            harness.make_agent("oracle")


class RunsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.jobs = harness.Jobs(base=self.tmp.name, curve=os.path.join(self.tmp.name, "none.json"))
        self.srv, self.env = make_http_server(0, "open", ui=True, api=self.jobs)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        if self.jobs.thread:
            self.jobs.thread.join(30)
        self.srv.shutdown()
        self.srv.server_close()
        self.env.close()
        self.tmp.cleanup()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json", **(headers or {})}
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = json.loads(r.read() or b"{}")
        c.close()
        return r.status, data

    def test_start_poll_and_read_a_run(self):
        code, res = self.req("POST", "/api/runs", {"policy": "reconcile", "split": "dev", "limit": 1})
        self.assertEqual(code, 200, res)
        rid = res["run"]
        deadline = time.time() + 30
        while time.time() < deadline:
            code, d = self.req("GET", "/api/runs/" + rid)
            if code == 200 and d["run"]["status"] != "running":
                break
            time.sleep(0.2)
        self.assertEqual(d["run"]["status"], "done")
        code, lst = self.req("GET", "/api/runs")
        self.assertEqual(lst["runs"][0]["id"], rid)
        code, st = self.req("GET", f"/api/runs/{rid}/steps?episode=0")
        self.assertEqual(code, 200)
        self.assertEqual(st["steps"][-1]["tool"], "submit")
        self.assertEqual(self.req("GET", "/api/curve"), (200, {"ok": True, "curve": None}))

    def test_training_settings_are_validated(self):
        for body in ({"method": "lora"}, {"iterations": 10_000}, {"population": 2}, {"episodes_per_candidate": 0},
                     {"dataset": {"preset": "private"}}, {"pace": 9}, {"seed": "1; rm -rf /"}, {"iterations": True}):
            code, res = self.req("POST", "/api/train", body)
            self.assertEqual(code, 400, body)
            self.assertEqual(res["error"]["code"], "bad_arguments")
        self.assertEqual(self.req("POST", "/api/train", {"method": "cem"}, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/train/../../x/curve", {})[0], 404)

    def test_refuses_bad_input_and_foreign_origins(self):
        self.assertEqual(self.req("POST", "/api/runs", {"policy": "oracle"})[0], 400)
        self.assertEqual(self.req("POST", "/api/runs", {"policy": "reconcile", "cmd": "rm -rf /"})[1].get("run", "")[:9], "reconcile")
        self.assertEqual(self.req("POST", "/api/runs", {"policy": "reconcile", "limit": 99})[0], 400)
        self.assertEqual(self.req("POST", "/api/runs", {"policy": "reconcile", "pace": 5})[0], 400)
        self.assertEqual(self.req("POST", "/api/runs", {"policy": "reconcile"}, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.req("GET", "/api/runs", headers={"Host": "evil.example"})[0], 403)
        for path in ("/api/runs/..", "/api/runs/%2e%2e%2fx", "/api/runs/x/steps?episode=../../", "/api/nothing"):
            self.assertEqual(self.req("GET", path)[0], 404, path)


class RunAgentCliTests(unittest.TestCase):
    def test_plain_terminal_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "AUDITGYM_RUNS": tmp, "PYTHONPATH": os.path.join(ROOT, "src"), "PYTHONIOENCODING": "utf-8"}
            p = subprocess.run([sys.executable, "-m", "auditgym.cli", "run-agent", "--policy", "reconcile", "--limit", "1", "--plain"],
                               capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn("ИТОГ", p.stdout)
            self.assertIn("submit", p.stdout)
            self.assertNotIn("\x1b[", p.stdout)
            self.assertEqual(len(os.listdir(tmp)), 1)
            bad = subprocess.run([sys.executable, "-m", "auditgym.cli", "run-agent", "--limit", "1"], capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()


class InterruptedRunTests(unittest.TestCase):
    """A run whose process is gone (the app closed mid-run) reads as "interrupted" instead of spinning forever."""

    def setUp(self):
        import tempfile
        self.base = tempfile.mkdtemp()

    def make(self, rid, **extra):
        import json
        d = os.path.join(self.base, rid)
        os.makedirs(d)
        with open(os.path.join(d, "run.json"), "w", encoding="utf-8") as fh:
            json.dump({"id": rid, "kind": "training", "status": "running", "status_note": "testing", "started": 1, **extra}, fh)
        return d

    def test_a_dead_process_means_interrupted(self):
        import subprocess, sys
        p = subprocess.Popen([sys.executable, "-c", "pass"])
        p.wait()
        self.make("train-dead", pid=p.pid)
        r = harness.read_run("train-dead", self.base)
        self.assertEqual(r["status"], "interrupted")
        self.assertNotIn("status_note", r)
        self.assertEqual([x["status"] for x in harness.list_runs(self.base)], ["interrupted"])

    def test_a_live_process_keeps_running(self):
        self.make("train-live", pid=os.getpid())
        self.assertEqual(harness.read_run("train-live", self.base)["status"], "running")

    def test_without_a_pid_only_a_stale_run_is_interrupted(self):
        d = self.make("train-old")
        self.assertEqual(harness.read_run("train-old", self.base)["status"], "running")
        old = __import__("time").time() - harness.STALE_SECONDS - 5
        os.utime(os.path.join(d, "run.json"), (old, old))
        self.assertEqual(harness.read_run("train-old", self.base)["status"], "interrupted")

    def test_finished_runs_are_untouched(self):
        self.make("train-done", pid=999999999, **{"status": "done"})
        self.assertEqual(harness.read_run("train-done", self.base)["status"], "done")


class SubprocessAgentCleanupTests(unittest.TestCase):
    """Every episode of an external agent starts a process: close() must close its pipes and reap it, not leave them
    to the garbage collector (open handles on Windows, zombies on POSIX)."""

    def test_close_closes_the_pipes_and_reaps_the_process(self):
        agent = harness.SubprocessAgent(f'"{sys.executable}" -c "import sys; sys.stdin.read()"' if os.name == "nt"
                                        else f"{sys.executable} -c 'import sys; sys.stdin.read()'")
        agent.reset({"ok": True, "result": {"manifest": {"episode_id": "ep_x"}}, "remaining_steps": 100})
        p = agent.proc
        agent.close()
        self.assertIsNone(agent.proc)
        self.assertTrue(p.stdout.closed and p.stderr.closed and p.stdin.closed)
        self.assertIsNotNone(p.returncode)

    def test_close_reaps_an_agent_that_ignores_end_of_input(self):
        agent = harness.SubprocessAgent(f'"{sys.executable}" -c "import time; time.sleep(30)"' if os.name == "nt"
                                        else f"{sys.executable} -c 'import time; time.sleep(30)'")
        agent.reset({"ok": True, "result": {"manifest": {"episode_id": "ep_x"}}, "remaining_steps": 100})
        p = agent.proc
        agent.close()                    # waits 2 s, kills, then reaps
        self.assertIsNotNone(p.returncode)
        self.assertTrue(p.stdout.closed and p.stderr.closed)
