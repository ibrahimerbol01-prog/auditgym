# AuditGym — design note

AuditGym is a reproducible RL environment for financial-audit agents: synthetic company books with hidden, recorded errors; five read-only investigation tools; a matcher and reward that pay for proof, not for persuasion. It is an environment and an evaluator — it trains nothing.

Numbers below come from `report.json` produced by `python -m auditgym.verify` (ENV 1.0.0, Python 3.11, one run ≈ 15 s).

## 1. Architecture

```
  Evaluator service (own process)          AuditEnv (Python API / stdio / HTTP)        Agent / policy
  generate(seed, config) ──public only──▶  reset(seed, config) -> (obs, info)   ◀──▶  {"tool", "args"}
  holds truth, provenance, clean books     step(action) -> 5-tuple                     sees only tool results
  score(findings, steps) ◀──submission───  submit -> evaluator                          never sees seed or truth
  reference() / finalize()  (organizer API, never reachable from the agent)
```

The environment process never loads `truth.json`, `provenance.json` or the clean tables: they live only in the evaluator service, which runs as a separate process speaking JSON lines. The agent talks to the environment only, so it has no channel to read or write evaluator state. In closed mode the terminal reward is `0.0` and `info` is `{}`; scores stay in the service until `finalize`.

## 2. Data generation

1. **Consistent hidden history** (`gen/history.py`): customers with a fixed billing currency, invoices with line items and service periods, payments (full, split, lump-sum, short-pay with a documented deduction and credit note, advances), supplier expenses, and daily synthetic FX random walks. The ledger is double entry in the base currency and balances by construction; every base amount is foreign amount × the policy-date rate, rounded half-even once.
2. **Recorded causal injections** (`gen/inject.py`): every change goes through a mutator that logs a replayable operation (`provenance.json`). `replay(clean, operations) == public` is checked for every episode.
3. **Anti-tell naming** (`gen/export.py`): IDs are assigned after injection by one canonical routine — chronological numbering from a random start, per-episode prefixes. `id_seed` changes only names, `layout_seed` only file row order.
4. **episode_id** is a hash of the canonical public tables, never of the seed (the generator is open source; a seed-derived id would let anyone recover the seed and regenerate the truth).

### Error types and the separation rule

| Type | What changes (only) | Expected amount | Minimal evidence |
|---|---|---|---|
| duplicate_invoice | a second invoice, same entity, line items **and service period**, new number | invoice total, invoice currency | both invoice ids |
| payment_allocation | allocation rows: part or all of a receipt left in 2350 Unapplied cash though the payment references the invoice | unapplied base amount | payment, invoice, unapplied row |
| date_or_fx (a) | booked base amount uses another day's rate | \|booked − correct\|, base | invoice, AR row, fx row of the policy date |
| date_or_fx (b) | posting date moved inside the period and amount at that day's rate | \|booked − correct\|, base | invoice, AR row, fx row of the policy date |
| period_classification | posting timestamp moved across the period boundary (amount stays correct) | correct base amount | invoice, AR row (+ policy-date fx row if foreign) |

No injection changes two of {amount, period, allocation rows, extra record}. Interaction scenarios: **A** — a foreign invoice near the period end with a wrong-day rate, posted after the boundary, and partly paid by a receipt that is only partly applied (3 linked issues); **B** — a duplicate whose second copy is also posted after the boundary (2 linked issues). Each issue's amount is its own injection delta, so fixing one never changes another.

**Legitimate distractors** (must not be flagged): split and lump-sum payments, short pay with a documented deduction + credit note, advances with no invoice reference held in unapplied cash, recurring invoices with the same lines and amount but a different service period, timestamps written in UTC that resolve to the next local day.

## 3. Contract and tools

`reset(seed, config)` → `(observation, info)`; the first observation carries the task, manifest, policy, tool schemas, the finding schema and the published per-type finding rules. `step(action)` → `(observation, reward, terminated, truncated, info)`. Tools: `list_records` (≤ 50 rows, stable opaque cursors), `get_record`, `get_document`, `calculator` (Decimal recursive-descent parser: numbers, `+ - * / ( )`, unary minus, limits on length, digits, depth and result size), `submit`. Every step — including unknown tools, tables and ids — consumes one step and returns a bounded error from a fixed code list with a fixed message. 100 steps including submit; 60 s wall clock (injectable clock); truncation returns `{}` and is scored as an empty submission with all steps counted.

## 4. Matching and reward (published, code in `eval/scoring.py`)

- Invalid structure (wrong keys or types, unknown type, NaN/Infinity, `bool`/float/negative/huge amounts, > 30 findings, > 10 evidence ids, explanation > 1000 chars, wrong episode_id) → episode ends, reward −1, evaluator log entry.
- Matching conventions follow the organizers' check definitions (Nov 20): ids and currency are compared exactly (case and spaces matter); `affected_ids` and `evidence_ids` are sets after the raw-length limits; an evidence id that does not exist in the episode makes the finding a FP.
- A finding matches an issue iff type, canonical `affected_ids` and currency are equal, `|claimed − expected| ≤ τ` (τ = `tolerance_minor` in truth if present, else the published `1 + conversions`, else 0), and the evidence contains one complete acceptable set. The jury's entry point is `judge_adapter.py` (README §0).
- One-to-one maximum matching (augmenting paths); ties prefer the smaller amount error, then the lower finding index. Unmatched and duplicate findings are false positives.
- P, R = 0 on a zero denominator; F1 = 2TP/(2TP+FP+FN); both empty → F1 = 1; empty reference with findings → F1 = 0.
- `reward = clip(2·F1 − 1 − 0.002·inspection_steps, −1, 1)`. The explanation is never parsed.

## 5. Measured results

Verification (our own stand-ins for the organizers' checks, one test per item):

| Area | Passed |
|---|---|
| Contract and isolation (C1–C20) | 20 / 20 |
| Data and reference (20 hidden-style episodes, incl. the independent verifier) | 20 / 20 |
| Reward reliability (R1–R20) | 20 / 20 |
| Reproducibility (20 pairs: exact repeat; new order and ids keep the oracle answer and reward) | 20 / 20 |
| Config fuzzing (50 random configs) | 37 valid episodes pass every check; 13 rejected with a bounded error; 0 failures |

Baseline policies, mean return on 9 hidden-style episodes (3 clean, 3 mixed, 3 interacting):

| Policy | Clean | Mixed | Interacting | Mean steps |
|---|---|---|---|---|
| Oracle (evaluator-only) | +1.000 | +1.000 | +1.000 | 1 |
| Reconciliation (public tools only) | +0.967 | +0.962 | +0.966 | 18.4 |
| Random (seed 7) | −1.000 | −1.000 | −1.000 | 10.6 |
| Flag-everything | −1.000 | −1.000 | −1.000 | 2 |

## 6. Failure analysis

The reconciliation baseline applies careful rules (company time zone, document date, service periods, documented deductions) and, with full information, finds all 89 issues on the 20 hidden-style episodes with 0 false positives. Its only cost is the step budget (≈ 19 page reads → −0.04).

What defeats simpler solvers — each row replaces one careful rule with a shortcut (rewards assume 20 steps):

| Shortcut | TP | FP | FN | Mean reward |
|---|---|---|---|---|
| Duplicates by entity + amount only (ignores service period) | 89 | 47 | 0 | +0.23 |
| Any cash in unapplied = allocation error (ignores documented advances) | 89 | 25 | 0 | +0.34 |
| UTC calendar dates instead of the company time zone | 89 | 5 | 0 | +0.92 |
| Right findings but no evidence ids | 22 | 67 | 67 | −0.15 |
| Careful rules (reference) | 89 | 0 | 0 | +0.96 |

So the distractors do their job: recurring invoices and advances punish the two most common shortcuts hard, the time-zone distractor is rarer (one or two per episode at distractor level 1), and unproven accusations are worth less than nothing.

## 7. Independent verification

`eval/verify_independent.py` was written by a separate agent from the specification only, without access to the generator or the rules engine (a test asserts it imports neither). It re-proves every declared issue from the public records and checks that one acceptable evidence set is sufficient *on its own*. On its first run it found a real bug — a foreign-currency period error whose evidence set could not prove the amount — which we fixed by adding the policy-date FX row to such sets. It now runs inside `verify` on all 20 hidden-style episodes.

## 8. Adversarial testing (red team)

A second separate agent attacked the environment white-box from the agent's side: path traversal through every id, cursor and URL; existence probing; cursor forging; malformed and oversized input on stdio, HTTP and the calculator (200k random calculator strings); about 2,600 extreme configs; scoring tricks; resubmission; closed-mode reward leaks; cross-episode state. It found eight real problems, each now a test in `tests/attacks/` and fixed:

| Finding | Severity | Fix |
|---|---|---|
| One malformed stdio line (5,000-digit integer, 50,000-deep JSON) killed the stdio front door | blocker | bounded error for any unparsable line; front doors never raise |
| Malformed HTTP bodies and Content-Length dropped the connection | low | 400 JSON errors |
| A non-JSON submission (set, bytes, 980-deep nesting) ended the episode without a score | medium | sanitized: invalid structure, reward −1, logged |
| `reset` mid-episode abandoned it unscored (read for free, then replay) | medium | an abandoned episode is scored as empty with all its steps charged |
| Round 2 (Gemini): `POST /reset` body `{"op": ...}` overrode the operation | medium | `/reset` passes only `seed` and `config` |
| Round 2: `NaN` / `Infinity` accepted as JSON on HTTP and stdio | low | strict JSON in and out (`parse_constant` rejects, `allow_nan=False`) |
| Round 2: `/fonts/` path with `\` or `..` (Windows traversal) | low | font names with `\`, `/` or `..` are refused |
| Open-mode near-miss reasons let an agent probe which (type, ids) are real | low-medium | only matched / not matched is shown; reasons stay with the organizer |
| Organizer commands (`reference`, `finalize`) reachable through the env's evaluator pipe; negative step counts accepted | low-medium | organizer token held only by the organizer client; the env gets a restricted channel; steps validated and counted by the evaluator |
| A bad `episode_dir` killed the evaluator process | low | bounded error |
| Cross-origin / foreign-Host POSTs accepted by the localhost server | low | Host, Origin and Content-Type checks |

It also trained classifiers on public features to predict which invoices host errors: formatting features (ids, minutes, round amounts, offsets, line counts) are at chance (AUC 0.49–0.51). It found one real tell — host invoices were drawn from a narrower date window — which we removed; the remaining signal comes from the errors' own nature (cut-off errors sit near the period end, FX errors need a foreign invoice). An in-process Python agent shares memory with the environment and is trusted by construction; untrusted agents should use the stdio or HTTP front doors.

## 9. Optional training (measured, not scored)

Training is optional in the brief and earns no points by itself; we include it to show the environment is usable for RL and to measure it honestly (§01: no improvement claim without a controlled comparison on held-out data).

- **What is trained.** A small auditor policy (`learner.AuditorPolicy`, 20 parameters: which tables to read, which checks to run, how strict) with the cross-entropy method (CEM) or REINFORCE, on freshly generated episodes in open mode, CPU only. No weights of a language model are trained.
- **How it is measured.** Every 2 iterations the current policy plays the 10 held-out **dev** episodes in closed mode; dev picks the best iteration. At the end, that policy is measured once on a fixed **test** set of 20 fresh episodes (5 clean, 5 with interacting errors, 10 with ordinary errors, seeds outside train, dev and the trainer's stream), next to the Reconciler and the Intern.
- **Result** (30 iterations × 16 candidates × 4 episodes, ~20 s on 4 cores):

| Seed | dev at start | best on dev | on test | test F1 | Reconciler on test |
|---:|---:|---:|---:|---:|---:|
| 1 | −0.645 | +0.961 | +0.961 | 1.00 | +0.961 |
| 2 | −0.600 | +0.961 | +0.961 | 1.00 | +0.961 |
| 3 | +0.013 | +0.961 | +0.961 | 1.00 | +0.961 |

  The same seed reproduces the same curve. REINFORCE (seed 1) reaches +0.745 on dev. **Training matches the hand-written Reconciler from a poor start; it does not beat it**, and we claim nothing more.
- **Controlled comparison: the gain comes from the reward.** The same runs (same seeds, episodes, search, dev and test measurement) with seeded noise in place of the evaluator's reward (`learner.train(..., control="noise")`, `python train/learn_rules.py --control noise`) end far lower: best on dev −0.110 / +0.009 / +0.286 and on test −0.137 / −0.131 / +0.479 for seeds 1–3, against +0.961 on dev and test for all three with the reward. The control is not flat at its start because keeping the best of 16 dev checks of a random walk is itself a weak search; that is exactly why it is the right baseline. The improvement therefore comes from the reward, not from the search procedure or the policy space (which contains both the careful rules and the naive shortcuts). Checked by `train/campaign.py` (seed 1, margin 0.5 on dev and test) and, on a short run, by `tests/test_evaluation_features.py`.
- **Local LLMs.** The app can evaluate an installed Ollama model in two modes. *Pure*: the model picks every action. *LLM + tools* (`policies/llm_assist.py`): code reads all tables, a broad check proposes candidates (including the brief's traps), the strict open rules re-check each one, and the model decides keep or drop from one compact line of facts per candidate; only real record ids are ever submitted. Measured on the 20 test episodes (CPU, Qwen2.5 GGUF): 1.5B pure −0.60 (no error found) → LLM + tools −0.09 (22 of 79 found, precision 0.88); 0.5B −0.50 → −0.33. Without the strict re-check the 1.5B model alone scores −0.82: on these books, small models cannot yet tell errors from legitimate patterns, so the gain comes mostly from the tools. Submitting every candidate scores +0.16 and an ideal judge +0.96, which bounds what a better model could reach.
- **Red team.** The app's Red team page (`redteam.py`) plays nine reward attacks (including flag-everything) and an RL attacker — a cheating policy trained with the same CEM to maximise reward without looking for errors — on the 20 test episodes. None beats silence (−0.50 on that mix); the RL attacker learns to claim nothing. This complements §8 and the R-checks; it is not part of the official verification.

## 10. Limitations (honest)

- **Synthetic only.** All companies, people, accounts and money are fictional; the FX series are random walks. Nothing here is evidence of fitness for real audit work, and the reward does not prove it.
- **Simplified FX policy.** Spot rate of the policy date in the company time zone, one rounding at the end; inspired by IAS 21 from secondary sources, not a faithful implementation.
- **Error density is unrealistic.** Up to 12 issues in 200–2,000 ledger rows is far above real base rates.
- **The careful baseline is strong.** With unlimited reading it solves every episode; difficulty comes from distractors and evidence requirements, not from hidden facts. We consider that correct for this brief (difficulty must not make the task unsolvable), but it means the environment separates careful from careless solvers more than strong from very strong ones.
- **Tolerance.** Absolute `1 + conversions` minor units forgives rounding only; a solver that rounds twice can miss by more.
- **Reward shape.** Silence on erroneous books and wild accusations on clean books both score −1; the reward cannot tell "did nothing" from "was badly wrong".
- **Open generator.** The code is public and deterministic. `episode_id` does not reveal the seed, but anyone with unlimited compute could search seeds by regenerating and comparing records; hidden seeds should be large (64-bit).
- **Training is small and bounded.** The optional trainer (§9) tunes a 20-parameter rule policy, not a language model; it reaches the Reconciler's level on held-out episodes and does not exceed it. Local LLMs (Ollama) can be evaluated in the app but are not trained; on a CPU a model that picks every action itself is cut by the 60 s limit after a few steps, and even with tools a 1.5B model reaches −0.09 on the test episodes, far below the Reconciler (§9).
- **Docker base image.** The Dockerfile pins `python:3.11-slim-bookworm` by digest; rebuilding on a new digest needs the pin updated by hand (instructions in the Dockerfile).
- **The 60 s limit is real.** The brief's 60 s per episode applies to the front doors too; an LLM agent that thinks for seconds per step will be truncated. The UI pauses the clock for human practice only.
- **Our checks are stand-ins.** The organizers' 20/20/20 check definitions were not available to us when this was written; our lists are built from the brief and may differ in detail.

## 11. Tools and resources used

Python 3.11 standard library only at runtime. Fonts: Inter and JetBrains Mono (SIL Open Font License, bundled with their licenses; the UI makes no network requests, which a browser test asserts). Built with the help of AI coding assistants (Anthropic Claude; Google Antigravity/Gemini), with every result checked by the tests above.
