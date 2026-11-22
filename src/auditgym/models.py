"""Preloaded models: download ready-made auditors (and, through Ollama, small local LLMs) so the app has something to
evaluate before anyone trains.

The catalogue is ``models/index.json`` in the repository (a checkout reads it from disk; installed builds download it
from GitHub over HTTPS). An auditor model is the complete run.json of one real training (``train/make_models.py``):
installing it checks the file's SHA-256 against the catalogue, checks its shape (a finished training whose policy is
20 finite numbers), and writes it into the runs folder, where the app lists it like any training (Training page,
Runs → model). Model files are data only: nothing in them is executed. Local LLMs are never stored here; installing
one runs ``ollama pull <name>`` when Ollama is installed.

Optional: nothing in the environment, the evaluator or ``verify`` needs these models or the network.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from . import harness

REMOTE = "https://raw.githubusercontent.com/ibrahimerbol01-prog/auditgym/main/models/"
LOCAL = os.path.join(harness.ROOT, "models")
MAX_BYTES = 2_000_000
NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{0,47}$")
PREFIX = "preloaded-"


class ModelError(Exception):
    pass


def source() -> str:
    """Where the catalogue comes from: AUDITGYM_MODELS_URL, else the checkout's models/ folder, else GitHub."""
    env = os.environ.get("AUDITGYM_MODELS_URL")
    if env:
        return env if env.endswith("/") else env + "/"
    return LOCAL + os.sep if os.path.isfile(os.path.join(LOCAL, "index.json")) else REMOTE


def _fetch(name: str, src: Optional[str] = None) -> bytes:
    src = src or source()
    if "/" in name or "\\" in name or ".." in name:
        raise ModelError(f"bad file name {name!r}")
    if src.startswith("https://"):
        req = urllib.request.Request(src + name, headers={"User-Agent": "auditgym-models"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 - fixed https base
                data = r.read(MAX_BYTES + 1)
        except OSError as exc:
            raise ModelError(f"could not download {name}: {exc}") from exc
    elif src.startswith("http://127.0.0.1:"):  # tests only: a local server
        with urllib.request.urlopen(src + name, timeout=20) as r:  # noqa: S310
            data = r.read(MAX_BYTES + 1)
    else:
        try:
            with open(os.path.join(src, name), "rb") as fh:
                data = fh.read(MAX_BYTES + 1)
        except OSError as exc:
            raise ModelError(f"could not read {name}: {exc}") from exc
    if len(data) > MAX_BYTES:
        raise ModelError(f"{name} is larger than {MAX_BYTES} bytes")
    return data


def catalogue(src: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        index = json.loads(_fetch("index.json", src))
    except ValueError as exc:
        raise ModelError("the model catalogue is not valid JSON") from exc
    out = []
    for m in index.get("models") or []:
        if isinstance(m, dict) and isinstance(m.get("name"), str) and NAME.match(m["name"]) and m.get("kind") in ("auditor", "ollama"):
            out.append(m)
    return out


def _valid_run(run: Any, name: str) -> Dict[str, Any]:
    from .learner import N_PARAMS
    if not isinstance(run, dict) or run.get("kind") != "training" or run.get("status") != "done":
        raise ModelError(f"{name}: not a finished training")
    if run.get("id") != PREFIX + name or not harness.RUN_ID.match(run["id"]):
        raise ModelError(f"{name}: unexpected id {str(run.get('id'))[:60]!r}")
    theta = (run.get("best") or {}).get("theta")
    if not (isinstance(theta, list) and len(theta) == N_PARAMS and
            all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in theta)):
        raise ModelError(f"{name}: the policy must be {N_PARAMS} finite numbers")
    return run


def runs_folder() -> str:
    return harness.runs_dir()


def installed(base: Optional[str] = None) -> Dict[str, bool]:
    base = base or runs_folder()
    out = {}
    for m in catalogue():
        if m["kind"] == "auditor":
            out[m["name"]] = os.path.isfile(os.path.join(base, PREFIX + m["name"], "run.json"))
        else:
            out[m["name"]] = m.get("ollama") in ollama_models()
    return out


def ollama_models() -> List[str]:
    from .policies import llm
    res = llm.list_models(timeout=1.0)
    return [m.get("name") for m in res.get("models") or [] if isinstance(m, dict)] if res.get("available") else []


def install(entry: Dict[str, Any], base: Optional[str] = None, src: Optional[str] = None,
            say: Callable[[str], None] = print) -> bool:
    """Install one catalogue entry. Returns True on success; explains failures through ``say``."""
    name = entry["name"]
    if entry["kind"] == "auditor":
        data = _fetch(entry.get("file") or "", src)
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise ModelError(f"{name}: checksum mismatch, not installed")
        try:
            run = _valid_run(json.loads(data), name)
        except ValueError as exc:
            raise ModelError(f"{name}: not valid JSON") from exc
        folder = os.path.join(base or runs_folder(), run["id"])
        os.makedirs(folder, exist_ok=True)
        harness._write_json(os.path.join(folder, "run.json"), run)
        say(f"  installed {name}: open the app → Runs → model “{entry.get('title', name)}”")
        return True
    from .policies.llm import valid_model_name
    tag = entry.get("ollama")
    if not valid_model_name(tag):
        raise ModelError(f"{name}: bad Ollama model name")
    exe = shutil.which("ollama")
    if not exe:
        say(f"  skipped {name}: needs Ollama (https://ollama.com), then run: ollama pull {tag}")
        return False
    say(f"  downloading {name} through Ollama (about {entry.get('download_mb', '?')} MB)…")
    return subprocess.run([exe, "pull", tag]).returncode == 0  # noqa: S603 - fixed program, validated name


def table(models: List[Dict[str, Any]], have: Dict[str, bool]) -> List[str]:
    lines = []
    for i, m in enumerate(models, 1):
        size = f"{m['bytes'] // 1024 + 1} KB" if m["kind"] == "auditor" else f"{m.get('download_mb', '?')} MB"
        score = f"test {m['test_reward']:+.2f}" if isinstance(m.get("test_reward"), (int, float)) else "via Ollama"
        mark = "installed" if have.get(m["name"]) else ""
        lines.append(f"  {i}. {m.get('title', m['name']):46s} {size:>7s}  {score:11s} {mark}")
        lines.append(f"     {m.get('description', '')}")
    return lines


def choose(answer: str, models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """'a' / 'all' → every model; '1,3' or '1 3' → those; 'auditors' → the small ones; anything else → none."""
    a = (answer or "").strip().lower()
    if a in ("a", "all", "y", "yes"):
        return list(models)
    if a in ("auditors", "small", "s"):
        return [m for m in models if m["kind"] == "auditor"]
    picked = []
    for tok in re.split(r"[\s,]+", a):
        if tok.isdigit() and 1 <= int(tok) <= len(models) and models[int(tok) - 1] not in picked:
            picked.append(models[int(tok) - 1])
    return picked


def main(argv: List[str]) -> int:
    """`auditgym models [list | install NAME... | install all | --ask]`."""
    ask = "--ask" in argv
    args = [a for a in argv if a != "--ask"]
    try:
        models = catalogue()
    except ModelError as exc:
        print(f"AuditGym models: {exc}", file=sys.stderr)
        return 0 if ask else 1  # the installer never fails because the catalogue is unreachable
    try:
        have = installed()
    except ModelError:
        have = {}
    if ask:
        print("\nAuditGym can download ready-made models, so you can evaluate one without training first:\n")
        print("\n".join(table(models, have)))
        try:
            answer = input("\nDownload which? [a] all, [s] the small auditors only, numbers like 1,3, or Enter to skip: ")
        except (EOFError, KeyboardInterrupt):
            answer = ""
        picked = choose(answer, models)
    elif args[:1] == ["install"]:
        names = args[1:]
        picked = list(models) if names == ["all"] else [m for m in models if m["name"] in names]
        unknown = sorted(set(names) - {m["name"] for m in models} - {"all"})
        if unknown or not names:
            print("unknown model(s): " + ", ".join(unknown) if unknown else "name a model, or: install all", file=sys.stderr)
            return 2
    else:
        print(f"Models from {source()}\n")
        print("\n".join(table(models, have)))
        print("\nInstall: auditgym models install NAME | all")
        return 0
    if not picked:
        print("No models downloaded. Later: auditgym models")
        return 0
    ok = True
    for m in picked:
        try:
            ok = install(m) and ok
        except ModelError as exc:
            print(f"  {exc}", file=sys.stderr)
            ok = False
    return 0 if ok or ask else 1
