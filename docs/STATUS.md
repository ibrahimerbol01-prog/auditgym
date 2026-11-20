# Snapshot — Nov 20, 22:10 (UTC+5)

Branch `snapshot/2026-11-20` freezes everything the team has at this moment. `main` keeps moving.

## Done and in the repo
- **Environment** (`src/auditgym/`): generator with 4 recorded error types and interactions, Gymnasium-style
  `AuditEnv` with 5 read-only tools, evaluator as a separate process, stdio and HTTP front doors. Standard library only.
- **Verification**: `python -m auditgym.verify` — all checks pass, estimated 100/100 on our copies of the brief's
  formulas; fuzz 37 valid configs OK / 13 rejected with a bounded error / 0 failures.
- **Tests**: 53 (incl. 16 + 4 red-team attacks, 7 static UI tests, 5 browser journeys, 3 optional Gymnasium tests).
- **UI** (`src/auditgym/ui/static/`): "auditor's working papers" design v6, dark + paper themes, offline fonts,
  keyboard and screen-reader support. Screenshots: `docs/screenshots/`.
- **Integrations**: optional Gymnasium adapter (`examples/gymnasium_env.py`), Docker image pinned by digest.
- **Docs**: README (jury quickstart), DESIGN.md (rules, measured results, red-team table, limitations),
  `docs/TASKS.md` (plan to the finish), `docs/DESIGN_BRIEF.md`, `docs/VIDEO_SCRIPT.md`, `docs/research/`.
- **CI**: tests + verify on Ubuntu and Windows, UI end-to-end in a browser, Gymnasium check, Docker offline.

## Outside the repo
- Slide deck (Claude artifact "AuditGym — презентация", 9 slides) — still in the earlier visual style; to be
  restyled to match the UI (lead).

## In progress / next
- T10 learning curve (Мади) → D1 chart → D2 polish → T12 → T11.
- T13 difficulty ladder, docs fixes (Ерназар).
- Video (T6), deck names + export (T7), submission (T9) by Nov 22 21:00.
