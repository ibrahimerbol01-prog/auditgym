"""Setup assistant (scout): schema, offline behaviour, a fake local Ollama, scaling with the machine. No network."""
import json
import re
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from auditgym import scout as scout_mod
from auditgym.scout import scout

DEAD_URL = "http://127.0.0.1:9"  # discard port: nothing listens, the connection is refused at once
CYRILLIC = re.compile(r"[А-Яа-яЁё]")

TAGS = {"models": [
    {"name": "llama3.2:3b", "model": "llama3.2:3b", "size": 2019393189,
     "details": {"parameter_size": "3.2B", "quantization_level": "Q4_K_M"}},
    {"name": "qwen2.5:1.5b", "model": "qwen2.5:1.5b", "size": 986061892,
     "details": {"parameter_size": "1.5B", "quantization_level": "Q4_K_M"}},
]}
CHAT_TEXT = "Обучение идёт на CPU с умеренной популяцией. Результат проверяется на отложенных эпизодах."


class FakeOllama(BaseHTTPRequestHandler):
    chats = []

    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(TAGS)
        else:
            self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path == "/api/chat":
            FakeOllama.chats.append(body)
            self._send({"model": body.get("model"), "message": {"role": "assistant", "content": CHAT_TEXT}, "done": True})
        else:
            self.send_error(404)


class ScoutTest(unittest.TestCase):
    def check_schema(self, s):
        self.assertEqual(set(s), {"machine", "ollama", "dataset", "recommendation", "explanation"})
        m = s["machine"]
        self.assertEqual(set(m), {"os", "python", "cpu_count", "ram_gb", "gpu"})
        self.assertIsInstance(m["os"], str)
        self.assertIsInstance(m["python"], str)
        self.assertIsInstance(m["gpu"], list)
        self.assertTrue(m["ram_gb"] is None or isinstance(m["ram_gb"], float))
        self.assertEqual(set(s["ollama"]), {"available", "models"})
        d = s["dataset"]
        self.assertEqual(set(d), {"train_configs", "dev_episodes", "presets"})
        self.assertEqual(d["presets"], ["mixed", "simple", "interacting"])
        self.assertEqual(d["dev_episodes"], 10)
        self.assertIsInstance(d["train_configs"], int)
        r = s["recommendation"]
        self.assertEqual(set(r), {"model", "config", "est_seconds", "reasons", "evaluate_llm"})
        self.assertEqual(r["model"], "auditor-cem")
        self.assertEqual(r["config"]["method"], "cem")
        self.assertEqual(r["config"]["dataset"], {"preset": "mixed"})
        for k in ("iterations", "population", "episodes_per_candidate"):
            self.assertIsInstance(r["config"][k], int)
        self.assertIsInstance(r["est_seconds"], int)
        self.assertGreater(r["est_seconds"], 0)
        self.assertTrue(3 <= len(r["reasons"]) <= 5)
        for reason in r["reasons"]:
            self.assertRegex(reason, CYRILLIC)
        json.dumps(s)  # serialisable for GET /api/scout

    def test_offline_full_schema_and_fast(self):
        t0 = time.perf_counter()
        s = scout(ollama_url=DEAD_URL)
        self.assertLess(time.perf_counter() - t0, 2.0)
        self.check_schema(s)
        self.assertEqual(s["ollama"], {"available": False, "models": []})
        self.assertIsNone(s["recommendation"]["evaluate_llm"])
        self.assertIsNone(s["explanation"])
        self.assertIsNone(scout(explain=True, ollama_url=DEAD_URL)["explanation"])

    def test_garbage_url_never_raises(self):
        for url in ("not a url", "", "http://[::1"):
            s = scout(ollama_url=url, timeout=0.2)
            self.assertFalse(s["ollama"]["available"])
            self.check_schema(s)

    def test_fake_ollama_models_and_explanation(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}"
            s = scout(ollama_url=url, timeout=2.0)
            self.check_schema(s)
            self.assertTrue(s["ollama"]["available"])
            self.assertEqual(s["ollama"]["models"], [
                {"name": "llama3.2:3b", "size_gb": 2.0, "params": "3.2B", "quant": "Q4_K_M"},
                {"name": "qwen2.5:1.5b", "size_gb": 1.0, "params": "1.5B", "quant": "Q4_K_M"}])
            self.assertEqual(s["recommendation"]["evaluate_llm"], "qwen2.5:1.5b")
            self.assertTrue(any("qwen2.5:1.5b" in r for r in s["recommendation"]["reasons"]))
            self.assertIsNone(s["explanation"])  # only on request
            FakeOllama.chats.clear()
            s2 = scout(explain=True, ollama_url=url, timeout=2.0)
            self.assertEqual(s2["explanation"], CHAT_TEXT)
            self.assertEqual(len(FakeOllama.chats), 1)
            chat = FakeOllama.chats[0]
            self.assertEqual(chat["model"], "qwen2.5:1.5b")
            self.assertIs(chat["stream"], False)
            self.assertLessEqual(chat["options"]["num_predict"], 200)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_recommendation_scales_with_cpu(self):
        def rec(cpu, ram):
            with mock.patch("os.cpu_count", return_value=cpu), mock.patch.object(scout_mod, "_ram_gb", return_value=ram):
                s = scout(ollama_url=DEAD_URL)
            self.assertEqual(s["machine"]["cpu_count"], cpu)
            return s["recommendation"]

        small, mid, big = rec(2, 4.0), rec(4, 16.0), rec(16, 32.0)
        self.assertEqual({k: small["config"][k] for k in ("population", "episodes_per_candidate", "iterations")},
                         {"population": 12, "episodes_per_candidate": 3, "iterations": 24})
        self.assertEqual({k: big["config"][k] for k in ("population", "episodes_per_candidate", "iterations")},
                         {"population": 24, "episodes_per_candidate": 4, "iterations": 30})
        self.assertLess(small["config"]["population"], mid["config"]["population"])
        self.assertLess(mid["config"]["population"], big["config"]["population"])
        self.assertLess(small["est_seconds"], big["est_seconds"])
        # low RAM alone also shrinks the job; unknown CPU count falls back to the small config
        self.assertEqual(rec(16, 3.5)["config"]["population"], 12)
        self.assertEqual(rec(None, None)["config"]["population"], 12)
        self.assertIn("2 ядра", small["reasons"][1])

    def test_smallest_model_tie_break(self):
        models = [{"name": "b", "size_gb": None, "params": "7B"}, {"name": "a", "size_gb": None, "params": "500M"}]
        self.assertEqual(scout_mod.smallest_model(models), "a")
        self.assertIsNone(scout_mod.smallest_model([]))


if __name__ == "__main__":
    unittest.main()
