"""Updates for the packaged app: find out whether a newer build exists and install it with the same one-line installer.

Two channels, chosen from the build stamp (BUILD.txt, "<ref> @ <sha> · built ..."):
  * release builds (ref like v0.2.0): the newest release of the public repository, plain HTTPS, no login;
  * team branch builds (any other ref): the newest successful "Desktop app" CI build of that branch, through the
    GitHub CLI (`gh`, logged in), compared by commit.

Installing reuses the installers (desktop/install.ps1, install.sh): they download, check SHA256SUMS, replace the app,
keep the `auditgym` command on PATH and start the new version. The updater starts the installer as a detached process
and the app then exits, so the files can be replaced. Its output goes to ~/.auditgym/update.log.

Standard library only; nothing here runs unless the app is a packaged build (or AUDITGYM_UPDATE_TEST is set).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request

PRIVATE = "ibrahimerbol01-prog/auditgym"           # the repository: CI builds of branches (artifacts need gh)
PUBLIC = PRIVATE                                   # its releases: release builds and their installers, no login
HOME = os.path.join(os.path.expanduser("~"), ".auditgym")
CACHE = os.path.join(HOME, "update.json")
LOG = os.path.join(HOME, "update.log")
TTL = 6 * 3600                                      # check GitHub at most every 6 hours (unauthenticated: 60 calls/h)
WIN = os.name == "nt"


def parse_stamp(stamp: str) -> tuple[str, str]:
    """'v0.2.0 @ 1a2b3c4 · built ...' -> ('v0.2.0', '1a2b3c4'); ('', '') for a source checkout."""
    m = re.match(r"^(\S+) @ ([0-9a-f]{7,40})", stamp or "")
    return (m.group(1), m.group(2)) if m else ("", "")


def built_at(stamp: str) -> str:
    """'... · built 2026-11-21 10:00 UTC' -> '2026-11-21T10:00Z' (comparable with GitHub's published_at); '' if absent."""
    m = re.search(r"built (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}) UTC", stamp or "")
    return f"{m.group(1)}T{m.group(2)}Z" if m else ""


def version_key(tag: str) -> tuple | None:
    """'v1.2.10' -> (1, 2, 10); None if the tag is not a plain release version."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def _get_json(url: str, timeout: float = 6.0):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "auditgym-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
        return json.load(r)


def _gh(*args: str) -> str | None:
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        out = subprocess.run([gh, *args], capture_output=True, text=True, timeout=20,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def latest_release() -> dict | None:
    d = _get_json(f"https://api.github.com/repos/{PUBLIC}/releases/latest")
    tag = d.get("tag_name") or ""
    return {"version": tag, "url": d.get("html_url"), "notes": (d.get("body") or "")[:2000],
            "published": d.get("published_at") or "", "commit": d.get("target_commitish") or ""} if version_key(tag) else None


def latest_branch_build(branch: str) -> dict | None:
    out = _gh("run", "list", "-R", PRIVATE, "--workflow", "desktop.yml", "--branch", branch, "--status", "success",
              "--limit", "1", "--json", "databaseId,headSha,createdAt")
    try:
        runs = json.loads(out) if out else []
    except ValueError:
        runs = []
    if not runs:
        return None
    r = runs[0]
    return {"version": f"{branch} @ {r['headSha'][:7]}", "sha": r["headSha"], "at": r.get("createdAt")}


def check(stamp: str, force: bool = False) -> dict:
    """What the app shows: {current, channel, available, latest, error}. Cached for TTL seconds."""
    ref, sha = parse_stamp(stamp)
    channel = "release" if version_key(ref) else ("branch" if ref else "source")
    res = {"current": stamp, "channel": channel, "available": False, "latest": None, "error": None}
    if channel == "source":
        res["error"] = "source checkout: update with git pull"
        return res
    try:
        with open(CACHE, encoding="utf-8") as fh:
            cached = json.load(fh)
        if not force and cached.get("stamp") == stamp and time.time() - cached.get("checked", 0) < TTL:
            return cached["result"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        if channel == "release":
            rel = latest_release()
            if rel:
                res["latest"] = rel
                res["available"] = version_key(rel["version"]) > version_key(ref)
        else:
            build = latest_branch_build(ref)
            if build is None:
                # No GitHub CLI (or no newer CI build): a test build moves to the public releases as soon as one is
                # newer than itself, so nobody is stuck on a pre-release build; never offers an older release.
                rel, when = latest_release(), built_at(stamp)
                same = bool(sha) and str(rel.get("commit", "") if rel else "").startswith(sha)  # this very build
                if rel and when and rel["published"][:16] > when[:16] and not same:
                    res.update(channel="release", latest=rel, available=True)
                else:
                    res["error"] = ("test build: it updates to the next release once one is published "
                                    "(or to newer test builds through the GitHub CLI: gh auth login)")
            else:
                res["latest"] = build
                res["available"] = not build["sha"].startswith(sha)
    except Exception as exc:  # noqa: BLE001 - offline or rate-limited: no update offer, the app works as before
        res["error"] = f"could not check for updates: {exc.__class__.__name__}"
        return res
    try:
        os.makedirs(HOME, exist_ok=True)
        with open(CACHE, "w", encoding="utf-8") as fh:
            json.dump({"stamp": stamp, "checked": time.time(), "result": res}, fh)
    except OSError:
        pass
    return res


def installer_command(info: dict, detached: bool = True) -> tuple[list[str], dict]:
    """The command that installs `info` (a check() result). Detached (from the app): waits for the app to quit,
    logs to LOG and starts the new version. Not detached (`auditgym update` in a terminal): output to the terminal."""
    env = dict(os.environ)
    for k in ("AUDITGYM_ZIP", "AUDITGYM_BASE_URL", "AUDITGYM_NO_LAUNCH", "AUDITGYM_VERSION", "AUDITGYM_BRANCH"):
        env.pop(k, None)
    name = "install.ps1" if WIN else "install.sh"
    if info["channel"] == "release":
        tag = info["latest"]["version"]
        env["AUDITGYM_VERSION"] = tag
        fetch = f"irm 'https://github.com/{PUBLIC}/releases/download/{tag}/{name}'" if WIN else \
            f"curl -fsSL 'https://github.com/{PUBLIC}/releases/download/{tag}/{name}'"
    else:
        branch = parse_stamp(info["current"])[0]
        env["AUDITGYM_BRANCH"] = branch
        fetch = f'gh api "repos/{PRIVATE}/contents/desktop/{name}?ref={branch}" -H "Accept: application/vnd.github.raw"'
    if WIN:
        run = f"& {{ {fetch} | Out-String | iex }}"
        script = f"Start-Sleep -Seconds 2; {run} *> '{LOG.replace(chr(39), chr(39) * 2)}'" if detached else run
        return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], env
    script = f"sleep 2; {fetch} | sh > '{LOG}' 2>&1" if detached else f"{fetch} | sh"
    return ["/bin/sh", "-c", script], env


def apply(info: dict) -> dict:
    """Start the installer detached (it outlives the app). The caller exits the app right after."""
    if not info.get("available"):
        return {"ok": False, "error": {"code": "no_update", "message": "already the newest version"}}
    os.makedirs(HOME, exist_ok=True)
    cmd, env = installer_command(info)
    kw: dict = {"env": env, "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if WIN:
        cmd[1:1] = ["-WindowStyle", "Hidden"]
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(cmd, **kw)  # noqa: S603 - fixed command built above
    except OSError as exc:
        return {"ok": False, "error": {"code": "spawn_failed", "message": str(exc)}}
    try:
        os.remove(CACHE)
    except OSError:
        pass
    return {"ok": True, "log": LOG}


class UpdateRoutes:
    """Wraps the harness API (Jobs) and adds GET /api/update and POST /api/update for the desktop app."""

    def __init__(self, api, stamp: str, on_exit, busy=lambda: False):
        self.api, self.stamp, self.on_exit, self.busy = api, stamp, on_exit, busy

    def __getattr__(self, name):  # everything else is the harness API
        return getattr(self.api, name)

    def get(self, path: str, query: dict):
        if path == "/api/update":
            return 200, {"ok": True, "update": check(self.stamp, force=query.get("force") == "1")}
        return self.api.get(path, query)

    def post(self, path: str, body):
        if path != "/api/update":
            return self.api.post(path, body)
        if self.busy():
            return 409, {"ok": False, "error": {"code": "busy", "message": "a training or evaluation is running"}}
        info = check(self.stamp)
        res = apply(info)
        if res["ok"]:
            self.on_exit()
        return (200 if res["ok"] else 409), res
