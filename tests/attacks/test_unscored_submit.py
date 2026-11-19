"""ATTACK: an invalid submission can dodge the -1 penalty and leave NO evaluator record.

``AuditEnv._submit`` sets ``self._done = True`` and only then serialises the submission for the
evaluator (``ServiceClient.call`` -> ``json.dumps``). If serialisation raises, the exception
escapes ``step()``: the episode is over for the agent, but the evaluator never scored it
(no ``invalid_structure`` -1, no log entry, nothing in ``finalize``).

Reproduction
  * Python API: ``env.step({"tool":"submit","args":{"findings": {..."affected_ids": {"X"}...}}})``
    (a ``set``; also bytes, a cyclic dict, or an int with > 4300 digits) -> TypeError/ValueError.
  * HTTP front door: a submission whose ``explanation`` is nested ~980 levels deep parses in
    ``do_POST`` but overflows the recursion limit in the deeper ``json.dumps`` call -> connection
    dropped, ``/state`` says done, evaluator has no record (verified; the exact depth depends on stack).
Rubric impact: reward reliability ("invalid structure -> episode ends, reward -1, evaluator-side
log entry" is not enforced) and, in closed mode, an agent can make bad episodes vanish from the
run results. Severity: medium.

Fix (src/auditgym/env/env.py, _submit): serialise/validate before marking done, e.g.
``try: findings = json.loads(json.dumps(findings, allow_nan=False)) except (TypeError, ValueError,
RecursionError): findings = None`` (None is then scored by the evaluator as invalid_structure -1);
also wrap ``service.call`` so step() never raises.
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
from auditgym.env.env import AuditEnv  # noqa: E402
from auditgym.eval.service import ServiceClient  # noqa: E402


class UnscoredSubmit(unittest.TestCase):
    def _bad(self, eid, ids):
        return {"tool": "submit", "args": {"findings": {"episode_id": eid, "findings": [
            {"type": "duplicate_invoice", "affected_ids": ids, "claimed_amount_minor": 1, "currency": "KZT",
             "evidence_ids": [], "explanation": ""}]}}}

    def test_python_api_unserialisable_submission_is_scored_minus_one(self):
        for payload in ({"X"}, b"X"):
            svc = ServiceClient(in_process=True)
            env = AuditEnv(mode="closed", service=svc)
            obs, _ = env.reset(1, {})
            eid = obs["result"]["manifest"]["episode_id"]
            try:
                env.step(self._bad(eid, payload))
            except Exception as exc:  # noqa: BLE001
                self.fail(f"step() raised {type(exc).__name__} for a {type(payload).__name__} in the submission")
            res = svc.call({"cmd": "finalize"})["results"]
            self.assertEqual(len(res), 1, "the submitted episode left no evaluator record")
            self.assertEqual(res[0]["reward"], -1.0)

    def test_http_deep_submission_leaves_episode_unscored(self):
        srv, env = make_http_server(0, "closed", ui=False)
        srv.handle_error = lambda *a: None
        port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def req(method, path, body=None):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                c.request(method, path, body=body, headers={"Content-Type": "application/json"})
                return json.loads(c.getresponse().read() or b"null")
            except (http.client.HTTPException, ConnectionError, json.JSONDecodeError):
                return None
        try:
            dodged = []
            for depth in range(1000, 940, -2):
                req("POST", "/reset", json.dumps({"seed": 3, "config": {}}))
                eid = req("GET", "/state")["episode_id"]
                before = len(env._svc.call({"cmd": "finalize"})["results"])  # organizer client
                body = ('{"action":{"tool":"submit","args":{"findings":{"episode_id":"%s","findings":[{"type":'
                        '"duplicate_invoice","affected_ids":["A"],"claimed_amount_minor":1,"currency":"KZT",'
                        '"evidence_ids":[],"explanation":%s}]}}}}') % (eid, "[" * depth + "]" * depth)
                req("POST", "/step", body)
                done = req("GET", "/state")["done"]
                after = len(env._svc.call({"cmd": "finalize"})["results"])  # organizer client
                if done and after == before:
                    dodged.append(depth)
            self.assertEqual(dodged, [], f"episodes ended without any evaluator record at depths {dodged}")
        finally:
            srv.shutdown()
            srv.server_close()
            env.close()


if __name__ == "__main__":
    unittest.main()
