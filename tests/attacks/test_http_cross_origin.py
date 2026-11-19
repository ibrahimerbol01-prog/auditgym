"""ATTACK: any web page can drive the localhost HTTP front door / UI (CSRF + DNS rebinding).

``make_http_server`` binds 127.0.0.1 but accepts any ``Host`` and ``Origin`` and parses the body as
JSON whatever the ``Content-Type``. A page the operator visits can therefore send a "simple"
cross-origin ``POST /step`` (``Content-Type: text/plain``, no CORS preflight) to reset, step or
submit the running episode, and via DNS rebinding (``Host: evil.example``) read ``/state`` and
``/data/*``. Rubric impact: contract & isolation (a third party can write into the episode that
is being evaluated). Severity: low (requires the operator to browse while the server runs).

Fix (src/auditgym/env/adapters.py): reject requests whose ``Host`` is not ``127.0.0.1:<port>`` /
``localhost:<port>``; for POST require ``Content-Type: application/json`` and reject a foreign
``Origin`` (403).
"""
import http.client
import json
import os
import sys
import threading
import unittest

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from auditgym.env.adapters import make_http_server  # noqa: E402


class CrossOrigin(unittest.TestCase):
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

    def _req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, r.read()

    def test_cross_origin_text_plain_post_is_rejected(self):
        st, _ = self._req("POST", "/reset", json.dumps({"seed": 1, "config": {}}),
                          {"Content-Type": "text/plain", "Origin": "http://evil.example"})
        self.assertIn(st, (403, 415), "a cross-origin text/plain POST reset the episode")

    def test_foreign_host_header_is_rejected(self):
        st, body = self._req("GET", "/state", headers={"Host": "evil.example:%d" % self.port})
        self.assertIn(st, (400, 403, 421), f"DNS-rebinding style request was served: {body[:80]!r}")


if __name__ == "__main__":
    unittest.main()
