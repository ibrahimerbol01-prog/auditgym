"""ATTACK: one malformed JSON line kills the stdio front door (``auditgym.cli serve --stdio``).

``adapters.serve_stdio`` only catches ``json.JSONDecodeError``. Two inputs that any client (or a
confused LLM agent) can send raise other exceptions inside ``json.loads`` and terminate the process:
  * nesting deeper than the recursion limit  -> RecursionError
  * an integer literal with > 4300 digits      -> ValueError (int max-str-digits, Python >= 3.11)
After the crash every later request (here: ``{"op":"state"}``) gets no answer: the environment
is gone.  Rubric impact: "crash of the core with malformed input" -> blocker; also violates the
documented contract "every malformed input returns a bounded error".

Fix (src/auditgym/env/adapters.py, serve_stdio): ``except (ValueError, RecursionError)`` around
``json.loads`` (JSONDecodeError is a ValueError) and wrap ``handle_request`` in a catch-all that
returns ``{"ok": false, "error": {"code": "bad_arguments", ...}}``.
"""
import json
import subprocess
import sys
import unittest

import os
import sys

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)


def sub_env():
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _run(lines):
    p = subprocess.run([sys.executable, "-m", "auditgym.cli", "serve", "--stdio"], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=60, env=sub_env())
    return p.returncode, [json.loads(x) for x in p.stdout.splitlines() if x.strip()]


class StdioCrash(unittest.TestCase):
    def test_deep_json_line_does_not_kill_server(self):
        rc, out = _run(['{"op":"step","action":' + "[" * 50000 + "]" * 50000 + "}", '{"op":"state"}'])
        self.assertEqual(rc, 0, "stdio front door crashed on deeply nested JSON")
        self.assertEqual(len(out), 2, "the request after the malformed line was never answered")
        self.assertIn("done", out[1])

    def test_huge_integer_does_not_kill_server(self):
        rc, out = _run(['{"op":"reset","seed":' + "9" * 5000 + "}", '{"op":"state"}'])
        self.assertEqual(rc, 0, "stdio front door crashed on a 5000-digit integer")
        self.assertEqual(len(out), 2)
        self.assertFalse(out[0].get("observation", out[0]).get("ok", True))


if __name__ == "__main__":
    unittest.main()
