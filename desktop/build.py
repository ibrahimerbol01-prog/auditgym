"""Build the AuditGym desktop app with PyInstaller.

Usage (from the repository root, in a virtual environment):
    python -m pip install -r desktop/requirements-desktop.txt
    python desktop/build.py

Output: dist/AuditGym/ (a folder with the AuditGym executable) and dist/AuditGym-<os>.zip to hand out.
Nothing here is imported by src/ or by the official verification.
"""
from __future__ import annotations

import os
import platform
import shutil
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

    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    archive = os.path.join(ROOT, "dist", f"AuditGym-{system}-{platform.machine().lower()}")
    shutil.make_archive(archive, "zip", os.path.join(ROOT, "dist"), "AuditGym")
    print(f"built {archive}.zip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
