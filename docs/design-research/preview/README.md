# UI preview (design proposal, not the shipped UI)

Static mock-ups of the planned UI. They are **not** wired to the environment; the shipped UI is still
`src/auditgym/ui/`. Open the HTML files directly in a browser: they are self-contained and work offline.

| File | What |
|---|---|
| `preview_v3.html` | **Current proposal.** Newcomer-first web/desktop app: result first, four-step path, findings in plain words, evidence and specialist metrics only on click. Neutral greys, monochrome buttons, one muted blue for data. |
| `terminal_v2.html` | Terminal mock-up for specialists (`run-agent`, proposed in task T12). |
| `v3-*.png`, `v2-terminal.png` | Screenshots at 1440×900 (graphite and paper) and 390×844. |

## Honesty notes
- All numbers are real: one recorded reconcile run (`ep_266dd8359c7dadbf`, 5 findings, all confirmed, reward
  0.970) from `trajectories.jsonl`, and baselines from `report.json`.
- The training curve is an **illustrative shape**, labelled as such, until task T10 writes `train/curve.json`.
- `run-agent` and its flags do not exist yet (task T12).
- The neutral palette departs from `docs/DESIGN_BRIEF.md` (warm graphite, brass, 3 px corners). Adopting it means
  changing the tokens in `src/auditgym/ui/static/style.css` and the brief together, then rerunning the contrast test.
  Every text colour in the proposal passes WCAG AA (≥ 4.5:1) in both themes.

## Regenerate
```bash
python3 docs/design-research/preview/tools/extract_data.py . docs/design-research/preview/tools
python3 docs/design-research/preview/tools/build3.py . docs/design-research/preview/tools   # needs build2.py next to it
```
`build.py` and `build2.py` produce the earlier v1 (working papers) and v2 (neutral, data-dense) previews.
