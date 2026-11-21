"""Red team (auditgym.redteam): no attack earns reward without finding errors; the arena runs end to end."""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from auditgym import harness, redteam  # noqa: E402


class Arena(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp()
        cls.arena = redteam.run_arena("arena-unit", base=cls.base, rl_iterations=3)
        cls.lanes = {x["key"]: x for x in cls.arena["lanes"]}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_every_lane_ran_on_the_twenty_test_episodes(self):
        self.assertEqual(self.arena["status"], "done")
        for k in redteam.LANES:
            self.assertEqual(self.lanes[k]["status"], "done", k)
            self.assertEqual(self.lanes[k]["episodes"], 20, k)

    def test_no_attack_is_an_exploit(self):
        s = self.arena["summary"]
        self.assertEqual(s["exploits"], 0, [x for x in self.arena["lanes"] if x.get("verdict") == "exploit"])
        floor = self.lanes["silence"]["reward"]
        for k in redteam.ATTACKS:
            if k not in redteam.INFORMED:
                self.assertLessEqual(self.lanes[k]["reward"], floor + redteam.MARGIN, k)
        self.assertLessEqual(self.lanes["rl_attacker"]["reward"], floor + redteam.MARGIN)

    def test_specific_defences(self):
        self.assertEqual(self.lanes["invalid_structure"]["reward"], -1.0, "a malformed answer scores -1")
        self.assertEqual(self.lanes["flag_all"]["reward"], -1.0, "the judges' attack gets nothing")
        self.assertLess(self.lanes["no_proof"]["reward"], self.lanes["reconcile"]["reward"] - 0.5, "proof is required")
        self.assertGreater(self.lanes["reconcile"]["reward"], 0.9)

    def test_lanes_are_replayable_runs_tagged_with_the_arena(self):
        r = harness.read_run(self.lanes["flag_all"]["run"], self.base)
        self.assertEqual((r["arena"], r["mode"]), ("arena-unit", "closed"))
        self.assertIsNotNone(harness.read_steps(r["id"], 0, self.base))


if __name__ == "__main__":
    unittest.main()
