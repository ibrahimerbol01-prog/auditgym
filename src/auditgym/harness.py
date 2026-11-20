"""Local harness: run an agent over the train or dev split in closed mode and record the run.

Used by the terminal (``python -m auditgym.cli run-agent``) and by the app's "Обучение и оценка" page.
This is organizer-side code: it owns the evaluator client and reads per-episode scores with ``finalize``,
keeping only the public metrics. The agent only ever sees observations; in closed mode they carry no reward.

A run is a folder ``<runs dir>/<run id>/`` with ``run.json`` (summary, rewritten as the run goes) and
``steps.jsonl`` (one compact line per step: tool, short arguments, ok / error code, rows, steps left).
Record contents are not stored, only counts.

Agents:
- built-in policies: ``reconcile``, ``random``, ``flag_all`` (the oracle needs the answer, so it is not offered);
- any program (``--cmd``): one process per episode, reads one observation (JSON) per line on stdin and writes
  one action (JSON) per line on stdout, exactly the AuditEnv action contract.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .env.env import AuditEnv
from .eval.service import ServiceClient
from .policies.baselines import FlagAllPolicy, Policy, RandomPolicy, ReconcilePolicy
from .version import ENV_VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILTIN = {"reconcile": ReconcilePolicy, "random": RandomPolicy, "flag_all": FlagAllPolicy}
SPLITS = ("dev", "train")
RUN_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,79}$")
PUBLIC_SCORE = ("status", "reward", "precision", "recall", "f1", "tp", "fp", "fn", "inspection_steps")


def runs_dir() -> str:
    return os.environ.get("AUDITGYM_RUNS") or os.path.join(os.path.expanduser("~"), ".auditgym", "runs")


def configs_dir() -> str:
    return os.environ.get("AUDITGYM_CONFIGS") or os.path.join(ROOT, "configs")


def episode_label(cfg: Dict[str, Any]) -> str:
    """Short label from the PUBLIC config only (never from the hidden answer)."""
    if cfg.get("clean"):
        extra = [c for c in cfg.get("foreign_currencies", []) if c not in ("EUR", "USD")]
        return "чистая" + (" · " + "/".join(extra) if extra else "")
    if cfg.get("interactions"):
        return "взаимод. " + "+".join(cfg["interactions"])
    n = sum(cfg.get("errors", {}).values())
    if n:
        return f"{n} ош."
    return "смешанная"


def load_split(split: str, base: Optional[str] = None) -> List[Dict[str, Any]]:
    if split not in SPLITS:
        raise ValueError("split must be dev or train")
    with open(os.path.join(base or configs_dir(), f"{split}.json"), encoding="utf-8") as fh:
        spec = json.load(fh)
    return [{"seed": e["seed"], "config": e["config"], "label": episode_label(e["config"])} for e in spec["episodes"]]


def brief_args(action: Any) -> Dict[str, Any]:
    """Short, display-only arguments of an action (never the full findings)."""
    args = action.get("args") if isinstance(action, dict) else None
    if not isinstance(args, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in ("table", "cursor", "id", "doc_id", "expression"):
        v = args.get(k)
        if isinstance(v, (str, int)) and not isinstance(v, bool):
            out[k] = v if not isinstance(v, str) else v[:60]
    f = args.get("findings")
    if isinstance(f, dict) and isinstance(f.get("findings"), list):
        out["findings"] = len(f["findings"])
    elif "findings" in args:
        out["findings"] = None
    return out


class SubprocessAgent(Policy):
    """An external program: one process per episode, JSON lines on stdin / stdout."""
    name = "cmd"

    def __init__(self, cmd: str, timeout: float = 120.0) -> None:
        if not cmd or not cmd.strip():
            raise ValueError("empty command")
        # POSIX: split like a shell (no shell is started). Windows: CreateProcess parses the string itself.
        self.argv = cmd if os.name == "nt" else shlex.split(cmd)
        self.timeout = timeout
        self.proc: Optional[subprocess.Popen] = None
        self.stderr_tail: List[str] = []

    def reset(self, first_obs):
        super().reset(first_obs)
        self.close()
        self.proc = subprocess.Popen(self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", bufsize=1)
        threading.Thread(target=self._drain, args=(self.proc,), daemon=True).start()

    def _drain(self, proc) -> None:
        for line in proc.stderr:
            self.stderr_tail = (self.stderr_tail + [line.rstrip()])[-5:]

    def act(self, obs):
        give_up = {"tool": "submit", "args": {"findings": None}}  # an invalid structure scores -1, honestly
        p = self.proc
        if p is None or p.poll() is not None:
            return give_up
        try:
            p.stdin.write(json.dumps(obs, ensure_ascii=False) + "\n")
            p.stdin.flush()
        except (BrokenPipeError, OSError):
            return give_up
        box: List[str] = []
        t = threading.Thread(target=lambda: box.append(p.stdout.readline()), daemon=True)
        t.start()
        t.join(self.timeout)
        if not box or not box[0].strip():
            return give_up
        try:
            action = json.loads(box[0])
        except ValueError:
            return {"tool": "unparseable_action", "args": {}}
        return action if isinstance(action, dict) else {"tool": "unparseable_action", "args": {}}

    def close(self) -> None:
        if self.proc is not None:
            try:
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


def make_agent(policy: Optional[str] = None, cmd: Optional[str] = None) -> Callable[[], Policy]:
    if cmd:
        agent = SubprocessAgent(cmd)
        return lambda: agent
    if policy not in BUILTIN:
        raise ValueError(f"unknown policy {policy!r}; choose one of {', '.join(BUILTIN)}")
    return BUILTIN[policy]


def new_run_id(agent: str, split: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", agent.lower()).strip("-")[:24] or "agent"
    return f"{slug}-{split}-{stamp}"


def _write_json(path: str, obj: Any) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def summarize(episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    done = [e for e in episodes if e.get("score")]
    if not done:
        return {"episodes_done": 0}
    mean = lambda k: round(sum(e["score"].get(k, 0.0) for e in done) / len(done), 4)
    scored = [e for e in done if e["score"].get("status") == "scored"]
    tp, fp, fn = (sum(e["score"].get(k, 0) for e in scored) for k in ("tp", "fp", "fn"))
    # Micro averages over all findings of scored episodes: a clean episode (nothing to find, nothing claimed)
    # adds nothing; an invalid or truncated submission has no findings to count and is reported separately.
    if scored:
        p = tp / (tp + fp) if tp + fp else (1.0 if fn == 0 else 0.0)
        r = tp / (tp + fn) if tp + fn else 1.0
    else:
        p = r = 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return {"episodes_done": len(done), "reward": mean("reward"), "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn, "not_scored": len(done) - len(scored), "steps": round(sum(e["steps"] for e in done) / len(done), 2),
            "seconds": round(sum(e["seconds"] for e in done), 2)}


def run_split(agent_name: str, make: Callable[[], Policy], split: str = "dev", limit: Optional[int] = None,
              run_id: Optional[str] = None, base: Optional[str] = None, configs: Optional[str] = None,
              on_event: Optional[Callable[[Dict[str, Any]], None]] = None, stop: Optional[threading.Event] = None,
              time_limit: Optional[float] = None, pace: float = 0.0) -> Dict[str, Any]:
    """Run ``make()`` on every episode of the split in closed mode; returns the run summary (also on disk).

    ``pace`` (seconds) waits before each step so a fast run can be watched; it is recorded in run.json and
    excluded from the measured seconds."""
    eps = load_split(split, configs)[: limit or None]
    run_id = run_id or new_run_id(agent_name, split)
    if not RUN_ID.match(run_id):
        raise ValueError("bad run id")
    folder = os.path.join(base or runs_dir(), run_id)
    os.makedirs(folder, exist_ok=True)
    emit = on_event or (lambda e: None)
    run: Dict[str, Any] = {"id": run_id, "kind": "evaluation", "agent": agent_name, "split": split, "mode": "closed",
                           "env_version": ENV_VERSION, "pace": pace, "status": "running", "started": time.time(), "finished": None,
                           "episodes": [{"index": i, "seed": e["seed"], "label": e["label"], "status": "queued"} for i, e in enumerate(eps)],
                           "summary": {"episodes_done": 0}}
    _write_json(os.path.join(folder, "run.json"), run)
    emit({"type": "run_start", "run": run})
    svc = ServiceClient()
    kw = {} if time_limit is None else {"time_limit": time_limit}
    env = AuditEnv(mode="closed", service=svc, run_id=run_id, **kw)
    steps_fh = open(os.path.join(folder, "steps.jsonl"), "w", encoding="utf-8")
    policy = None
    try:
        for i, e in enumerate(eps):
            if stop is not None and stop.is_set():
                run["status"] = "stopped"
                break
            rec = run["episodes"][i]
            rec["status"] = "running"
            t0 = time.perf_counter()
            obs, _ = env.reset(seed=e["seed"], config=e["config"])
            if not obs.get("ok"):
                rec.update(status="error", error="bad_config")
                continue
            rec["episode_id"] = obs["result"]["manifest"]["episode_id"]
            _write_json(os.path.join(folder, "run.json"), run)
            emit({"type": "episode_start", "index": i, "episode": rec})
            policy = make()
            policy.reset(obs)
            last, n, done, waited = obs, 0, False, 0.0
            while not done:
                if stop is not None and stop.is_set():
                    break
                if pace:
                    time.sleep(pace)
                    waited += pace
                action = policy.act(last)
                last, _r, terminated, truncated, _info = env.step(action)
                n += 1
                done = terminated or truncated
                res = last.get("result") if isinstance(last.get("result"), dict) else {}
                line = {"ep": i, "n": n, "tool": action.get("tool") if isinstance(action, dict) else None,
                        "args": brief_args(action), "ok": bool(last.get("ok")) or truncated,
                        "error": (last.get("error") or {}).get("code"), "rows": len(res["rows"]) if isinstance(res.get("rows"), list) else None,
                        "left": last.get("remaining_steps"), "truncated": truncated}
                steps_fh.write(json.dumps(line, ensure_ascii=False) + "\n")
                steps_fh.flush()
                emit({"type": "step", **line})
            if isinstance(policy, SubprocessAgent):
                policy.close()
            if not done:  # stopped mid-episode
                run["status"] = "stopped"
                rec["status"] = "stopped"
                break
            results = svc.call({"cmd": "finalize", "run_id": run_id}).get("results") or [{}]
            score = {k: results[-1][k] for k in PUBLIC_SCORE if k in results[-1]}
            rec.update(status="done", steps=n, seconds=round(time.perf_counter() - t0 - waited, 3), score=score)
            run["summary"] = summarize(run["episodes"])
            _write_json(os.path.join(folder, "run.json"), run)
            emit({"type": "episode_end", "index": i, "episode": rec, "summary": run["summary"]})
        else:
            run["status"] = "done"
    except Exception as exc:  # noqa: BLE001 - a broken agent or config ends the run with a readable status
        run["status"] = "error"
        run["error"] = str(exc)[:200]
    finally:
        steps_fh.close()
        if isinstance(policy, SubprocessAgent):
            policy.close()
        env.close()
        run["finished"] = time.time()
        run["summary"] = summarize(run["episodes"])
        _write_json(os.path.join(folder, "run.json"), run)
        emit({"type": "run_end", "run": run})
    return run


# ---------------------------------------------------------------- read side (app and terminal)
def list_runs(base: Optional[str] = None) -> List[Dict[str, Any]]:
    base = base or runs_dir()
    out = []
    if os.path.isdir(base):
        for name in os.listdir(base):
            p = os.path.join(base, name, "run.json")
            if RUN_ID.match(name) and os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as fh:
                        r = json.load(fh)
                except (OSError, ValueError):
                    continue
                out.append({k: r.get(k) for k in ("id", "kind", "agent", "split", "mode", "status", "started", "finished", "summary")}
                           | {"episodes": len(r.get("episodes", []))})
    return sorted(out, key=lambda r: r.get("started") or 0, reverse=True)


def read_run(run_id: str, base: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not RUN_ID.match(run_id or ""):
        return None
    p = os.path.join(base or runs_dir(), run_id, "run.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def read_steps(run_id: str, episode: int, base: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    if not RUN_ID.match(run_id or ""):
        return None
    p = os.path.join(base or runs_dir(), run_id, "steps.jsonl")
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError):
        return None
    return [r for r in rows if r.get("ep") == episode]


class Jobs:
    """At most one run at a time, started from the app with a built-in policy (never an arbitrary command)."""

    def __init__(self, base: Optional[str] = None, configs: Optional[str] = None, curve: Optional[str] = None) -> None:
        self.base, self.configs = base, configs
        self.curve_path = curve or os.path.join(ROOT, "train", "curve.json")
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.stop_ev = threading.Event()
        self.current: Optional[str] = None

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, policy: Any, split: Any, limit: Any = None, pace: Any = 0.0) -> Dict[str, Any]:
        if policy not in BUILTIN or split not in SPLITS:
            return {"ok": False, "error": {"code": "bad_arguments", "message": "policy must be reconcile, random or flag_all; split dev or train"}}
        if limit is not None and not (isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= 10):
            return {"ok": False, "error": {"code": "bad_arguments", "message": "limit must be 1..10"}}
        if not (isinstance(pace, (int, float)) and not isinstance(pace, bool) and 0 <= pace <= 0.5):
            return {"ok": False, "error": {"code": "bad_arguments", "message": "pace must be 0..0.5 seconds"}}
        with self.lock:
            if self.busy():
                return {"ok": False, "error": {"code": "busy", "message": "another run is in progress", "run": self.current}}
            run_id = new_run_id(policy, split)
            n = 1
            while os.path.exists(os.path.join(self.base or runs_dir(), run_id)):
                n += 1
                run_id = f"{new_run_id(policy, split)}-{n}"
            self.stop_ev = threading.Event()
            self.current = run_id
            self.thread = threading.Thread(target=run_split, daemon=True, kwargs=dict(
                agent_name=policy, make=BUILTIN[policy], split=split, limit=limit, run_id=run_id, base=self.base,
                configs=self.configs, stop=self.stop_ev, pace=float(pace)))
            self.thread.start()
        return {"ok": True, "run": run_id}

    def stop(self, run_id: str) -> Dict[str, Any]:
        if self.busy() and run_id == self.current:
            self.stop_ev.set()
            return {"ok": True}
        return {"ok": False, "error": {"code": "not_running", "message": "this run is not running"}}

    # HTTP routes: return (status, json)
    def get(self, path: str, query: Dict[str, str]):
        if path == "/api/curve":  # the trainer's learning curve (T10), or null until it has run
            try:
                with open(self.curve_path, encoding="utf-8") as fh:
                    return 200, {"ok": True, "curve": json.load(fh)}
            except (OSError, ValueError):
                return 200, {"ok": True, "curve": None}
        if path == "/api/runs":
            return 200, {"ok": True, "runs": list_runs(self.base), "running": self.current if self.busy() else None,
                         "policies": list(BUILTIN), "splits": list(SPLITS)}
        m = re.match(r"^/api/runs/([^/]+)$", path)
        if m:
            r = read_run(m.group(1), self.base)
            return (200, {"ok": True, "run": r}) if r else (404, {"ok": False, "error": {"code": "not_found", "message": "no such run"}})
        m = re.match(r"^/api/runs/([^/]+)/steps$", path)
        if m:
            ep = query.get("episode", "")
            rows = read_steps(m.group(1), int(ep), self.base) if ep.isdigit() and len(ep) < 4 else None
            return (200, {"ok": True, "steps": rows}) if rows is not None else (404, {"ok": False, "error": {"code": "not_found", "message": "no such run or episode"}})
        return None

    def post(self, path: str, body: Any):
        b = body if isinstance(body, dict) else {}
        if path == "/api/runs":
            res = self.start(b.get("policy"), b.get("split", "dev"), b.get("limit"), b.get("pace", 0.0))
            return (200 if res["ok"] else (409 if res["error"]["code"] == "busy" else 400)), res
        m = re.match(r"^/api/runs/([^/]+)/stop$", path)
        if m:
            res = self.stop(m.group(1))
            return (200 if res["ok"] else 409), res
        return None


if __name__ == "__main__":  # pragma: no cover - convenience
    print(json.dumps(list_runs(), indent=1, ensure_ascii=False))
    sys.exit(0)
