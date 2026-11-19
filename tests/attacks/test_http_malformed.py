"""ATTACK: malformed HTTP requests get no response at all (connection dropped, traceback on stderr).

``make_http_server.Handler.do_POST`` only catches ``json.JSONDecodeError``. These requests raise
inside the handler, so ``socketserver`` prints a traceback and closes the socket without a status:
  * ``Content-Length: abc``            -> ValueError in int()
  * ``Content-Length: -5``             -> ValueError in rfile.read()
  * body nested 5000 deep              -> RecursionError
  * body with a 5000-digit integer     -> ValueError (int max-str-digits)
  * body that is not UTF-8             -> UnicodeDecodeError
The server thread survives (so not a blocker), but the front door violates its own contract
("bounded error from a fixed code list") and clients see RemoteDisconnected. Rubric: contract &
isolation (minor).

Fix (src/auditgym/env/adapters.py, do_POST): parse Content-Length in try/except, reject n < 0,
and catch ``(ValueError, RecursionError, UnicodeDecodeError)`` around ``json.loads`` -> 400 JSON.
"""
import http.client
import socket
import threading
import unittest

import os
import sys

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from auditgym.env.adapters import make_http_server


class HttpMalformed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.env = make_http_server(0, "open", ui=False)
        cls.srv.handle_error = lambda *a: None  # keep test output clean
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.env.close()

    def _raw(self, data):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(data)
        out = b""
        try:
            while True:
                c = s.recv(65536)
                if not c:
                    break
                out += c
        except socket.timeout:
            pass
        s.close()
        return out

    def _post(self, body, cl=None):
        cl = str(len(body)) if cl is None else cl
        return self._raw(b"POST /step HTTP/1.0\r\nContent-Length: " + cl.encode() + b"\r\n\r\n" + body)

    def _assert_bounded(self, resp, what):
        self.assertTrue(resp.startswith(b"HTTP/1.0 4"), f"{what}: no HTTP error status, got {resp[:60]!r}")
        self.assertIn(b'"error"', resp, f"{what}: no bounded JSON error")

    def test_non_numeric_content_length(self):
        self._assert_bounded(self._post(b"{}", "abc"), "Content-Length: abc")

    def test_negative_content_length(self):
        self._assert_bounded(self._post(b"{}", "-5"), "Content-Length: -5")

    def test_deep_json(self):
        self._assert_bounded(self._post(b"[" * 5000 + b"]" * 5000), "deep JSON")

    def test_huge_int(self):
        self._assert_bounded(self._post(b'{"action":' + b"9" * 5000 + b"}"), "5000-digit int")

    def test_invalid_utf8(self):
        self._assert_bounded(self._post(b'{"action":"\xff\xfe"}'), "invalid UTF-8")


if __name__ == "__main__":
    unittest.main()
