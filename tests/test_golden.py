"""Generator drift guard: the open train/dev episodes must regenerate byte-for-byte."""
import hashlib
import json
import os
import unittest

from auditgym.gen.build import generate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestGolden(unittest.TestCase):
    def test_open_episodes_regenerate_exactly(self):
        golden = json.load(open(os.path.join(ROOT, "episodes", "golden_hashes.json"), encoding="utf-8"))
        got = {}
        for split in ("train", "dev"):
            spec = json.load(open(os.path.join(ROOT, "configs", f"{split}.json"), encoding="utf-8"))
            for item in spec["episodes"]:
                ep = generate(item["seed"], item["config"])
                got[f"{split}/{ep['public']['manifest']['episode_id']}"] = hashlib.sha256(json.dumps(ep, sort_keys=True).encode()).hexdigest()
        self.assertEqual(got, golden)


if __name__ == "__main__":
    unittest.main()
