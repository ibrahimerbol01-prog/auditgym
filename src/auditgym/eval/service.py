"""Evaluator service: generates episodes, holds the truth, scores submissions (plan §3, §6.3).

It runs as a separate process (JSON lines over stdin/stdout). The environment only ever
receives public data from it; the agent talks to the environment, never to this process, so
it has no way to read or write evaluator state. In closed mode scores stay here until
``finalize``.

Organizer interface (never used by the environment): ``reference`` and ``finalize``.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional

from ..config import ConfigError
from ..gen.build import generate
from .scoring import StructureError, score, validate_structure


ORGANIZER_COMMANDS = {"reference", "finalize"}
ENV_COMMANDS = {"generate", "load", "score", "tick", "ping"}


class EvaluatorCore:
    def __init__(self, log_path: Optional[str] = None, token: Optional[str] = None) -> None:
        self.token = token
        self._eps: Dict[str, Dict[str, Any]] = {}
        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._n = 0
        self.log: List[Dict[str, Any]] = []
        self._log_path = log_path

    def _log(self, entry: Dict[str, Any]) -> None:
        self.log.append(entry)
        if self._log_path:
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")

    # ----- commands -----
    def generate(self, seed: Any, config: Any, mode: str = "open", run_id: str = "default") -> Dict[str, Any]:
        if mode not in ("open", "closed"):
            return {"ok": False, "error": {"code": "bad_arguments", "message": "mode must be open or closed"}}
        try:
            ep = generate(seed, config)
        except ConfigError as exc:
            return {"ok": False, "error": {"code": "bad_config", "message": str(exc)[:200]}}
        return self._register(ep, mode, run_id)

    def load(self, episode_dir: str, mode: str = "open", run_id: str = "default") -> Dict[str, Any]:
        from ..env.loader import load_episode_dir
        ep = load_episode_dir(episode_dir, with_private=True)
        return self._register(ep, mode, run_id)

    def _register(self, ep: Dict[str, Any], mode: str, run_id: str) -> Dict[str, Any]:
        self._n += 1
        handle = f"h{self._n}"
        self._eps[handle] = {"private": ep["private"], "episode_id": ep["public"]["manifest"]["episode_id"],
                             "mode": mode, "run_id": run_id, "scored": False, "ticks": 0}
        return {"ok": True, "handle": handle, "public": ep["public"]}

    def tick(self, handle: str) -> Dict[str, Any]:
        """The environment reports every inspection step, so a score can never be cheaper than the steps taken."""
        ep = self._eps.get(handle)
        if ep is None or ep["scored"]:
            return {"ok": False, "error": {"code": "episode_over", "message": "unknown or already scored episode"}}
        ep["ticks"] += 1
        return {"ok": True}

    def score(self, handle: str, submission: Any, inspection_steps: int, truncated: bool = False,
              status: Optional[str] = None) -> Dict[str, Any]:
        ep = self._eps.get(handle)
        if ep is None or ep["scored"]:
            return {"ok": False, "error": {"code": "episode_over", "message": "unknown or already scored episode"}}
        if isinstance(inspection_steps, bool) or not isinstance(inspection_steps, int) or not 0 <= inspection_steps <= 100:
            return {"ok": False, "error": {"code": "bad_arguments", "message": "inspection_steps must be in [0, 100]"}}
        inspection_steps = max(inspection_steps, ep["ticks"])
        ep["scored"] = True
        issues = ep["private"]["truth"]["issues"]
        if truncated:
            res = score([], issues, inspection_steps)
            res["status"] = status or "truncated"
        else:
            try:
                validate_structure(submission, ep["episode_id"])
                res = score(submission["findings"], issues, inspection_steps)
                res["status"] = "scored"
            except StructureError as exc:
                res = {"status": "invalid_structure", "reward": -1.0, "error": str(exc)[:200], "tp": 0,
                       "fp": 0, "fn": len(issues), "precision": 0.0, "recall": 0.0, "f1": 0.0,
                       "inspection_steps": inspection_steps}
                self._log({"event": "invalid_structure", "episode_id": ep["episode_id"], "error": str(exc)[:200]})
        res["episode_id"] = ep["episode_id"]
        res["n_issues"] = len(issues)
        self._results.setdefault(ep["run_id"], []).append(res)
        self._log({"event": "scored", "episode_id": ep["episode_id"], "status": res["status"], "reward": res["reward"]})
        if ep["mode"] == "closed":
            return {"ok": True, "reward": 0.0}
        return {"ok": True, "reward": res["reward"], "report": _public_report(res)}

    def reference(self, handle: str) -> Dict[str, Any]:
        ep = self._eps.get(handle)
        if ep is None:
            return {"ok": False, "error": {"code": "unknown_id", "message": "unknown handle"}}
        return {"ok": True, "truth": ep["private"]["truth"]}

    def finalize(self, run_id: str = "default") -> Dict[str, Any]:
        return {"ok": True, "results": self._results.get(run_id, [])}

    def dispatch(self, req: Dict[str, Any]) -> Dict[str, Any]:
        cmd = req.get("cmd")
        if cmd in ORGANIZER_COMMANDS and (self.token is None or req.get("token") != self.token):
            return {"ok": False, "error": {"code": "unknown_tool", "message": "organizer command not allowed on this channel"}}
        try:
            if cmd == "generate":
                return self.generate(req.get("seed"), req.get("config"), req.get("mode", "open"), req.get("run_id", "default"))
            if cmd == "load":
                return self.load(req["dir"], req.get("mode", "open"), req.get("run_id", "default"))
            if cmd == "score":
                return self.score(req["handle"], req.get("submission"), req["inspection_steps"], bool(req.get("truncated")),
                                  req.get("status") if req.get("status") in ("truncated", "abandoned") else None)
            if cmd == "tick":
                return self.tick(req["handle"])
            if cmd == "reference":
                return self.reference(req["handle"])
            if cmd == "finalize":
                return self.finalize(req.get("run_id", "default"))
            if cmd == "ping":
                return {"ok": True}
        except Exception:  # noqa: BLE001 - any failure is a bounded error; the evaluator must never die
            return {"ok": False, "error": {"code": "bad_arguments", "message": "bad request"}}
        return {"ok": False, "error": {"code": "unknown_tool", "message": "unknown command"}}


def _public_report(res: Dict[str, Any]) -> Dict[str, Any]:
    """What an open-mode player may see: metrics and their own findings' outcomes, never the reference."""
    keep = ("status", "reward", "precision", "recall", "f1", "tp", "fp", "fn", "inspection_steps", "error")
    out = {k: res[k] for k in keep if k in res}
    # Only matched / not matched per finding: near-miss reasons would let an agent probe which
    # (type, affected_ids) hypotheses are real, so they stay in the organizer results.
    out["per_finding"] = [{"index": f["index"], "matched": f["matched"]} for f in res.get("per_finding", [])]
    return out


def serve_stdio() -> None:
    core = EvaluatorCore(os.environ.get("AUDITGYM_EVAL_LOG"), os.environ.get("AUDITGYM_ORGANIZER_TOKEN"))
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = core.dispatch(req) if isinstance(req, dict) else {"ok": False, "error": {"code": "bad_arguments", "message": "bad request"}}
        except Exception:  # noqa: BLE001 - malformed input never stops the evaluator
            resp = {"ok": False, "error": {"code": "bad_arguments", "message": "bad request"}}
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


class ServiceClient:
    """ORGANIZER client: talks to an evaluator service subprocess (default) or an in-process core.

    It holds the organizer token, so it may call ``reference`` and ``finalize``. The environment
    never hands this object to agents: it talks through ``EnvChannel``, which can only generate,
    load, tick and score.
    """

    def __init__(self, in_process: bool = False, log_path: Optional[str] = None) -> None:
        import secrets
        self._lock = threading.Lock()
        self._token = secrets.token_hex(16)
        self.core: Optional[EvaluatorCore] = None
        self.proc = None
        if in_process:
            self.core = EvaluatorCore(log_path, self._token)
        else:
            env = dict(os.environ)
            env["AUDITGYM_ORGANIZER_TOKEN"] = self._token
            if log_path:
                env["AUDITGYM_EVAL_LOG"] = log_path
            src_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            env["PYTHONPATH"] = src_root + os.pathsep + env.get("PYTHONPATH", "")
            self.proc = subprocess.Popen([sys.executable, "-m", "auditgym.eval.service"], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, text=True, env=env, bufsize=1)

    def call(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Organizer call (carries the token)."""
        return self._send({**req, "token": self._token})

    def _send(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if self.core is not None:
            return json.loads(json.dumps(self.core.dispatch(json.loads(json.dumps(req)))))
        with self._lock:
            assert self.proc and self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(json.dumps(req) + "\n")
            self.proc.stdin.flush()
            line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("evaluator service stopped")
        return json.loads(line)

    def close(self) -> None:
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
            except Exception:  # noqa: BLE001 - best effort shutdown of a child process
                self.proc.kill()
            self.proc = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: BLE001
            pass


class EnvChannel:
    """What the environment (and anything holding it) may say to the evaluator."""

    def __init__(self, client: ServiceClient) -> None:
        self._client = client

    def call(self, req: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(req, dict) or req.get("cmd") not in ENV_COMMANDS:
            return {"ok": False, "error": {"code": "unknown_tool", "message": "command not allowed on the environment channel"}}
        clean = {k: v for k, v in req.items() if k != "token"}
        return self._client._send(clean)


if __name__ == "__main__":
    serve_stdio()
