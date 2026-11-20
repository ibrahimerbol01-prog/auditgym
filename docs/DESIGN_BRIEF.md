# UI design brief (for whoever edits `src/auditgym/ui/`)

The UI is the jury's first impression. It must look like a design studio made it **for auditors**, not like an
AI-generated SaaS template. The concept is **"auditor's working papers"**: dark graphite paper, ivory ink, one brass
accent, a red pen for exceptions.

## Keep (this is the identity)
- **Tick marks** (inline SVG symbols `#tm-agree`, `#tm-foot`, `#tm-trace`, `#tm-exc`): ✓ agreed to document, Σ footed,
  ↔ traced, ⊗ exception. Use them for verification states, always with the legend nearby.
- **Working-paper references**: A-1 Ledger, A-2 Invoices, A-3 Payments, A-4 FX, B-1 record/document, B-2 calculations,
  C-1 findings, C-2 evaluator's conclusion, K-1 classification, R-1…R-4 report. New panels get a code in this scheme.
- **Working-paper header** blocks (Client · Period · Prepared by · Reviewed by) on major panels.
- **Accounting numbers**: monospace with tabular figures, negatives in parentheses, single rule above / double rule
  below totals, currency code after the figure, dimmed decimals.
- **Typography**: Source Serif 4 light for display and big numbers, Inter for UI text, JetBrains Mono only for data,
  IDs and code. No other families.
- **Colour** only from the tokens in `style.css` (`--bg --s1 --s2 --s3 --txt --txt2 --txt3 --gold --gold2 --pos --neg …`,
  both themes). Green/red only for meaning (correct/exception, +/−), never decoration. Colour is never the only signal:
  always a sign, mark or word too.
- **Depth** from surfaces and hairlines, not shadows or glows.
- **Motion**: tokens `--t-fast` 120 ms, `--t` 200 ms, `--t-slow` 320 ms; colour/border/opacity changes on hover, no
  lifting buttons; the hero "reviewer's pen" animation plays once; everything static under `prefers-reduced-motion`.

## Never (these read as AI template)
Ticker tapes, one italic gold word in a headline, letter-spaced ALL-CAPS labels everywhere (one deliberate use per
screen at most), section numbers 01/02/03, glowing cards, gradient blobs, decorative pulsing dots, a grid of four icon
cards, stock illustrations, emoji, fake testimonials/logos, any real company's brand look.

## Honesty
Every number shown is real: read it from `report.json`, `curve.json`, the episode, or the hero guard test's facts.
The UI never touches `private/`, truth or provenance, and never highlights rows for the player (except the explicit
"check it yourself" deep link from the hero).

## Quality bar for every UI PR
- Before/after screenshots at 1440×900 and 390×844 (Playwright, see `tests/test_ui_browser.py` for the in-process
  server), dark and paper theme.
- All tests green: `PYTHONPATH=src CHROME_PATH=<chrome> AUDITGYM_E2E=1 python -m unittest discover -s tests -q`
  (contrast for both themes, ids, labels, offline, fonts, hero figures, full journey by mouse and keyboard).
- No horizontal overflow at 390, 768, 1280, 1920 px. Keyboard reachable, visible focus, labels for every control.
- Offline: no CDN, fonts bundled with their OFL licence.

## References we learned from (patterns, not looks)
Stripe — discipline: a flat considered colour beats a cheap imitation of an effect. Linear — few theme variables,
pixel alignment you feel after minutes. Mercury — serif headline + sans body, hairline depth, mono for data, no hover
lifts. Bruno Simon — let people touch the product in the first seconds. The Pudding — a story shaped like a V:
wide → one detail → wide again.
