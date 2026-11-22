"""The desktop wrapper (desktop/app.py) must serve the same UI and never become a back door.

Standard library only: pywebview and PyInstaller are not needed for these tests.
"""
import importlib.util
import os
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_app():
    spec = importlib.util.spec_from_file_location("auditgym_desktop_app", os.path.join(ROOT, "desktop", "app.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DesktopAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_app()

    def test_serves_only_public_data_files(self):
        files = self.app.data_files()
        self.assertIn("/data/train.json", files)
        self.assertIn("/data/dev.json", files)
        for path in files.values():
            self.assertNotIn("private", path.replace("\\", "/").split("/"))

    def test_child_dispatch_only_runs_the_evaluator_service(self):
        self.assertFalse(self.app.run_child_if_requested(["AuditGym"]))
        self.assertFalse(self.app.run_child_if_requested(["AuditGym", "--smoke"]))
        with self.assertRaises(SystemExit):
            self.app.run_child_if_requested(["AuditGym", "-m", "os"])
        with self.assertRaises(SystemExit):
            self.app.run_child_if_requested(["AuditGym", "-m", "auditgym.cli", "verify"])

    def test_smoke_plays_one_episode_through_the_ui_server(self):
        self.assertEqual(self.app.smoke(), 0)

    def test_installers_download_the_files_the_build_produces(self):
        spec = importlib.util.spec_from_file_location("auditgym_desktop_build", os.path.join(ROOT, "desktop", "build.py"))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)  # PyInstaller is only imported inside build.main()
        self.assertRegex(build.asset_name(), r"^AuditGym-(windows|macos|linux)-(x64|arm64)\.zip$")
        with open(os.path.join(ROOT, "desktop", "install.ps1"), encoding="utf-8") as fh:
            self.assertIn("'AuditGym-windows-x64.zip'", fh.read())
        with open(os.path.join(ROOT, "desktop", "install.sh"), encoding="utf-8") as fh:
            sh = fh.read()
        self.assertIn('ASSET="AuditGym-$OS-$ARCH.zip"', sh)
        for os_name in ("macos", "linux"):
            self.assertIn(f"OS={os_name}", sh)
        # Branch builds: CI names each artifact after the zip, and both installers ask for exactly that name.
        with open(os.path.join(ROOT, ".github", "workflows", "desktop.yml"), encoding="utf-8") as fh:
            wf = fh.read()
        self.assertIn('echo "ASSET=${f%.zip}"', wf)
        self.assertIn("name: ${{ env.ASSET }}", wf)
        self.assertIn('-n "${ASSET%.zip}"', sh)
        with open(os.path.join(ROOT, "desktop", "install.ps1"), encoding="utf-8") as fh:
            self.assertIn("-n ($Asset -replace '\\.zip$', '')", fh.read())

    def test_terminal_command_entry(self):
        spec = importlib.util.spec_from_file_location("auditgym_cli_entry", os.path.join(ROOT, "desktop", "cli_entry.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        with self.assertRaises(SystemExit):  # the same evaluator-only dispatch as the app
            mod.main(["auditgym", "-m", "os"])
        self.assertEqual(mod.main(["auditgym", "--version"]), 0)
        with open(os.path.join(ROOT, "desktop", "build.py"), encoding="utf-8") as fh:
            build = fh.read()
        self.assertIn('"cli_entry.py", "auditgym"', build)
        with open(os.path.join(ROOT, "desktop", "install.ps1"), encoding="utf-8") as fh:
            self.assertIn("'cli'", fh.read())
        with open(os.path.join(ROOT, "desktop", "install.sh"), encoding="utf-8") as fh:
            self.assertIn('"$BIN/auditgym"', fh.read())

    def test_desktop_code_never_reads_truth(self):
        with open(os.path.join(ROOT, "desktop", "app.py"), encoding="utf-8") as fh:
            text = fh.read()
        for word in ("truth.json", "provenance", "private/"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()


def load_updater():
    spec = importlib.util.spec_from_file_location("auditgym_desktop_updater", os.path.join(ROOT, "desktop", "updater.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class UpdaterTests(unittest.TestCase):
    """desktop/updater.py: which build is newer, and the installer command that replaces the app (no network here)."""

    def setUp(self):
        import tempfile
        self.u = load_updater()
        self.tmp = tempfile.mkdtemp()
        self.u.HOME = self.tmp
        self.u.CACHE = os.path.join(self.tmp, "update.json")
        self.u.LOG = os.path.join(self.tmp, "update.log")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_versions_and_stamps(self):
        self.assertEqual(self.u.parse_stamp("v0.2.0 @ 1a2b3c4 · built 2026-11-21 10:00 UTC"), ("v0.2.0", "1a2b3c4"))
        self.assertEqual(self.u.parse_stamp("source checkout"), ("", ""))
        self.assertGreater(self.u.version_key("v0.10.0"), self.u.version_key("v0.9.9"))
        self.assertIsNone(self.u.version_key("task/design-and-desktop"))

    def test_release_channel_offers_only_a_newer_release_and_caches(self):
        calls = []
        self.u.latest_release = lambda: calls.append(1) or {"version": "v0.3.0", "url": "u", "notes": ""}
        res = self.u.check("v0.2.0 @ 1a2b3c4 · built x")
        self.assertEqual((res["channel"], res["available"], res["latest"]["version"]), ("release", True, "v0.3.0"))
        self.u.check("v0.2.0 @ 1a2b3c4 · built x")
        self.assertEqual(len(calls), 1, "the second check within the TTL comes from the cache")
        self.assertFalse(self.u.check("v0.3.0 @ 9f9f9f9 · built x")["available"])

    def test_branch_channel_compares_commits(self):
        self.u.latest_branch_build = lambda b: {"version": f"{b} @ abcdef1", "sha": "abcdef1234", "at": None}
        self.assertTrue(self.u.check("main @ 1a2b3c4 · built x")["available"])
        self.assertFalse(self.u.check("main @ abcdef1 · built x", force=True)["available"])
        self.u.latest_branch_build = lambda b: None
        self.u.latest_release = lambda: {"version": "v0.2.0", "url": "u", "notes": "", "published": "2026-11-22T12:00:00Z"}
        older = self.u.check("main @ 1a2b3c4 · built 2026-11-22 13:00 UTC", force=True)
        self.assertFalse(older["available"], "never offers a release older than the build")
        self.assertIn("gh auth login", older["error"])
        newer = self.u.check("3/merge @ 1a2b3c4 · built 2026-11-22 11:00 UTC", force=True)
        self.assertEqual((newer["channel"], newer["available"], newer["latest"]["version"]), ("release", True, "v0.2.0"),
                         "without gh, a test build moves to a newer release")
        self.u.latest_release = lambda: {"version": "v0.2.0", "url": "u", "notes": "", "published": "2026-11-22T12:00:00Z",
                                         "commit": "1a2b3c4d5e6f"}
        same = self.u.check("main @ 1a2b3c4 · built 2026-11-22 11:00 UTC", force=True)
        self.assertFalse(same["available"], "a release of this very commit is not an update")
        cmd, env = self.u.installer_command(newer, detached=False)
        self.assertEqual(env["AUDITGYM_VERSION"], "v0.2.0")
        self.assertNotIn("AUDITGYM_BRANCH", env)

    def test_pull_request_builds_are_named_after_their_branch(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build", os.path.join(ROOT, "desktop", "build.py"))
        b = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(b)
        with mock.patch.dict(os.environ, {"GITHUB_HEAD_REF": "task/x", "GITHUB_REF_NAME": "3/merge", "GITHUB_SHA": "abcdef1234"}):
            self.assertTrue(b.build_stamp().startswith("task/x @ abcdef1 · built "))
        with mock.patch.dict(os.environ, {"AUDITGYM_REF": "v0.2.1", "GITHUB_REF_NAME": "main", "GITHUB_SHA": "abcdef1234"}):
            self.assertTrue(b.build_stamp().startswith("v0.2.1 @ abcdef1 · built "), "a release started by hand from main")

    def test_offline_and_source_checkout_offer_nothing(self):
        def boom():
            raise OSError("offline")
        self.u.latest_release = boom
        res = self.u.check("v0.2.0 @ 1a2b3c4 · built x")
        self.assertFalse(res["available"])
        self.assertTrue(res["error"])
        self.assertEqual(self.u.check("source checkout")["channel"], "source")

    def test_installer_command_pins_the_offered_version(self):
        info = {"channel": "release", "current": "v0.2.0 @ 1a2b3c4 · built x", "available": True, "latest": {"version": "v0.3.0"}}
        cmd, env = self.u.installer_command(info)
        self.assertEqual(env["AUDITGYM_VERSION"], "v0.3.0")
        self.assertIn(f"{self.u.PUBLIC}/releases/download/v0.3.0/install.", cmd[-1])
        self.assertIn(self.u.LOG, cmd[-1].replace("''", "'"))
        info = {"channel": "branch", "current": "main @ 1a2b3c4 · built x", "available": True, "latest": {"version": "main @ abcdef1"}}
        cmd, env = self.u.installer_command(info, detached=False)
        self.assertEqual(env["AUDITGYM_BRANCH"], "main")
        self.assertIn("contents/desktop/install.", cmd[-1])
        self.assertNotIn(self.u.LOG, cmd[-1])

    def test_routes_refuse_while_busy_and_pass_everything_else_through(self):
        class Api:
            def get(self, path, query):
                return 200, {"from": "jobs"}

            def post(self, path, body):
                return 200, {"from": "jobs"}
        exits = []
        r = self.u.UpdateRoutes(Api(), "v0.2.0 @ 1a2b3c4 · built x", on_exit=lambda: exits.append(1), busy=lambda: True)
        self.assertEqual(r.get("/api/runs", {})[1], {"from": "jobs"})
        self.assertEqual(r.post("/api/train", {})[1], {"from": "jobs"})
        self.assertEqual(r.post("/api/update", {})[0], 409)
        r.busy = lambda: False
        self.u.latest_release = lambda: {"version": "v0.2.0", "url": "u", "notes": ""}
        status, res = r.post("/api/update", {})
        self.assertEqual((status, res["error"]["code"]), (409, "no_update"))
        self.assertEqual(exits, [])


class LicenceTests(unittest.TestCase):
    """The desktop builds ship the licences of what they bundle, at the versions actually pinned."""

    def test_notices_match_the_pinned_desktop_dependencies_and_ship_in_builds(self):
        with open(os.path.join(ROOT, "desktop", "THIRD_PARTY_NOTICES.md"), encoding="utf-8") as fh:
            notices = fh.read()
        with open(os.path.join(ROOT, "desktop", "requirements-desktop.txt"), encoding="utf-8") as fh:
            pins = [line.split("==") for line in fh if "==" in line and not line.startswith("#")]
        for name, version in pins:
            self.assertIn(f"{version.strip()}", notices, f"{name}: update THIRD_PARTY_NOTICES.md for the new version")
        with open(os.path.join(ROOT, "desktop", "build.py"), encoding="utf-8") as fh:
            build = fh.read()
        self.assertIn("THIRD_PARTY_NOTICES.md", build)
        self.assertIn('"LICENSE"', build)
        with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as fh:
            self.assertTrue(fh.read().startswith("MIT License"))
