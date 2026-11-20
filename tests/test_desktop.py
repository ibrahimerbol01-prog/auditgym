"""The desktop wrapper (desktop/app.py) must serve the same UI and never become a back door.

Standard library only: pywebview and PyInstaller are not needed for these tests.
"""
import importlib.util
import os
import unittest

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

    def test_desktop_code_never_reads_truth(self):
        with open(os.path.join(ROOT, "desktop", "app.py"), encoding="utf-8") as fh:
            text = fh.read()
        for word in ("truth.json", "provenance", "private/"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
