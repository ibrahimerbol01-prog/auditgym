"""Command line:  python -m auditgym.cli <command>

  verify                      run the full verification (same as python -m auditgym.verify)
  demo                        play one episode with the reconciliation baseline, printed as text
  serve --stdio|--http        JSON front doors (HTTP binds to 127.0.0.1 only)
  ui [--port 8000]            thin local web UI (offline), including the run page (/runs.html)
  run-agent --policy NAME | --cmd "PROGRAM" [--split dev] [--limit N] [--pace S] [--plain]
                              run an agent on a split in closed mode; live trace in the terminal, saved for the app
  generate --seed N [--config FILE] --out DIR      export one episode (public + private)
  build-suite --out DIR       regenerate the 10 train and 10 dev episodes from configs/
  evaluate --private DIR --findings FILE --steps N  organizer scoring of one submission
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# A packaged build (desktop/) points these at its bundled copies; a checkout uses the repository.
DATA_DIRS = [d for d in (os.environ.get("AUDITGYM_DATA"),) if d]
CONFIGS = os.environ.get("AUDITGYM_CONFIGS") or os.path.join(ROOT, "configs")


def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_demo(_args) -> int:
    from .env.env import AuditEnv
    from .policies.baselines import ReconcilePolicy, run_episode
    env = AuditEnv()
    traj = []
    res = run_episode(env, ReconcilePolicy(), 20261119, {"interactions": ["A", "B"]}, trajectory=traj)
    for t in traj:
        a = t["action"]
        args = {k: (v if k != "findings" else f"<{len(v['findings'])} findings>") for k, v in a["args"].items()}
        o = t["observation"]
        brief = o.get("result", {}).get("next_cursor", "") if o.get("ok") else o.get("error", {}).get("code", "")
        print(f"#{t['step']:>3} {a['tool']:<13} {json.dumps(args)[:70]:<72} {str(brief)[:20]}")
    rep = res["final_observation"]["result"]["report"]
    print(f"\nepisode {res['episode_id']}  reward {res['return']:+.3f}  P {rep['precision']:.2f} R {rep['recall']:.2f} "
          f"F1 {rep['f1']:.2f}  steps {res['steps']}")
    env.close()
    return 0


def cmd_serve(args) -> int:
    from .env.adapters import make_http_server, serve_stdio
    if args.stdio:
        serve_stdio(args.mode)
        return 0
    srv, env = make_http_server(args.port, args.mode, ui=False)
    print(f"AuditGym HTTP front door on http://127.0.0.1:{args.port}  (POST /reset, POST /step, GET /state)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    env.close()
    return 0


def ui_extra_files() -> dict:
    """Read-only data files the UI may fetch under /data/ (public artefacts only)."""
    extra = {}
    for name in ("report.json", "trajectories.jsonl"):
        for base in (os.getcwd(), *DATA_DIRS, ROOT):  # Docker writes them to /work (cwd); a checkout keeps them at the root
            p = os.path.join(base, name)
            if os.path.exists(p):
                extra["/data/" + name] = p
                break
    for split in ("train", "dev"):
        extra[f"/data/{split}.json"] = os.path.join(CONFIGS, f"{split}.json")
    curve = os.path.join(ROOT, "train", "curve.json")  # written by the trainer (T10) once it exists
    if os.path.exists(curve):
        extra["/data/curve.json"] = curve
    return extra


def cmd_ui(args) -> int:
    from .env.adapters import make_http_server
    from .harness import Jobs
    srv, env = make_http_server(args.port, "open", ui=True, extra_files=ui_extra_files(), host=args.host, api=Jobs())
    url = f"http://127.0.0.1:{args.port}/"
    print(f"AuditGym UI: {url}")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 - opening a browser is a convenience only
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    env.close()
    return 0


def cmd_run_agent(args) -> int:
    from .harness import make_agent, run_split, runs_dir
    from .termview import TermView, baseline_means
    if bool(args.policy) == bool(args.agent_cmd):
        print("give exactly one of --policy NAME or --cmd \"PROGRAM\"", file=sys.stderr)
        return 2
    view = TermView(plain=args.plain)
    for base in (os.getcwd(), *DATA_DIRS, ROOT):
        if os.path.exists(os.path.join(base, "report.json")):
            view.compare = baseline_means(os.path.join(base, "report.json"))
            break
    name = args.policy or args.name or "cmd"
    try:
        make = make_agent(args.policy, args.agent_cmd)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    run_id = None
    if args.name:
        from .harness import new_run_id
        run_id = new_run_id(args.name, args.split)
    view.saved = os.path.join(runs_dir(), "<id>")
    first = {}

    def on_event(e):
        if e["type"] == "run_start":
            first["id"] = e["run"]["id"]
            view.saved = os.path.join(runs_dir(), e["run"]["id"])
        view(e)
    try:
        run = run_split(name, make, args.split, args.limit, run_id=run_id, on_event=on_event, pace=args.pace)
    except KeyboardInterrupt:
        print("\nостановлено", file=sys.stderr)
        return 130
    return 0 if run["status"] == "done" else 1


def cmd_generate(args) -> int:
    from .gen.build import generate
    from .gen.export import write_episode
    cfg = _load_json(args.config) if args.config else None
    d = write_episode(args.out, generate(args.seed, cfg), (cfg or {}).get("layout_seed", 0))
    print(d)
    return 0


def cmd_build_suite(args) -> int:
    from .gen.build import generate
    from .gen.export import write_episode
    import hashlib
    hashes = {}
    for split in ("train", "dev"):
        spec = _load_json(os.path.join(ROOT, "configs", f"{split}.json"))
        for item in spec["episodes"]:
            ep = generate(item["seed"], item["config"])
            d = write_episode(os.path.join(args.out, split), ep, item["config"].get("layout_seed", 0))
            hashes[f"{split}/{os.path.basename(d)}"] = hashlib.sha256(json.dumps(ep, sort_keys=True).encode()).hexdigest()
            print(split, os.path.basename(d))
    with open(os.path.join(args.out, "golden_hashes.json"), "w", encoding="utf-8") as fh:
        json.dump(hashes, fh, indent=2, sort_keys=True)
    return 0


def cmd_evaluate(args) -> int:
    from .eval.scoring import StructureError, parse_submission, score, validate_structure
    truth = _load_json(os.path.join(args.private, "truth.json"))
    with open(args.findings, encoding="utf-8") as fh:
        text = fh.read()
    try:
        sub = validate_structure(parse_submission(text), truth["episode_id"])
        res = score(sub["findings"], truth["issues"], args.steps)
        res["status"] = "scored"
    except StructureError as exc:
        res = {"status": "invalid_structure", "reward": -1.0, "error": str(exc)}
    print(json.dumps(res, indent=2))
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    from .verify import utf8_output
    utf8_output()  # Cyrillic, ✓ and block characters on any console code page (Windows: cp1252)
    if argv[:1] == ["verify"]:
        # Handed straight to the verifier: argparse's REMAINDER no longer captures options such as --out after a
        # subcommand on current Python 3.11 releases, which broke the Docker image's default command.
        from .verify import main as vmain
        return vmain(argv[1:])
    if not argv and sys.stdin.isatty() and sys.stdout.isatty():
        argv = ["tui"]  # `auditgym` on its own, in a terminal: the interactive terminal UI
    ap = argparse.ArgumentParser(prog="auditgym")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tui", help="interactive terminal UI (also: auditgym with no arguments)")
    sub.add_parser("verify").add_argument("rest", nargs=argparse.REMAINDER)
    sub.add_parser("demo")
    s = sub.add_parser("serve")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--stdio", action="store_true")
    g.add_argument("--http", action="store_true")
    s.add_argument("--port", type=int, default=8080)
    s.add_argument("--mode", choices=["open", "closed"], default="open")
    u = sub.add_parser("ui")
    u.add_argument("--port", type=int, default=8000)
    u.add_argument("--no-browser", action="store_true")
    u.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 only inside Docker")
    ra = sub.add_parser("run-agent", help="run an agent on a split in closed mode")
    ra.add_argument("--policy", choices=["reconcile", "random", "flag_all"])
    ra.add_argument("--cmd", dest="agent_cmd", help="external agent: reads observations (JSON lines) on stdin, writes actions on stdout")
    ra.add_argument("--name", help="short name for a --cmd agent (used in the run id)")
    ra.add_argument("--split", choices=["dev", "train", "test"], default="dev",
                    help="test: 20 fresh episodes never used for training or model choice")
    ra.add_argument("--limit", type=int, help="only the first N episodes")
    ra.add_argument("--pace", type=float, default=0.0, help="seconds to wait before each step (demos); not counted in time")
    ra.add_argument("--plain", action="store_true", help="plain lines, no colours or redraw")
    gen = sub.add_parser("generate")
    gen.add_argument("--seed", type=int, required=True)
    gen.add_argument("--config")
    gen.add_argument("--out", required=True)
    bs = sub.add_parser("build-suite")
    bs.add_argument("--out", default=os.path.join(ROOT, "episodes"))
    ev = sub.add_parser("evaluate")
    ev.add_argument("--private", required=True)
    ev.add_argument("--findings", required=True)
    ev.add_argument("--steps", type=int, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "tui":
        from .tui import main as tmain
        return tmain()
    if args.cmd == "verify":
        from .verify import main as vmain
        return vmain(args.rest)
    return {"demo": cmd_demo, "serve": cmd_serve, "ui": cmd_ui, "run-agent": cmd_run_agent, "generate": cmd_generate,
            "build-suite": cmd_build_suite, "evaluate": cmd_evaluate}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
