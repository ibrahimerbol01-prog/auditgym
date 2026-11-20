"""Red-team round 2 attacks from the agent side (task T3).

Each test demonstrates a real hole found in round 2:
1. HTTP POST /reset op-override: body {"op": "step", ...} overwrites "op": "reset" via dict unpacking.
2. HTTP GET /fonts/ backslash traversal: "/" check does not block "\\" or ".." on Windows.
3. Non-strict JSON (NaN/Infinity) accepted by HTTP and stdio front doors.
"""
import http.client
import json
import os
import subprocess
import sys
import threading
import unittest

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from auditgym.env.adapters import make_http_server  # noqa: E402


class RedTeamRound2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.env = make_http_server(0, "open", ui=True)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.env.close()

    def _post(self, path, raw_body: bytes):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("POST", path, body=raw_body, headers={
            "Host": f"127.0.0.1:{self.port}",
            "Content-Type": "application/json",
            "Content-Length": str(len(raw_body)),
        })
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def _get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    def test_reset_endpoint_cannot_be_hijacked_via_op_field(self):
        # Sending {"op": "state"} to POST /reset must still execute reset, not state.
        status, data = self._post("/reset", json.dumps({"op": "state", "seed": 1, "config": {}}).encode())
        self.assertEqual(status, 200)
        body = json.loads(data)
        self.assertIn("observation", body, f"POST /reset executed non-reset op: {body}")

    def test_fonts_endpoint_blocks_backslash_and_dotdot_traversal(self):
        for bad in ("/fonts/..\\app.js", "/fonts/..%5capp.js", "/fonts/..\\..\\pyproject.toml", "/fonts/..\\.woff2"):
            status, _ = self._get(bad)
            self.assertEqual(status, 404, f"traversal path was not rejected: {bad}")

    def test_http_rejects_nan_and_infinity_json(self):
        for payload in (b'{"seed": 1, "config": {"n_entities": NaN}}',
                        b'{"action": {"tool": "list_records", "args": {"limit": Infinity}}}'):
            status, data = self._post("/step", payload)
            self.assertEqual(status, 400, f"HTTP accepted non-standard JSON {payload!r}: {status} {data!r}")

    def test_stdio_rejects_nan_and_infinity_json(self):
        env = {**os.environ, "PYTHONPATH": SRC}
        p = subprocess.Popen(
            [sys.executable, "-m", "auditgym.cli", "serve", "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        try:
            assert p.stdin and p.stdout
            p.stdin.write('{"op": "reset", "seed": 1, "config": {"n_entities": NaN}}\n')
            p.stdin.flush()
            resp = json.loads(p.stdout.readline())
            self.assertFalse(resp.get("ok", True), f"stdio accepted NaN: {resp}")
            self.assertEqual(resp.get("error", {}).get("code"), "bad_arguments")
        finally:
            if p.stdin:
                p.stdin.close()
            p.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
