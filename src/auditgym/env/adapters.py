"""Front doors: JSON lines over stdio and a localhost-only HTTP server (plan §6.5).

Both speak exactly the action/observation contract of AuditEnv. The HTTP server also serves the
thin UI from a fixed whitelist of static files (never anything under private/).
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional

from .env import AuditEnv

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui", "static")
STATIC_WHITELIST = {"/": "index.html", "/index.html": "index.html", "/play.html": "play.html", "/report.html": "report.html", "/runs.html": "runs.html", "/train.html": "train.html", "/settings.html": "settings.html", "/arena.html": "arena.html",
                    "/app.js": "app.js", "/home.js": "home.js", "/shell.js": "shell.js", "/i18n.js": "i18n.js", "/report.js": "report.js", "/runs.js": "runs.js", "/train.js": "train.js", "/settings.js": "settings.js", "/arena.js": "arena.js", "/style.css": "style.css"}
FONT_EXT = {".woff2": "font/woff2"}
CTYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


BAD = {"ok": False, "error": {"code": "bad_arguments", "message": "invalid request"}}


def _loads_strict(text: str) -> Any:
    def _bad(const: str) -> Any:
        raise ValueError(f"invalid JSON constant: {const}")
    return json.loads(text, parse_constant=_bad)


def handle_request(env: AuditEnv, req: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return _handle(env, req)
    except Exception:  # noqa: BLE001 - a front door answers every request with a bounded error
        return dict(BAD)


def _handle(env: AuditEnv, req: Dict[str, Any]) -> Dict[str, Any]:
    op = req.get("op") if isinstance(req, dict) else None
    if op == "reset":
        obs, info = env.reset(req.get("seed"), req.get("config"))
        return {"observation": obs, "info": info}
    if op == "step":
        obs, reward, te, tr, info = env.step(req.get("action"))
        return {"observation": obs, "reward": reward, "terminated": te, "truncated": tr, "info": info}
    if op == "state":
        return env.state()
    return {"ok": False, "error": {"code": "bad_arguments", "message": "op must be reset, step or state"}}


def serve_stdio(mode: str = "open") -> None:
    env = AuditEnv(mode=mode)
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = _loads_strict(line)
        except (ValueError, RecursionError):  # bad JSON, >4300-digit ints, absurd nesting
            resp: Dict[str, Any] = {"ok": False, "error": {"code": "bad_arguments", "message": "invalid JSON"}}
        else:
            resp = handle_request(env, req)
        try:
            out = json.dumps(resp, allow_nan=False)
        except (TypeError, ValueError, RecursionError):
            out = json.dumps(BAD)
        sys.stdout.write(out + "\n")
        sys.stdout.flush()
    env.close()


def make_http_server(port: int = 8000, mode: str = "open", ui: bool = True, extra_files: Optional[Dict[str, str]] = None,
                     host: str = "127.0.0.1", api: Any = None):
    """``api`` (optional, UI only): an object with ``get(path, query)`` and ``post(path, body)`` that answer
    ``/api/...`` routes with ``(status, json)`` or None; the local harness (auditgym.harness.Jobs) uses it."""
    env = AuditEnv(mode=mode, time_limit=None if ui else 60.0)
    lock = threading.Lock()
    extra = extra_files or {}

    class Handler(BaseHTTPRequestHandler):
        server_version = "AuditGym"

        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: Any, code: int = 200) -> None:
            try:
                data = json.dumps(obj, allow_nan=False).encode()
            except (TypeError, ValueError, RecursionError):
                data, code = json.dumps(BAD).encode(), 500
            self._send(code, data, "application/json")

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if not self._host_ok():
                return self._json({"ok": False, "error": {"code": "forbidden", "message": "bad host"}}, 403)
            if path == "/state":
                with lock:
                    return self._json(env.state())
            if ui and api is not None and path.startswith("/api/"):
                from urllib.parse import parse_qsl
                query = dict(parse_qsl(self.path.split("?", 1)[1])) if "?" in self.path else {}
                res = api.get(path, query)
                if res is not None:
                    return self._json(res[1], res[0])
            if path in extra:
                with open(extra[path], "rb") as fh:
                    return self._send(200, fh.read(), "application/json" if path.endswith((".json", ".jsonl")) else "text/plain")
            if ui and path in STATIC_WHITELIST:
                fp = os.path.join(STATIC_DIR, STATIC_WHITELIST[path])
                with open(fp, "rb") as fh:
                    return self._send(200, fh.read(), CTYPES[os.path.splitext(fp)[1]])
            if ui and path.startswith("/fonts/"):
                fname = path[7:]
                if "/" not in fname and "\\" not in fname and ".." not in fname and os.path.splitext(fname)[1] in FONT_EXT:
                    fp = os.path.join(STATIC_DIR, "fonts", fname)
                    if os.path.isfile(fp):
                        with open(fp, "rb") as fh:
                            return self._send(200, fh.read(), FONT_EXT[".woff2"])
            return self._json({"ok": False, "error": {"code": "not_found", "message": "not found"}}, 404)

        def _host_ok(self) -> bool:
            port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if host != "127.0.0.1":
                return True  # inside Docker (0.0.0.0) the published host name is not known in advance
            return self.headers.get("Host", "") in allowed

        def do_POST(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            # Read the body before any answer, refusals included: a server that closes a socket with unread data makes
            # Windows reset the connection, and the client can lose the response (a 403 arrived as WinError 10053).
            raw = self.rfile.read(n) if 0 < n <= 1_000_000 else b""
            if not self._host_ok():
                return self._json({"ok": False, "error": {"code": "forbidden", "message": "bad host"}}, 403)
            origin = self.headers.get("Origin")
            if origin and origin.rstrip("/") not in (f"http://127.0.0.1:{self.server.server_address[1]}",
                                                     f"http://localhost:{self.server.server_address[1]}"):
                return self._json({"ok": False, "error": {"code": "forbidden", "message": "cross-origin request"}}, 403)
            if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
                return self._json({"ok": False, "error": {"code": "bad_arguments", "message": "Content-Type must be application/json"}}, 415)
            if n < 0:
                return self._json({"ok": False, "error": {"code": "bad_arguments", "message": "bad Content-Length"}}, 400)
            if n > 1_000_000:
                return self._json({"ok": False, "error": {"code": "bad_arguments", "message": "body too large"}}, 413)
            try:
                body = _loads_strict(raw.decode("utf-8") or "{}")
            except (ValueError, RecursionError, UnicodeDecodeError):
                return self._json({"ok": False, "error": {"code": "bad_arguments", "message": "invalid JSON"}}, 400)
            if ui and api is not None and path.startswith("/api/"):
                res = api.post(path, body)
                if res is not None:
                    return self._json(res[1], res[0])
            with lock:
                if path == "/reset":
                    b = body if isinstance(body, dict) else {}
                    return self._json(handle_request(env, {"op": "reset", "seed": b.get("seed"), "config": b.get("config")}))
                if path == "/step":
                    return self._json(handle_request(env, {"op": "step", "action": body.get("action") if isinstance(body, dict) else None}))
            return self._json({"ok": False, "error": {"code": "not_found", "message": "not found"}}, 404)

    srv = ThreadingHTTPServer((host, port), Handler)
    return srv, env
