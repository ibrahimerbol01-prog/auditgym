"""Local harness: run an agent over the train or dev split in closed mode and record the run.

Used by the terminal (``python -m auditgym.cli run-agent``) and by the app's "Обучение и оценка" page.
This is organizer-side code: it owns the evaluator client and reads per-episode scores with ``finalize``,
keeping only the public metrics. The agent only ever sees observations; in closed mode they carry no reward.

A run is a folder ``<runs dir>/<run id>/`` with ``run.json`` (summary, rewritten as the run goes) and
``steps.jsonl`` (one compact line per step: tool, short arguments, ok / error code, rows, steps left).
Record contents are not stored, only counts.

Agents:
- built-in policies: ``reconcile``, ``random``, ``flag_all`` (the oracle needs the answer, so it is not offered);
- a local LLM through Ollama on 127.0.0.1 (``policy="llm"`` + an installed ``llm_model``; policies/llm.py), in-process;
  with ``assist: true`` the model judges candidates that code reads and proposes (policies/llm_assist.py);
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
from .policies import llm as _llm
from .policies.baselines import FlagAllPolicy, Policy, RandomPolicy, ReconcilePolicy
from .version import ENV_VERSION

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BUILTIN = {"reconcile": ReconcilePolicy, "random": RandomPolicy, "flag_all": FlagAllPolicy}
LLM_DEFAULT_LIMIT = 3                     # local LLMs are slow: a few episodes unless asked for more (1..20)
SPLITS = ("dev", "train")                 # the open episode files in configs/
EVAL_SPLITS = ("dev", "train", "test")     # "test": 20 fresh episodes never used for training or model choice
TRAIN_PRESETS = ("mixed", "simple", "interacting")
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
    if split == "test":
        from .learner import test_split  # generated, not a file: see learner.test_split
        return test_split(base)
    if split not in SPLITS:
        raise ValueError("split must be dev, train or test")
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
        try:
            for line in proc.stderr:
                self.stderr_tail = (self.stderr_tail + [line.rstrip()])[-5:]
        except (OSError, ValueError):   # close() closed the pipe: the episode is over
            pass

    @staticmethod
    def _read_line(stream, box: List[str]) -> None:
        try:
            box.append(stream.readline())
        except (OSError, ValueError):   # closed under a reader that timed out
            pass

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
        t = threading.Thread(target=self._read_line, args=(p.stdout, box), daemon=True)
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
            p, self.proc = self.proc, None
            try:
                p.stdin.close()
            except OSError:
                pass
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
                try:
                    p.wait(timeout=2)      # reap it: no zombie on POSIX, no open process handle on Windows
                except subprocess.TimeoutExpired:
                    pass
            for f in (p.stdout, p.stderr):  # every episode starts a new process: close its pipes, do not wait for GC
                try:
                    f.close()
                except (OSError, ValueError):
                    pass


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
    # Windows refuses to replace a file another thread is reading at that moment (the app polls run.json while the
    # run writes it): retry briefly instead of failing the run.
    for attempt in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.02)


class Analysis:
    """Measured failure analysis of one run, from the organizer's results: which error types were caught or
    missed, what types the false findings claimed, and the reward by kind of episode. Collected per episode,
    written to run.json only at the end of the run. Near-miss reasons are deliberately left out: like the
    evaluator's public report, nothing on disk tells an agent which wrong hypothesis was close."""

    def __init__(self) -> None:
        self.by_type: Dict[str, Dict[str, int]] = {}
        self.false_by_type: Dict[str, int] = {}
        self.by_label: Dict[str, List[float]] = {}

    def add(self, result: Dict[str, Any], action: Any, label: str) -> None:
        for t, v in (result.get("per_type") or {}).items():
            d = self.by_type.setdefault(t, {"issues": 0, "found": 0})
            d["issues"] += int(v.get("issues", 0))
            d["found"] += int(v.get("found", 0))
        claims = submitted_findings(action)
        for pf in result.get("per_finding") or []:
            if pf.get("matched"):
                continue
            i = pf.get("index")
            t = claims[i].get("type") if isinstance(i, int) and 0 <= i < len(claims) and isinstance(claims[i], dict) else None
            t = t if isinstance(t, str) and len(t) < 40 else "invalid"
            self.false_by_type[t] = self.false_by_type.get(t, 0) + 1
        if isinstance(result.get("reward"), (int, float)):
            kind = "clean" if label.startswith("чистая") else "interacting" if label.startswith("взаимод") else "errors"
            self.by_label.setdefault(kind, []).append(float(result["reward"]))

    def out(self) -> Dict[str, Any]:
        return {"by_type": self.by_type, "false_by_type": self.false_by_type,
                "by_kind": {k: {"episodes": len(v), "reward": round(sum(v) / len(v), 4)} for k, v in sorted(self.by_label.items())},
                "episodes": sum(len(v) for v in self.by_label.values())}


def submitted_findings(action: Any) -> List[Any]:
    """The findings list of a submit action (any shape an agent sent; never trusted beyond reading types)."""
    if not isinstance(action, dict) or action.get("tool") != "submit":
        return []
    f = (action.get("args") or {}).get("findings") if isinstance(action.get("args"), dict) else None
    f = f.get("findings") if isinstance(f, dict) else f
    return f if isinstance(f, list) else []


def summarize(episodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    done = [e for e in episodes if e.get("score")]
    if not done:
        return {"episodes_done": 0}
    mean = lambda k: round(sum(e["score"].get(k, 0.0) for e in done) / len(done), 4)
    scored = [e for e in done if e["score"].get("status") == "scored"]
    tp, fp, fn = (sum(e["score"].get(k, 0) for e in scored) for k in ("tp", "fp", "fn"))
    # Micro averages over all findings of scored episodes: a clean episode (nothing to find, nothing claimed)
    # adds nothing; an invalid or truncated submission has no findings to count and is reported separately.
    # The brief's definitions (section 05, as in eval.scoring.prf1): P or R is 0 when its denominator is 0;
    # F1 = 2TP/(2TP+FP+FN), and 1 when there was nothing to find and nothing was claimed.
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0) if scored else 0.0
    return {"episodes_done": len(done), "reward": mean("reward"), "precision": round(p, 4), "recall": round(r, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn, "not_scored": len(done) - len(scored), "steps": round(sum(e["steps"] for e in done) / len(done), 2),
            "seconds": round(sum(e["seconds"] for e in done), 2)}


def run_split(agent_name: str, make: Callable[[], Policy], split: str = "dev", limit: Optional[int] = None,
              run_id: Optional[str] = None, base: Optional[str] = None, configs: Optional[str] = None,
              on_event: Optional[Callable[[Dict[str, Any]], None]] = None, stop: Optional[threading.Event] = None,
              time_limit: Optional[float] = None, pace: float = 0.0, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
                           "env_version": ENV_VERSION, "pace": pace, "status": "running", "pid": os.getpid(), "started": time.time(), "finished": None,
                           "episodes": [{"index": i, "seed": e["seed"], "label": e["label"], "status": "queued"} for i, e in enumerate(eps)],
                           "summary": {"episodes_done": 0}, **(meta or {})}
    analysis = Analysis()
    # An external program (--cmd) runs on this machine and could read run.json while the run goes on. In closed mode
    # the reward stays with the evaluator until the run ends (brief §04), so its scores are written only at the end.
    probe = make()
    hide = isinstance(probe, SubprocessAgent)
    if hide:
        run["scores_hidden_until_end"] = True
    held: Dict[int, Dict[str, Any]] = {}
    _write_json(os.path.join(folder, "run.json"), run)
    emit({"type": "run_start", "run": run})
    svc = ServiceClient()
    kw = {} if time_limit is None else {"time_limit": time_limit}
    env = AuditEnv(mode="closed", service=svc, run_id=run_id, **kw)
    steps_fh = open(os.path.join(folder, "steps.jsonl"), "w", encoding="utf-8")
    policy = None
    action: Any = None
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
            analysis.add(results[-1], action, e["label"])
            rec.update(status="done", steps=n, seconds=round(time.perf_counter() - t0 - waited, 3))
            held[i] = score
            if not hide:
                rec["score"] = score
                run["summary"] = summarize(run["episodes"])
            _write_json(os.path.join(folder, "run.json"), run)
            emit({"type": "episode_end", "index": i, "episode": dict(rec, score=score), "summary": summarize([dict(e, score=held[e["index"]]) if e["index"] in held else e for e in run["episodes"]])})
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
        for i, sc in held.items():                     # the run is over: the evaluator's scores may now be shown
            run["episodes"][i]["score"] = sc
        run.pop("scores_hidden_until_end", None)
        run["summary"] = summarize(run["episodes"])
        if run["summary"].get("episodes_done"):
            run["analysis"] = analysis.out()
        _write_json(os.path.join(folder, "run.json"), run)
        emit({"type": "run_end", "run": run})
    return run


# ---------------------------------------------------------------- read side (app and terminal)
STALE_SECONDS = 600   # a run that says "running" but has written nothing for this long has lost its process


def _pid_alive(pid: Any) -> Optional[bool]:
    """Whether a process exists: True / False when the system can tell, None when it cannot. Never signals it (on
    Windows, os.kill(pid, 0) would terminate the process, so it asks the kernel instead)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    if pid == os.getpid():
        return True
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            h = k32.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                return {87: False, 5: True}.get(k32.GetLastError())  # no such process / access denied (it exists)
            try:
                code = ctypes.c_ulong()
                if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                    return None
                return code.value == 259                       # STILL_ACTIVE
            finally:
                k32.CloseHandle(h)
        except Exception:  # noqa: BLE001 - no answer is not an error
            return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def settle_status(run: Dict[str, Any], folder: str) -> Dict[str, Any]:
    """A run whose process is gone (the app was closed or crashed mid-run) still says "running" in its run.json and
    would spin forever. Report it as "interrupted": at once when its recorded process no longer exists, otherwise
    once nothing in its folder has changed for STALE_SECONDS. Derived on read; run.json is left as it is."""
    if run.get("status") != "running":
        return run
    alive = _pid_alive(run.get("pid")) if run.get("pid") is not None else None
    if alive is not True:
        try:
            age = time.time() - max(os.path.getmtime(os.path.join(folder, f)) for f in os.listdir(folder))
        except (OSError, ValueError):
            age = 0.0
        if alive is False or age > STALE_SECONDS:
            run = {**run, "status": "interrupted"}
            run.pop("status_note", None)
    return run


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
                r = settle_status(r, os.path.join(base, name))
                out.append({k: r.get(k) for k in ("id", "kind", "agent", "model", "method", "split", "mode", "status", "started",
                                                   "finished", "summary", "at", "iterations", "group", "model_run", "seed", "llm_model", "arena")}
                           | {"test_reward": ((r.get("test") or {}).get("auditor") or {}).get("reward"),
                              "preset": ((r.get("config") or {}).get("dataset") or {}).get("preset"),
                              "preloaded": (r.get("preloaded") or {}).get("title") if isinstance(r.get("preloaded"), dict) else None}
                           | {"episodes": len(r.get("episodes", [])),
                              "rewards": [(e.get("score") or {}).get("reward") for e in r.get("episodes", [])]})
    return sorted(out, key=lambda r: r.get("started") or 0, reverse=True)


def read_run(run_id: str, base: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not RUN_ID.match(run_id or ""):
        return None
    p = os.path.join(base or runs_dir(), run_id, "run.json")
    for attempt in range(25):
        try:
            with open(p, encoding="utf-8") as fh:
                return settle_status(json.load(fh), os.path.dirname(p))
        except PermissionError:  # Windows: the run is replacing run.json at this very moment; it takes milliseconds
            if attempt == 24:
                return None
            time.sleep(0.02)
        except (OSError, ValueError):
            return None
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


_DEV_BASE: Dict[str, Dict[str, Any]] = {}   # deterministic, so computed once per process
_BASE_LOCK = threading.Lock()

class Jobs:
    """At most one run at a time, started from the app with a built-in policy (never an arbitrary command)."""

    def __init__(self, base: Optional[str] = None, configs: Optional[str] = None, curve: Optional[str] = None) -> None:
        self.base, self.configs = base, configs
        self.curve_path = curve or os.path.join(ROOT, "train", "curve.json")
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.stop_ev = threading.Event()
        self.current: Optional[str] = None
        self.verify_args = ["--fuzz", "50"]          # the official command's default; tests pass a smaller fuzz
        self.vlock = threading.Lock()
        self.vproc: Optional[subprocess.Popen] = None
        self.vstate: Dict[str, Any] = {"running": False, "lines": [], "exit": None, "dir": None, "started": None}

    # ---- judge mode: the official verification, run from the app in its own process
    def verify_start(self) -> Dict[str, Any]:
        import tempfile
        with self.vlock:
            if self.vstate["running"]:
                return {"ok": False, "error": {"code": "busy", "message": "the check is already running"}}
            d = tempfile.mkdtemp(prefix="auditgym-verify-")
            cmd = [sys.executable, "-m", "auditgym.verify", "--out", os.path.join(d, "report.json"),
                   "--trajectories", os.path.join(d, "trajectories.jsonl"), *self.verify_args]
            env = dict(os.environ)
            if not getattr(sys, "frozen", False):  # a checkout or pip install: the child imports this same package
                src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
            env["PYTHONIOENCODING"] = "utf-8"
            try:
                self.vproc = subprocess.Popen(cmd, cwd=d, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                              stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError as exc:
                return {"ok": False, "error": {"code": "start_failed", "message": str(exc)[:200]}}
            self.vstate = {"running": True, "lines": [], "exit": None, "dir": d, "started": time.time()}
            proc, state = self.vproc, self.vstate

        def pump() -> None:
            for line in proc.stdout:  # type: ignore[union-attr]
                if len(state["lines"]) < 400:
                    state["lines"].append(line.rstrip("\n")[:300])
            state["exit"] = proc.wait()
            state["running"] = False
        threading.Thread(target=pump, daemon=True).start()
        return {"ok": True}

    def verify_status(self) -> Dict[str, Any]:
        st = self.vstate
        out: Dict[str, Any] = {"ok": True, "running": st["running"], "lines": list(st["lines"]), "exit": st["exit"],
                               "seconds": round(time.time() - st["started"], 1) if st["started"] else None, "report": None}
        if not st["running"] and st["dir"] and st["exit"] == 0:
            try:
                with open(os.path.join(st["dir"], "report.json"), encoding="utf-8") as fh:
                    out["report"] = json.load(fh)
            except (OSError, ValueError):
                pass
        return out

    def busy(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def start(self, policy: Any, split: Any, limit: Any = None, pace: Any = 0.0, model: Any = None,
              llm_model: Any = None, assist: Any = False) -> Dict[str, Any]:
        meta: Dict[str, Any] = {}
        if policy == "llm" and model is None:      # a local Ollama model: checked against what the server reports
            if not _llm.valid_model_name(llm_model):
                return {"ok": False, "error": {"code": "bad_arguments", "message": "llm_model must be an installed Ollama model name"}}
            if split not in EVAL_SPLITS:
                return {"ok": False, "error": {"code": "bad_arguments", "message": "split must be dev, train or test"}}
            tags = _llm.list_models(timeout=1.5)
            if not tags["available"]:
                return {"ok": False, "error": {"code": "ollama_unavailable", "message": "Ollama is not running on 127.0.0.1:11434"}}
            name = _llm.resolve_model(llm_model, tags["models"])
            if name is None:
                return {"ok": False, "error": {"code": "bad_arguments", "message": "llm_model is not installed in Ollama",
                                               "models": tags["models"]}}
            if assist is True:    # LLM + audit tools: code reads and proposes, the model judges (policies/llm_assist.py)
                from .policies.llm_assist import OllamaAssistedPolicy
                make = (lambda m: (lambda: OllamaAssistedPolicy(m)))(name)
                policy, meta = _llm.agent_name(name) + "-assist", {"llm_model": name, "llm_assist": True}
            else:
                make = (lambda m: (lambda: _llm.OllamaPolicy(m)))(name)
                policy, meta = _llm.agent_name(name), {"llm_model": name}
            limit = LLM_DEFAULT_LIMIT if limit is None else limit
        elif model is not None:                      # a trained auditor: the best parameters of a training run
            r = read_run(model, self.base) if isinstance(model, str) and RUN_ID.match(model) else None
            theta = ((r or {}).get("best") or {}).get("theta")
            if not r or r.get("kind") != "training" or not theta:
                return {"ok": False, "error": {"code": "bad_arguments", "message": "model must be a finished training run"}}
            from .learner import AuditorPolicy
            make = (lambda th: (lambda: AuditorPolicy(th)))(list(theta))
            policy, meta = f"auditor-{r.get('method', 'cem')}", {"model_run": r["id"], "model_method": r.get("method")}
        elif policy in BUILTIN:
            make = BUILTIN[policy]
        else:
            make = None
        if make is None or split not in EVAL_SPLITS:
            return {"ok": False, "error": {"code": "bad_arguments", "message": "policy must be reconcile, random, flag_all or llm (or a trained model); split dev, train or test"}}
        if limit is not None and not (isinstance(limit, int) and not isinstance(limit, bool) and 1 <= limit <= 20):
            return {"ok": False, "error": {"code": "bad_arguments", "message": "limit must be 1..20"}}
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
                agent_name=policy, make=make, split=split, limit=limit, run_id=run_id, base=self.base,
                configs=self.configs, stop=self.stop_ev, pace=float(pace), meta=meta))
            self.thread.start()
            # Answer only once run.json exists, so the caller's first read of the run never races the thread.
            path = os.path.join(self.base or runs_dir(), run_id, "run.json")
            for _ in range(200):
                if os.path.exists(path) or not self.thread.is_alive():
                    break
                time.sleep(0.025)
        return {"ok": True, "run": run_id}

    def stop(self, run_id: str) -> Dict[str, Any]:
        if self.busy() and (run_id == self.current or run_id.startswith(str(self.current).rsplit("-s", 1)[0] + "-s")):
            self.stop_ev.set()
            return {"ok": True}
        return {"ok": False, "error": {"code": "not_running", "message": "this run is not running"}}

    def start_train(self, body: Any) -> Dict[str, Any]:
        """Start a training job (auditgym.learner) from the app. Every setting is checked: the browser can only
        choose among the trainer's own options."""
        b = body if isinstance(body, dict) else {}
        def num(key, lo, hi, default, integer=True):
            v = b.get(key, default)
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi and (not integer or float(v).is_integer())
            if not ok:
                raise ValueError(f"{key} must be {'an integer ' if integer else ''}in {lo}..{hi}")
            return int(v) if integer else float(v)
        try:
            method = b.get("method", "cem")
            if method not in ("cem", "reinforce"):
                raise ValueError("method must be cem or reinforce")
            preset = (b.get("dataset") or {}).get("preset", "mixed") if isinstance(b.get("dataset", {}), dict) else None
            if preset not in TRAIN_PRESETS:
                raise ValueError("dataset.preset must be one of " + ", ".join(TRAIN_PRESETS))
            config = {"method": method, "iterations": num("iterations", 2, 200, 30), "population": num("population", 4, 64, 16),
                      "episodes_per_candidate": num("episodes_per_candidate", 1, 10, 4),
                      "elite_frac": num("elite_frac", 0.05, 0.5, 0.25, integer=False), "seed": num("seed", 0, 1_000_000, 1),
                      "eval_every": num("eval_every", 1, 20, 2), "pace": num("pace", 0, 0.5, 0.0, integer=False),
                      "dataset": {"preset": preset}}
            seeds = b.get("seeds")
            if seeds is not None:
                ok = isinstance(seeds, list) and 2 <= len(seeds) <= 5 and len(set(map(str, seeds))) == len(seeds) and all(
                    isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= 1_000_000 for x in seeds)
                if not ok:
                    raise ValueError("seeds must be 2..5 different integers in 0..1000000")
        except ValueError as exc:
            return {"ok": False, "error": {"code": "bad_arguments", "message": str(exc)}}
        from . import learner  # imported lazily: the evaluation-only app does not need it
        with self.lock:
            if self.busy():
                return {"ok": False, "error": {"code": "busy", "message": "another run is in progress", "run": self.current}}
            run_id = new_run_id(f"auditor-{method}", "train")
            self.stop_ev = threading.Event()
            self.current = run_id
            if seeds:
                group = "g-" + run_id
                ids = [f"{run_id}-s{x}" for x in seeds]
                run_id = self.current = ids[0]

                def series() -> None:               # the same configuration on each seed, one after another
                    for x, rid in zip(seeds, ids):
                        if self.stop_ev.is_set():
                            break
                        self.current = rid
                        learner.train(config={**config, "seed": x}, run_id=rid, base=self.base, stop=self.stop_ev,
                                      configs=self.configs, meta={"group": group, "group_seeds": seeds})
                self.thread = threading.Thread(target=series, daemon=True)
            else:
                self.thread = threading.Thread(target=learner.train, daemon=True,
                                               kwargs=dict(config=config, run_id=run_id, base=self.base, stop=self.stop_ev,
                                                           configs=self.configs))
            self.thread.start()
            path = os.path.join(self.base or runs_dir(), run_id, "run.json")
            for _ in range(200):
                if os.path.exists(path) or not self.thread.is_alive():
                    break
                time.sleep(0.025)
        return {"ok": True, "run": run_id, **({"group": group, "runs": ids} if seeds else {})}

    def start_arena(self, quick: bool = False) -> Dict[str, Any]:
        """The red-team arena (auditgym.redteam): every attack on the test episodes, then an RL attacker."""
        from . import redteam
        with self.lock:
            if self.busy():
                return {"ok": False, "error": {"code": "busy", "message": "another run is in progress", "run": self.current}}
            arena_id = new_run_id("arena", "test")
            self.stop_ev = threading.Event()
            self.current = arena_id
            self.thread = threading.Thread(target=redteam.run_arena, daemon=True, kwargs=dict(
                arena_id=arena_id, base=self.base, stop=self.stop_ev, rl_iterations=4 if quick else 10))  # always all 20 test episodes (the first 5 are clean)
            self.thread.start()
            path = os.path.join(self.base or runs_dir(), arena_id, "run.json")
            for _ in range(200):
                if os.path.exists(path) or not self.thread.is_alive():
                    break
                time.sleep(0.025)
        return {"ok": True, "run": arena_id}

    def export(self, run_id: str, lang: str = "en") -> Dict[str, Any]:
        """Write a Markdown report of a training run to its folder (report.md) and return it."""
        r = read_run(run_id, self.base) if RUN_ID.match(run_id or "") else None
        if not r or r.get("kind") != "training":
            return {"ok": False, "error": {"code": "not_found", "message": "no such training run"}}
        group = [read_run(x["id"], self.base) for x in list_runs(self.base) if r.get("group") and x.get("group") == r.get("group")]
        from .report_md import training_report
        text = training_report(r, [g for g in group if g], lang if lang in ("en", "ru") else "en")
        path = os.path.join(self.base or runs_dir(), run_id, "report.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return {"ok": True, "path": path, "markdown": text}

    def save_curve(self, run_id: str) -> Dict[str, Any]:
        """Copy a finished training run's learning curve to train/curve.json (shown on the runs page, T-1)."""
        r = read_run(run_id, self.base)
        if not r or r.get("kind") != "training":
            return {"ok": False, "error": {"code": "not_found", "message": "no such training run"}}
        points = [{"iteration": p["i"], "train_reward": p.get("train_mean"),
                   **({"dev_reward": p["dev"]["reward"], "steps": p["dev"].get("steps")} if p.get("dev") else {})}
                  for p in r.get("points", [])]
        os.makedirs(os.path.dirname(self.curve_path), exist_ok=True)
        _write_json(self.curve_path, {"points": points, "config": r.get("config"), "run": run_id, "env_version": r.get("env_version")})
        return {"ok": True, "path": self.curve_path}

    # HTTP routes: return (status, json)
    def get(self, path: str, query: Dict[str, str]):
        if path == "/api/verify":  # judge mode: progress and, when finished, the fresh report.json
            return 200, self.verify_status()
        if path == "/api/update":  # updates exist in the packaged desktop app only (desktop/updater.py answers there)
            return 200, {"ok": True, "update": None}
        if path == "/api/scout":
            from . import scout as _scout
            return 200, {"ok": True, "scout": _scout.scout(explain=query.get("explain") == "1")}
        if path == "/api/llm/models":  # installed local Ollama models (short timeout; available false without Ollama)
            return 200, {"ok": True, **_llm.list_models(timeout=1.0)}
        if path == "/api/baselines":  # the Reconciler and the random policy on the same dev split the training charts use
            key = self.configs or configs_dir()
            with _BASE_LOCK:
                if key not in _DEV_BASE:
                    from .learner import dev_baselines
                    _DEV_BASE[key] = {k: v.get("reward") for k, v in dev_baselines(key).items()}
            return 200, {"ok": True, "split": "dev", "baselines": _DEV_BASE[key]}
        if path == "/api/curve":  # the trainer's learning curve (T10), or null until it has run
            try:
                with open(self.curve_path, encoding="utf-8") as fh:
                    return 200, {"ok": True, "curve": json.load(fh)}
            except (OSError, ValueError):
                return 200, {"ok": True, "curve": None}
        if path == "/api/runs":
            return 200, {"ok": True, "runs": list_runs(self.base), "running": self.current if self.busy() else None,
                         "policies": list(BUILTIN), "splits": list(EVAL_SPLITS)}
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
            res = self.start(b.get("policy"), b.get("split", "dev"), b.get("limit"), b.get("pace", 0.0), b.get("model"),
                             b.get("llm_model"), b.get("assist", False))
            return (200 if res["ok"] else (409 if res["error"]["code"] in ("busy", "ollama_unavailable") else 400)), res
        m = re.match(r"^/api/runs/([^/]+)/stop$", path)
        if m:
            res = self.stop(m.group(1))
            return (200 if res["ok"] else 409), res
        if path == "/api/verify":
            res = self.verify_start()
            return (200 if res["ok"] else 409), res
        if path == "/api/arena":
            res = self.start_arena(bool(b.get("quick")))
            return (200 if res["ok"] else 409), res
        m = re.match(r"^/api/runs/([^/]+)/export$", path)
        if m:
            res = self.export(m.group(1), b.get("lang", "en"))
            return (200 if res["ok"] else 404), res
        if path == "/api/train":
            res = self.start_train(body)
            return (200 if res["ok"] else (409 if res["error"]["code"] == "busy" else 400)), res
        m = re.match(r"^/api/train/([^/]+)/curve$", path)
        if m:
            res = self.save_curve(m.group(1))
            return (200 if res["ok"] else 404), res
        return None


if __name__ == "__main__":  # pragma: no cover - convenience
    print(json.dumps(list_runs(), indent=1, ensure_ascii=False))
    sys.exit(0)
