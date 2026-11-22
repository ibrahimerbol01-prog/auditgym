# AuditGym

![AuditGym](docs/banner.png)

**Русский** · [English below](#english)

## По-русски: руководство для жюри

**Воспроизводимая RL-среда и оценщик для ИИ-аудиторов финансовой отчётности.** Синтетические книги вымышленных
компаний со скрытыми записанными ошибками четырёх типов, пять инструментов расследования только для чтения, общий
matcher и итоговая награда, которые платят за доказанные находки, а не за убедительный текст. Genesis Hackathon 2026 ·
трек FinTech · лицензия MIT.

### Установка: приложение или терминал

**Настольное приложение** — Windows, macOS, Linux. Не нужны Python и права администратора, работает без сети. Одна
строка скачивает последний релиз, сверяет его с `SHA256SUMS.txt`, ставит приложение **и** команду `auditgym` для
терминала, затем предлагает готовые обученные модели.

```powershell
irm https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.ps1 | iex      # Windows (PowerShell)
```
```bash
curl -fsSL https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.sh | sh  # macOS / Linux
```

Или скачайте архив для своей системы из [последнего релиза](https://github.com/ibrahimerbol01-prog/auditgym/releases/latest).
Обновления: «Настройки → Обновления» в приложении или `auditgym update`. Интерфейс на русском и английском.

**Терминал** — из исходников, Python 3.11–3.13. Только стандартная библиотека, ничего не скачивается.

```bash
git clone https://github.com/ibrahimerbol01-prog/auditgym && cd auditgym
python -m pip install -e .
auditgym            # терминальный интерфейс: обучение, «модель в работе», запуски и их повтор по шагам
auditgym ui         # то же приложение в браузере (http://127.0.0.1:8000)
auditgym verify     # проверка жюри: 100 из 100, около 20 секунд, без сети
```

### Проверка одной командой (без сети, ≈ 20 с)

```bash
docker build -t auditgym .
docker run --rm --network none auditgym            # = python -m auditgym.verify, в пределах 2 CPU / 4 ГБ
```

Результат: **100.0 из 100 по формулам брифа, 85 из 85 проверок**. Без Docker: `auditgym verify` (или
`PYTHONPATH=src python -m auditgym.verify`; в PowerShell `$env:PYTHONPATH="src"; python -m auditgym.verify`).
Официальный интерфейс жюри `judge_adapter.py` и его тесты: `PYTHONPATH=src python -m unittest tests.test_judge_adapter -v`
(в контейнере — раздел 0 ниже). Тот же прогон есть в приложении: страница «Режим жюри».

### Где проверяется каждый критерий брифа (§10)

| Критерий (баллы) | Что проверяем | Id в `report.json` |
|---|---|---|
| **Контракт и изоляция** (25) | сигнатуры `reset`/`step` и JSON; воспроизводимость между процессами; изоляция состояния; страницы по 50 строк и стабильные курсоры; ограниченные ошибки, которые стоят шаг; точный десятичный калькулятор; лимиты 100 шагов и 60 с; `submit` завершает эпизод; неверная структура → −1; **никакого скрытого эталона в наблюдениях, ошибках, путях и отладке**; в закрытом режиме награда 0 до конца прогона | C1–C20 |
| **Данные и эталон** (25) | книги сходятся до внесения ошибки, объявленное расхождение появляется после, независимый верификатор доказывает каждую ошибку только по записям | D1–D20 |
| **Надёжность награды** (25) | верное и доказанное лучше молчания на книгах с ошибками; молчание лучше ложных обвинений на чистых; дубли ничего не дают; «пометить всё» плохо; экономия шагов лишь слегка различает равные ответы; неверные тип, id, сумма, валюта или доказательства не засчитываются; убедительное объяснение ничего не меняет | R1–R20 |
| **Воспроизводимость и обобщение** (15) | 20 пар: точный повтор seed + действий и та же компания с перемешанным порядком и новыми ID дают тот же ответ оракула и ту же награду | P1–P20 |
| **Инженерия и объяснение** (10) | одна команда без сети; версии и конфиги записаны; журналы траекторий с нужными полями и без эталона; измеренный разбор провалов; честные ограничения | E1–E5 |

**Награда** (бриф §05, без изменений): `clip(2·F1 − 1 − 0.002·шаги, −1, 1)`. Код сопоставления — `src/auditgym/eval/scoring.py`.

### Материалы раздела 09

| Требуется | Где |
|---|---|
| Исходный код с лицензией и зафиксированными зависимостями | `src/auditgym/` (`gen/` — генератор, `env/` — среда), `LICENSE`; внешних зависимостей нет, образ Docker закреплён по хэшу |
| README с единой командой проверки | эта страница |
| Matcher и награда, схемы, политики | `src/auditgym/eval/scoring.py`, `eval/service.py`; схемы в первом наблюдении; `policy.json` в каждом эпизоде |
| 10 train- и 10 dev-эпизодов | `episodes/train/`, `episodes/dev/` (конфиги в `configs/`, контрольные хэши проверяются тестами) |
| Тесты среды, сопоставления и награды | `tests/` (181 тест, в том числе атаки в `tests/attacks/` и тесты интерфейса жюри) |
| Четыре адаптера базовых политик | `src/auditgym/policies/baselines.py`: oracle, reconcile, random, flag_all |
| `trajectories.jsonl` | в корне; поля episode_id, step, action, observation, reward, terminated, truncated; эталона в наблюдениях нет (проверка E3) |
| Записка о дизайне | [DESIGN.md](DESIGN.md) |
| Демо | приложение, терминальный интерфейс, `auditgym demo`, демо-видео |

### Откуда данные

Данные **генерируются**, а не хранятся: каждая компания строится из числа-seed примерно за секунду, без сети. Сначала
чистые книги (клиенты, счета, платежи, расходы, ежедневные курсы; главная книга сходится по построению), затем по
сценарию вносятся ошибки, и каждое изменение записывается — это и есть закрытый эталон. Один seed всегда даёт ту же
компанию байт в байт, поэтому фиксированные экзамены (10 train, 10 dev, 20 test) воспроизводимы, а для обучения
каждый раз создаются новые компании: одно стандартное обучение — 120 разных компаний, ни одна не повторяется и не
совпадает с опубликованными эпизодами.

### Обучение (необязательно, измерено честно)

Небольшой аудитор (политика из 20 параметров, CEM на CPU, около 30 с) на seed 1/2/3 доходит на dev от −0.62 / −0.60 /
+0.28 до **+0.961**, на 20 свежих тестовых эпизодах — **+0.961**, как ручной Сверщик, не лучше. На seed 1–12 каждый
стандартный прогон заканчивает на тесте не ниже +0.81 (в среднем +0.95, 11 из 12 — максимум +0.961). Контрольное
сравнение: тот же поиск с шумом вместо награды даёт на тесте −0.13 / +0.48 / +0.02 — прирост даёт именно награда.
Независимая проверка на 25 сидах — [docs/reports/training_25_seeds.md](docs/reports/training_25_seeds.md). Подробности и честные
ограничения — в [DESIGN.md](DESIGN.md).

---

<a id="english"></a>

## English: a guide for the judges

**A reproducible RL environment and evaluator for financial-audit agents.** Synthetic books of fictional companies with
hidden, recorded errors; five read-only tools; a shared matcher and terminal reward that pay for proven findings, not
for persuasive text. Genesis Hackathon 2026 · FinTech track · MIT licence.

### Install: desktop or terminal

**Desktop app**: Windows, macOS, Linux. No Python, no admin rights, works offline. One line downloads the latest
release, checks it against `SHA256SUMS.txt`, installs the app **and** the `auditgym` terminal command, then offers the
ready-made trained models.

```powershell
irm https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.ps1 | iex      # Windows (PowerShell)
```
```bash
curl -fsSL https://github.com/ibrahimerbol01-prog/auditgym/releases/latest/download/install.sh | sh  # macOS / Linux
```

Or download the zip for your system from the [latest release](https://github.com/ibrahimerbol01-prog/auditgym/releases/latest).
Updates: Settings → Updates in the app, or `auditgym update`. Details: [desktop/README.md](desktop/README.md).

**Terminal**: from source, any Python 3.11–3.13. The runtime is the standard library only, so nothing is downloaded.

```bash
git clone https://github.com/ibrahimerbol01-prog/auditgym && cd auditgym
python -m pip install -e .
auditgym            # terminal UI: train, watch the model at work, browse and replay runs
auditgym ui         # the same app in your browser (http://127.0.0.1:8000)
auditgym verify     # the judges' check: 100 / 100, about 20 s, offline
```

The official check, in a container with no network (§1 below): `docker build -t auditgym .` then
`docker run --rm --network none auditgym`.

---

The rest of this page follows the brief: **§1** how to check everything with one command, **§2** where each of the
100 points is verified, **§3** the deliverables of brief §09, **§4** what the judges' own policies will see, **§5** the demo,
**§6** plugging in an agent, **§7** optional work that earns no points but is measured honestly, **§8** limitations.

---

## 0. Judge adapter (organizers' check definitions, Nov 20)

`judge_adapter.py` in the repository root (in the container: `/app/judge_adapter.py`; the image already sets
`PYTHONPATH=/app/src:/app`, so `import judge_adapter` works from any working directory) implements the published
interface exactly. Self-check inside the container:
`docker run --rm --network none -w /app --entrypoint python auditgym -m unittest tests.test_judge_adapter -v`.

```python
import judge_adapter as J
J.generate_episode(seed, config, output_dir)          # public/ + private/ (truth, provenance, clean) in output_dir
env = J.make_env()
obs, info = env.reset(seed, {"mode": "closed", "episode_dir": output_dir, "team_config": {}})
obs, reward, terminated, truncated, info = env.step({"name": "list_records", "args": {"table": "ledger", "cursor": None, "limit": 50}})
J.score_episode(output_dir, findings_json, inspection_steps)   # {"tp","fp","fn","precision","recall","f1","return"}
```

- **Tables**: `ledger`, `invoices`, `payments`, `fx` (canonical names, no translation). Documents: `get_document{doc_id}`.
- **Record keys**: ledger `row_id`, invoices `invoice_id`, payments `payment_id`, fx `"<date>|<source>|<target>"`, documents `doc_id`.
- **Results**: list_records `{"records": [...], "next_cursor": str|null}`; get_record / get_document the object;
  calculator a decimal string (`"0.3"` for `0.1+0.2`); submit `{"accepted": true}` (train mode adds the report).
- **Observations**: first `{"task", "manifest", "policy", "remaining_steps": 100}`, then
  `{"result", "error", "remaining_steps"}`; errors are `{"code", "message"}` without paths, seeds or truth.
- **Closed mode**: every reward returned to the policy is `0`, including the terminal one; the true reward is computed
  and logged by the evaluator process. `mode: "train"` returns the terminal reward.
- **Error types** (`type`): `duplicate_invoice`, `payment_allocation`, `date_or_fx`, `period_classification`.
  Canonical `affected_ids`: the invoice(s) for duplicates (original + copy), FX and period errors; the payment and the
  invoice for allocation errors.
- **Matcher conventions** (as published): ids and currency compared exactly; `affected_ids`/`evidence_ids` are sets
  after the raw-length limits; an unknown evidence id makes the finding a FP; one-to-one maximum matching;
  **τ** per issue = `tolerance_minor` in truth if present (fixtures: set it, e.g. `0`), else the rule in every
  `policy.json` (`1 + conversions`), else `0`.
- **Scenarios for D01–D20** via `team_config`: `errors` (count per type, 0–4, each type independently),
  `interactions` (`["A"]`: foreign invoice near period end with FX + period + partial payment; `["B"]`: duplicate whose
  copy is also mis-periodized), `distractor_level` 0–2 (split / lump-sum payments, short pay with credit note,
  advances in unapplied cash, recurring invoices, UTC timestamps at the period boundary), `foreign_share`,
  `period_months`, `layout_seed`, `id_seed`. A clean company: all `errors` 0 and no interactions.
- **Self-check of the published tests**: `PYTHONPATH=src python -m unittest tests.test_judge_adapter -v` runs C01–C17,
  C19, matcher tests 1–20, examples M01–M12 and the paired checks (row permutation + ID renaming in a copy).

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
| Tests of the environment, matching and reward | `tests/`: 181 tests including `tests/attacks/` (malformed input, cross-origin requests, crashes, red-team rounds) |
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

**Ready-made models** (optional, so there is something to evaluate before anyone trains): `models/` holds four
auditors trained by §7 — each one complete training run (14 KB: 20 numbers plus its curves and test result) — and the
catalogue also lists two small local LLMs that are pulled through Ollama, never stored here. `auditgym models` lists
them; `auditgym models install auditor-cem` (or `all`) puts one in the app under Runs → *Ready-made models*. Every
file is checked against its SHA-256 in `models/index.json`; `train/make_models.py` rebuilds them from the same seeds.

| Model | On the 20 test episodes |
|---|---|
| General auditor (CEM, mixed companies), recommended | +0.96, F1 1.00 |
| Auditor for interacting errors | +0.69 |
| REINFORCE auditor | +0.66 |
| Untrained control (noise instead of reward) | −0.14 |
| Qwen2.5 0.5B / 1.5B through Ollama (LLM + tools) | −0.33 / −0.09 |

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
| **Trained auditor** (a 20-parameter rule policy, CEM on CPU, about 20 s), seeds 1–3 | dev from −0.62 / −0.60 / +0.28 to **+0.961**; test **+0.961**, F1 1.00 — equal to the Reconciler, not better. Over seeds 1–12: every Standard run ends at +0.81 or more on test (mean +0.95; 11 of 12 at +0.961). A teammate's 25-seed check: [docs/reports/training_25_seeds.md](docs/reports/training_25_seeds.md) |
| **Control: the same training with noise instead of the reward** (brief §01), seeds 1–3 | test −0.13 / +0.48 / +0.02 against +0.961 with the reward: the gain comes from the reward, not from the search or the policy space |
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

## License

MIT (`LICENSE`). Bundled fonts: SIL Open Font License (`src/auditgym/ui/static/fonts/OFL-*.txt`). The desktop builds
also bundle a Python runtime, pywebview and the PyInstaller bootloader under permissive licences (the bootloader's GPL
exception allows MIT distribution): `desktop/THIRD_PARTY_NOTICES.md`, shipped inside every build. All data is
synthetic: no real companies, people, bank records or payments.
