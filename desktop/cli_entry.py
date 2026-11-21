"""`auditgym` terminal command in the packaged build: `python -m auditgym.cli` without Python or the repository.

The installers put it on PATH next to the desktop app, e.g. `auditgym run-agent --policy reconcile`. Like the app,
it answers `<exe> -m auditgym.eval.service` by running the evaluator (the environment starts the evaluator as
`sys.executable -m auditgym.eval.service`, and in a frozen build sys.executable is this program), so scoring still
happens in a separate process. Not part of src/ or of the official verification.
"""
from __future__ import annotations

import os
import sys

FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(__file__))
if not FROZEN:
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))
    sys.path.insert(0, HERE)

from app import BASE, build_stamp, run_child_if_requested  # noqa: E402  (desktop/app.py; no GUI import at load)


def update(stamp: str) -> int:
    """`auditgym update`: install the newest build (app and terminal command) with the one-line installer."""
    import updater
    info = updater.check(stamp, force=True)
    if info.get("error") and not info.get("latest"):
        print(f"auditgym update: {info['error']}")
        return 1
    if not info["available"]:
        print(f"auditgym is up to date ({stamp})")
        return 0
    print(f"auditgym update: {stamp}  ->  {info['latest']['version']}")
    import subprocess
    if os.name == "nt":
        # Windows cannot replace a running program: the installer runs in its own window after this command exits.
        cmd, env = updater.installer_command(info, detached=False)
        env["AUDITGYM_NO_LAUNCH"] = "1"
        cmd[-1] = "Start-Sleep -Seconds 1; " + cmd[-1] + "; Read-Host 'Press Enter to close'"
        subprocess.Popen(cmd, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE)
        print("the installer opened in a new window; open a new terminal when it is done")
        return 0
    cmd, env = updater.installer_command(info, detached=False)
    env["AUDITGYM_NO_LAUNCH"] = "1"
    return subprocess.call(cmd, env=env)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if run_child_if_requested(argv):
        return 0
    for stream in (sys.stdout, sys.stderr):  # Cyrillic and block characters on any Windows code page
        if stream is not None and (getattr(stream, "encoding", "") or "").lower().replace("-", "") != "utf8":
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    if FROZEN:
        data = os.path.join(BASE, "data")
        os.environ.setdefault("AUDITGYM_DATA", data)
        os.environ.setdefault("AUDITGYM_CONFIGS", os.path.join(data, "configs"))
    if argv[1:2] in (["--version"], ["version"]):
        print(f"auditgym {build_stamp()}")
        return 0
    if argv[1:2] == ["update"]:
        return update(build_stamp())
    from auditgym.cli import main as cli_main
    return cli_main(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
