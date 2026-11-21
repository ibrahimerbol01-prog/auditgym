"""Train the parametric auditor (auditgym.learner) and write the learning curve to train/curve.json.

    PYTHONPATH=src python train/learn_rules.py --seed 1 [--iterations 30] [--method cem]

Training episodes are generated fresh (never a train-split or dev seed) and played in open mode; the current
policy is measured on the 10 held-out dev episodes in closed mode. CPU only, standard library only.
The run folder goes to $AUDITGYM_RUNS if set, else to a temporary directory.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "src"))

from auditgym import harness, learner  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Train the parametric auditor; write train/curve.json")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--iterations", type=int, default=30)
    ap.add_argument("--method", choices=("cem", "reinforce"), default="cem")
    ap.add_argument("--population", type=int, default=16)
    ap.add_argument("--episodes", type=int, default=4, help="episodes per candidate")
    ap.add_argument("--preset", choices=learner.PRESETS, default="mixed")
    ap.add_argument("--eval-every", type=int, default=2)
    ap.add_argument("--out", default=os.path.join(HERE, "curve.json"))
    a = ap.parse_args(argv)
    config = {"method": a.method, "iterations": a.iterations, "population": a.population,
              "episodes_per_candidate": a.episodes, "seed": a.seed, "dataset": {"preset": a.preset},
              "eval_every": a.eval_every}
    base = os.environ.get("AUDITGYM_RUNS") or tempfile.mkdtemp(prefix="auditgym-train-")

    def show(e):
        if e["type"] != "iteration":
            return
        p, d = e["point"], e["point"]["dev"]
        dev = f" | dev {d['reward']:+.3f} F1 {d['f1']:.2f} fp {d['fp']:.1f} steps {d['steps']:.1f}" if d else ""
        print(f"it {p['i']:3d}  train mean {p['train_mean']:+.3f} elite {p['train_elite']:+.3f} best {p['train_best']:+.3f}"
              f"  sigma {p['sigma']:.2f}  {p['eps_per_sec'] or 0:.0f} ep/s{dev}", flush=True)

    t0 = time.perf_counter()
    run = learner.train(config, base=base, on_event=show)
    elapsed = time.perf_counter() - t0
    if run["status"] != "done":
        print(f"training {run['status']}: {run.get('error', '')}", file=sys.stderr)
        return 1
    base_dev = learner.dev_baselines()
    points = [{"iteration": p["i"], "train_reward": p["train_mean"],
               **({"dev_reward": p["dev"]["reward"], "steps": p["dev"]["steps"]} if p["dev"] else {})}
              for p in run["points"]]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    harness._write_json(a.out, {"points": points, "config": run["config"], "run": run["id"],
                                "env_version": run["env_version"],
                                "baselines": {k: v["reward"] for k, v in base_dev.items()},
                                "best": {"i": run["best"]["i"], "dev": run["best"]["dev"], "describe": run["best"]["describe"]}})
    s = run["summary"]
    print(f"dev reward {s['dev_start']:+.3f} -> best {s['dev_best']:+.3f} (last {s['dev_last']:+.3f}); "
          f"reconcile {base_dev['reconcile']['reward']:+.3f}, random {base_dev['random']['reward']:+.3f}; "
          f"{s['episodes']} episodes in {elapsed:.1f} s")
    print("learned policy:")
    for d in run["best"]["describe"]:
        print(f"  {d['label']}: {d['value']}")
    print(f"wrote {a.out} (run folder {os.path.join(base, run['id'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
