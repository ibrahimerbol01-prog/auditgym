"""Extract the real data the UI previews use into data.json.

Usage: python3 extract_data.py <repo_dir> <out_dir>
Reads trajectories.jsonl (one reconcile run) and report.json. Never reads private/ or truth.
"""
import collections
import json
import sys
from pathlib import Path

repo, out = Path(sys.argv[1]), Path(sys.argv[2])
EP = "ep_266dd8359c7dadbf"  # a recorded reconcile run with 5 findings, all confirmed
runs = collections.defaultdict(list)
for line in (repo / "trajectories.jsonl").read_text().splitlines():
    d = json.loads(line)
    runs[(d["policy"], d["episode_id"])].append(d)
steps = []
for d in runs[("reconcile", EP)]:
    a, o = d["action"], d["observation"]
    if a["tool"] == "list_records":
        rows = o["result"]["rows"]
        steps.append({"step": d["step"], "tool": "list_records", "table": a["args"]["table"], "rows": len(rows),
                      "remaining": o["remaining_steps"], "sample": rows[:4]})
    else:
        steps.append({"step": d["step"], "tool": a["tool"], "findings": a["args"]["findings"]["findings"],
                      "report": o["result"]["report"], "remaining": o["remaining_steps"], "reward": d["reward"]})
rep = json.loads((repo / "report.json").read_text())
table = []
for (pol, ep), st in runs.items():
    if pol != "reconcile":
        continue
    last = st[-1]
    r = last["observation"]["result"]["report"]
    table.append({"episode": ep, "steps": len(st), "reward": last["reward"], "p": r["precision"], "r": r["recall"],
                  "f1": r["f1"], "tp": r["tp"], "fp": r["fp"], "fn": r["fn"]})
data = {"episode": EP, "steps": steps, "policy_summary": rep["policy_summary"], "failure_analysis": rep["failure_analysis"],
        "versions": rep["versions"], "estimated_score": rep["estimated_score"], "reconcile_runs": table}
(out / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
print("wrote", out / "data.json")
