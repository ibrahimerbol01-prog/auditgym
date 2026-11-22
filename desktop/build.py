"""Build the AuditGym desktop app with PyInstaller.

Usage (from the repository root, in a virtual environment):
    python -m pip install -r desktop/requirements-desktop.txt
    python desktop/build.py

Output: dist/AuditGym/ (or dist/AuditGym.app on macOS) with the `auditgym` terminal command in dist/AuditGym/cli/
(macOS: dist/auditgym-cli/), and dist/AuditGym-<os>-<arch>.zip, the file the one-line installers
(desktop/install.ps1, desktop/install.sh) download from a GitHub Release or a CI build.
Nothing here is imported by src/ or by the official verification.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEP = os.pathsep  # PyInstaller --add-data uses ';' on Windows and ':' elsewhere


def build_stamp() -> str:
    """One line that says exactly what was built: tag or branch, commit, UTC time (CI sets the GITHUB_* values)."""
    # a pull-request build is named after its branch (GITHUB_HEAD_REF), not GitHub's temporary "<n>/merge" ref
    # AUDITGYM_REF: the release tag (release.yml sets it, also for a release started by hand from a branch)
    ref = os.environ.get("AUDITGYM_REF") or os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME") or _git("rev-parse", "--abbrev-ref", "HEAD") or "local"
    sha = (os.environ.get("GITHUB_SHA") or _git("rev-parse", "HEAD") or "unknown")[:7]
    when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"{ref} @ {sha} · built {when}"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main() -> int:
    import PyInstaller.__main__

    def add(src: str, dest: str) -> list[str]:
        return ["--add-data", f"{os.path.join(ROOT, src)}{SEP}{dest}"]

    data: list[str] = []
    data += add("src/auditgym/ui/static", "auditgym/ui/static")
    data += add("configs", "data/configs")
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    stamp_file = os.path.join(ROOT, "build", "BUILD.txt")
    with open(stamp_file, "w", encoding="utf-8") as fh:
        fh.write(build_stamp() + "\n")
    data += ["--add-data", f"{stamp_file}{SEP}data"]
    data += add("desktop/icon.png", "data")  # Linux menu entry and window icon
    data += add("LICENSE", "data") + add("desktop/THIRD_PARTY_NOTICES.md", "data")  # licences travel with the app
    for name in ("report.json", "trajectories.jsonl"):
        if os.path.exists(os.path.join(ROOT, name)):
            data += add(name, "data")

    def common(script: str, name: str, work: str) -> list[str]:
        return [os.path.join(ROOT, "desktop", script), "--name", name, "--noconfirm", "--clean",
                "--onedir",             # a folder starts fast and avoids re-extracting for the evaluator process
                "--paths", os.path.join(ROOT, "src"), "--paths", os.path.join(ROOT, "desktop"),
                "--collect-submodules", "auditgym",
                "--workpath", os.path.join(ROOT, "build", work), "--specpath", os.path.join(ROOT, "build", work)] + data

    # 1. the desktop app: no console window on Windows, an .app bundle on macOS
    args = common("app.py", "AuditGym", "app") + ["--windowed", "--hidden-import", "updater", "--distpath", os.path.join(ROOT, "dist")]
    icon = os.path.join(ROOT, "desktop", "icon.ico" if sys.platform == "win32" else "icon.icns")
    if os.path.exists(icon):
        args += ["--icon", icon]
    PyInstaller.__main__.run(args)
    # 2. the `auditgym` terminal command (console program), in its own process so the two builds never mix state
    cli_dist = os.path.join(ROOT, "build", "cli-dist")
    subprocess.run([sys.executable, "-m", "PyInstaller", *common("cli_entry.py", "auditgym", "cli"), "--console", "--hidden-import", "updater",
                    "--distpath", cli_dist], check=True)

    archive = os.path.join(ROOT, "dist", asset_name())
    dist = os.path.join(ROOT, "dist")
    if sys.platform == "darwin":
        # The .app stays untouched (adding files inside would break its signature); the command sits next to it.
        shutil.rmtree(os.path.join(dist, "auditgym-cli"), ignore_errors=True)
        subprocess.run(["ditto", os.path.join(cli_dist, "auditgym"), os.path.join(dist, "auditgym-cli")], check=True)
        stage = os.path.join(ROOT, "build", "mac-stage")
        shutil.rmtree(stage, ignore_errors=True)
        os.makedirs(stage)
        for name in ("AuditGym.app", "auditgym-cli"):  # ditto keeps symlinks and permissions; a plain zip would not
            subprocess.run(["ditto", os.path.join(dist, name), os.path.join(stage, name)], check=True)
        for name in ("LICENSE", "desktop/THIRD_PARTY_NOTICES.md"):
            shutil.copy(os.path.join(ROOT, name), os.path.join(stage, os.path.basename(name)))
        subprocess.run(["ditto", "-c", "-k", stage, archive], check=True)
    else:
        target = os.path.join(dist, "AuditGym", "cli")
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(os.path.join(cli_dist, "auditgym"), target, symlinks=True)
        for name in ("LICENSE", "desktop/THIRD_PARTY_NOTICES.md"):  # visible next to the program, too
            shutil.copy(os.path.join(ROOT, name), os.path.join(dist, "AuditGym", os.path.basename(name)))
        shutil.make_archive(archive[: -len(".zip")], "zip", dist, "AuditGym")
    shutil.copy(stamp_file, os.path.join(dist, "BUILD.txt"))
    with open(archive, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    with open(os.path.join(dist, "SHA256SUMS.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{digest}  {os.path.basename(archive)}\n")
    print(f"built {archive} ({build_stamp()})")
    return 0


def asset_name() -> str:
    """Stable release file names the installers look for: AuditGym-<os>-<arch>.zip."""
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"AuditGym-{system}-{arch}.zip"


if __name__ == "__main__":
    sys.exit(main())
