# Training flow: shared contract (Nov 21)

Owner: Мади. The app's new flow: home **Launch** → choose model and dataset → setup assistant (scout) recommends
→ launch → live **training telemetry**. Case PDF rules this must respect: training is optional, CPU only (no GPU,
no paid API, no network), and an improvement may only be shown as a **controlled comparison on held-out data**
(dev, closed mode) next to the base policies. Standard library only in `src/`.

## 1. Learnable auditor and trainer: `src/auditgym/learner.py` (agent A)

- `AuditorPolicy(theta)`: a `policies.baselines.Policy` whose behaviour is set by a parameter vector `theta`
  (list of floats, ~20–40). It acts only through the public tool contract (like `ReconcilePolicy`). Parameters
  decide which tables to read and how many pages, which of the four checks to run, their strictness / tolerances,
  local vs UTC dates, which evidence IDs to attach, and a cap on findings. A random `theta` behaves like the naive
  tricks in `policies/naive.py` (score near −1); a good `theta` reproduces the careful rules (≈ +0.96).
- `describe(theta) -> list[dict]`: human-readable learned policy, e.g.
  `{"key": "fx_check", "label": "Проверка курсов", "value": "вкл · допуск 2", "on": true}`.
- `PARAM_NAMES: list[str]`, `N_PARAMS: int`.
- `train(config, run_id=None, base=None, on_event=None, stop=None) -> dict` runs a training job and writes the run
  folder (same root as evaluation runs: `harness.runs_dir()` or `base`):
  - `config` keys (all optional, defaults in brackets): `method` ("cem" | "reinforce") ["cem"], `iterations` [30],
    `population` [16], `episodes_per_candidate` [4], `elite_frac` [0.25], `seed` [1],
    `dataset` {"preset": "mixed" | "simple" | "interacting" ["mixed"]}, `eval_every` [2], `pace` [0.0].
  - Training episodes are generated fresh from `seed` (never a dev seed, never a train-split seed).
    Training sees reward (open mode). Every `eval_every` iterations (and at iteration 0 and the last one) the
    current best policy is evaluated on the **10 dev episodes in closed mode** exactly like
    `harness.run_split` (finalize, public score fields only).
  - Writes `<runs>/<run_id>/run.json`, rewritten after every iteration:
    ```json
    {"id": "...", "kind": "training", "model": "auditor-cem", "method": "cem", "status": "running|done|stopped|error",
     "config": {...}, "env_version": "1.0.0", "started": 0, "finished": null,
     "iterations": 30, "at": 7,
     "points": [{"i": 0, "train_mean": -0.8, "train_best": -0.2, "train_elite": -0.4, "sigma": 0.9,
                 "episodes": 64, "seconds": 1.3, "eps_per_sec": 49.0,
                 "dev": {"reward": -0.7, "f1": 0.1, "precision": 0.2, "recall": 0.1, "fp": 3.1, "steps": 22.0} | null}],
     "best": {"theta": [...], "describe": [...], "dev": {...} | null, "i": 6},
     "summary": {"dev_start": -0.9, "dev_best": 0.6, "dev_last": 0.6, "episodes": 448, "seconds": 9.1},
     "pid": 1234,
     "live": {"i": 6, "candidate": 3, "episode_id": "ep_...", "seed": "123...", "steps": 18, "reward": 0.97,
              "pages": {"fx": 4, "invoices": 2, "payments": 2, "ledger": 9}, "rows": {...}, "issues": 7, "clean": false,
              "tp": 7, "fp": 0, "fn": 0, "precision": 1.0, "recall": 1.0, "f1": 1.0,
              "findings": [{"type": "date_or_fx", "ids": ["IN-..."], "amount_minor": 2596944, "currency": "KZT",
                            "evidence": 3, "matched": true}]}}
    ```
    Each point also carries the search itself (shown in the "Model at work" panel of the training page):
    `scores` (every candidate's mean training reward), `elite` (the indices the update used), `mu` (the mean of
    theta after the update) and `cpu_seconds` (process CPU time of the iteration). `live` is the best candidate of
    the latest iteration replayed on that iteration's first training episode (open mode, scored by the evaluator;
    one extra episode, not counted in `episodes`); `issues` is the evaluator's count (`tp + fn`), 0 for a clean
    company. Older runs have none of these fields.
  - `on_event(e)`: `{"type": "iteration", "point": {...}}`, `{"type": "run_end", "run": {...}}`.
  - Deterministic for a given config (same seed → same curve).
  - CEM escapes local optima with the training reward only (dev is never fed back into the search): the mean of
    theta is bounded to ±3 (σ(3) = 0.95, so a setting can still flip; unbounded, it drifted to ±10 and every
    candidate behaved alike), the best candidate of an iteration is carried into the next one (elitism), the elite
    is rank-weighted, and after 4 iterations without a better elite mean (+0.02) the search widens again
    (σ ≥ 1.5). Over seeds 1–12, Standard (30 × 16 × 4) went from 3 runs stuck at −0.13 on test (duplicates only)
    to none (mean +0.92), and Deep (40 × 24 × 4) to +0.961 on every seed. REINFORCE is unchanged.
- `train/learn_rules.py --seed 1 [--iterations N] [--method cem]`: CLI wrapper; prints progress, writes
  `train/curve.json` = `{"points": [{"iteration": i, "train_reward": train_mean, "dev_reward": dev.reward, "steps": ...}], "config": ..., "baselines": ...}`
  (only points with a dev evaluation carry `dev_reward`).

## 2. Scout: `src/auditgym/scout.py` (agent B)

`scout(explain=False, ollama_url="http://127.0.0.1:11434", timeout=0.6) -> dict`, never raises, works offline:
```json
{"machine": {"os": "Windows 11", "python": "3.11.9", "cpu_count": 8, "ram_gb": 16.0, "gpu": [{"name": "...", "vram_gb": 8}] },
 "ollama": {"available": true, "models": [{"name": "qwen2.5:1.5b", "size_gb": 0.9, "params": "1.5B", "quant": "Q4_K_M"}]},
 "dataset": {"train_configs": 10, "dev_episodes": 10, "presets": ["mixed", "simple", "interacting"]},
 "recommendation": {"model": "auditor-cem", "config": {"method": "cem", "iterations": 30, "population": 16,
                    "episodes_per_candidate": 4, "dataset": {"preset": "mixed"}},
                    "est_seconds": 40, "reasons": ["...", "..."],
                    "evaluate_llm": "qwen2.5:1.5b" | null},
 "explanation": "plain-language text from the local LLM" | null}
```
Russian text in `reasons`. Recommendation adapts population / episodes to CPU and RAM; an LLM is only ever
proposed for evaluation (the PDF: no GPU dependence, weights training optional).

## 3. HTTP API (Мади, in `harness.Jobs`)

- `GET /api/scout` → `{"ok": true, "scout": {...}}`; `GET /api/scout?explain=1` adds the LLM explanation.
- `POST /api/train` body = learner `config` → `{"ok": true, "run": "<id>"}` (409 `busy` if any job runs).
- `GET /api/runs/<id>` → `{"ok": true, "run": <run.json>}` (works for both kinds); `GET /api/runs` lists both
  kinds (`kind` field; training items carry `summary.dev_best` and `at/iterations`).
- `POST /api/runs/<id>/stop` stops either kind.
- `POST /api/train/<id>/curve` → copies the run's curve to `train/curve.json` (shown on «Запуски» T-1).

## 4. UI: `/train.html` + `/train.js` (agent C)

Home hero gets a primary **«Запустить обучение»** button → `/train.html`. Wizard (one page, steps):
1. **Модель**: trainable auditor (CEM — recommended / REINFORCE); Ollama models from the scout listed as
   «только оценка» with the terminal command to copy (the browser never starts an external program).
2. **Данные**: training-episode preset (смешанные / простые / с взаимодействиями), episodes per candidate,
   population, iterations, seed; evaluation set fixed: 10 held-out dev episodes, closed mode (locked, explained).
3. **Помощник**: scout result (machine, models found, recommendation with reasons, est. time), «Применить» fills
   the form; optional «Объяснить» asks the local LLM.
4. **Запуск** → telemetry dashboard on the same page (`#run=<id>`), polling `GET /api/runs/<id>` every 700 ms.

Telemetry (dataviz rules: one hero figure, solid hairline grid, 2 px lines, ≥ 8 px markers with a surface ring,
crosshair + tooltip listing every series at that iteration, legend for ≥ 2 series, values in text colour, no
dual axis, table view):
- KPI row: iteration i / N, **dev reward best** (hero, with gap to reconcile 0.97 and to the start), train mean,
  episodes seen, episodes/s, elapsed.
- Chart 1 (main, wide): **held-out dev reward** per evaluated iteration, with reference lines reconcile / random.
- Chart 2: train reward — population mean, elite mean, best.
- Chart 3: dev F1, precision, recall.
- Chart 4: dev false findings per episode. Chart 5: dev steps per episode. Chart 6: search spread σ.
- Card: learned policy (`best.describe`) as a readable list; buttons «Остановить», «Сохранить кривую».
Colours only from `style.css` tokens (add a training section at the end of `style.css`); light + dark; 1440 and 390 px.
