# AuditGym — a guide for the judges

**A reproducible RL environment and evaluator for financial-audit agents.** Synthetic books of fictional companies with
hidden, recorded errors; five read-only tools; a shared matcher and terminal reward that pay for proven findings, not
for persuasive text. Genesis Hackathon 2026 · FinTech track · MIT licence.

![AuditGym](docs/banner.png)

This page follows the brief: **§1** how to check everything with one command, **§2** where each of the 100 points is
verified, **§3** the deliverables of brief §09, **§4** what the judges' own policies will see, **§5** the demo,
**§6** plugging in an agent, **§7** optional work that earns no points but is measured honestly, **§8** limitations.

---

## 1. One command, offline (≈ 20 s)

```bash
docker build -t auditgym .
docker run --rm --network none auditgym            # = python -m auditgym.verify, inside 2 CPU / 4 GB
```

**Without Docker** — any Python 3.11, 3.12 or 3.13; no dependencies (the runtime is the standard library only), so
nothing is downloaded:

```bash
git clone https://github.com/ibrahimerbol01-prog/auditgym && cd auditgym
python -m pip install -e .        # adds the `auditgym` command; no packages are fetched
auditgym verify                   # the same check as the Docker image
```

Or with no install step at all, from the checkout:

```bash
PYTHONPATH=src python -m auditgym.verify                      # Linux / macOS
$env:PYTHONPATH="src"; python -m auditgym.verify              # Windows PowerShell
```

After `pip install -e .`, every command below also works as `auditgym <command>` (`auditgym ui`, `auditgym tui`,
`auditgym demo`, `auditgym run-agent ...`).

Expected output (abridged):

```
1 Contract & isolation         20/20 ✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓
2 Data & reference             20/20 ✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓
3 Reward reliability           20/20 ✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓
4 Reproducibility              20/20 ✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓✓
5 Engineering & explanation     5/5  ✓✓✓✓✓
Estimated score: 100.0 / 100
```

It needs no network, GPU or paid API, writes `report.json` (versions, every check, diagnostics, failure analysis) and
`trajectories.jsonl`, and exits non-zero if any check fails. Both files are also committed. CI runs the same command
on Linux, on Windows and in the Docker image on every change.

## 2. Where each criterion of brief §10 is verified

Our checks are built from the brief's published definitions (the organisers' own lists may differ in detail).
Every check has an id in `report.json`; the code is in `src/auditgym/verify.py`.

| Criterion (points) | What we check | Ids |
|---|---|---|
| **Contract & isolation** (25) | `reset`/`step` signatures and JSON; reproducibility across processes; isolated state; 50-row pages and stable cursors; bounded errors that cost a step; exact decimal calculator that refuses code; 100-step and 60 s limits (`truncated=true`, empty answer); `submit` ends the episode; invalid structure → −1; 30 / 10 / 1 000 limits; nothing after the end; **no hidden truth in observations, errors, paths or debug output**; reward 0 during the episode and nothing scored in closed mode until the run ends | C1–C20 |
| **Data & reference** (25) | On hidden-style episodes: the books balance before the error is planted, the declared discrepancy appears after it, and an independent verifier proves each issue from the records alone | D1–D20 |
| **Reward reliability** (25) | Correct + proven beats silence on erroneous books; silence beats false accusations on clean books; duplicates give nothing; flag-everything scores badly; saving steps only slightly separates equal answers; wrong type, ids, amount, currency or evidence do not match; guessed ids are false positives; one-to-one matching; resubmission refused; NaN / bool / huge amounts rejected; timeout scored as an empty answer; zero-denominator rules; a persuasive explanation changes nothing | R1–R20 |
| **Reproducibility & generalisation** (15) | 20 pairs: an exact repeat of seed + actions, and the same company with shuffled order and new IDs keeps the oracle's answer and reward | P1–P20 |
| **Engineering & explanation** (10) | one command offline; versions and configs recorded; trajectory logs with the required fields and no reference in observations; measured failure analysis; honest limitations | E1–E5 |

The blockers named in §10 — leaked hidden data, writing into the evaluator, real financial data, a broken core — are
what C19, C20 and the out-of-process evaluator guard against. All data is synthetic.

**The reward** (brief §05, unchanged): `clip(2·F1 − 1 − 0.002·inspection_steps, −1, 1)`. Matching, tolerances and the
normalisation code are published (`src/auditgym/eval/scoring.py`, [DESIGN.md](DESIGN.md) §4).

## 3. Deliverables (brief §09)

| The brief asks for | Where |
|---|---|
| Source with a licence and pinned dependencies: generator and environment | `src/auditgym/` (`gen/`, `env/`), `LICENSE` (MIT); no runtime dependencies; the Docker base image pinned by digest |
| README: container instructions and one verification command | this page, §1 |
| Shared matcher and reward, schemas and policies | `src/auditgym/eval/scoring.py`, `eval/service.py`; schemas in the first observation; `policy.json` per episode |
| 10 open train and 10 open dev episodes | `episodes/train/`, `episodes/dev/` (configs in `configs/`; golden hashes tested) |
| Tests of the environment, matching and reward | `tests/`: 130+ tests including `tests/attacks/` (malformed input, cross-origin requests, crashes, red-team rounds) |
| Four baseline policy adapters | `src/auditgym/policies/baselines.py`: oracle (evaluator-only), reconcile, random (fixed seed), flag_all |
| `trajectories.jsonl` with episode_id, step, action, observation, reward, terminated, truncated; no reference in observations | committed; regenerated by verify; checked by E3 |
| A short design note | [DESIGN.md](DESIGN.md) |
| A demo | §5 below (a scripted policy is enough; a local model is optional) |

## 4. What the organisers' policies will see (brief §06)

The same four policies run on every environment. On our episodes (from `report.json`):

| Policy | Clean | Mixed | Interacting | Steps | Time / episode |
|---|---:|---:|---:|---:|---:|
| Oracle (evaluator-only, checks the maximum) | +1.000 | +1.000 | +1.000 | 1 | 0.04 s |
| Reconcile (careful rules, public tools only) | +0.967 | +0.962 | +0.966 | 18 | 0.04 s |
| Random explorer (fixed seed) | −1.000 | −1.000 | −1.000 | 11 | 0.04 s |
| Flag everything (attack) | −1.000 | −1.000 | −1.000 | 2 | 0.08 s |

P, R, F1, return, steps and time per episode and policy are in `report.json` → `policies` (the diagnostics of §10).

- **Hidden seeds and new combinations.** `reset(seed, config)` accepts any valid config (see *Config* in §6); invalid
  ones return a bounded error. Every verify run fuzzes 50 random configs (0 failures).
- **Measured failure analysis.** The careful rules find every issue by type (duplicates 22/22, allocation 19/19,
  date/FX 25/25, period 23/23) with no false findings, while each naive shortcut loses to a planted distractor:
  duplicates by amount only +0.23, "any unapplied cash is an error" +0.34, UTC dates instead of the company time zone
  +0.92, findings without evidence −0.15 (`report.json` → `failure_analysis`, [DESIGN.md](DESIGN.md) §6).

## 5. See it working (demo)

```bash
PYTHONPATH=src python -m auditgym.cli demo        # one episode by the reconciliation baseline, as text
PYTHONPATH=src python -m auditgym.cli ui          # the app on http://127.0.0.1:8000 (offline; English, Russian in Settings)
PYTHONPATH=src python -m auditgym.cli tui         # the same in the terminal
docker run --rm -p 8000:8000 auditgym ui --host 0.0.0.0 --no-browser    # the app from the image
```

In the app:

- **Investigation** — play an episode by hand with the same tools and limits as an agent.
- **Runs** — evaluate a policy in closed mode on dev, train or a fresh **test** set of 20 episodes; replay every step;
  a failure analysis by error type appears when the run ends.
- **Red team** — *try to break the reward*: nine attacks aimed at it (flag-everything, repeat spam, type shotgun,
  evidence padding, amount hedging, proof-free findings, blind guessing, a malformed answer) and an **RL attacker**
  trained with CEM to win reward without looking for errors. Result: **0 of 9 attacks beat silence**, and the RL
  attacker learns that claiming nothing is the best it can do (−0.50, the floor). About 13 s; every attack replayable.
- **Training** — the optional trainer of §7 with live telemetry, a seed comparison and a Markdown report export.

A desktop build (Windows / macOS / Linux, with in-app updates) is produced by CI from `desktop/`; judges do not need it.

## 6. Plug in an agent

Any program that reads one observation (JSON) per line on stdin and writes one action (JSON) per line on stdout runs
in closed mode, where it never sees a reward:

```bash
PYTHONPATH=src python -m auditgym.cli run-agent --policy reconcile --split dev
PYTHONPATH=src python -m auditgym.cli run-agent --name mine --cmd "python examples/random_agent.py" --split test
```

Python, in-process:

```python
from auditgym.env.env import AuditEnv
env = AuditEnv(mode="open")                       # "closed": reward 0.0 until the run ends
obs, info = env.reset(seed=1, config={"interactions": ["A"]})
obs, reward, terminated, truncated, info = env.step(
    {"tool": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 50}})
# tools: list_records, get_record, get_document, calculator, submit
```

Gymnasium (`examples/gymnasium_env.py`, checked with `check_env` in CI):

```python
from examples.gymnasium_env import AuditGymEnv
env = AuditGymEnv(mode="open", action_mode="discrete")   # or action_mode="text" for JSON tool calls
```

Front doors for other languages: `python -m auditgym.cli serve --stdio` (JSON lines) or `serve --http --port 8080`
(127.0.0.1 only). Organizer scoring of one submission: `python -m auditgym.cli evaluate --private DIR --findings FILE --steps N`.

**Episode format** (brief §03). One fictional company, one reporting period: 416–1 336 ledger rows and 71–157
documents in the open suite, 0–12 issues. Public files per episode (`episodes/<split>/<episode_id>/public/`):
`manifest.json` (schema version, episode id, base currency, period, time zone, counts, rounding, `currency_exponents`),
`ledger.csv`, `invoices.jsonl`, `payments.jsonl`, `fx.csv`, `policy.json`, `documents.jsonl`. Times are ISO-8601 with
offsets, money is integer minor units, FX rates are decimal strings, missing links are explicit `null`.
Evaluator-only: `truth.json`, `provenance.json` (replayable), `clean/` (the books before injection).

**Config.** `n_invoices` (20–100), `n_expenses` (20–600), `errors` (per type 0–4), `clean`, `interactions` (`A`, `B`),
`base_currency`, `foreign_currencies` (1–3), `foreign_share` (0.2–0.8), `timezone`, `period_year`,
`period_start_month`, `period_months` (1–3), `distractor_level` (0–2), `layout_seed`, `id_seed`, `config_version`
(`src/auditgym/config.py`).

## 7. Optional work — measured, not scored

The brief scores the environment, not our agents, and forbids improvement claims without a controlled comparison on
held-out data. So everything below is measured on episodes the method never saw: 10 **dev** episodes pick the best
iteration, and a fixed **test** set of 20 fresh episodes (5 clean, 5 interacting, 10 with errors) reports it once.

| What | Result on the 20 test episodes |
|---|---|
| **Trained auditor** (a 20-parameter rule policy, CEM on CPU, about 20 s), seeds 1–3 | dev from −0.65 / −0.60 / +0.01 to **+0.961**; test **+0.961**, F1 1.00 — equal to the Reconciler, not better |
| **Control: the same training with noise instead of the reward** (brief §01), seeds 1–3 | test −0.14 / −0.13 / +0.48 against +0.961 with the reward: the gain comes from the reward, not from the search or the policy space |
| **Red team** (§5) | 0 of 9 attacks beat silence; the RL attacker converges to silence |
| **Local LLM, pure** (Qwen2.5 1.5B / 0.5B on CPU; the model picks every action) | −0.60 / −0.50: no error found before the 60 s limit |
| **Local LLM + tools** (code reads and proposes, the strict rules re-check, the model decides) | −0.09 / −0.33 (1.5B: 22 of 79 errors, precision 0.88). Without the re-check the model alone scores −0.82: the gain comes mostly from the tools |

To re-run all of it before a submission: `python train/campaign.py` (about 5 min, 20 checks; `report.json` untouched).

## 8. Honest limitations

Synthetic data only; a simplified FX policy; unrealistic error density; a strong careful baseline (the task separates
careful from careless solvers more than strong from very strong ones); an absolute rounding tolerance; a reward that
cannot tell "did nothing" from "was badly wrong" on erroneous books; an open, deterministic generator (hidden seeds
should be 64-bit); the 60 s limit cuts slow agents; our check lists are stand-ins for the organisers'. Details:
[DESIGN.md](DESIGN.md) §10.

## Repository

```
src/auditgym/   gen/ (history, injections, export, self-checks)   env/ (env, tools, calculator, front doors)
                eval/ (scoring, evaluator service, independent verifier)   policies/ (4 baselines, rules, LLM)
                verify.py  cli.py  harness.py (runs)  learner.py (optional trainer)  redteam.py  ui/  tui.py
configs/        open train/dev seeds and configs           episodes/   10 train + 10 dev episodes
tests/          unit tests, the 5 rubric areas, attacks, golden hashes, UI        examples/   agents, Gymnasium adapter
desktop/        desktop app and installers (optional)      train/      trainer CLI, pre-submission campaign
```

## Кратко по-русски

AuditGym — воспроизводимая среда для обучения ИИ-аудиторов: синтетические книги вымышленных компаний со скрытыми
записанными ошибками четырёх типов, пять инструментов только для чтения и награда за доказанные выводы.
**Проверка одной командой, без сети:** `docker run --rm --network none auditgym` (или
`$env:PYTHONPATH="src"; python -m auditgym.verify` в Windows) → 100/100, 85 из 85 проверок. Где проверяется каждый
критерий — §2, материалы из §09 брифа — §3, базовые политики жюри — §4. Приложение: `python -m auditgym.cli ui`
(английский по умолчанию, русский в «Настройках»). Без Docker: `python -m pip install -e .` → `auditgym verify`
(Python 3.11–3.13, ничего не скачивается). Необязательное обучение (§7) проверено контрольным сравнением: с наградой
+0.96 на тестовых эпизодах для трёх seed, с шумом вместо награды −0.14 / −0.13 / +0.48. Подробности и честные
ограничения — в [DESIGN.md](DESIGN.md).

## License

MIT (`LICENSE`). Bundled fonts: SIL Open Font License (`src/auditgym/ui/static/fonts/OFL-*.txt`). The desktop builds
also bundle a Python runtime, pywebview and the PyInstaller bootloader under permissive licences (the bootloader's GPL
exception allows MIT distribution): `desktop/THIRD_PARTY_NOTICES.md`, shipped inside every build. All data is
synthetic: no real companies, people, bank records or payments.
