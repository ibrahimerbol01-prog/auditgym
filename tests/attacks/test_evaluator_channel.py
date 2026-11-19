"""ATTACK: the env's evaluator pipe also serves organizer commands, and one bad command kills it.

1. ``AuditEnv.service`` is the same ``ServiceClient`` pipe that accepts the organizer interface.
   Any code holding the env object (a Python policy, a tool wrapper, a notebook agent) can call
   ``env.service.call({"cmd": "reference", "handle": env._ep["handle"]})`` and get ``truth.json``,
   or ``{"cmd": "score", ..., "inspection_steps": -1000}`` to write its own score.
   DESIGN.md claims the agent "has no channel to read or write evaluator state"; that holds for the
   stdio/HTTP front doors only. Severity: low-medium (in-process agents only).
   Fix (src/auditgym/eval/service.py): give the env pipe a restricted command set (generate/load/
   score) and serve reference/finalize on a separate organizer channel or behind a token not held
   by the env; reject negative/implausible inspection_steps.
2. ``EvaluatorCore.dispatch`` only catches KeyError/TypeError/ValueError; ``load`` of a missing
   directory raises FileNotFoundError, which terminates the evaluator subprocess. The env is then
   permanently broken (RuntimeError / BrokenPipeError on every later reset). Reachable via
   ``env.reset(options={"episode_dir": ...})`` (harness side, not via front doors). Severity: low.
   Fix: catch ``Exception`` in dispatch / serve_stdio and return a bounded error; in env.reset wrap
   ``service.call`` and return the bounded ``bad_config`` observation.
"""
import os
import sys
import unittest

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src"))
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from auditgym.env.env import AuditEnv  # noqa: E402


class EvaluatorChannel(unittest.TestCase):
    def test_env_pipe_refuses_organizer_reference(self):
        env = AuditEnv(mode="closed")  # default: evaluator in a separate process
        try:
            env.reset(1, {})
            resp = env.service.call({"cmd": "reference", "handle": env._ep["handle"]})
            self.assertFalse(resp.get("ok"), "truth.json is readable through the env's own evaluator pipe")
        finally:
            env.close()

    def test_env_pipe_refuses_self_scoring(self):
        env = AuditEnv(mode="open")
        try:
            obs, _ = env.reset(1, {"clean": True})
            eid = obs["result"]["manifest"]["episode_id"]
            resp = env.service.call({"cmd": "score", "handle": env._ep["handle"],
                                     "submission": {"episode_id": eid, "findings": []}, "inspection_steps": -1000})
            self.assertFalse(resp.get("ok") and resp.get("reward", 0) >= 1.0,
                             "agent-side code scored its own episode with negative steps")
        finally:
            env.close()

    def test_bad_episode_dir_does_not_kill_evaluator(self):
        env = AuditEnv(mode="open")
        try:
            try:
                obs, _ = env.reset(options={"episode_dir": "/nonexistent-auditgym-dir"})
                self.assertFalse(obs.get("ok"))
            except Exception as exc:  # noqa: BLE001
                self.fail(f"reset raised {type(exc).__name__}: {exc}")
            obs, _ = env.reset(1, {})
            self.assertTrue(obs.get("ok"), "env unusable after one bad load")
        except Exception as exc:  # noqa: BLE001
            self.fail(f"evaluator died: {type(exc).__name__}: {exc}")
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
