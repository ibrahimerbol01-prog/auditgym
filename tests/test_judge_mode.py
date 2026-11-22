"""Judge mode: the app runs the official verification in its own process and serves the fresh report."""
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from auditgym import harness  # noqa: E402


class JudgeMode(unittest.TestCase):
    def test_verify_runs_from_the_app_and_its_report_is_served(self):
        jobs = harness.Jobs(base=tempfile.mkdtemp())
        jobs.verify_args = ["--fuzz", "2"]
        self.assertEqual(jobs.get("/api/verify", {})[1]["running"], False)
        st, res = jobs.post("/api/verify", {})
        self.assertEqual(st, 200, res)
        self.assertEqual(jobs.post("/api/verify", {})[0], 409, "one check at a time")
        for _ in range(1800):
            s = jobs.get("/api/verify", {})[1]
            if not s["running"]:
                break
            time.sleep(0.1)
        self.assertEqual(s["exit"], 0, "\n".join(s["lines"][-20:]))
        self.assertEqual(s["report"]["estimated_score"]["total"], 100.0)
        self.assertTrue(any("Estimated score" in line for line in s["lines"]))
        self.assertEqual(sum(len(v) for v in s["report"]["areas"].values()), 85)


if __name__ == "__main__":
    unittest.main()
