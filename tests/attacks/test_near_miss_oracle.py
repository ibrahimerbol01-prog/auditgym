"""ATTACK: the open-mode report's ``near_miss`` field is a truth-membership oracle.

``scoring.score`` labels every *unmatched* finding with ``near_miss`` = "currency" /
"amount outside tolerance" / "evidence set incomplete" iff some hidden issue has the same type
and the same affected_ids, and ``None`` otherwise; ``service._public_report`` passes it to the
agent. A probe submission of up to 30 guesses with amount 0 and no evidence therefore tells the
agent exactly which (type, affected_ids) hypotheses are real issues. Because reset(seed) is
replayable from the front door (see test_reset_abandon), the agent can probe, reset the same
seed and submit only confirmed issues - reward earned from leaked truth, not from audit evidence.
Rubric impact: "leaking hidden data (truth)" in open mode. Severity: low-medium (needs replay;
reward alone is a 1-bit oracle, near_miss is a 30-hypothesis-per-episode oracle).

Fix (src/auditgym/eval/service.py, _public_report): drop ``near_miss`` from ``per_finding`` (keep
it only in the organizer results), or only report it for findings that already name a
complete acceptable evidence set.
"""
import os
import sys
import unittest

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from auditgym.env.env import AuditEnv  # noqa: E402
from auditgym.eval.service import ServiceClient  # noqa: E402


class NearMissOracle(unittest.TestCase):
    def test_report_does_not_separate_real_from_fabricated_hypotheses(self):
        svc = ServiceClient(in_process=True)
        env = AuditEnv(mode="open", service=svc)
        obs, _ = env.reset(5, {})
        eid = obs["result"]["manifest"]["episode_id"]
        real = svc.call({"cmd": "reference", "handle": env._ep["handle"]})["truth"]["issues"][0]  # organizer side
        # The agent's probe: right hypothesis but zero effort (amount 0, no evidence) vs a fabricated one.
        probe = lambda ids: {"type": real["type"], "affected_ids": ids, "claimed_amount_minor": 0,  # noqa: E731
                             "currency": real["currency"], "evidence_ids": [], "explanation": ""}
        fake_ids = [x[:-1] + ("0" if x[-1] != "0" else "1") for x in real["affected_ids"]]
        obs, _, _, _, _ = env.step({"tool": "submit", "args": {"findings": {
            "episode_id": eid, "findings": [probe(real["affected_ids"]), probe(fake_ids)]}}})
        pf = obs["result"]["report"]["per_finding"]
        self.assertFalse(pf[0]["matched"] or pf[1]["matched"])
        self.assertEqual(pf[0].get("near_miss"), pf[1].get("near_miss"),
                         f"report reveals which hypothesis is a hidden issue: {pf}")


if __name__ == "__main__":
    unittest.main()
