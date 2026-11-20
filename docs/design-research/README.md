# AI app design: market research for the AuditGym UI

Collected Nov 20, 2026 by the UI design owner (with Claude Code). Purpose: ground the UI decisions in
`docs/DESIGN_BRIEF.md` in data about what the AI market actually looks like, and specify the planned
Agent lab (temperature, token and step settings).

## The short version

1. **The AI market is light, blue-or-monochrome and rounded.** Of 84 measured AI product pages, 81% are
   light-first, 48% have no saturated button colour at all (black/white buttons), and blue is the most
   common accent. Our graphite-first theme, brass accent and 3 px corners are already in the minority. That is
   what makes the UI recognisable, so keep them.
2. **"AI purple" is no longer the tell.** Only 4% of pages use a violet/purple accent. The current commodity
   signals are **gradients (51% of pages)** and **frosted-glass blur (35%)**. Our never-list already bans
   gradient blobs and glows; add backdrop blur to it.
3. **Serif display type is the premium signal in AI and finance.** About 15 of 84 market pages set their
   headline in a serif (Claude, Copilot, Claude Code, Harvey, Mercury, Rogo, Fieldguide, Vellum, PromptLayer,
   Artificial Analysis, Zed…). Two use the exact same family as us (Source Serif 4: W&B Weave, Basis). Our
   Source Serif 4 + Inter + JetBrains Mono trio is on-trend without being generic. Inter alone is the top-3
   font on only 25% of pages.
4. **Everyone says "agents" (80%), half talk about evidence (51%).** Finance AI positions itself as
   "auditable AI" (Trullion), "agentic" (BlackLine, Fieldguide, DataSnipper) and "trusted" (AlphaSense, Rogo).
   AuditGym's honest pitch — reward only for *proved* findings — fits that vocabulary; the UI should show
   the proof, not claim it.
5. **Claude and ChatGPT as references: copy the developer playgrounds, not the chat screen.** The case
   brief says the product is *not a chatbot*, and our design brief forbids a real company's brand look. The
   playgrounds (Claude Console, OpenAI Playground, Google AI Studio, AI SDK Playground, PromptLayer,
   promptfoo) share one layout that suits an "Agent lab": settings in a right rail, a run log in the centre,
   and a results grid for comparing runs (section 6).
6. **Pattern libraries agree with our direction.** 55 Shape of AI patterns, Microsoft's 18 HAX guidelines
   and 16 Smashing transparency patterns are collected in `patterns.json`. The ones that matter most for us:
   *Footprints / Audit trail* (replay), *Verification* (confirm before submit), *Partial success* (per-finding
   result), *Parameters* and *Cost estimates* (Agent lab), HAX G1/G2/G11 (say what the system can do, how
   well, and why).

## 1. Method

- **115 public pages** captured with headless Chromium on Nov 20, 2026: 95 AI products across 9 market
  segments plus pattern libraries and design references, and a second batch of 20 LLM playgrounds and
  parameter panels.
- Each page: a **1440×900** screenshot, a full-page screenshot (capped at 6,000 px) and a **390×844** mobile
  screenshot — the same sizes our design brief's quality bar uses. Light colour scheme, cookie banners
  dismissed where possible.
- **Measured in the page** (computed styles of visible elements, first ~2.5 screens): page background and
  theme, fonts ranked by amount of text, headline font/size/weight, saturated button colours, button corner
  radius, gradients, coloured glow shadows, backdrop blur, letter-spaced caps labels, and how often the copy
  says *agent* or *evidence/sources/citations*.
- **92 pages were measurable.** 23 were not: bot checks or login walls (ChatGPT, OpenAI Playground, Mistral
  Console, Pi, Meta AI, Lovable, Replit, LMArena), timeouts (Numeric, Basis, FloQast) or pages with too
  little text to measure (Grok, Qwen, Humanloop…). Their screenshots are still in the image set where they
  rendered. Market statistics use the **84 measurable product pages** (pattern libraries and design
  references excluded).

### Limits (read before quoting a number)
- These are public marketing, docs and landing pages, not the logged-in apps. The playground layouts in
  section 6 come from the public docs pages and screenshots, not from using the products.
- The measures are heuristics. "Serif headline" was counted by hand from font names, because brand serifs
  (Arcadia, Arizona, Anthropic Serif…) cannot be detected automatically. An emoji measure was dropped
  because the detector also counted © and ™.
- One day's snapshot, a sample of well-known products rather than a census, and small segments
  (n = 5–16): treat segment percentages as directional.

## 2. Market context

- Generative AI app downloads roughly doubled to 3.8 billion in 2025, and consumer spending more than tripled
  to over $5 billion ([TechCrunch on Sensor Tower](https://techcrunch.com/2026/01/21/consumers-spent-more-on-mobile-apps-than-games-in-2025-driven-by-ai-app-adoption/?rand=324));
  Sensor Tower expects AI app in-app revenue above $4 billion in H1 2026 alone
  ([Sensor Tower](https://sensortower.com/press/sensor-tower-state-of-ai-2026-report-global-time-spent-on-generative-ai-apps-projected-to-more-than-double-year-over-year)).
- In Q2 2026, ChatGPT held about 60% of generative-AI consumer revenue and Claude rose to second place
  ([9to5Mac](https://9to5mac.com/?p=1064275)). The 7th edition of a16z's top-100 gen-AI consumer apps
  (Oct 2026) ranks products by traffic ([a16z](https://a16z.com/100-gen-ai-apps-7/)).
- These are consumer figures. They are context for why Claude and ChatGPT set users' expectations of what
  an AI product looks like; they are not about our niche (RL environments and audit tooling).

## 3. What the market looks like: measured

Percentages are shares of measurable pages in each segment.

| Measure | All market | assistant | benchmark | builder | eval | evidence | finance | local | playground | productivity |
|---|---|---|---|---|---|---|---|---|---|---|
| n | 84 | 7 | 5 | 9 | 14 | 5 | 15 | 7 | 16 | 6 |
| Dark theme first | 19% | 0% | 0% | 22% | 29% | 40% | 27% | 0% | 12% | 33% |
| Inter is a top-3 font | 25% | 14% | 0% | 33% | 14% | 20% | 33% | 14% | 38% | 33% |
| System font stack is top-3 | 13% | 14% | 0% | 11% | 14% | 0% | 0% | 43% | 19% | 17% |
| Any gradient element | 51% | 57% | 40% | 67% | 57% | 60% | 67% | 29% | 25% | 67% |
| Coloured glow shadows | 8% | 0% | 20% | 0% | 7% | 0% | 13% | 14% | 6% | 17% |
| Backdrop blur (glass) | 35% | 29% | 0% | 33% | 14% | 100% | 33% | 57% | 25% | 67% |
| ≥3 letter-spaced caps labels | 12% | 0% | 20% | 11% | 21% | 0% | 7% | 29% | 12% | 0% |
| Accent is indigo/violet/purple | 4% | 0% | 20% | 0% | 7% | 0% | 7% | 0% | 0% | 0% |
| No saturated button colour | 48% | 57% | 20% | 33% | 57% | 40% | 27% | 86% | 50% | 67% |
| Pill-shaped buttons (≥20 px) | 29% | 43% | 40% | 44% | 14% | 60% | 27% | 29% | 12% | 33% |
| Square-ish buttons (≤4 px) | 17% | 14% | 20% | 22% | 29% | 20% | 20% | 14% | 6% | 0% |
| Median h1 size (px) | 50 | 43 | 44 | 36 | 50 | 64 | 68 | 50 | 37 | 64 |
| Copy mentions "agent" | 80% | 57% | 80% | 89% | 93% | 100% | 73% | 86% | 69% | 83% |
| Copy mentions evidence/sources | 51% | 43% | 100% | 33% | 64% | 80% | 60% | 57% | 38% | 0% |

- **Accent hues** (pages with a saturated button colour): blue 20, red/pink 6, green 5, yellow/gold 4,
  teal 4, orange/brown 2, indigo/violet 2, magenta/purple 1. A brass/gold accent like ours is rare (4).
- **Fonts** (top 3 by text volume): Inter 21 pages, the Apple system stack 8, SF Mono 6, then a long tail
  of brand fonts (Anthropic Sans/Serif, DM Sans, Source Sans, Geist, Mona Sans, Montserrat…).
- **Serif headlines** (hand count from font names): about 15 of 84, concentrated in assistants (Claude,
  Copilot), developer tools from the same vendors (Claude Code, Claude Console docs, Zed), finance
  (Mercury, Rogo, Fieldguide, Numeric, Basis) and legal/evidence (Harvey).

**Where AuditGym sits:** dark-first (minority, 19%), brass accent (rare), 3 px corners (with the 17% "precise"
camp, mostly eval tools), serif + sans + mono (on-trend), no gradients/glow/blur (the opposite of the 51%/35%
commodity look). The current identity is already differentiated by the numbers.

## 4. What each segment does: observed

From the contact sheets (`contact_sheets/*.jpg` in the image set).

- **Assistants (Claude, ChatGPT, Gemini, Perplexity, Grok, Kimi, Qwen, DeepSeek, Mistral):** one centred
  input as the whole first screen, a short greeting line, suggestion chips under the input, the model picker
  *inside* the input ("Auto ▾"), a quiet left sidebar for history and projects, almost no colour, lots of
  white space. Claude's marketing uses a warm off-white and a serif headline — the same family of feeling as
  our "paper" theme.
- **LLM playgrounds (Google AI Studio, AI SDK Playground, PromptLayer, OpenRouter, Langfuse/Braintrust/Weave
  playground docs, promptfoo viewer):** three panes. Left: navigation or prompt list. Centre: the prompt and
  the streamed output. Right: a **"Run settings" rail** with model, temperature, max output tokens, top-p,
  stop sequences, seed and structured-output toggles. AI SDK Playground puts **two models side by side**;
  promptfoo's viewer is a **matrix of test cases × configurations** with pass/fail per cell.
- **Eval and observability (LangSmith, Braintrust, Phoenix, Weave, Langfuse, Inspect, Opik, Helicone,
  MLflow):** dark heroes with a product screenshot; inside the product, a summary-metrics row above a
  **samples table** (Inspect's log viewer: input, target, answer, score per sample, with a score filter) and
  collapsible **trace trees** of tool calls.
- **Benchmarks (Vals, Artificial Analysis, SWE-bench, Epoch, METR):** leaderboard tables, bar charts and
  editorial methodology pages. The credibility comes from showing the method next to the number.
- **Finance and audit AI (MindBridge, DataSnipper, Trullion, Rillet, Digits, Fieldguide, BlackLine,
  AuditBoard, Ramp, Brex, Mercury, Hebbia, AlphaSense, Rogo, Pennylane):** two visual camps. *Fintech
  premium*: serif display, deep green or graphite, texture or photography (Basis uses a photo of a
  handwritten ledger; Mercury a landscape; Rogo a deep green field). *Enterprise SaaS*: bright blue, product
  screenshots in browser frames. Copy is "agentic", "auditable", "trusted".
- **Evidence apps (Elicit, Consensus, Harvey, NotebookLM, Hex, Julius):** inline citations and a sources
  panel next to the answer — the closest relatives of our "finding + evidence IDs".
- **Local AI (Ollama, LM Studio, Jan, Open WebUI, Msty, GPT4All, AnythingLLM):** monochrome, a download
  button, a real screenshot of the app; 86% use no saturated button colour.

## 5. Pattern catalogs → AuditGym screens

`patterns.json` holds 55 Shape of AI patterns (6 groups), Microsoft's 18 HAX guidelines and 16 Smashing
transparency patterns plus 11 anti-patterns. The mapping that matters:

| Screen | Patterns that apply | What it means in our UI |
|---|---|---|
| Start | HAX G1 *make clear what the system can do*; Shape of AI *Initial CTA*, *Example gallery* | One primary action; the episode list is the example gallery; say plainly what the agent can and cannot do (5 read-only tools, 100 steps) |
| Investigate | *Footprints*, *Stream of Thought*, *Cost estimates*; Smashing *Living breadcrumb* | The action log is the footprint trail; every action shows that it costs one step before it is taken; the step counter is the breadcrumb |
| Findings | *Citations / References*, *Verification*; Smashing *Intent preview* | Evidence IDs are citations; the confirm-before-submit dialog is the intent preview |
| Result | HAX G2 *how well*, G11 *why*; Smashing *Partial success*, *Audit trail* | Per-finding outcome (matched or not) instead of one verdict; link from the result to the replay |
| Replay | Smashing *Dynamic checklist*, *Audit trail / Show work* | Planned / current / done steps; every step can be reopened |
| Agent lab (planned) | *Model management*, *Parameters*, *Cost estimates*, *Variations*, *Branches*, *Controls*, *Caveat*, *Disclosure* | Section 6 |

**Anti-patterns to keep out** (Smashing): a generic spinner or "Working…" text, binary failure banners,
unsanitised raw logs, a personified tone on a serious task, blaming the AI for a tool failure.

## 6. Agent lab: what the playground research suggests

The team wants temperature, token and step controls. The research points to this shape (in our
working-paper language, not any vendor's look):

- **Layout: three panes.** Left: agent and episodes. Centre: the run log, one line per tool call, each
  expandable (like a collapsed tool-call row), with the step counter. Right: **L-1 Run settings** rail.
- **L-1 Run settings** (proposed working-paper code; the brief asks new panels to get one):
  - *Agent*: random · reconcile · flag-all · local LLM (Ollama).
  - *Model*: picked from the models the local Ollama server lists; disabled with a one-line install hint
    when Ollama is not running (empty state, not an error).
  - *Sampling*: temperature (0–2, default 0), top-p, max tokens per reply, seed. Hidden for the scripted
    agents, where they mean nothing.
  - *Budget*: token budget per episode, max steps (capped at the environment's 100).
  - *Run*: episode split and number of repeats.
- **L-2 Run log** in the centre, streamed; **L-3 Comparison schedule** below or as a tab: rows = episodes,
  columns = runs (each column header shows its settings), cells = reward with a tick mark (✓ matched,
  ⊗ exception) — promptfoo's matrix, drawn as an audit schedule with a total row.
- **Caveat and disclosure:** label LLM runs as such, and say that LLM results are not exactly repeatable
  across machines even at temperature 0 with a seed.
- **Guardrail:** these are agent settings only. The environment's limits and the scoring do not change, and
  every run records its settings next to its score.

This depends on task T12 (the agent runner) in `docs/TASKS.md`; it is a proposal for the lead, not
assigned work.

## 7. Recommendations for the UI owner

1. **Keep the working-papers identity.** The data shows it is differentiated on theme, accent, corners and
   type.
2. **Add backdrop blur (frosted glass) to the never-list**; it is now as common a template signal as
   gradients (35% of pages).
3. **Borrow calm, not chrome, from Claude/ChatGPT:** one primary action per screen, monochrome controls
   with a single accent, collapsed tool-call rows that expand on demand.
4. **Do not build a chat screen.** The case brief says "not a chatbot"; a chat layout invites that reading.
5. **Watch the overlap with Basis** (ledger photography, Source Serif 4): our identity is the *system* of tick
   marks, references and accounting rules — not paper imagery.
6. **Put the numbers in the deck.** A "UI rationale" slide with the table in section 3 and the pattern map in
   section 5 gives the jury criteria to judge the UI by.
7. **Fix in the current UI:** in the 1440×900 dark capture the hero working paper has a large empty area
   below the reconciliation (it may be the hero animation mid-play at 1.5 s; check the final frame).

## 8. Files

| File | What |
|---|---|
| `README.md` | This report |
| `samples.csv`, `samples.json` | One row per captured page: category, URLs, theme, fonts, accent, radius, signals, screenshot file names; `samples.json` also has the raw measurements |
| `stats.md` | The statistics table, regenerated by `tools/aggregate.py` |
| `patterns.json` | Shape of AI (55), Microsoft HAX (18), Smashing transparency (16 + 11 anti-patterns) |
| `tools/` | `capture.js` (Playwright capture), `aggregate.py` (dataset, stats, contact sheets), `targets*.json` |

The screenshots (342 files, about 47 MB) and contact sheets are third-party pages, so they are **kept out
of the repository** and shared separately.

To regenerate (dev machine with Node and Playwright, not part of the offline build):

```bash
node docs/design-research/tools/capture.js docs/design-research/tools/targets.json research-out
node docs/design-research/tools/capture.js docs/design-research/tools/targets2.json research-out
cp docs/design-research/tools/targets*.json research-out/
python3 docs/design-research/tools/aggregate.py research-out research-out/out
```

## Sources

Products: the 115 URLs in `samples.csv`. Market and patterns:
[Sensor Tower State of AI 2026](https://sensortower.com/press/sensor-tower-state-of-ai-2026-report-global-time-spent-on-generative-ai-apps-projected-to-more-than-double-year-over-year) ·
[TechCrunch](https://techcrunch.com/2026/01/21/consumers-spent-more-on-mobile-apps-than-games-in-2025-driven-by-ai-app-adoption/?rand=324) ·
[9to5Mac](https://9to5mac.com/?p=1064275) ·
[a16z top 100, 7th edition](https://a16z.com/100-gen-ai-apps-7/) ·
[Shape of AI](https://www.shapeof.ai/) ·
[Microsoft HAX Design Library](https://www.microsoft.com/en-us/haxtoolkit/library/) ·
[Smashing: AI transparency patterns, part 2](https://www.smashingmagazine.com/2026/05/practical-interface-patterns-ai-transparency/) and
[part 1](https://www.smashingmagazine.com/2026/04/identifying-necessary-transparency-moments-agentic-ai-part1/) ·
[Inspect log viewer](https://inspect.aisi.org.uk/log-viewer.html) ·
[Gigazine on the Show HN design study](https://www.gigazine.net/gsc_news/en/20260423-design-slop) (not verified against the original).
