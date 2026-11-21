"""A local LLM (Ollama) as an in-process agent: policies/llm.py and the runs API (policy "llm").

No real model and no network: a fake Ollama on a free 127.0.0.1 port serves /api/tags and scripted /api/chat
replies; AUDITGYM_OLLAMA_URL points the policy at it (honoured only for 127.0.0.1 / localhost).
"""
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from auditgym import harness
from auditgym.env.adapters import make_http_server
from auditgym.policies import llm

DEAD_URL = "http://127.0.0.1:9"  # discard port: the connection is refused at once

LIST = json.dumps({"tool": "list_records", "args": {"table": "invoices", "cursor": None, "limit": 50}})
SUBMIT_LIST = json.dumps({"tool": "submit", "args": {"findings": []}})  # a bare list, no episode id: the policy fixes it
SCRIPTS = {
    "fake-good:1b": [LIST, SUBMIT_LIST],
    "fake-garbage:1b": ["this is not JSON, sorry"],
    "fake-prose:1b": [json.dumps({"answer": "the books look fine"})],
    "fake-slow:1b": ["SLEEP"],
    "solo:latest": [SUBMIT_LIST],
}


class FakeOllama(BaseHTTPRequestHandler):
    chats = []
    lock = threading.Lock()

    def log_message(self, *args):
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except OSError:  # the policy gave up waiting (the timeout test): nobody to answer
            pass

    def do_GET(self):
        if self.path == "/api/tags":
            self._send({"models": [{"name": n, "model": n, "size": 1000 + i} for i, n in enumerate(SCRIPTS)]
                       + [{"name": "fake-500:1b", "model": "fake-500:1b"}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path != "/api/chat":
            return self._send({"error": "not found"}, 404)
        with FakeOllama.lock:
            FakeOllama.chats.append(body)
            model = body.get("model")
            # The n-th call in the current episode: count the assistant turns the policy sent back.
            n = sum(1 for m in body.get("messages", []) if m.get("role") == "assistant")
        if model == "fake-500:1b":
            return self._send({"error": "model crashed"}, 500)
        script = SCRIPTS.get(model) or []
        content = script[min(n, len(script) - 1)] if script else ""
        if content == "SLEEP":
            time.sleep(1.5)
            content = SUBMIT_LIST
        self._send({"model": model, "message": {"role": "assistant", "content": content}, "done": True})


def first_obs(eid="ep-1", steps=100):
    return {"ok": True, "remaining_steps": steps,
            "result": {"task": "audit", "tools": {}, "policy": {}, "finding_schema": {}, "finding_rules": [],
                       "manifest": {"episode_id": eid}}}


class LlmBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=cls.fake.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.fake.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.fake.shutdown()
        cls.fake.server_close()

    def setUp(self):
        FakeOllama.chats = []
        self.envp = mock.patch.dict(os.environ, {"AUDITGYM_OLLAMA_URL": self.url})
        self.envp.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.jobs = harness.Jobs(base=self.tmp.name, curve=os.path.join(self.tmp.name, "none.json"))
        self.srv, self.env = make_http_server(0, "open", ui=True, api=self.jobs)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        if self.jobs.thread:
            self.jobs.thread.join(60)
        self.srv.shutdown()
        self.srv.server_close()
        self.env.close()
        self.tmp.cleanup()
        self.envp.stop()

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=json.dumps(body) if body is not None else None,
                  headers={"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"})
        r = c.getresponse()
        data = json.loads(r.read() or b"{}")
        c.close()
        return r.status, data

    def finish(self, rid):
        deadline = time.time() + 60
        while time.time() < deadline:
            code, d = self.req("GET", "/api/runs/" + rid)
            if code == 200 and d["run"]["status"] != "running":
                return d["run"]
            time.sleep(0.1)
        self.fail("run did not finish")


class RunsWithAnLlm(LlmBase):
    def test_models_route_lists_installed_models(self):
        code, d = self.req("GET", "/api/llm/models")
        self.assertEqual(code, 200)
        self.assertEqual(d, {"ok": True, "available": True, "models": list(SCRIPTS) + ["fake-500:1b"]})

    def test_a_run_with_the_fake_model_is_scored_in_closed_mode(self):
        code, res = self.req("POST", "/api/runs", {"policy": "llm", "llm_model": "fake-good:1b", "split": "dev", "limit": 1})
        self.assertEqual(code, 200, res)
        run = self.finish(res["run"])
        self.assertEqual(run["status"], "done", run)
        self.assertEqual(run["mode"], "closed")
        self.assertEqual(run["agent"], "llm-fake-good-1b")
        self.assertEqual(run["llm_model"], "fake-good:1b")
        self.assertTrue(run["id"].startswith("llm-fake-good-1b-dev-"))
        self.assertEqual(run["summary"]["episodes_done"], 1)
        self.assertEqual(run["episodes"][0]["score"]["status"], "scored")  # the bare list got the episode id
        code, st = self.req("GET", f"/api/runs/{run['id']}/steps?episode=0")
        self.assertEqual([s["tool"] for s in st["steps"]], ["list_records", "submit"])
        self.assertEqual(len(FakeOllama.chats), 2)
        body = FakeOllama.chats[0]
        self.assertEqual(body["model"], "fake-good:1b")
        self.assertEqual(body["format"], "json")
        self.assertFalse(body["stream"])
        self.assertLessEqual(body["options"]["temperature"], 0.3)
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertIn(run["episodes"][0]["episode_id"], body["messages"][1]["content"])
        # The second call carries the first answer and the observation it produced.
        roles = [m["role"] for m in FakeOllama.chats[1]["messages"]]
        self.assertEqual(roles, ["system", "user", "assistant", "user"])
        self.assertIn("Observation:", FakeOllama.chats[1]["messages"][-1]["content"])

    def test_default_limit_is_three_and_malformed_output_does_not_crash(self):
        for model in ("fake-garbage:1b", "fake-prose:1b", "fake-500:1b"):
            code, res = self.req("POST", "/api/runs", {"policy": "llm", "llm_model": model, "split": "dev"})
            self.assertEqual(code, 200, res)
            run = self.finish(res["run"])
            self.assertEqual(run["status"], "done", (model, run))
            self.assertEqual(len(run["episodes"]), 3)
            self.assertEqual(run["summary"]["episodes_done"], 3)
            for e in run["episodes"]:
                self.assertEqual(e["steps"], 1)  # one failed answer: an empty, valid submission at once
                self.assertEqual(e["score"]["status"], "scored")
                self.assertEqual(e["score"]["fp"], 0)
            self.jobs.thread.join(30)

    def test_implicit_latest_tag(self):
        code, res = self.req("POST", "/api/runs", {"policy": "llm", "llm_model": "solo", "split": "dev", "limit": 1})
        self.assertEqual(code, 200, res)
        run = self.finish(res["run"])
        self.assertEqual(run["llm_model"], "solo:latest")
        self.assertEqual(run["agent"], "llm-solo-latest")

    def test_models_not_installed_or_badly_named_are_refused(self):
        for name in ("qwen2.5:7b", "fake-good", "../etc/passwd", "a b", "x;rm -rf /", "", None, 7, ["fake-good:1b"],
                     "http://evil.example/x", "a" * 200, "fake-good:1b\n"):
            code, res = self.req("POST", "/api/runs", {"policy": "llm", "llm_model": name, "split": "dev", "limit": 1})
            self.assertEqual(code, 400, (name, res))
            self.assertEqual(res["error"]["code"], "bad_arguments")
        for extra in ({"limit": 0}, {"limit": 21}, {"limit": True}, {"split": "private"}, {"pace": 5}):
            body = {"policy": "llm", "llm_model": "fake-good:1b", "split": "dev", **extra}
            code, res = self.req("POST", "/api/runs", body)
            self.assertEqual(code, 400, (extra, res))
        self.assertIsNone(self.jobs.thread)

    def test_ollama_down_is_409(self):
        with mock.patch.dict(os.environ, {"AUDITGYM_OLLAMA_URL": DEAD_URL}):
            code, res = self.req("POST", "/api/runs", {"policy": "llm", "llm_model": "fake-good:1b", "split": "dev"})
            self.assertEqual(code, 409, res)
            self.assertEqual(res["error"]["code"], "ollama_unavailable")
            self.assertEqual(self.req("GET", "/api/llm/models"), (200, {"ok": True, "available": False, "models": []}))
        self.assertIsNone(self.jobs.thread)


class PolicyUnits(LlmBase):
    def test_request_timeout_ends_the_episode_with_an_empty_submission(self):
        p = llm.OllamaPolicy("fake-slow:1b", timeout=0.3)
        p.reset(first_obs("ep-9"))
        t0 = time.monotonic()
        a = p.act(p.first)
        self.assertLess(time.monotonic() - t0, 1.4)
        self.assertEqual(a, {"tool": "submit", "args": {"findings": {"episode_id": "ep-9", "findings": []}}})
        self.assertIn("timed out", p.last_error or "")

    def test_never_past_the_episode_time_limit_or_the_step_budget(self):
        p = llm.OllamaPolicy("fake-good:1b", episode_seconds=2.0)  # less than the safety margin: no call at all
        p.reset(first_obs("ep-2"))
        self.assertEqual(p.act(p.first)["args"]["findings"], {"episode_id": "ep-2", "findings": []})
        p = llm.OllamaPolicy("fake-good:1b")
        p.reset(first_obs("ep-3", steps=2))
        self.assertEqual(p.act(p.first)["tool"], "submit")
        self.assertEqual(FakeOllama.chats, [])

    def test_submit_gets_the_right_episode_id(self):
        a = llm.fix_submit({"tool": "submit", "args": {"findings": {"episode_id": "wrong", "findings": []}}}, "ep-1")
        self.assertEqual(a["args"]["findings"]["episode_id"], "ep-1")
        self.assertEqual(llm.fix_submit({"tool": "submit", "args": {"findings": [1]}}, "e")["args"]["findings"],
                         {"episode_id": "e", "findings": [1]})
        self.assertEqual(llm.fix_submit({"tool": "submit", "args": "x"}, "e"), {"tool": "submit", "args": {}})

    def test_base_url_override_only_on_this_machine(self):
        for bad in ("http://example.com:11434", "https://127.0.0.1:11434", "http://127.0.0.1.evil.example:80",
                    "http://user:pw@127.0.0.1:1", "http://127.0.0.1:1/x?y", "file:///etc/passwd", "http://[::1]:1",
                    "http://127.0.0.1:99999"):
            with mock.patch.dict(os.environ, {"AUDITGYM_OLLAMA_URL": bad}):
                self.assertEqual(llm.ollama_url(), llm.DEFAULT_URL, bad)
        for good, want in (("http://localhost:5", "http://localhost:5"), ("http://127.0.0.1:8/", "http://127.0.0.1:8")):
            with mock.patch.dict(os.environ, {"AUDITGYM_OLLAMA_URL": good}):
                self.assertEqual(llm.ollama_url(), want)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AUDITGYM_OLLAMA_URL", None)
            self.assertEqual(llm.ollama_url(), "http://127.0.0.1:11434")

    def test_names_and_agent_names(self):
        for ok in ("qwen2.5:1.5b", "llama3.2", "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF:Q4_K_M"):
            self.assertTrue(llm.valid_model_name(ok), ok)
        self.assertEqual(llm.agent_name("qwen2.5:1.5b"), "llm-qwen2.5-1.5b")
        self.assertEqual(harness.new_run_id(llm.agent_name("qwen2.5:1.5b"), "dev")[:21], "llm-qwen2-5-1-5b-dev-")


if __name__ == "__main__":
    unittest.main()
