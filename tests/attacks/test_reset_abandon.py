"""ATTACK: reset() silently abandons the running episode -> free reading, cherry-picking, no record.

``AuditEnv.reset`` drops ``self._ep`` without telling the evaluator, so an unfinished episode is
never scored (not even as truncated). Through the front doors (stdio/HTTP) the *client* sends
``reset`` with any seed/config, so an agent can:
  1. read 99 pages of seed S, reset(S) again (same episode_id, deterministic), and submit in one
     step: the evaluator charges 0 inspection steps -> the 0.002/step cost is avoidable;
  2. abandon any episode it is unsure about (closed mode: it simply never appears in finalize /
     AUDITGYM_EVAL_LOG), and
  3. in closed mode choose ``{"clean": true}`` itself and submit [] for a logged reward of +1.0.
Rubric impact: reward reliability (step cost and failure are escapable) and contract & isolation
(the agent decides what the evaluator records). Severity: medium (high if a closed-mode
leaderboard is run through the stdio/HTTP front door).

Fix (src/auditgym/env/env.py, reset): if an episode is active (``self._ep and not self._done``),
score it first with ``{"cmd": "score", ..., "truncated": True, "inspection_steps": steps}``; for
closed-mode front doors (adapters.py) ignore client seed/config and serve an organizer-supplied
episode list, and record seed/config per result in the evaluator.
"""
import os
import sys
import unittest

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from auditgym.env.adapters import handle_request  # noqa: E402
from auditgym.env.env import AuditEnv  # noqa: E402
from auditgym.eval.service import ServiceClient  # noqa: E402


class ResetAbandon(unittest.TestCase):
    def test_abandoned_episode_is_recorded_and_its_steps_charged(self):
        svc = ServiceClient(in_process=True)
        env = AuditEnv(mode="closed", service=svc)
        # Episode 1 (has 4 issues): read 60 pages, then abandon it with a front-door reset.
        r1 = handle_request(env, {"op": "reset", "seed": 11, "config": {}})
        eid1 = r1["observation"]["result"]["manifest"]["episode_id"]
        cursor = None
        for _ in range(60):
            o = handle_request(env, {"op": "step", "action": {"tool": "list_records",
                                                              "args": {"table": "ledger", "cursor": cursor}}})
            cursor = o["observation"]["result"]["next_cursor"]
        # Episode 2: identical episode (same seed) - all knowledge is already in hand.
        r2 = handle_request(env, {"op": "reset", "seed": 11, "config": {}})
        self.assertEqual(r2["observation"]["result"]["manifest"]["episode_id"], eid1)
        handle_request(env, {"op": "step", "action": {"tool": "submit", "args": {"findings": {
            "episode_id": eid1, "findings": []}}}})
        res = svc.call({"cmd": "finalize"})["results"]
        self.assertEqual(len(res), 2, "the abandoned episode left no evaluator record")
        charged = sum(r["inspection_steps"] for r in res)
        self.assertGreaterEqual(charged, 60, f"60 inspection steps were taken but only {charged} were charged")


if __name__ == "__main__":
    unittest.main()
