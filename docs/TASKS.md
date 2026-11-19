# Remaining tasks (assigned by the lead)

Status on Nov 19, 23:45: core, verify (all checks), 33 tests, UI, DESIGN.md, README, deck, video script are done.
Each task below has an owner, a tool and a definition of done. Branch `task/<id>`, PR to `main`.

| ID | Task | Owner · tool | Done when |
|---|---|---|---|
| T1 | Docker offline run on Windows: `docker build -t auditgym .` then `docker run --rm --network none auditgym`; pin the base image by digest in the Dockerfile (`docker buildx imagetools inspect python:3.11-slim-bookworm`) | D · human + Gemini Flash | output ends with every check passing; Dockerfile has `@sha256:`; timing with `--cpus=2 --memory=4g` noted in the PR |
| T2 | Matcher mutation check: `tests/test_mutations.py` flips each rule of `eval/scoring.py` (ignore type / currency / ids, tolerance +100, partial evidence, allow duplicate matches) via monkeypatch and asserts that `verify.reward_checks()` then has at least one failure for every mutation | A · Claude Code (Sonnet) | every mutation is caught; if one survives, add the missing reward check |
| T3 | Red team round 2 (different model family than round 1): attack `env/`, `env/adapters.py`, `eval/` from the agent side; every success becomes a failing test in `tests/attacks/` (do NOT edit `src/`) | C · Antigravity Gemini Pro | PR with new attack tests or "nothing found" plus the list of attacks tried |
| T4 | Clean-clone check on a second machine (Windows): `git clone`, `$env:PYTHONPATH="src"; python -m auditgym.verify`, `python -m auditgym.cli ui`, play one episode from the video script | B · human | screenshot of verify output + UI in the PR; fix README wording if a step was unclear |
| T5 | UI polish (only `src/auditgym/ui/static/`): disabled buttons look disabled; empty states; keyboard focus outlines; nothing else | B · Gemini Flash | before/after screenshots; tests and verify still green |
| T6 | Video: record by `docs/VIDEO_SCRIPT.md` (2:30), Russian voice | B · human | mp4 in the team Drive folder |
| T7 | Deck: put team names on the cover and the repo link on the last slide; export PPTX + PDF | C · human | files in the team Drive folder |
| T8 | Official check definitions (brief §10): find them in the cabinet / Telegram; if found, map each official check to ours in `docs/OFFICIAL_CHECKS.md` and list gaps | A · human + Claude | mapping table; gaps turned into tasks |
| T9 | Submission (Nov 22): make the repo public, Drive folder with video + deck + GitHub link, send from the cabinet, track = FinTech, by 21:00 | lead (human) | confirmation screenshot |

Order of urgency: T1, T4 (they can block grading), then T2, T3, T8, then T5–T7, then T9.
Freeze for `src/`: Nov 22, 18:00.
