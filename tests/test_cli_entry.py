"""Regression tests for the entry points CI and Docker use.

1. The Docker default command `python -m auditgym.cli verify --out ... --trajectories ...` must reach verify with
   its options (argparse.REMAINDER used to reject them).
2. Output must not crash where stdout is a cp1252 pipe, as on Windows CI (verify prints tick marks and rules).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args, **env_extra):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"), **env_extra)
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, cwd=ROOT, timeout=300)


class CliEntryTests(unittest.TestCase):
    def test_docker_default_command_is_accepted(self):
        with open(os.path.join(ROOT, "Dockerfile"), encoding="utf-8") as fh:
            text = fh.read()
        entry = json.loads(re.search(r"^ENTRYPOINT\s+(\[.*\])", text, re.M).group(1))
        cmd = json.loads(re.search(r"^CMD\s+(\[.*\])", text, re.M).group(1))
        self.assertEqual(entry[1:], ["-m", "auditgym.cli"])
        self.assertEqual(cmd[0], "verify")
        # Same options as the Docker default, pointed at a temp folder; --help keeps the test fast.
        r = run(["-m", "auditgym.cli", *cmd, "--help"])
        self.assertEqual(r.returncode, 0, r.stderr)
        for opt in cmd[1:]:
            if opt.startswith("--"):
                self.assertIn(opt, r.stdout)

    def test_cli_verify_passes_options_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "report.json")
            r = run(["-m", "auditgym.cli", "verify", "--out", out, "--trajectories", os.path.join(tmp, "t.jsonl"),
                     "--fuzz", "2"], PYTHONIOENCODING="cp1252")
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
            self.assertTrue(os.path.exists(out))
            self.assertIn("Estimated score", r.stdout)

    def test_output_survives_a_cp1252_pipe(self):
        code = "from auditgym.verify import utf8_output; utf8_output(); print('\\u2713 \\u03a3 \\u2194 \\u2297 \\u2212 \\u0410')"
        r = run(["-c", code], PYTHONIOENCODING="cp1252")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("✓", r.stdout)


if __name__ == "__main__":
    unittest.main()
