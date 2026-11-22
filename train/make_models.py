"""Build the preloaded models in models/ from real training runs (reproducible: same seeds, same results).

    PYTHONPATH=src python train/make_models.py

Each auditor model is the complete run.json of one training (learning curves, the learned settings, the result on
the fresh test set), so the app shows it exactly like a training the user ran. models/index.json lists every model
with its SHA-256; the installer and `auditgym models` download from it. Local LLMs are listed too: they are pulled
through Ollama (`ollama pull`), never stored in this repository.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from auditgym import learner  # noqa: E402

OUT = os.path.join(ROOT, "models")

AUDITORS = [
    ("auditor-cem", "General auditor (recommended)",
     "Trained with CEM on mixed companies. Reads every table and runs all four checks; matches the hand-written "
     "Reconciler on the test set.", {"method": "cem", "seed": 1}, None),
    ("auditor-cem-interacting", "Auditor for interacting errors",
     "Trained only on companies whose errors interact (the brief's hardest cases).",
     {"method": "cem", "seed": 1, "dataset": {"preset": "interacting"}}, None),
    ("auditor-reinforce", "REINFORCE auditor",
     "Trained with the policy-gradient method instead of CEM: noisier, weaker. Useful to compare methods.",
     {"method": "reinforce", "seed": 1}, None),
    ("auditor-noise-control", "Untrained control (noise instead of reward)",
     "The same training, but the search saw random noise instead of the reward. Shows what the auditor does "
     "without learning: the gap to the others is what training adds.", {"method": "cem", "seed": 1}, "noise"),
]

LLMS = [
    {"name": "qwen2.5-0.5b", "kind": "ollama", "ollama": "qwen2.5:0.5b", "title": "Qwen2.5 0.5B (local LLM)",
     "description": "Smallest local language model, about 400 MB, via Ollama. In the app: Runs → LLM or LLM + tools. "
                    "Measured on the test set: −0.50 alone, −0.33 with tools.", "download_mb": 398, "licence": "Apache-2.0"},
    {"name": "qwen2.5-1.5b", "kind": "ollama", "ollama": "qwen2.5:1.5b", "title": "Qwen2.5 1.5B (local LLM)",
     "description": "Small local language model, about 1 GB, via Ollama. Measured on the test set: −0.60 alone, "
                    "−0.09 with tools (precision 0.88).", "download_mb": 986, "licence": "Apache-2.0"},
]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    entries = []
    for name, title, desc, cfg, control in AUDITORS:
        run = learner.train(cfg, run_id="preloaded-" + name, base=tempfile.mkdtemp(prefix="auditgym-models-"),
                            control=control)
        if run["status"] != "done":
            print(f"{name}: training {run['status']} {run.get('error', '')}", file=sys.stderr)
            return 1
        run["preloaded"] = {"name": name, "title": title}
        data = (json.dumps(run, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")
        with open(os.path.join(OUT, name + ".json"), "wb") as fh:
            fh.write(data)
        test = (run.get("test") or {}).get("auditor") or {}
        entries.append({"name": name, "kind": "auditor", "file": name + ".json", "title": title, "description": desc,
                        "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "dev_best": run["summary"]["dev_best"], "test_reward": test.get("reward"),
                        "test_f1": test.get("f1"), "env_version": run.get("env_version")})
        print(f"{name:26s} dev best {run['summary']['dev_best']:+.3f}  test {test.get('reward'):+.3f}  {len(data)} bytes")
    index = {"version": 1, "about": "Preloaded models for AuditGym. Auditors are training runs (20 numbers each plus "
                                   "their curves); local LLMs are pulled through Ollama.",
             "models": entries + LLMS}
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"wrote {OUT}/index.json ({len(entries)} auditors, {len(LLMS)} local LLMs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
