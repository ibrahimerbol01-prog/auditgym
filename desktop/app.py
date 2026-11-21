"""AuditGym desktop app: the same local UI as `python -m auditgym.cli ui`, in its own native window.

This file is a thin wrapper. It is NOT part of src/ (which stays standard-library only) and NOT part of the official
verification, which runs headless in Docker. It only:
  1. starts the existing UI server (auditgym.env.adapters.make_http_server) on a free 127.0.0.1 port,
  2. opens it in a native window with pywebview (falls back to the default browser if pywebview is missing),
  3. in a frozen build, routes `<app> -m auditgym.eval.service` back to the evaluator service, because the
     environment starts the evaluator as `sys.executable -m auditgym.eval.service` and in a frozen build
     sys.executable is this app. The evaluator therefore still runs in its own process, as in every other mode.

Usage:
  python desktop/app.py            open the window
  python desktop/app.py --browser  use the default browser instead of a native window
  python desktop/app.py --smoke    headless self-check: serve, play one episode, exit 0 on success
"""
from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
import threading
import urllib.request

APP_NAME = "AuditGym"
FROZEN = getattr(sys, "frozen", False)
# Frozen: data files sit next to the bundled code. Source checkout: the repository root.
BASE = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if not FROZEN:
    sys.path.insert(0, os.path.join(BASE, "src"))

CHILD_MODULES = ("auditgym.eval.service",)


def build_stamp() -> str:
    """What this build is (written by desktop/build.py); 'source checkout' when run from the repository."""
    try:
        with open(os.path.join(BASE, "data", "BUILD.txt"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return "source checkout"


def run_child_if_requested(argv: list[str]) -> bool:
    """Frozen builds only: act as `python -m <module>` for the evaluator service. Returns True if it ran."""
    if len(argv) >= 3 and argv[1] == "-m":
        module = argv[2]
        if module not in CHILD_MODULES:
            raise SystemExit(f"{APP_NAME}: refusing to run module {module!r}")
        # A windowed (no console) build may start with no Python-level std streams; the parent always passes pipes.
        if sys.stdin is None:
            sys.stdin = open(0, "r", encoding="utf-8", closefd=False)
        if sys.stdout is None:
            sys.stdout = open(1, "w", encoding="utf-8", closefd=False, buffering=1)
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        sys.argv = [module] + argv[3:]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return True
    return False


def data_files(base: str = BASE) -> dict:
    """The read-only public files the UI may fetch under /data/ (same set as cli.ui_extra_files)."""
    data_dir = os.path.join(base, "data") if FROZEN else base
    extra = {}
    for name in ("report.json", "trajectories.jsonl"):
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            extra["/data/" + name] = p
    for split in ("train", "dev"):
        p = os.path.join(data_dir, "configs", f"{split}.json")
        if os.path.exists(p):
            extra[f"/data/{split}.json"] = p
    return extra


def start_server(port: int = 0):
    """Start the UI server in a background thread. Returns (server, env, url)."""
    from auditgym.env.adapters import make_http_server
    from auditgym.harness import Jobs
    srv, env = make_http_server(port, "open", ui=True, extra_files=data_files(), host="127.0.0.1",
                                api=Jobs(configs=os.path.join(BASE, "data", "configs") if FROZEN else None,
                                         # the bundle is read-only: a saved learning curve goes to the user's folder
                                         curve=os.path.join(os.path.expanduser("~"), ".auditgym", "curve.json") if FROZEN else None))
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    threading.Thread(target=srv.serve_forever, name="auditgym-ui", daemon=True).start()
    return srv, env, url


def stop_server(srv, env) -> None:
    srv.shutdown()
    srv.server_close()
    env.close()


def _request(url: str, body: dict | None = None) -> tuple[int, bytes]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # localhost: never through a proxy
    with opener.open(req, timeout=60) as resp:
        return resp.status, resp.read()


def smoke() -> int:
    """Headless self-check used by CI on the built app: static files, data files, one full episode."""
    srv, env, url = start_server()
    try:
        status, page = _request(url)
        assert status == 200 and b"<html" in page.lower(), "index page"
        assert _request(url + "data/train.json")[0] == 200, "train configs"
        first = json.loads(_request(url + "data/train.json")[1])["episodes"][0]
        obs = json.loads(_request(url + "reset", {"seed": first["seed"], "config": first["config"]})[1])["observation"]
        assert obs["ok"] and obs["remaining_steps"] == 100, f"reset: {str(obs)[:200]}"
        episode_id = obs["result"]["manifest"]["episode_id"]
        step = json.loads(_request(url + "step", {"action": {"tool": "list_records",
                                                              "args": {"table": "ledger", "cursor": None, "limit": 5}}})[1])
        assert step["observation"]["ok"] and step["observation"]["remaining_steps"] == 99, f"step: {str(step)[:200]}"
        # Submitting goes through the evaluator service, which runs as a separate process.
        done = json.loads(_request(url + "step", {"action": {"tool": "submit", "args": {
            "findings": {"episode_id": episode_id, "findings": []}}}})[1])
        assert done["terminated"] is True and isinstance(done["reward"], (int, float)), f"submit: {str(done)[:200]}"
        # The runs page: one closed-mode episode through the harness (its own evaluator process), into a temp folder.
        assert _request(url + "runs.html")[0] == 200, "runs page"
        import tempfile
        import time
        os.environ["AUDITGYM_RUNS"] = tempfile.mkdtemp(prefix="auditgym-smoke-")
        started = json.loads(_request(url + "api/runs", {"policy": "reconcile", "split": "dev", "limit": 1})[1])
        assert started.get("ok"), f"start run: {started}"
        run = {}
        for _ in range(300):
            run = json.loads(_request(url + "api/runs/" + started["run"])[1]).get("run") or {}
            if run.get("status") not in (None, "running"):
                break
            time.sleep(0.1)
        assert run.get("status") == "done" and run["summary"]["reward"] > 0.5, f"run: {str(run)[:300]}"
    finally:
        stop_server(srv, env)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if run_child_if_requested(argv):
        return 0
    ap = argparse.ArgumentParser(prog=APP_NAME, description="AuditGym desktop app")
    ap.add_argument("--browser", action="store_true", help="open in the default browser instead of a native window")
    ap.add_argument("--smoke", action="store_true", help="headless self-check, exit code 0 on success")
    ap.add_argument("--smoke-out", help="also write the smoke result to this file (windowed builds have no console)")
    ap.add_argument("--version", action="store_true", help="print which build this is and exit")
    args = ap.parse_args(argv[1:])
    if args.version:
        if sys.stdout:
            print(f"{APP_NAME} {build_stamp()}")
        return 0

    if args.smoke:
        try:
            code = smoke()
            msg = f"AuditGym desktop smoke: OK ({build_stamp()})"
        except Exception as exc:  # noqa: BLE001 - report any failure as a non-zero exit
            code, msg = 1, f"AuditGym desktop smoke: FAILED: {exc!r}"
        if args.smoke_out:
            with open(args.smoke_out, "w", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        if sys.stdout:
            print(msg)
        return code

    srv, env, url = start_server()
    try:
        if not args.browser and open_native_window(url):
            return 0
        import webbrowser
        webbrowser.open(url)
        if sys.stdout:
            print(f"{APP_NAME} is running at {url} (press Ctrl+C or close this terminal to stop)")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return 0
    finally:
        stop_server(srv, env)


def open_native_window(url: str) -> bool:
    """Show the UI in a native window; False if no native window is possible (no pywebview or no GUI backend)."""
    try:
        import webview  # pywebview: optional, installed only for the desktop build
    except ImportError:
        return False
    try:
        webview.create_window(f"{APP_NAME} · {build_stamp()}", url, width=1440, height=900, min_size=(390, 640))
        webview.start()  # returns when the window is closed
        return True
    except Exception:  # noqa: BLE001 - e.g. Linux without GTK/Qt: fall back to the browser
        return False


if __name__ == "__main__":
    sys.exit(main())
