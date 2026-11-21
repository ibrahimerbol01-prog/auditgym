# UI design brief (for whoever edits `src/auditgym/ui/`)

The UI is the jury's first impression. It must look like a design studio made it **for auditors**, not like an
AI-generated SaaS template. The concept is **"auditor's working papers"**: dark graphite paper, ivory ink, one brass
accent, a red pen for exceptions.

## Style decision v2: neutral & clean (Мади, Nov 21) — current
Replaces the "working papers" look (dark graphite, brass, serif) on every page, which the owner did not like.
- **Light by default**, `[data-theme=dark]` mirrors it (toggle "Тёмная / Светлая", saved as `ag-theme`).
- White cards (`--s1`) on an off-white page (`--bg`), thin lines, 8 / 12 px radii, quiet shadows.
- **Inter** for all text and headings (600–700, tight tracking); **JetBrains Mono** for numbers and identifiers.
- **One accent:** blue `--gold` (the token name is historical) for actions, links, focus and ticks. Green / red only
  for results. No grain, no crop marks, no W/P code boxes, no gradients.
- Every colour is still a token in `style.css`; WCAG AA is checked for both themes by `tests/test_ui_static.py`.
- The sections below that describe the working-papers identity are kept for history; where they conflict, this wins.

## Layout decision v2: training harness (Мади, Nov 20, evening) — current
Chosen from three options after a market study (`docs/design-research/harness/`: TensorBoard, MLflow, Aim, Optuna and
Trackio run locally; 26 product sites). **B for the app, C for the terminal.** It replaces the chat layout below.

- **B · Training console → the app page "Запуски" (`/runs.html`).** Inspired by Prime Intellect Hosted Training and
  OpenAI fine-tuning, drawn in the working-papers identity. One run per screen: progress (% of episodes, one segment
  per episode), reward per episode with the base policies as dashed reference lines, a status card (agent, split,
  closed mode, env version, duration, agent time), four stat tiles, episode tiles (label from the public config
  only), comparison with oracle / reconcile / random / flag_all from `report.json`, and the learning curve once
  `train/curve.json` exists (T10). "Журнал шагов" lists every step (tool, short arguments, rows, steps left).
  "Новый запуск" starts a built-in policy from the page; **an external agent is never started from the browser**:
  the dialog builds the terminal command (model, temperature, max tokens) to copy.
- **C · Terminal trace → `python -m auditgym.cli run-agent`.** A rolling window of the last 8 steps redrawn in place,
  each episode collapsing to one result line with a reward bar, then a score card and a comparison with the base
  policies. ANSI only on a real terminal; `--plain`, pipes and `NO_COLOR` get plain lines. Not a full-screen TUI,
  no curses, standard library only.
- **One source of truth:** both read and write the same run folders (`~/.auditgym/runs/<id>/run.json`,
  `steps.jsonl`; `AUDITGYM_RUNS` overrides), produced by `auditgym.harness` in closed mode. The app shows runs made
  in the terminal and vice versa.

## Layout decision v1 (Мади, Nov 20) — superseded by v2
**The UI is a Claude-style chat with a sidebar of big graphs of the training process and telemetry.**

- **Centre: the chat.** A calm, centred conversation thread with a composer at the bottom, in the manner of Claude's
  chat. An episode reads as a conversation: each agent step is one turn (action → observation), shown as a compact
  tool-call row that expands on click; the last turn is the submitted findings (C-1) and the evaluator's conclusion
  (C-2).
- **Sidebar: big graphs.**
  - *Training process*: reward against training iteration from `train/curve.json` (task T10/D1), with the held-out
    (dev) curve and the reconcile baseline drawn on the same axes.
  - *Telemetry of the current run*: steps used of 100, P, R, F1, return (reward), steps and agent time (the
    diagnostics the case PDF asks for), plus tokens when an LLM agent runs.
- **Proposed panel codes:** L-2 run thread, T-1 training curve, T-2 run telemetry.
- **Open question:** what the person types in the composer — tool actions (play mode) or instructions to an LLM agent
  (needs T12 and a local Ollama). Decide before building the composer.

### Two audiences, two interfaces (Мади, Nov 20)
Both run on the same environment and evaluator, so they can never show different results.

| | **Web app: for newcomers** | **Terminal: for specialists** |
|---|---|---|
| Who | Jury members, auditors, students, anyone seeing an RL environment for the first time | RL/ML engineers who train or benchmark agents |
| Goal | Understand what the environment does and why the score is fair, in a few minutes, without reading docs | Run, script and compare agents fast and reproducibly |
| Shape | The chat + graphs layout above | Commands with compact tables, every option as a flag, `--json` output for scripts |
| Defaults | Everything pre-filled; one obvious next action per screen; plain-language labels with hover help for terms (invoice, allocation, period, FX rate, evidence, F1) | Nothing hidden: seeds, configs, splits, closed/open mode, and agent settings (temperature, top-p, max tokens, token budget, max steps ≤ 100) as flags |
| Advanced settings | Behind an "Advanced" disclosure, closed by default | Always available |

- **Bridge between them:** every run in the web app shows the exact terminal command that reproduces it, with a copy
  button. Newcomers see where the specialist path starts; specialists can reproduce any demo run.
- **Terminal constraints:** `src/` is standard library only and CI runs on Windows, so no `curses`, `rich` or
  `textual`. The terminal interface is a well-formatted command line (aligned tables, tick marks with a legend,
  colour only as an extra signal and switchable off), not a full-screen TUI. It extends the existing `cli.py`
  commands and the planned `run-agent` (T12).

### Rules from the case PDF that this layout must respect
- **Not a chatbot** (§01: "среда для возможного дообучения модели, а не платёжное приложение, чат-бот или один
  аудиторский отчёт"). The chat is the *view of an episode*, not a general assistant: every message is an
  environment step or its result.
- **Inspired by Claude, not copied.** Take the structure and the calm; no Anthropic colours, fonts or logo (see the
  never-list below); the thread uses the working-papers identity.
- **Training graphs need a held-out comparison** (§01: improvement may not be claimed "без контролируемого сравнения
  на отложенных данных"). Always show the dev curve and a baseline next to the training curve.
- **No hints during an episode; closed mode hides reward** (§04: reward and diagnostics stay with the evaluator until
  the run ends). In closed mode the telemetry panel shows steps and time only, and fills in the scores after submit.
- **Show P, R, F1, return, steps and agent time as diagnostics** (§10) — the telemetry panel is where they live.
- **A scripted policy is enough for the demo; a local model is optional** (§07, §09). The UI must work fully with
  the scripted agents and no LLM installed.

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
