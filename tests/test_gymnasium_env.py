"""Optional Gymnasium adapter tests (task T14).

Skipped when ``gymnasium`` is not installed, unless ``AUDITGYM_GYM=1`` (set in CI).
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import gymnasium as gym
    from gymnasium.utils.env_checker import check_env
except ImportError:  # pragma: no cover - optional dependency
    gym = None
    check_env = None

REQUIRED = os.environ.get("AUDITGYM_GYM") == "1"


@unittest.skipIf(gym is None and not REQUIRED, "gymnasium not installed (optional RL adapter test)")
class TestGymnasiumAdapter(unittest.TestCase):
    def setUp(self):
        if gym is None or check_env is None:
            raise AssertionError("AUDITGYM_GYM=1 but gymnasium is not installed")
        from examples.gymnasium_env import AuditGymEnv
        self.AuditGymEnv = AuditGymEnv

    def test_check_env_text_space(self):
        env = self.AuditGymEnv(mode="open", action_mode="text")
        try:
            check_env(env, skip_render_check=True)
        finally:
            env.close()

    def test_check_env_discrete_space(self):
        env = self.AuditGymEnv(mode="open", action_mode="discrete")
        try:
            check_env(env, skip_render_check=True)
        finally:
            env.close()

    def test_deterministic_reset_and_submit(self):
        env = self.AuditGymEnv(mode="open", action_mode="discrete", default_config={"clean": True})
        try:
            obs1, _ = env.reset(seed=42)
            obs2, _ = env.reset(seed=42)
            self.assertEqual(obs1, obs2)
            parsed = json.loads(obs1)
            self.assertTrue(parsed["ok"])
            obs, reward, terminated, truncated, _ = env.step(5)  # submit []
            self.assertTrue(terminated)
            self.assertFalse(truncated)
            self.assertGreaterEqual(reward, -1.0)
            self.assertLessEqual(reward, 1.0)
            self.assertTrue(env.observation_space.contains(obs))
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
