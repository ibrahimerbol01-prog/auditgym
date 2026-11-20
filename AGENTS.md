# AuditGym — rules for every AI agent (Claude Code, Antigravity/Gemini)

FinTech case of Genesis Hackathon 2026: an RL environment + evaluator for audit agents. The jury
scores the environment, not an agent. Deadline Nov 22, 23:59 Astana (UTC+5); freeze 18:00.

## Before you change anything
- Run `PYTHONPATH=src python -m unittest discover -s tests -q` (53 tests; the 5 browser tests and 3 Gymnasium tests run when Playwright / gymnasium are installed, CI always runs them) and
  `PYTHONPATH=src python -m auditgym.verify` (must end with every check passing). Both must stay green.
- Read DESIGN.md (how it works, published rules) and docs/TASKS.md (your task).

## Hard rules
- Python 3.11 standard library only in `src/`. No new dependencies.
- Money = integer minor units; conversions only via `money.convert` (Decimal, half-even). No float for money.
- Randomness only via `seeding.Rng` / `derive_seed`; never `hash()`, `random.randint`, set-order output.
- Time zones only from `timeutil.TZ_OFFSETS_MIN`; never `zoneinfo`.
- Never weaken a check, a test or `tests/attacks/*` to make something pass. A failing test is a bug report.
- Agent-facing code (`env/`, `policies/` except oracle, `ui/`) never touches truth, provenance or `private/`.
- Changing generation changes episodes: then run `python -m auditgym.cli build-suite` and commit the new
  `episodes/` and `episodes/golden_hashes.json` together, and say so in the commit message.
- UI is owned by Мади (read docs/DESIGN_BRIEF.md). Only one UI PR open at a time.
- UI: `tests/test_ui_static.py` (files, fonts, ids, labels, contrast, offline) and `tests/test_ui_browser.py`
  (full journey by mouse and keyboard) must stay green. Colours come only from the tokens in `style.css`.
- Field names follow the brief exactly (see README "The environment in one screen").

## Workflow
- One branch per task: `task/<name>`. Small commits. Open a PR to `main`; the lead reviews and merges.
- "Done" = paste the last lines of the test run and of `verify` in the PR description.
- If the brief or DESIGN.md does not decide something, stop and ask in the PR instead of guessing.
