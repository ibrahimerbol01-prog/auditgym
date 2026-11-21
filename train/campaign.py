"""Pre-submission check of the whole harness, end to end (about 3 minutes on 4 cores):

    python train/campaign.py            # full: verify, policies, external agent, 6 trainings, HTTP API, desktop smoke
    python train/campaign.py --quick    # under a minute: one short training

1. the official verification (python -m auditgym.verify) in a scratch copy, so report.json here is not rewritten
2. every built-in policy through the harness on dev and train, closed mode
3. an external agent as a separate program (--cmd examples/random_agent.py)
4. trainings measured on the held-out dev episodes: CEM on 3 seeds, the same seed twice (must be identical),
   REINFORCE, CEM on the "interacting" dataset
5. the app's HTTP API: start a training and an evaluation, refusals for busy / bad input
6. the desktop smoke test from source

Runs go to a temporary folder (not ~/.auditgym/runs). Prints one line per check and exits 1 if any fails;
--out FILE also saves every number as JSON. Not part of the official verification. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--quick", action="store_true", help="one short training instead of six")
    ap.add_argument("--out", help="save all results as JSON")
    args = ap.parse_args(argv)

    runs = tempfile.mkdtemp(prefix="auditgym-campaign-")
    os.environ["AUDITGYM_RUNS"] = runs
    from auditgym import harness, learner
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
    results: dict = {}
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name:<44} {detail}", flush=True)

    # 1. official verification, in a copy
    work = tempfile.mkdtemp()
    shutil.copytree(ROOT, os.path.join(work, "r"), ignore=shutil.ignore_patterns(".git", "build", "dist", "__pycache__"))
    t = time.time()
    p = subprocess.run([sys.executable, "-m", "auditgym.verify"], cwd=os.path.join(work, "r"), env=dict(env, PYTHONPATH="src"),
                       capture_output=True, text=True)
    try:
        with open(os.path.join(work, "r", "report.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        all_checks = [c for a in rep["areas"].values() for c in a]
        ok_n = sum(1 for c in all_checks if c["passed"])
        results["verify"] = {"exit": p.returncode, "score": rep["estimated_score"]["total"], "passed": ok_n, "checks": len(all_checks)}
        check("official verification", p.returncode == 0 and ok_n == len(all_checks),
              f"{rep['estimated_score']['total']}/100, {ok_n}/{len(all_checks)} checks, {time.time() - t:.0f} s")
    except (OSError, ValueError, KeyError) as exc:
        check("official verification", False, f"exit {p.returncode}: {exc}")
    shutil.rmtree(work, ignore_errors=True)

    # 2. built-in policies
    expect = {"reconcile": (0.9, 1.0), "random": (-1.0, -0.5), "flag_all": (-1.0, -0.5)}
    for split in ("dev", "train"):
        for pol, (lo, hi) in expect.items():
            rid = f"{pol}-{split}-campaign"
            harness.run_split(pol, harness.BUILTIN[pol], split=split, run_id=rid, base=runs)
            r = harness.read_run(rid, runs) or {}
            s = r.get("summary") or {}
            errors = [e.get("error") for e in r.get("episodes", []) if e.get("error")]
            results[f"policy {pol}/{split}"] = s
            check(f"{pol} on {split}", r.get("status") == "done" and not errors and lo <= (s.get("reward") or -9) <= hi,
                  f"reward {s.get('reward'):+.3f}  P/R/F1 {s.get('precision', 0):.2f}/{s.get('recall', 0):.2f}/{s.get('f1', 0):.2f}"
                  f"  {s.get('episodes_done')} episodes")

    # 3. external agent, a separate process
    p = subprocess.run([sys.executable, "-m", "auditgym.cli", "run-agent", "--name", "extrandom", "--cmd",
                        f'"{sys.executable}" examples/random_agent.py', "--split", "dev", "--plain"],
                       cwd=ROOT, env=env, capture_output=True, text=True)
    ext = next((r for r in harness.list_runs(runs) if r["id"].startswith("extrandom")), None)
    s = (ext or {}).get("summary") or {}
    results["external agent"] = s
    check("external agent (--cmd)", p.returncode == 0 and s.get("episodes_done") == 10, f"reward {s.get('reward')}, {s.get('episodes_done')} episodes")

    # 4. trainings on held-out dev
    base_reward = (results.get("policy reconcile/dev") or {}).get("reward")
    std = {"method": "cem", "iterations": 30, "population": 16, "episodes_per_candidate": 4, "elite_frac": 0.25, "eval_every": 2,
           "dataset": {"preset": "mixed"}, "pace": 0.0, "seed": 1}
    plan = [("cem seed 1", {**std, "iterations": 8, "population": 8, "episodes_per_candidate": 2})] if args.quick else [
        ("cem seed 1", std), ("cem seed 2", {**std, "seed": 2}), ("cem seed 3", {**std, "seed": 3}), ("cem seed 1 again", std),
        ("reinforce seed 1", {**std, "method": "reinforce"}), ("cem interacting", {**std, "dataset": {"preset": "interacting"}})]
    curves = {}
    for name, cfg in plan:
        t = time.time()
        rid = "train-" + name.replace(" ", "-")
        learner.train(config=cfg, run_id=rid, base=runs)
        r = harness.read_run(rid, runs) or {}
        s = r.get("summary") or {}
        curves[name] = [p["dev"]["reward"] for p in r.get("points", []) if p.get("dev")]
        results[f"training {name}"] = s
        gain = (s.get("dev_best") or 0) - (s.get("dev_start") or 0)
        vs = f", Reconciler {base_reward:+.3f}" if base_reward is not None else ""
        check(f"training: {name}", r.get("status") == "done" and gain >= 0,
              f"dev {s.get('dev_start'):+.3f} -> best {s.get('dev_best'):+.3f}{vs}  ({time.time() - t:.0f} s)")
    if "cem seed 1 again" in curves:
        check("training is reproducible (same seed)", curves["cem seed 1"] == curves["cem seed 1 again"], "identical dev curves")

    # 5. the app's HTTP API
    from auditgym.env.adapters import make_http_server
    srv, env_ = make_http_server(0, "open", ui=True, host="127.0.0.1", api=harness.Jobs(base=runs))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"

    def call(path: str, body=None):
        req = urllib.request.Request(url + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def wait(rid: str) -> dict:
        for _ in range(900):
            r = call(f"/api/runs/{rid}")[1].get("run") or {}
            if r.get("status") != "running":
                return r
            time.sleep(0.2)
        return {}

    st, res = call("/api/train", {"method": "cem", "dataset": {"preset": "simple"}, "iterations": 6, "population": 8, "episodes_per_candidate": 2})
    busy = call("/api/runs", {"policy": "reconcile", "split": "dev"})[0] == 409
    tr = wait(res.get("run", ""))
    st2, res2 = call("/api/runs", {"policy": "reconcile", "split": "dev", "limit": 3})
    ev = wait(res2.get("run", ""))
    steps = call(f"/api/runs/{res2.get('run')}/steps?episode=0")[0]
    bad = call("/api/runs", {"policy": "rm -rf /", "split": "dev"})[0] == 400 and call("/api/train", {"iterations": 10_000})[0] == 400
    srv.shutdown()
    env_.close()
    check("HTTP API: training + evaluation", st == 200 and tr.get("status") == "done" and ev.get("status") == "done" and steps == 200,
          f"evaluation reward {(ev.get('summary') or {}).get('reward')}")
    check("HTTP API: refuses busy and bad input", busy and bad, "409 while busy, 400 for an unknown policy or config")

    # 6. desktop smoke from source
    p = subprocess.run([sys.executable, os.path.join("desktop", "app.py"), "--smoke"], cwd=ROOT, env=env, capture_output=True, text=True)
    check("desktop app smoke test", p.returncode == 0, (p.stdout + p.stderr).strip().splitlines()[-1][:80] if (p.stdout + p.stderr).strip() else "")

    shutil.rmtree(runs, ignore_errors=True)
    failed = [c for c in checks if not c[1]]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} passed" + (f"; failed: {', '.join(c[0] for c in failed)}" if failed else ""))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump({"checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks], "results": results, "curves": curves}, fh, indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
