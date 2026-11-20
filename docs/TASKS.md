# Plan to the finish (assigned by the lead)

Status on Nov 20, 01:30: core, verify (all checks), 45 tests, UI v3, CI, DESIGN.md, README, deck, video script are done.
UI v5 redesign ("audit working papers") is in progress on `task/ui-redesign-pro`.

**The new main idea:** the case is "RL environments *for fine-tuning* models". The strongest proof that our
environment is good is that **something actually learns on it**. Every task below serves one of two stories:
1. *The environment is correct* (contract, data, reward, reproducibility) — mostly done.
2. *The environment trains* — learning curves on held-out episodes (new: T10–T14).

**Team:** A = **Мади** (Claude Code, Pro: Sonnet by default, Opus only for reviews) · C = **Ерназар** (Google Antigravity / Gemini) ·
B, D = humans without an agent (video, Docker, clean clone) · lead = owner + the lead Claude (reviews, merges, design).
Ерназар starts with **T3 → T13 → T14**. Мади starts with **T10 → T12 → T2**, T11 if time allows.

Rules for every task: branch `task/<id>-<short>`, PR to `main`, paste the outputs, AGENTS.md applies.
Training code lives in `train/` or `examples/`, **never in `src/`** (src stays standard-library only).
Anything that needs truth must get it through the evaluator service (score/reward), never by reading `private/`.

## Must (blocks grading or the story)

| ID | Task | Owner · tool | Done when |
|---|---|---|---|
| T1 | Docker offline run on Windows: `docker build -t auditgym .`, `docker run --rm --network none auditgym`; pin the base image by digest (`docker buildx imagetools inspect python:3.11-slim-bookworm`) | D · human + Gemini Flash | output ends with every check passing; Dockerfile has `@sha256:`; CI `docker-offline` green |
| T4 | Clean clone on a second Windows machine: `git clone`, `$env:PYTHONPATH="src"; python -m auditgym.verify`, `python -m auditgym.cli ui`, play the video-script episode | B · human | screenshots in the PR; README fixed where a step was unclear |
| T10 | **Learning curve, pure Python.** `train/learn_rules.py`: a small parametric auditor (which checks to run, tolerances, when to abstain; ~20–60 parameters) trained with REINFORCE / cross-entropy method on **freshly generated** episodes (new seeds, never dev), reward from the evaluator only. Evaluate every N iterations on the 10 dev episodes in closed mode. Write `train/curve.json` (iteration, train reward, dev reward, steps) and a chart on the report page. Deterministic by seed. Runs on a laptop CPU in ≤ 15 min | A · Claude Code (Sonnet) | dev reward rises from ≈ −1 to clearly positive; chart in report; `python train/learn_rules.py --seed 1` reproduces the curve; numbers in DESIGN.md |
| T16 | UI v5 review and merge; restyle deck + `docs/banner.png` to the same visual language | lead + design agent | merged; 45+ tests green; deck matches UI |
| T6 | Video (2:30, Russian voice) from `docs/VIDEO_SCRIPT.md`, updated with: hero animation as opening shot, learning curve (T10) as the climax | B · human | mp4 in the Drive folder |
| T7 | Deck: team names, repo link, new slide "Среда обучает" with the T10 curve (+ T11 if done); export PPTX + PDF | C · human | files in the Drive folder |
| T9 | Submission: repo public, Drive folder (video + deck + GitHub link), send from the cabinet, track FinTech | lead (human) | confirmation screenshot, by Nov 22 21:00 |

## Should (strong extra points)

| ID | Task | Owner · tool | Done when |
|---|---|---|---|
| T2 | Matcher mutation check `tests/test_mutations.py`: flip each rule of `eval/scoring.py` via monkeypatch; every mutation must be caught by `verify.reward_checks()` | A · Claude Code | every mutation caught (or a new reward check added) |
| T3 | Red team round 2 from the agent side; every success becomes a failing test in `tests/attacks/` | C · Antigravity Gemini Pro | PR with new attacks or "nothing found" + list tried |
| T12 | **Plug-and-play benchmark.** `python -m auditgym.cli run-agent --cmd "<program>" --split dev` launches any external agent process, connects it to the environment over stdio in closed mode, runs the split, prints a score card (mean reward, F1, steps, per error type). Ship `examples/random_agent.py` and `examples/llm_agent.py` (local LLM via Ollama HTTP, e.g. `qwen2.5:1.5b`; inference only, honest result) | A · Claude Code | one command benchmarks any agent; README section "Подключить своего агента" |
| T13 | **Difficulty ladder.** `python -m auditgym.cli ladder`: reward of reconcile / random / flag_all across `distractor_level` 0–2 × error count; writes `ladder.json`; report page chart. Shows the curriculum knobs work | C · Gemini Pro | chart shows reconcile degrading gracefully with difficulty; no change to scoring |
| T14 | **Gymnasium adapter** `examples/gymnasium_env.py` (optional import, Discrete/Text spaces documented) + test skipped when `gymnasium` is absent; README snippet "3 lines to use with your RL framework" | D · Gemini Flash | `gymnasium.utils.env_checker.check_env` passes in CI extra job |
| T8 | Official check definitions (brief §10): find them in the cabinet / Telegram; map to ours in `docs/OFFICIAL_CHECKS.md`; gaps → tasks | A · human + Claude | mapping table |

## Ambitious (hard; we try, and show only what is honestly done)

| ID | Task | Owner · tool | Done when |
|---|---|---|---|
| T11 | **Fine-tune an LLM with GRPO on our reward (Unsloth, free Google Colab T4).** Task format: a compact public "case packet" built from an episode through the public tools (one invoice + its payments + relevant FX + ledger rows), the model outputs a findings JSON; reward = our evaluator's score. Model: Qwen2.5 0.5B/1.5B (4-bit LoRA). Before/after on held-out dev packets. Notebook in `train/grpo_colab.ipynb`, results in `train/grpo_results.json`. Save checkpoints to Drive (Colab disconnects) | A · human with Google account + Claude Code | dev reward after > before with the same seeds; if not by Nov 21 22:00, we do not show it |
| T15 | Multi-step LLM agent through the real environment (tool calls `list_records` → `submit`) using the T11 model via T12 harness | A · Claude Code | score card on dev, whatever it is |
| T17 | Final-stage show (Nov 28–29): "Аудитор против ИИ" — a jury member plays a 3-minute episode in the UI, then reconcile and (if any) the trained model play the same episode; local leaderboard | lead + B | rehearsed twice |

## Timeline (Astana / Tashkent time, UTC+5)

| When | What |
|---|---|
| Fri Nov 20, morning | T1, T4 start (blockers). T10 starts (A). Lead: review T3, merge UI v5 (T16) |
| Fri Nov 20, afternoon | T11 Colab setup and a first tiny run (A). T12 (A or second Claude session), T13 (C) |
| Sat Nov 21 | T10 done → chart into report + DESIGN.md. T11 main run. T2, T14. Deck + video draft with real curves |
| Sat Nov 21, 22:00 | **Go / no-go for T11**: only a real, reproducible improvement goes into the deck |
| Sun Nov 22, 12:00 | Feature freeze: only fixes after this |
| Sun Nov 22, 18:00 | Code freeze for `src/` |
| Sun Nov 22, 21:00 | Submission (T9) — two hours of buffer before 23:59 |

## Paste-ready prompt for a teammate's agent

```
Clone https://github.com/ibrahimerbol01-prog/auditgym. Read AGENTS.md, CONTRIBUTING.md, DESIGN.md and
docs/TASKS.md. Your task is T<number>. Run the tests and verify first; both must be green.
Work only on branch task/T<number>-<short>. Training/example code goes to train/ or examples/, never src/.
Never read private/ or truth from agent or training code — get rewards only from the evaluator.
Finish with tests and verify green and open a PR to main using the template with the outputs pasted.
If something is not decided by the brief or DESIGN.md, ask in the PR instead of guessing.
```
