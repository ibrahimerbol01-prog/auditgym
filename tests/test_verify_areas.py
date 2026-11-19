"""Run the same checks as `python -m auditgym.verify`, as unit tests (one test per check)."""
import unittest

from auditgym.eval.service import ServiceClient
from auditgym import verify


class _Area(unittest.TestCase):
    def assertAllPass(self, checks):
        failed = [f"{c['id']} {c['name']}: {c['error']}" for c in checks if not c["passed"]]
        self.assertEqual(failed, [])


class TestAreas(_Area):
    @classmethod
    def setUpClass(cls):
        cls.svc = ServiceClient()

    @classmethod
    def tearDownClass(cls):
        cls.svc.close()

    def test_contract_and_isolation(self):
        self.assertAllPass(verify.contract_checks(self.svc))

    def test_reward_reliability(self):
        self.assertAllPass(verify.reward_checks())

    def test_reproducibility_pairs(self):
        self.assertAllPass(verify.repro_checks(self.svc))

    def test_data_and_reference(self):
        checks, _ = verify.data_checks(None)
        self.assertAllPass(checks)

    def test_fuzz_configs(self):
        res = verify.fuzz(40)
        self.assertEqual(res["failures"], [])
        self.assertGreater(res["valid_episodes_ok"], 20)


if __name__ == "__main__":
    unittest.main()
