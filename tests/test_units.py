import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

from auditgym.config import ConfigError, make_config
from auditgym.env.calculator import CalcError, evaluate
from auditgym.env.loader import load_episode_dir
from auditgym.eval.scoring import prf1, score, terminal_reward
from auditgym.gen.build import generate
from auditgym.gen.export import write_episode
from auditgym.money import convert
from auditgym.seeding import Rng, derive_seed


class TestMoneyAndSeeds(unittest.TestCase):
    def test_convert_half_even_and_exponents(self):
        self.assertEqual(convert(100, "USD", "KZT", "488.005"), 48800)   # 1.00 USD -> 488.005 -> 488.00 (half even)
        self.assertEqual(convert(1000, "JPY", "USD", "0.0066"), 660)     # JPY exp 0 -> USD exp 2
        self.assertEqual(convert(1000, "KWD", "KZT", "1"), 100)          # KWD exp 3 -> KZT exp 2
        with self.assertRaises(TypeError):
            convert(True, "USD", "KZT", "1")

    def test_seed_stable(self):
        self.assertEqual(derive_seed("a", 1), derive_seed("a", 1))
        self.assertNotEqual(derive_seed("a", 1), derive_seed("a", 2))
        self.assertEqual([Rng(5).rand_int(0, 9) for _ in range(3)], [Rng(5).rand_int(0, 9) for _ in range(3)])


class TestConfig(unittest.TestCase):
    def test_defaults_and_partial(self):
        self.assertEqual(make_config({}).n_invoices, make_config(None).n_invoices)
        self.assertEqual(make_config({"errors": {"date_or_fx": 2}}).errors["duplicate_invoice"], 0)

    def test_bounded_errors(self):
        for bad in ({"nope": 1}, {"n_invoices": 5}, {"errors": {"x": 1}}, {"base_currency": "XXX"},
                    {"timezone": "Mars/Base"}, {"n_invoices": True}, "string", {"interactions": ["Z"]},
                    {"errors": {"date_or_fx": 4, "period_classification": 4, "duplicate_invoice": 4}, "interactions": ["A"]}):
            with self.assertRaises(ConfigError):
                make_config(bad)


class TestCalculator(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(evaluate("0.1 + 0.2"), "0.3")
        self.assertEqual(evaluate("-(3-5)*2"), "4")

    def test_rejects(self):
        for e in ("1e3", "a", "1//2", "(" * 25 + "1" + ")" * 25, "1/0", "", "2 3"):
            with self.assertRaises(CalcError):
                evaluate(e)


class TestScoring(unittest.TestCase):
    def test_metrics(self):
        self.assertEqual(prf1(0, 0, 0), (0.0, 0.0, 1.0))
        self.assertEqual(prf1(0, 2, 0)[2], 0.0)
        self.assertAlmostEqual(terminal_reward(1.0, 10), 0.98)
        self.assertEqual(terminal_reward(0.0, 400), -1.0)

    def test_empty_reference_and_findings(self):
        self.assertEqual(score([], [], 0)["reward"], 1.0)


class TestExportRoundTrip(unittest.TestCase):
    def test_files_reload_identically(self):
        ep = generate(77, {"interactions": ["A", "B"], "layout_seed": 3})
        with tempfile.TemporaryDirectory() as d:
            path = write_episode(d, ep, layout_seed=3)
            back = load_episode_dir(path, with_private=True)
        self.assertEqual(json.dumps(back["public"], sort_keys=True), json.dumps(ep["public"], sort_keys=True))
        self.assertEqual(back["private"]["truth"], ep["private"]["truth"])
        self.assertEqual(json.dumps(back["private"]["clean"], sort_keys=True), json.dumps(ep["private"]["clean"], sort_keys=True))


class TestHttpAndUiWhitelist(unittest.TestCase):
    def test_http_episode_and_traversal(self):
        from auditgym.env.adapters import make_http_server
        srv, env = make_http_server(0, ui=True)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        base = f"http://127.0.0.1:{port}"

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req).read())
        try:
            r = post("/reset", {"seed": 5, "config": {}})
            eid = r["observation"]["result"]["manifest"]["episode_id"]
            s = post("/step", {"action": {"tool": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 3}}})
            self.assertEqual(len(s["observation"]["result"]["rows"]), 3)
            s = post("/step", {"action": {"tool": "submit", "args": {"findings": {"episode_id": eid, "findings": []}}}})
            self.assertTrue(s["terminated"])
            for p in ("/../private/truth.json", "/%2e%2e/README.md", "/fonts/../../cli.py", "/static/../env/env.py", "/etc/passwd"):
                with self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + p)
        finally:
            srv.shutdown()
            env.close()


if __name__ == "__main__":
    unittest.main()
