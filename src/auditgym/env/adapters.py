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
STATIC_WHITELIST = {"/": "index.html", "/index.html": "index.html", "/report.html": "report.html",
                    "/app.js": "app.js", "/report.js": "report.js", "/style.css": "style.css"}
FONT_EXT = {".woff2": "font/woff2"}
CTYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


def handle_request(env: AuditEnv, req: Dict[str, Any]) -> Dict[str, Any]:
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
            req = json.loads(line)
        except json.JSONDecodeError:
            resp: Dict[str, Any] = {"ok": False, "error": {"code": "bad_arguments", "message": "invalid JSON"}}
        else:
            resp = handle_request(env, req)
        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()
    env.close()


def make_http_server(port: int = 8000, mode: str = "open", ui: bool = True, extra_files: Optional[Dict[str, str]] = None,
                     host: str = "127.0.0.1"):
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
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/state":
                with lock:
                    return self._json(env.state())
            if path in extra:
                with open(extra[path], "rb") as fh:
                    return self._send(200, fh.read(), "application/json" if path.endswith((".json", ".jsonl")) else "text/plain")
            if ui and path in STATIC_WHITELIST:
                fp = os.path.join(STATIC_DIR, STATIC_WHITELIST[path])
                with open(fp, "rb") as fh:
                    return self._send(200, fh.read(), CTYPES[os.path.splitext(fp)[1]])
            if ui and path.startswith("/fonts/") and "/" not in path[7:] and os.path.splitext(path)[1] in FONT_EXT:
                fp = os.path.join(STATIC_DIR, "fonts", path[7:])
                if os.path.isfile(fp):
                    with open(fp, "rb") as fh:
                        return self._send(200, fh.read(), FONT_EXT[".woff2"])
            return self._json({"ok": False, "error": {"code": "not_found", "message": "not found"}}, 404)

        def do_POST(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                return self._json({"ok": False, "error": {"code": "bad_arguments", "message": "body too large"}}, 413)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._json({"ok": False, "error": {"code": "bad_arguments", "message": "invalid JSON"}}, 400)
            with lock:
                if path == "/reset":
                    return self._json(handle_request(env, {"op": "reset", **(body if isinstance(body, dict) else {})}))
                if path == "/step":
                    return self._json(handle_request(env, {"op": "step", "action": body.get("action") if isinstance(body, dict) else None}))
            return self._json({"ok": False, "error": {"code": "not_found", "message": "not found"}}, 404)

    srv = ThreadingHTTPServer((host, port), Handler)
    return srv, env
