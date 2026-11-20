"""Build the AuditGym desktop app with PyInstaller.

Usage (from the repository root, in a virtual environment):
    python -m pip install -r desktop/requirements-desktop.txt
    python desktop/build.py

Output: dist/AuditGym/ (or dist/AuditGym.app on macOS) and dist/AuditGym-<os>-<arch>.zip, the file the
one-line installers (desktop/install.ps1, desktop/install.sh) download from a GitHub Release.
Nothing here is imported by src/ or by the official verification.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEP = os.pathsep  # PyInstaller --add-data uses ';' on Windows and ':' elsewhere


def main() -> int:
    import PyInstaller.__main__

    def add(src: str, dest: str) -> list[str]:
        return ["--add-data", f"{os.path.join(ROOT, src)}{SEP}{dest}"]

    args = [
        os.path.join(ROOT, "desktop", "app.py"),
        "--name", "AuditGym",
        "--noconfirm", "--clean",
        "--onedir",                     # a folder starts fast and avoids re-extracting for the evaluator process
        "--windowed",                   # no console window on Windows / an .app bundle on macOS
        "--paths", os.path.join(ROOT, "src"),
        "--collect-submodules", "auditgym",
        "--distpath", os.path.join(ROOT, "dist"),
        "--workpath", os.path.join(ROOT, "build", "pyinstaller"),
        "--specpath", os.path.join(ROOT, "build"),
    ]
    args += add("src/auditgym/ui/static", "auditgym/ui/static")
    args += add("configs", "data/configs")
    for name in ("report.json", "trajectories.jsonl"):
        if os.path.exists(os.path.join(ROOT, name)):
            args += add(name, "data")
    icon = os.path.join(ROOT, "desktop", "icon.ico" if sys.platform == "win32" else "icon.icns")
    if os.path.exists(icon):
        args += ["--icon", icon]
    PyInstaller.__main__.run(args)

    archive = os.path.join(ROOT, "dist", asset_name())
    dist = os.path.join(ROOT, "dist")
    if sys.platform == "darwin":
        # ditto keeps the .app bundle's symlinks and permissions, which a plain zip would break
        subprocess.run(["ditto", "-c", "-k", "--keepParent", os.path.join(dist, "AuditGym.app"), archive], check=True)
    else:
        shutil.make_archive(archive[: -len(".zip")], "zip", dist, "AuditGym")
    print(f"built {archive}")
    return 0


def asset_name() -> str:
    """Stable release file names the installers look for: AuditGym-<os>-<arch>.zip."""
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    return f"AuditGym-{system}-{arch}.zip"


if __name__ == "__main__":
    sys.exit(main())
