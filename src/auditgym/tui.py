"""Terminal UI: the desktop app's flow in a terminal. `auditgym` with no arguments (on a terminal) or `auditgym tui`.

Four sections, switched with Tab or 1-4: Home (start a training: model, data, size, and one seed or seeds 1, 2, 3
to compare them), Training (live telemetry: a braille chart of the dev reward, the population mean and the
Reconciler baseline, the key numbers next to it and, once it is done, the result on 20 fresh test episodes; `m`
evaluates the trained model on them, `x` exports report.md), Runs (every training and evaluation with details and
the measured failure analysis; Enter on an evaluation replays it step by step; `e` evaluates a built-in policy on
dev or test) and Settings (language, version, updates, the verification report). It drives the same harness as the app (auditgym.harness.Jobs), so runs
started here show up in the app and the other way round.

Standard library only. Drawing uses ANSI escapes rather than curses, because Python on Windows has no curses; only
the lines that changed are rewritten, so it does not flicker. English by default; Russian in Settings (saved in
~/.auditgym/tui.json) or with AUDITGYM_LANG=ru. NO_COLOR turns colours off.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .harness import Jobs, list_runs, read_run, read_steps, runs_dir

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREFS = os.path.join(os.path.expanduser("~"), ".auditgym", "tui.json")

# ---------------------------------------------------------------- text
T: Dict[str, Dict[str, str]] = {
    "en": {
        "home": "Home", "train": "Training", "runs": "Runs", "settings": "Settings",
        "ready": "Ready to train?",
        "sub": "The auditor learns on generated books of fictional companies and is tested on episodes it has not seen.",
        "model": "Model", "data": "Data", "size": "Size",
        "cem": "Auditor · CEM", "reinforce": "Auditor · REINFORCE",
        "cem_d": "cross-entropy search: stable, converges fast on CPU", "reinforce_d": "policy gradient: noisier, for comparison",
        "mixed": "Mixed", "simple": "Simple errors", "interacting": "Interacting",
        "mixed_d": "clean cases, distractors and every error type", "simple_d": "one error type at a time",
        "interacting_d": "errors that mask each other: the hardest",
        "fast": "Fast", "std": "Standard", "deep": "Deep",
        "size_d": "{it} iter. × {pop} cand. × {ep} ep. = {total} episodes", "status": "status",
        "start": "Start training", "new": "New training", "datasets": "Datasets", "badge_mixed": "recommended", "badge_simple": "beginner", "badge_interacting": "hard", "population": "Population", "elite": "elite {k} of {p} → next mean", "samples": "{p} samples → gradient step", "recent": "Recent", "no_runs": "No runs yet.",
        "machine": "{cpu} · {ram} GB RAM · CPU only · offline", "machine_q": "CPU only · offline",
        "k_home": "↑↓ field   ←→ change   Enter start   Tab section   q quit",
        "busy": "Another training or evaluation is running: wait for it on the Training or Runs page.",
        "started": "Started {id}", "failed": "Could not start: {msg}",
        "running": "running", "done": "done", "stopped": "stopped", "error": "error", "interrupted": "interrupted",
        "iteration": "iteration {i}/{n}",
        "chart": "Reward on held-out dev episodes", "l_dev": "dev reward", "l_train": "population mean", "l_ref": "Reconciler",
        "best": "best (dev)", "last": "last (dev)", "vs": "vs Reconciler", "f1": "F1 (dev)", "fp": "false findings / ep.",
        "steps": "steps / ep.", "elapsed": "elapsed", "eta": "left", "episodes": "episodes",
        "k_train": "s stop   Tab section   q quit",
        "no_train": "No training yet. Start one on Home (press 1).",
        "waiting": "waiting for the first dev check",
        "k_runs": "↑↓ select   Enter open/replay   e evaluate (dev/test)   Tab section   q quit",
        "eval_ask": "Evaluate 1 Reconciler · 2 Intern · 3 Alarmist (then dev or test) · Esc cancel",
        "training": "Training", "evaluation": "Evaluation",
        "reward": "reward", "precision": "precision", "recall": "recall", "time": "time", "split": "split",
        "config": "configuration", "seed": "seed", "open_hint": "Enter: open the live view",
        "language": "Language", "version": "Version", "updates": "Updates", "update_how": "run  auditgym update  in a terminal",
        "report": "Verification report", "report_line": "{score} / 100 by the brief's formulas · {ok} of {n} checks passed",
        "report_none": "report.json not found: run  python -m auditgym.verify", "data_dir": "Runs folder",
        "k_settings": "←→ language   Tab section   q quit",
        "quit_running": "A run is in progress: press q again to stop it and quit, any other key to stay.",
        "source": "source checkout", "tagline": "an offline RL environment for audit agents",
        "oracle": "Oracle", "reconcile": "Reconciler", "random": "Intern", "flag_all": "Alarmist",
        "s": "s", "min": "min",
        "seeds": "Seeds", "seeds_1": "1", "seeds_3": "3 · 1, 2, 3",
        "seeds_1_d": "one run, seed 1", "seeds_3_d": "seeds 1, 2, 3 in a row, to compare the seeds",
        "test_box": "Test ({n} fresh episodes)", "auditor": "Trained auditor", "testing": "measuring on the test set",
        "testing_state": "testing", "test_failed": "the test could not run", "test_reward": "test reward",
        "found_by_type": "found / missed by error type", "missed": "missed", "false_by": "false findings", "none": "none",
        "by_kind": "reward by kind of episode", "k_clean": "clean", "k_errors": "with errors", "k_interacting": "interacting",
        "duplicate_invoice": "duplicates", "payment_allocation": "payments", "date_or_fx": "dates / FX",
        "period_classification": "periods", "invalid": "invalid",
        "k_train_done": "m evaluate on test   x export report   n new training   Tab section   q quit",
        "no_model": "This training has no trained model yet.", "exported": "Report saved: {path}",
        "model_of": "model", "group_seeds": "seeds of the group", "best_short": "best dev", "test": "test", "mean": "mean",
        "split_ask": "{policy} on: d 10 dev episodes · t 20 fresh test episodes · Esc cancel",
        "replay": "Replay", "episode": "episode", "no_steps": "No steps recorded for this episode.",
        "k_replay": "←→ episode   ↑↓ scroll   Esc back   Tab section   q quit",
        "c_tool": "tool", "c_args": "arguments", "c_ok": "result", "c_rows": "rows", "c_left": "left",
        "truncated": "out of steps", "steps_n": "steps", "replay_hint": "Enter: replay it step by step",
        "pop_title": "Population · iteration {i}", "pop_best": "best {b} · worst {w}",
        "pop_elite": "kept (elite {k})", "pop_top": "top {k}", "pop_rest": "dropped", "pop_wait": "first iteration: the candidates are playing",
        "maw": "Model at work · iteration {i} · candidate #{c}", "maw_wait": "Model at work",
        "t_fx": "FX rates", "t_invoices": "Invoices", "t_payments": "Payments", "t_ledger": "Ledger",
        "pages": "{p} p · {r} rows", "not_read": "not read", "ev": "evaluator", "correct": "correct", "false": "false",
        "missed_of": "missed {fn} of {n}", "clean_ok": "clean company: it correctly submitted nothing",
        "nothing": "submitted nothing: only misses count", "more": "+{n} more", "first_it": "the first iteration is running…",
        "weights": "Weights σ(θ) · the whole model", "cpu": "CPU {cpu}%", "eps_s": "{n}/s",
        "w_labels": "read FX|read invoices|read payments|read ledger|FX pages|invoice pages|payment pages|ledger pages|check dups|check payments|check FX|check period|dup match|FX tolerance|FX local date|period local|strict alloc.|evidence|min amount|max findings",
    },
    "ru": {
        "home": "Главная", "train": "Обучение", "runs": "Запуски", "settings": "Настройки",
        "ready": "Готовы обучать?",
        "sub": "Аудитор учится на сгенерированных книгах вымышленных компаний и проверяется на эпизодах, которых не видел.",
        "model": "Модель", "data": "Данные", "size": "Объём",
        "cem": "Аудитор · CEM", "reinforce": "Аудитор · REINFORCE",
        "cem_d": "кросс-энтропийный поиск: стабильно, быстро сходится на CPU", "reinforce_d": "градиент политики: шумнее, для сравнения",
        "mixed": "Смешанные", "simple": "Простые ошибки", "interacting": "С взаимодействиями",
        "mixed_d": "чистые случаи, отвлекающие записи и все типы ошибок", "simple_d": "по одной ошибке за раз",
        "interacting_d": "ошибки маскируют друг друга: сложнее всего",
        "fast": "Быстро", "std": "Стандарт", "deep": "Глубоко",
        "size_d": "{it} итер. × {pop} канд. × {ep} эп. = {total} эпизодов", "status": "статус",
        "start": "Запустить обучение", "new": "Новое обучение", "datasets": "Наборы данных", "badge_mixed": "рекомендуем", "badge_simple": "начальный", "badge_interacting": "сложный", "population": "Популяция", "elite": "элита {k} из {p} → новое среднее", "samples": "{p} проб → шаг градиента", "recent": "Недавние", "no_runs": "Запусков пока нет.",
        "machine": "{cpu} · {ram} ГБ ОЗУ · только CPU · без сети", "machine_q": "только CPU · без сети",
        "k_home": "↑↓ поле   ←→ выбор   Enter запуск   Tab раздел   q выход",
        "busy": "Уже идёт обучение или оценка: дождитесь его на странице «Обучение» или «Запуски».",
        "started": "Запущено: {id}", "failed": "Не удалось запустить: {msg}",
        "running": "идёт", "done": "завершено", "stopped": "остановлено", "error": "ошибка", "interrupted": "прервано",
        "iteration": "итерация {i}/{n}",
        "chart": "Награда на отложенных dev-эпизодах", "l_dev": "награда dev", "l_train": "среднее популяции", "l_ref": "Сверщик",
        "best": "лучшая (dev)", "last": "последняя (dev)", "vs": "против Сверщика", "f1": "F1 (dev)", "fp": "ложных находок / эп.",
        "steps": "шагов / эп.", "elapsed": "прошло", "eta": "осталось", "episodes": "эпизодов",
        "k_train": "s стоп   Tab раздел   q выход",
        "no_train": "Обучений пока нет. Запустите на главной (клавиша 1).",
        "waiting": "ждём первую проверку на dev",
        "k_runs": "↑↓ выбор   Enter открыть/повтор   e оценка (dev/тест)   Tab раздел   q выход",
        "eval_ask": "Оценка: 1 Сверщик · 2 Стажёр · 3 Паникёр (затем d dev или t тест) · Esc отмена",
        "training": "Обучение", "evaluation": "Оценка",
        "reward": "награда", "precision": "точность", "recall": "полнота", "time": "время", "split": "выборка",
        "config": "конфигурация", "seed": "сид", "open_hint": "Enter: открыть живой вид",
        "language": "Язык", "version": "Версия", "updates": "Обновления", "update_how": "выполните  auditgym update  в терминале",
        "report": "Отчёт проверки", "report_line": "{score} из 100 по формулам брифа · пройдено {ok} из {n} проверок",
        "report_none": "report.json не найден: запустите  python -m auditgym.verify", "data_dir": "Папка запусков",
        "k_settings": "←→ язык   Tab раздел   q выход",
        "quit_running": "Идёт запуск: нажмите q ещё раз, чтобы остановить его и выйти, любую другую клавишу — остаться.",
        "source": "запуск из исходников", "tagline": "офлайн RL-среда для агентов-аудиторов",
        "oracle": "Эталон", "reconcile": "Сверщик", "random": "Стажёр", "flag_all": "Паникёр",
        "s": "с", "min": "мин",
        "seeds": "Сиды", "seeds_1": "1", "seeds_3": "3 · 1, 2, 3",
        "seeds_1_d": "один запуск, сид 1", "seeds_3_d": "сиды 1, 2, 3 подряд, чтобы сравнить сиды",
        "test_box": "Тест ({n} новых эпизодов)", "auditor": "Обученный аудитор", "testing": "замер на тестовой выборке",
        "testing_state": "тест", "test_failed": "тест не удалось провести", "test_reward": "награда на тесте",
        "found_by_type": "найдено / пропущено по типам ошибок", "missed": "пропущено", "false_by": "ложные находки", "none": "нет",
        "by_kind": "награда по видам эпизодов", "k_clean": "чистые", "k_errors": "с ошибками", "k_interacting": "взаимодействия",
        "duplicate_invoice": "дубли", "payment_allocation": "оплаты", "date_or_fx": "даты / курсы",
        "period_classification": "периоды", "invalid": "неверные",
        "k_train_done": "m оценить на тесте   x экспорт отчёта   n новое   Tab раздел   q выход",
        "no_model": "У этого обучения ещё нет обученной модели.", "exported": "Отчёт сохранён: {path}",
        "model_of": "модель", "group_seeds": "сиды группы", "best_short": "лучш. dev", "test": "тест", "mean": "среднее",
        "split_ask": "{policy}: d 10 dev-эпизодов · t 20 новых тестовых эпизодов · Esc отмена",
        "replay": "Повтор", "episode": "эпизод", "no_steps": "Для этого эпизода шаги не записаны.",
        "k_replay": "←→ эпизод   ↑↓ прокрутка   Esc назад   Tab раздел   q выход",
        "c_tool": "инструмент", "c_args": "аргументы", "c_ok": "результат", "c_rows": "строк", "c_left": "ост.",
        "truncated": "шаги кончились", "steps_n": "шагов", "replay_hint": "Enter: повтор по шагам",
        "pop_title": "Популяция · итерация {i}", "pop_best": "лучший {b} · худший {w}",
        "pop_elite": "оставлены (элита {k})", "pop_top": "лучшие {k}", "pop_rest": "отброшены", "pop_wait": "первая итерация: кандидаты играют",
        "maw": "Модель в работе · итерация {i} · кандидат №{c}", "maw_wait": "Модель в работе",
        "t_fx": "Курсы", "t_invoices": "Счета", "t_payments": "Платежи", "t_ledger": "Книга",
        "pages": "стр {p} · строк {r}", "not_read": "не читал", "ev": "оценщик", "correct": "верно", "false": "ложных",
        "missed_of": "пропущено {fn} из {n}", "clean_ok": "чистая компания: модель верно ничего не отправила",
        "nothing": "ничего не отправила: считаются только пропуски", "more": "ещё {n}", "first_it": "идёт первая итерация…",
        "weights": "Веса σ(θ) · вся модель", "cpu": "CPU {cpu}%", "eps_s": "{n}/с",
        "w_labels": "читать курсы|читать счета|читать платежи|читать книгу|стр. курсов|стр. счетов|стр. платежей|стр. книги|дубли|разноска|курсы|период|критерий дубля|допуск курса|дата курса|дата периода|строгая разн.|доказательства|порог суммы|предел находок",
    },
}
TABS = ("home", "train", "runs", "settings")
MODELS = ("cem", "reinforce")
DATASETS = ("mixed", "simple", "interacting")
SIZES = {"fast": {"iterations": 12, "population": 8, "episodes_per_candidate": 2},
         "std": {"iterations": 30, "population": 16, "episodes_per_candidate": 4},
         "deep": {"iterations": 40, "population": 24, "episodes_per_candidate": 4}}
POLICIES = ("reconcile", "random", "flag_all")
SEEDS = (None, [1, 2, 3])                     # Home's "Seeds" field: one run, or the same configuration on seeds 1, 2, 3
ERR_TYPES = ("duplicate_invoice", "payment_allocation", "date_or_fx", "period_classification")
KINDS = ("clean", "errors", "interacting")

# the wordmark: the app logo's 5x7 letters, two pixel rows per character with half blocks (▀ ▄ █)
FONT = {
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"], "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."], "I": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."], "G": [".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."],
    "Y": ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."], "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
}


MARK = ["######.", ".......", "###....", "......#", ".#...#.", "..#.#..", "...#..."]   # ledger lines and a tick
TICK = [(4, 1), (5, 2), (6, 3), (5, 4), (4, 5), (3, 6)]                                # the tick, in stroke order


def wordmark(text: str = "AUDITGYM", tick: int = 6, mark: bool = True) -> List[str]:
    """The logo as half-block text: the mark (its tick drawn up to `tick` pixels), then the letters."""
    m = [list(r) for r in MARK]
    for k, (y, x) in enumerate(TICK):
        if k >= tick:
            m[y][x] = "."
    rows = [("".join(m[y]) + "...." if mark else "") + "".join(FONT[c][y] + "." for c in text) for y in range(7)]
    rows.append("." * len(rows[0]))
    out = []
    for y in range(0, 8, 2):
        out.append("".join({("#", "#"): "█", ("#", "."): "▀", (".", "#"): "▄"}.get((a, b), " ") for a, b in zip(rows[y], rows[y + 1])).rstrip())
    return out


# ---------------------------------------------------------------- small ASCII animations (the app's motifs)
def beat(t: float, n: int = 18) -> str:
    """A heartbeat line scrolling left: the app is alive, offline, on the CPU."""
    line = "▁▁▁▁▁▂▁▁▃▇▁▅▂▁▁▁▁▁▁▁▁▁▁▂▃▂▁▁"
    k = int(t * 9) % len(line)
    return (line[k:] + line[:k])[:n]


def art(name: str, t: float) -> List[str]:
    """4×16 pictures of the three datasets (the same ideas as the app's recipe cards)."""
    if name == "simple":       # one error type at a time: a cursor walks down the ledger and ticks each row
        n = int(t * 2.2) % 6
        rows = ["────── ───", "──── ──────", "─────── ──", "─── ───────"]
        return [(("▸ " if i == n else "  ") + r + (" ✓" if i < n else "  ")).ljust(16) for i, r in enumerate(rows)]
    if name == "mixed":        # mixed books: rows of entries shuffle, one of them is wrong
        k = int(t * 2.5)
        out = []
        for i in range(4):
            v = (i * 7 + k * 3) % 5
            out.append(("  " + "── " * (1 + (i + k) % 3) + ("×" if v == 0 else "·") + "  " + "─" * (2 + v % 3)).ljust(16)[:16])
        return out
    g = [[" "] * 16 for _ in range(4)]   # interacting errors: two boxes drift into each other; the overlap is masked
    a = round(2 + 2 * math.sin(t * 1.6))

    def rect(x: int, y: int, w: int, h: int) -> None:
        for i in range(w):
            for j in range(h):
                edge = "─" if j in (0, h - 1) else "│" if i in (0, w - 1) else None
                if edge and 0 <= x + i < 16:
                    c = g[y + j][x + i]
                    g[y + j][x + i] = "┼" if c not in (" ", edge) else edge
    rect(a, 0, 7, 3)
    rect(9 - a, 1, 7, 3)
    return ["".join(r) for r in g]


def _h(i: int, j: int) -> int:
    h = (i * 374761393 + j * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return h ^ (h >> 16)


def ledger(i: int, j: int) -> str:
    """The hidden ledger under the loupe: rows of accounting figures like '  4 812.50   -1 204.00'."""
    o = _h(0, j) % 13
    n, f = (i + o) // 13, _h((i + o) // 13 + 7, j)
    cell = "  " + ("-" if _h(n, j) % 6 == 0 else " ") + str(1 + f % 9) + " " + str(100 + (f >> 4) % 900) + "." + str(10 + (f >> 12) % 90)
    return cell.ljust(13)[(i + o) % 13]


TOKEN = re.compile(r"(\x1b\[[0-9;?]*[A-Za-z])|(.)", re.S)


def cells(line: str) -> List[Tuple[str, str]]:
    """A drawn line as (character, active style) cells."""
    out, sty = [], ""
    for m in TOKEN.finditer(line):
        if m.group(1):
            sty = "" if m.group(1) == "\x1b[0m" else sty + m.group(1)
        else:
            out.append((m.group(2), sty))
    return out


class Backdrop:
    """The app's background in ASCII, behind every section: two layers of dots drifting left at different speeds
    (parallax) and a loupe roaming the screen that reads the hidden ledger. Content always wins: the backdrop only
    shows in empty cells away from text and outside boxes, the way the app's cards cover its canvas."""

    def __init__(self, st: "Style") -> None:
        self.st = st

    def lens(self, w: int, n: int, t: float) -> Tuple[float, float, float]:
        r = max(2.5, min(4.5, n / 4))
        cx = 6 + (math.sin(t * 0.23) + 1) / 2 * (w - 12)
        cy = r + (math.sin(t * 0.31 + 1.3) + 1) / 2 * max(0.0, n - 1 - 2 * r)
        return cx, cy, r

    @staticmethod
    def clear(lines: List[str], lens: Tuple[float, float, float], margin: int = 4) -> bool:
        """True when the loupe's circle, plus a margin, covers only empty cells: its fake ledger figures must never
        appear next to the real numbers of a page, where they would read as data."""
        cx, cy, r = lens
        x0, x1 = int(cx - 2 * r) - margin, int(cx + 2 * r) + margin
        for j in range(max(0, int(cy - r) - 1), min(len(lines), int(cy + r) + 2)):
            cs = cells(lines[j])
            if any(c != " " for c, _ in cs[max(0, x0): max(0, x1 + 1)]):
                return False
        return True

    def glyph(self, i: int, j: int, t: float, lens: Optional[Tuple[float, float, float]]) -> Tuple[str, str]:
        st = self.st
        cx, cy, r = lens if lens else (-99.0, -99.0, 0.0)
        inside = lambda a, b: math.hypot((a - cx) / 2, b - cy) < r
        if lens and inside(i, j):
            dx, dy = (i - cx) / 2, j - cy
            if not all(inside(a, b) for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))):
                tx, ty = -dy, dx
                slope = abs(ty) / (abs(tx) * 2 + 1e-9)
                return ("─" if slope < 0.4 else "│" if slope > 2.5 else ("╱" if tx * ty < 0 else "╲")), st.NEAR
            return ledger(i + int(t * 1.5), j), (st.B if math.hypot(dx, dy) < r * 0.55 else "")
        near = i + int(t * 2.0)                      # near layer: every 4th column on even rows, 2 columns/s
        if j % 2 == 0 and near % 4 == 0 and _h(near // 4, j) % 5:
            return "·", st.NEAR
        far = i + int(t * 0.8)                       # far layer: sparser, slower, fainter
        if j % 2 == 1 and far % 6 == 0 and _h(far // 6, j + 99) % 3 == 0:
            return "·", st.FAR
        return " ", ""

    def compose(self, line: str, j: int, n: int, w: int, t: float, lens: Optional[Tuple[float, float, float]]) -> str:
        cs = cells(line)
        cs += [(" ", "")] * (w - len(cs))
        cs = cs[:w]
        used = [x for x, (c, _) in enumerate(cs) if c != " "]
        lo, hi = (used[0] - 2, used[-1] + 2) if used else (w, -1)   # a line's content, edge to edge, plus a margin
        out, cur = [], ""
        for x, (c, sty) in enumerate(cs):
            if c == " " and not (lo <= x <= hi):
                c, sty = self.glyph(x, j, t, lens)
            if sty != cur:
                out.append(self.st.R + sty)
                cur = sty
            out.append(c)
        return "".join(out) + self.st.R


def field(w: int, n: int, t: float, st: "Style") -> List[str]:
    """The app's background in ASCII: a quiet dot grid, and a loupe drifting across it that reads the ledger."""
    if n < 5 or w < 30:
        return [""] * n
    r = min(4.5, (n - 1) / 2 + 0.4)                    # radius in rows; a cell is about twice as tall as wide
    cx = 6 + (math.sin(t * 0.33) + 1) / 2 * (w - 14)
    cy = (n - 1) / 2 + math.sin(t * 0.21) * max(0.0, (n - 1) / 2 - r)
    inside = lambda i, j: math.hypot((i - cx) / 2, j - cy) < r
    out = []
    for j in range(n):
        line, cur = [], ""
        for i in range(w):
            dx, dy = (i - cx) / 2, j - cy
            if inside(i, j) and not all(inside(a, b) for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1))):
                tx, ty = -dy, dx                           # the rim: one cell thick, drawn along its tangent
                slope = abs(ty) / (abs(tx) * 2 + 1e-9)     # a cell is about twice as tall as it is wide
                ch, sty = ("─" if slope < 0.4 else "│" if slope > 2.5 else ("╱" if tx * ty < 0 else "╲")), st.D
            elif inside(i, j):
                ch, sty = ledger(i, j), st.B if math.hypot(dx, dy) < r * 0.55 else ""
            else:
                ch, sty = ("·" if (i % 4 == 0 and j % 2 == 0 and _h(i, j) % 5) else " "), st.D
            if ch == " ":
                sty = ""
            if sty != cur:
                line.append(st.R + sty if st.R else "")
                cur = sty
            line.append(ch)
        out.append("".join(line) + st.R)
    return out


# ---------------------------------------------------------------- styling (ANSI); widths ignore the escapes
ESC = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class Style:
    def __init__(self, colour: bool) -> None:
        on = colour
        self.R = "\x1b[0m" if on else ""
        self.B = "\x1b[1m" if on else ""
        self.D = "\x1b[2m" if on else ""
        self.INV = "\x1b[7m" if on else ""
        self.POS = "\x1b[38;5;75m" if on else ""    # blue: better (same pair as the app's charts)
        self.NEG = "\x1b[38;5;203m" if on else ""   # red: worse
        self.FAR = "\x1b[38;5;237m" if on else ""   # background: the slow, far dot layer
        self.NEAR = "\x1b[38;5;241m" if on else ""  # background: the near layer and the loupe rim

    def val(self, v: Optional[float], digits: int = 2, signed: bool = True) -> str:
        if v is None:
            return self.D + "—" + self.R
        s = (("+" if v > 0 else "−" if v < 0 else " ") if signed else ("−" if v < 0 else "")) + f"{abs(v):.{digits}f}"
        return (self.POS if v > 0 else self.NEG if v < 0 else "") + s + self.R


def vlen(s: str) -> int:
    return len(ESC.sub("", s))


def pad(s: str, w: int) -> str:
    return clip(s, w) + " " * max(0, w - vlen(s))


def clip(s: str, w: int) -> str:
    """Cut to w visible characters, keeping escapes (and closing any open style)."""
    if vlen(s) <= w:
        return s
    out, n, i = [], 0, 0
    while i < len(s) and n < w:
        m = ESC.match(s, i)
        if m:
            out.append(m.group(0)); i = m.end(); continue
        out.append(s[i]); n += 1; i += 1
    return "".join(out) + ("\x1b[0m" if "\x1b[" in s else "")


def box(title: str, body: List[str], w: int, st: Style) -> List[str]:
    """A rounded frame of width w around body lines."""
    if not title:
        return [st.D + "╭" + "─" * (w - 2) + "╮" + st.R] + \
               [st.D + "│" + st.R + " " + pad(line, w - 4) + " " + st.D + "│" + st.R for line in body] + \
               [st.D + "╰" + "─" * (w - 2) + "╯" + st.R]
    return [st.D + "╭─ " + st.R + st.B + title + st.R + st.D + " " + "─" * max(0, w - vlen(title) - 5) + "╮" + st.R] + \
           [st.D + "│" + st.R + " " + pad(line, w - 4) + " " + st.D + "│" + st.R for line in body] + \
           [st.D + "╰" + "─" * (w - 2) + "╯" + st.R]


def bar(found: int, total: int, w: int, st: Style) -> str:
    """A small found / missed bar: found in blue, missed in faint red (`████░░`)."""
    k = max(0, min(w, round(found / total * w))) if total else 0
    return st.POS + "█" * k + st.R + st.NEG + st.D + "░" * (w - k) + st.R


def short_path(path: str) -> str:
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if home and home != os.sep and path.startswith(home + os.sep) else path


def wrap(text: str, w: int) -> List[str]:
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > w:
            out.append(line)
            line = word
        else:
            line = (line + " " + word).strip()
    return out + ([line] if line else [])


def cores(n: int, lang: str) -> str:
    if lang != "ru":
        return f"{n} {'core' if n == 1 else 'cores'}"
    k, d = n % 100, n % 10
    return f"{n} " + ("ядер" if 11 <= k <= 14 else "ядро" if d == 1 else "ядра" if 2 <= d <= 4 else "ядер")


def fmt_time(sec: Optional[float], tx: Dict[str, str]) -> str:
    if sec is None:
        return "—"
    sec = max(0, int(sec))
    return f"{sec // 60} {tx['min']} {sec % 60:02d} {tx['s']}" if sec >= 60 else f"{sec} {tx['s']}"


# ---------------------------------------------------------------- braille chart
DOTS = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))


def chart(series: List[Tuple[List[Tuple[float, float]], str, bool]], w: int, h: int, x_max: float,
          lo: float = -1.0, hi: float = 1.0) -> List[List[Tuple[str, str]]]:
    """Plot (x, y) series into w×h braille cells. Each series: (points, style, dotted). Returns rows of (char, style);
    a later series wins a shared cell."""
    W, H = w * 2, h * 4
    bits = [[0] * w for _ in range(h)]
    owner = [[""] * w for _ in range(h)]

    def px(x: float, y: float) -> Tuple[int, int]:
        return (round(x / max(x_max, 1e-9) * (W - 1)), round((hi - max(lo, min(hi, y))) / (hi - lo) * (H - 1)))

    def dot(x: int, y: int, style: str) -> None:
        if 0 <= x < W and 0 <= y < H:
            bits[y // 4][x // 2] |= DOTS[y % 4][x % 2]
            owner[y // 4][x // 2] = style

    for pts, style, dotted in series:
        p = [px(x, y) for x, y in pts]
        if len(p) == 1:
            dot(*p[0], style)
        for (x0, y0), (x1, y1) in zip(p, p[1:]):       # straight segments between samples
            n = max(abs(x1 - x0), abs(y1 - y0), 1)
            for k in range(n + 1):
                if dotted and k % 4 >= 2:
                    continue
                dot(round(x0 + (x1 - x0) * k / n), round(y0 + (y1 - y0) * k / n), style)
    return [[(chr(0x2800 + bits[r][c]) if bits[r][c] else " ", owner[r][c]) for c in range(w)] for r in range(h)]


# ---------------------------------------------------------------- terminal I/O
class Terminal:
    """Raw keys and in-place drawing; restores the terminal on exit (also after an error)."""

    def __init__(self) -> None:
        self.prev: List[str] = []
        self.size = (0, 0)
        self.win = os.name == "nt"
        self.saved = None

    def __enter__(self) -> "Terminal":
        if self.win:
            os.system("")                              # enables ANSI escapes in the Windows console
            try:
                import ctypes
                k = ctypes.windll.kernel32
                h = k.GetStdHandle(-11)
                mode = ctypes.c_uint32()
                if k.GetConsoleMode(h, ctypes.byref(mode)):
                    k.SetConsoleMode(h, mode.value | 0x0004)
            except Exception:  # noqa: BLE001 - older consoles: os.system("") above is enough on Windows 10+
                pass
        else:
            import termios
            import tty
            fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
        sys.stdout.flush()
        return self

    def __exit__(self, *exc: Any) -> None:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        if self.saved is not None:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.saved)

    def keys(self, timeout: float) -> List[str]:
        if self.win:
            import msvcrt
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if msvcrt.kbhit():
                    c = msvcrt.getwch()
                    if c in ("\x00", "\xe0"):
                        k = {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch())
                        return [k] if k else []
                    return parse_keys(c)
                time.sleep(0.02)
            return []
        import select
        fd = sys.stdin.fileno()
        if not select.select([fd], [], [], timeout)[0]:
            return []
        return parse_keys(os.read(fd, 256).decode("utf-8", "ignore"))

    def draw(self, lines: List[str]) -> None:
        w, h = shutil.get_terminal_size((100, 30))
        if (w, h) != self.size:
            self.size, self.prev = (w, h), []
            sys.stdout.write("\x1b[2J")
        lines = (lines + [""] * h)[:h]
        out = []
        for y, line in enumerate(lines):
            if y < len(self.prev) and self.prev[y] == line:
                continue
            out.append(f"\x1b[{y + 1};1H" + clip(line, w) + "\x1b[0m\x1b[K")
        self.prev = lines
        if out:
            sys.stdout.write("".join(out))
            sys.stdout.flush()


SEQ = {"\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left", "\x1bOA": "up", "\x1bOB": "down",
       "\x1bOC": "right", "\x1bOD": "left", "\x1b[Z": "backtab"}
SINGLE = {"\r": "enter", "\n": "enter", "\t": "tab", "\x1b": "esc", "\x03": "ctrl-c", "\x7f": "backspace", "\x08": "backspace"}


def parse_keys(data: str) -> List[str]:
    """Every key in one read (keys typed fast, or pasted, arrive together)."""
    out, i = [], 0
    while i < len(data):
        if data[i] == "\x1b" and data[i:i + 3] in SEQ:
            out.append(SEQ[data[i:i + 3]]); i += 3; continue
        if data[i] == "\x1b" and data[i + 1:i + 2] in ("[", "O"):   # an escape sequence we do not use: skip it
            j = i + 2
            while j < len(data) and not data[j].isalpha() and data[j] != "~":
                j += 1
            i = j + 1; continue
        c = data[i]
        out.append(SINGLE.get(c, c.lower())); i += 1
    return out


# ---------------------------------------------------------------- the app
def _report() -> Optional[Dict[str, Any]]:
    for base in (os.getcwd(), os.environ.get("AUDITGYM_DATA") or "", ROOT):
        p = os.path.join(base, "report.json") if base else ""
        if p and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                return None
    return None


def load_lang() -> str:
    env = (os.environ.get("AUDITGYM_LANG") or "").lower()
    if env in T:
        return env
    try:
        with open(PREFS, encoding="utf-8") as fh:
            v = json.load(fh).get("lang")
            return v if v in T else "en"
    except (OSError, ValueError, AttributeError):
        return "en"


def save_lang(lang: str) -> None:
    try:
        os.makedirs(os.path.dirname(PREFS), exist_ok=True)
        with open(PREFS, "w", encoding="utf-8") as fh:
            json.dump({"lang": lang}, fh)
    except OSError:
        pass


class App:
    def __init__(self, jobs: Optional[Jobs] = None, base: Optional[str] = None, colour: bool = True,
                 lang: Optional[str] = None, scout: bool = True) -> None:
        self.jobs = jobs or Jobs(base=base)
        self.base = base
        self.st = Style(colour)
        self.lang = lang or load_lang()
        self.tab = 0
        self.field = 0
        self.pick = {"model": 0, "data": 0, "size": 1, "seeds": 0}
        self.sel = 0
        self.ask_eval = False
        self.ask_split: Optional[str] = None          # the policy chosen in the `e` prompt, waiting for d(ev) / t(est)
        self.replay: Optional[Dict[str, Any]] = None  # Runs: the replay of an evaluation {"id", "ep", "scroll"}
        self.group_ids: Optional[List[str]] = None    # a seed group started here: the Training page follows it
        self.quitting = False
        self.msg = ""
        self.msg_at = 0.0
        self.bg = Backdrop(self.st)
        self.backdrop = True
        self.train_id: Optional[str] = None
        self.machine: Dict[str, Any] = {}
        self.t0 = time.monotonic()
        self._runs: List[Dict[str, Any]] = []
        self._runs_at = 0.0
        self._run_cache: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
        self._steps_cache: Dict[Tuple[str, int], Tuple[float, Optional[List[Dict[str, Any]]]]] = {}
        rep = _report()
        self.report = rep
        from .termview import baseline_means
        self.baseline = {}
        for b in (os.getcwd(), os.environ.get("AUDITGYM_DATA") or "", ROOT):
            if b and os.path.isfile(os.path.join(b, "report.json")):
                self.baseline = baseline_means(os.path.join(b, "report.json"))
                break
        if scout:
            threading.Thread(target=self._scout, daemon=True).start()

    @property
    def tx(self) -> Dict[str, str]:
        return T[self.lang]

    def _scout(self) -> None:
        try:
            from .scout import scout
            d = scout(timeout=1.5)
            self.machine = d.get("machine") or {}
            rec = (d.get("recommendation") or {}).get("config")
            if rec:
                SIZES["std"] = {k: rec[k] for k in ("iterations", "population", "episodes_per_candidate")}
        except Exception:  # noqa: BLE001 - the machine line is a nicety
            pass

    # ---- data, read from disk at most a few times a second
    def runs(self) -> List[Dict[str, Any]]:
        if time.monotonic() - self._runs_at > 1.0:
            # the red-team arena is one row; its lanes (one evaluation per attack) stay on the app's Red team page
            self._runs, self._runs_at = [r for r in list_runs(self.base) if not r.get("arena")], time.monotonic()
        return self._runs

    def run(self, run_id: str) -> Optional[Dict[str, Any]]:
        at, r = self._run_cache.get(run_id, (0.0, None))
        if time.monotonic() - at > 0.5:
            r = read_run(run_id, self.base)
            self._run_cache[run_id] = (time.monotonic(), r)
        return r

    def steps(self, run_id: str, ep: int) -> Optional[List[Dict[str, Any]]]:
        at, rows = self._steps_cache.get((run_id, ep), (0.0, None))
        if time.monotonic() - at > 1.0:
            rows = read_steps(run_id, ep, self.base)
            self._steps_cache[(run_id, ep)] = (time.monotonic(), rows)
        return rows

    def note(self, text: str) -> None:
        self.msg, self.msg_at = text, time.monotonic()

    def fail(self, res: Dict[str, Any]) -> None:
        err = res.get("error") or {}
        self.note(self.tx["busy"] if err.get("code") == "busy" else self.tx["failed"].format(msg=err.get("message", "?")))

    # ---- keys
    def handle(self, k: str) -> bool:
        """False to quit."""
        if self.quitting:
            if k in ("q", "ctrl-c"):
                if self.jobs.busy():
                    self.jobs.stop_ev.set()
                return False
            self.quitting, self.msg = False, ""
            return True
        if self.ask_eval:                                  # `e`, step 1: the policy
            self.ask_eval = False
            if k in ("1", "2", "3"):
                self.ask_split = POLICIES[int(k) - 1]
            return True
        if self.ask_split:                                 # `e`, step 2: d(ev) or t(est); Enter = dev
            policy, self.ask_split = self.ask_split, None
            if k in ("d", "enter", "t"):
                self.start_eval(policy, "test" if k == "t" else "dev")
            return True
        if k in ("q", "ctrl-c"):
            if self.jobs.busy():
                self.quitting, self.msg = True, self.tx["quit_running"]
                return True
            return False
        if k == "tab":
            self.tab = (self.tab + 1) % len(TABS); return True
        if k == "backtab":
            self.tab = (self.tab - 1) % len(TABS); return True
        if k in ("1", "2", "3", "4"):
            self.tab = int(k) - 1; return True
        getattr(self, "key_" + TABS[self.tab])(k)
        return True

    def key_home(self, k: str) -> None:
        names = ("model", "data", "size", "seeds")
        opts = {"model": MODELS, "data": DATASETS, "size": tuple(SIZES), "seeds": SEEDS}
        if k == "up":
            self.field = (self.field - 1) % (len(names) + 1)
        elif k == "down":
            self.field = (self.field + 1) % (len(names) + 1)
        elif k in ("left", "right") and self.field < len(names):
            f = names[self.field]
            self.pick[f] = (self.pick[f] + (1 if k == "right" else -1)) % len(opts[f])
        elif k == "enter":
            self.start_training()

    def key_train(self, k: str) -> None:
        r = self.current_training()
        if k == "s" and r and r.get("status") == "running":
            self.jobs.stop(r["id"])
        elif k == "n":
            self.tab, self.field = 0, 4                    # Home, on the start button
        elif k == "m" and r:
            self.start_model_eval(r)
        elif k == "x" and r:
            res = self.jobs.export(r["id"], self.lang)
            if res.get("ok"):
                self.note(self.tx["exported"].format(path=short_path(res["path"])))
            else:
                self.fail(res)

    def key_runs(self, k: str) -> None:
        if self.replay is not None:
            return self.key_replay(k)
        runs = self.runs()
        if k == "up":
            self.sel = max(0, self.sel - 1)
        elif k == "down":
            self.sel = min(max(0, len(runs) - 1), self.sel + 1)
        elif k == "e":
            self.ask_eval = True
        elif k == "enter" and runs:
            r = runs[min(self.sel, len(runs) - 1)]
            if r.get("kind") == "training":
                self.train_id, self.tab, self.group_ids = r["id"], 1, None
            else:
                self.replay = {"id": r["id"], "ep": 0, "scroll": 0}

    def key_replay(self, k: str) -> None:
        rp = self.replay or {}
        n = len((self.run(rp.get("id", "")) or {}).get("episodes") or [])
        if k in ("esc", "backspace"):
            self.replay = None
        elif k in ("left", "right") and n:
            rp["ep"], rp["scroll"] = (rp["ep"] + (1 if k == "right" else -1)) % n, 0
        elif k == "up":
            rp["scroll"] = max(0, rp["scroll"] - 1)
        elif k == "down":
            rp["scroll"] += 1                                # clamped when drawn

    def key_settings(self, k: str) -> None:
        if k in ("left", "right", "enter"):
            self.lang = "ru" if self.lang == "en" else "en"
            save_lang(self.lang)

    # ---- actions
    def start_training(self) -> None:
        body = {"method": MODELS[self.pick["model"]], "dataset": {"preset": DATASETS[self.pick["data"]]},
                **SIZES[tuple(SIZES)[self.pick["size"]]]}
        seeds = SEEDS[self.pick["seeds"]]
        if seeds:
            body["seeds"] = list(seeds)
        res = self.jobs.start_train(body)
        if res.get("ok"):
            self.train_id, self.tab, self.msg = res["run"], 1, ""
            self.group_ids = res.get("runs")
            self._runs_at = 0.0
        else:
            self.fail(res)

    def start_eval(self, policy: str, split: str = "dev") -> None:
        res = self.jobs.start(policy, split)
        if res.get("ok"):
            self.note(self.tx["started"].format(id=res["run"]))
            self._runs_at, self.sel, self.replay = 0.0, 0, None
        else:
            self.fail(res)

    def start_model_eval(self, r: Dict[str, Any]) -> None:
        """`m` on Training: the trained auditor (best-on-dev parameters) on the fresh test split, then Runs."""
        if not (r.get("best") or {}).get("theta"):
            return self.note(self.tx["no_model"])
        res = self.jobs.start(None, "test", model=r["id"])
        if not res.get("ok"):
            return self.fail(res)
        self._runs_at = 0.0
        ids = [x["id"] for x in self.runs()]
        self.sel = ids.index(res["run"]) if res["run"] in ids else 0
        self.tab, self.replay = 2, None
        self.note(self.tx["started"].format(id=res["run"]))

    def current_training(self) -> Optional[Dict[str, Any]]:
        if self.group_ids and self.train_id in self.group_ids and self.jobs.current in self.group_ids \
                and self.jobs.busy() and self.run(self.jobs.current):   # a seed group: follow the running seed
            self.train_id = self.jobs.current
        rid = self.train_id or next((r["id"] for r in self.runs() if r.get("kind") == "training"), None)
        return self.run(rid) if rid else None

    # ---- drawing
    def render(self, w: int, h: int) -> List[str]:
        st, tx = self.st, self.tx
        spin = "⣾⣽⣻⢿⡿⣟⣯⣷"[int((time.monotonic() - self.t0) * 10) % 8]
        tabs = []
        for i, name in enumerate(TABS):
            label = f" {i + 1} {tx[name]} "
            tabs.append(st.INV + st.B + label + st.R if i == self.tab else st.D + label + st.R)
        now = time.monotonic() - self.t0
        right = st.D + beat(now) + st.R + "  " + (st.POS + spin + st.R + " " + tx["running"] if self.jobs.busy() else st.D + "ENV 1.0.0" + st.R)
        head = " " + st.B + "▚▞ AuditGym" + st.R + "   " + "".join(tabs)
        if vlen(head) + vlen(right) + 2 > w:                 # narrow: the heartbeat gives way to the tabs
            right = right.split("  ", 1)[-1]
        lines = [pad(head, max(0, w - vlen(right) - 1)) + right, st.D + "─" * w + st.R]
        body = getattr(self, "draw_" + TABS[self.tab])(w, h - 4)
        lines += body[: h - 4]
        lines += [""] * (h - 2 - len(lines))
        if self.st.R and self.backdrop:                    # the drifting backdrop behind the body (not with NO_COLOR)
            n = h - 4
            lens = self.bg.lens(w, n, now)
            if not self.bg.clear(lines[2:h - 2], lens):    # the loupe never sits beside real numbers: it hides
                lens = None
            lines[2:h - 2] = [self.bg.compose(line, j, n, w, now, lens) for j, line in enumerate(lines[2:h - 2])]
        keys = {"home": "k_home", "train": "k_train", "runs": "k_runs", "settings": "k_settings"}[TABS[self.tab]]
        if TABS[self.tab] == "train":
            r = self.current_training()
            keys = "k_train" if r and r.get("status") == "running" else "k_train_done"
        elif TABS[self.tab] == "runs" and self.replay is not None:
            keys = "k_replay"
        if self.msg and not self.quitting and time.monotonic() - self.msg_at > 5:
            self.msg = ""
        note = self.msg or (tx["eval_ask"] if self.ask_eval else tx["split_ask"].format(policy=tx[self.ask_split]) if self.ask_split else "")
        lines.append((st.B if note else "") + " " + (note or "") + st.R)
        lines.append(st.D + " " + tx[keys] + st.R)
        return [clip(line, w) for line in lines]

    def draw_home(self, w: int, h: int) -> List[str]:
        st, tx = self.st, self.tx
        t = time.monotonic() - self.t0
        cyc = (t + 3) % 6
        tick = min(len(TICK), int(cyc * 7))                     # the tick redraws itself every 6 s
        sparkle = ""
        if tick == len(TICK) and cyc < 1.6:                     # ...and sparkles when it lands
            k = int(t * 8) % 3
            sparkle = " " * 9 + ["✦", "✦ ·", "✦ · ✧"][k]
        out: List[str] = [("  " + st.B + sparkle + st.R) if sparkle else ""]
        phase = (t * 16) % 110 - 25                             # a shaded sheen runs across the letters
        for y, row in enumerate(wordmark(tick=tick)):
            s = ""
            for x, ch in enumerate(row):
                d = abs(x - phase - y * 1.5)
                if ch == " ":
                    s += " "
                elif d < 1:
                    s += st.B + ("░" if ch == "█" else ch) + st.R
                elif d < 2:
                    s += st.B + ("▒" if ch == "█" else ch) + st.R
                elif d < 3.2:
                    s += ("▓" if ch == "█" else ch)
                else:
                    s += st.D + ch + st.R
            out.append("  " + s)
        mark_w = 2 + vlen(wordmark(tick=6)[0]) + 5
        intro = [st.B + tx["ready"] + st.R] + [st.D + x + st.R for x in wrap(tx["sub"], w - mark_w - 2)]
        if w - mark_w >= 34 and len(intro) <= 4:          # wide: the intro sits beside the logo
            for k, line in enumerate(intro):
                out[1 + k] = pad(out[1 + k], mark_w) + line
            out.append("")
        else:
            out += ["", "  " + st.B + tx["ready"] + st.R] + ["  " + st.D + x + st.R for x in wrap(tx["sub"], w - 4)[:2]] + [""]
        m = self.machine
        mline = tx["machine"].format(cpu=cores(m["cpu_count"], self.lang), ram=m["ram_gb"]) if m.get("cpu_count") and m.get("ram_gb") else tx["machine_q"]
        size_key = tuple(SIZES)[self.pick["size"]]
        sz = SIZES[size_key]
        rows = [
            ("model", tx[MODELS[self.pick["model"]]], tx[MODELS[self.pick["model"]] + "_d"]),
            ("data", tx[DATASETS[self.pick["data"]]], tx[DATASETS[self.pick["data"]] + "_d"]),
            ("size", tx[size_key], tx["size_d"].format(it=sz["iterations"], pop=sz["population"], ep=sz["episodes_per_candidate"],
                                                     total=sz["iterations"] * sz["population"] * sz["episodes_per_candidate"])),
            ("seeds", tx["seeds_" + str(len(SEEDS[self.pick["seeds"]] or [1]))], tx["seeds_" + str(len(SEEDS[self.pick["seeds"]] or [1])) + "_d"]),
        ]
        bw = min(w - 4, 92)
        wide = bw >= 88                                   # room for a hint next to every field
        body = []
        for i, (key, val, desc) in enumerate(rows):
            on = i == self.field
            sel = (st.INV + " ‹ " + val + " › " + st.R) if on else ("   " + val + "   ")
            body.append(pad((st.B + "▸ " + st.R if on else "  ") + pad(st.D + tx[key] + st.R, 9) + sel, 36) + (st.D + desc + st.R if wide else ""))
        body.append("" if wide else "  " + st.D + (rows[self.field][2] if self.field < len(rows) else "") + st.R)
        go = " ⏎ " + tx["start"] + " "
        body.append(pad(st.D + mline + st.R, bw - 4 - vlen(go) - 2) + ((st.INV + st.B + go + st.R) if self.field == len(rows) else st.B + go + st.R))
        out += ["  " + line for line in box(tx["new"], body, bw, st)]
        if h - len(out) >= 11:                                   # the three datasets, as in the app: framed cards
            cw = (bw - 4) // 3
            cards = []
            for i, d in enumerate(DATASETS):
                on = i == self.pick["data"]
                pic = art(d, t * (2.2 if on else 1.0))
                badge = st.D + tx["badge_" + d] + st.R
                name = (st.INV + st.B + " " + tx[d] + " " + st.R) if on else (st.B + tx[d] + st.R)
                body = [(st.R if on else st.D) + "  " + p + st.R for p in pic] + [pad(name, cw - 4 - vlen(badge)) + badge]
                frame = box("", body, cw, st) if not on else [c.replace(st.D, st.B) for c in box("", body, cw, st)]
                cards.append(frame)
            out += [" " + "  ".join(row) for row in zip(*cards)]
        room = min(5, h - len(out) - 2)
        if room <= 0 and self.runs():                            # no room left: the Runs page lists them
            return out
        out += ["", "  " + st.B + tx["recent"] + st.R]
        runs = self.runs()[: max(0, room)]
        if not runs:
            out.append("  " + st.D + tx["no_runs"] + st.R)
        for r in runs:
            out.append("  " + self.run_row(r, min(w - 4, 92)))
        return out

    def run_name(self, r: Dict[str, Any]) -> str:
        tx = self.tx
        if r.get("kind") == "arena":
            return "Red team · " + ("attack on the reward" if self.lang == "en" else "атака на награду")
        if r.get("kind") == "training":
            name = f"{tx['training']} · {'REINFORCE' if r.get('method') == 'reinforce' else 'CEM'}"
            return name + (f" · {tx['seed']} {r['seed']}" if r.get("group") and r.get("seed") is not None else "")
        agent = r.get("agent") or ""
        if agent.startswith("auditor-") and agent[8:] in MODELS:      # a trained auditor: "Evaluation · Auditor · CEM"
            name = f"{tx['evaluation']} · {tx[agent[8:]]}"
        else:
            name = f"{tx['evaluation']} · {tx.get(agent, agent or '?')}"
        return name + (f" · {tx['test']}" if r.get("split") == "test" else "")

    def run_value(self, r: Dict[str, Any]) -> Optional[float]:
        s = r.get("summary") or {}
        return s.get("dev_best") if r.get("kind") == "training" else (s.get("reward") if s.get("episodes_done") else None)

    def run_row(self, r: Dict[str, Any], w: int, selected: bool = False) -> str:
        st = self.st
        v = self.run_value(r)
        running = r.get("status") == "running"
        dot = (st.POS + "⣾⣽⣻⢿⡿⣟⣯⣷"[int((time.monotonic() - self.t0) * 10) % 8] + st.R) if running else \
            ((st.POS if (v or 0) > 0 else st.NEG) + "●" + st.R if v is not None else st.D + "○" + st.R)
        when = time.strftime("%d.%m %H:%M", time.localtime(r.get("started") or 0))
        left = f"{dot} {self.run_name(r)}"
        right = f"{st.val(v)}  {st.D}{when}{st.R}"
        if vlen(left) + 1 + vlen(right) > w:              # tight: the date gives way to the name
            right = st.val(v)
        line = pad(left, max(0, w - vlen(right) - 1)) + " " + right
        return (st.INV + ESC.sub("", line) + st.R) if selected else line

    def draw_train(self, w: int, h: int) -> List[str]:
        st, tx = self.st, self.tx
        r = self.current_training()
        if not r:
            return ["", "  " + st.D + tx["no_train"] + st.R]
        cfg = r.get("config") or {}
        n = r.get("iterations") or cfg.get("iterations") or 1
        pts = r.get("points") or []
        at = r.get("at") or len(pts)
        status = r.get("status") or "running"
        testing = r.get("status_note") == "testing"
        spin = "⣾⣽⣻⢿⡿⣟⣯⣷"[int((time.monotonic() - self.t0) * 10) % 8]
        title = f"{tx['training']} · {tx[cfg.get('method', 'cem')]} · {tx.get((cfg.get('dataset') or {}).get('preset', 'mixed'), '')}"
        if r.get("group") and r.get("seed") is not None:
            title += f" · {tx['seed']} {r['seed']}"
        state = (st.POS + spin + " " + tx["running"] + st.R) if status == "running" else \
            (st.POS + spin + " " + tx["testing_state"] + st.R) if testing else \
            ((st.NEG if status == "error" else st.D) + tx.get(status, status) + st.R)
        lp = pts[-1] if pts else None
        cpu = (min(100, round(100 * lp["cpu_seconds"] / lp["seconds"])) if lp and lp.get("cpu_seconds") is not None and lp.get("seconds") else None)
        proc = (st.D + tx["cpu"].format(cpu=cpu) + " · " + st.R) if cpu is not None and status == "running" else ""
        right = f"{proc}{tx['iteration'].format(i=at, n=n)}  {state}"
        out = ["", "  " + pad(st.B + title + st.R, max(0, w - 4 - vlen(right))) + right, ""]

        s = r.get("summary") or {}
        last_dev = next((p["dev"] for p in reversed(pts) if p.get("dev")), None)
        best = s.get("dev_best")
        ref = self.baseline.get("reconcile")
        started, finished = r.get("started"), r.get("finished")
        elapsed = ((finished or time.time()) - started) if started else None
        eta = (elapsed / at * (n - at)) if (elapsed and at and status == "running") else None
        kv = [
            (tx["best"], st.val(best) if best is not None else st.D + tx["waiting"] + st.R),
            (tx["last"], st.val(s.get("dev_last") if s.get("dev_last") is not None else (last_dev or {}).get("reward"))),
            (tx["vs"], st.val(best - ref) if best is not None and ref is not None else st.D + "—" + st.R),
            (tx["f1"], f"{last_dev['f1']:.2f}" if last_dev else "—"),
            (tx["fp"], f"{last_dev['fp']:.1f}" if last_dev else "—"),
            (tx["steps"], f"{last_dev['steps']:.1f}" if last_dev else "—"),
            (tx["episodes"], str(sum(p.get("episodes", 0) for p in pts)) +
             (st.D + " · " + tx["eps_s"].format(n=round(lp["eps_per_sec"])) + st.R if lp and lp.get("eps_per_sec") and status == "running" else "")),
            (tx["elapsed"], fmt_time(elapsed, tx) + (st.D + " · " + tx["eta"] + " ≈ " + fmt_time(eta, tx) + st.R if eta is not None else "")),
        ]
        has_test = bool(r.get("test")) or testing
        test_title = tx["test_box"].format(n=(r.get("test") or {}).get("episodes") or 20)
        avail = h - 3 - 2                                   # rows between the title and the progress bar
        side_w = 32
        kv_box = box(tx["train"], [pad(st.D + k + st.R, side_w - 4 - vlen(v)) + v for k, v in kv], side_w, st)
        test_box = box(test_title, self.test_body(r, side_w - 4), side_w, st) if has_test else []
        pop_t, pop_rows = self.population(r, side_w - 4)
        pop = box(pop_t, pop_rows, side_w, st) if pop_rows else []
        if w >= 90 and len(kv_box) + len(test_box) <= avail:
            # wide: the numbers, the test and the population in a column beside the chart; under both, the model at
            # work (what the best candidate just did, and the weights) in the rows the column and a chart can spare
            need = max(12, len(kv_box) + len(test_box) + (len(pop) if not has_test else 0))
            maw = self.model_at_work(r, w - 4, min(14, avail - need - 1))
            if maw:
                avail -= len(maw) + 1
            cw = w - 4 - side_w - 2
            leg = self.legend(cw, ref)
            left = self.chart_box(r, cw, max(4, min(24, h - 12, avail - 3 - len(leg))), leg)
            col = kv_box + test_box
            if pop and len(col) + len(pop) <= max(len(left), avail):
                col += pop
            if len(col) > len(left):                         # let the chart grow to the column's height
                left = self.chart_box(r, cw, max(4, min(avail, len(col)) - 3 - len(leg)), leg)
            rows = max(len(left), len(col))
            left += [" " * cw] * (rows - len(left))
            col += [""] * (rows - len(col))
            out += ["  " + a + "  " + b for a, b in zip(left, col)]
            if maw:
                out += [""] + ["  " + x for x in maw]
        else:
            # narrow or short: the test beside the chart (or under it), the numbers in two columns below
            ncol = 2 if w >= 60 else 1
            colw = (w - 4 - 2 * (ncol - 1)) // ncol
            per = -(-len(kv) // ncol)
            cells = [pad(st.D + k + st.R, colw - vlen(v)) + v for k, v in kv]
            kv_rows = ["  " + "  ".join(pad(cells[c * per + i], colw) for c in range(ncol) if c * per + i < len(cells)) for i in range(per)]
            tw = 32
            beside = has_test and w - 4 - tw - 2 >= 40
            cw = w - 4 - (tw + 2 if beside else 0)
            leg = self.legend(cw, ref)
            under = box(test_title, self.test_body(r, w - 8), w - 4, st) if has_test and not beside else []
            ch = max(4, min(16, avail - len(kv_rows) - 3 - len(leg) - len(under)))
            left = self.chart_box(r, cw, ch, leg)
            if beside:
                tb = box(test_title, self.test_body(r, tw - 4), tw, st)
                rows = max(len(left), len(tb))
                left += [" " * cw] * (rows - len(left))
                tb += [""] * (rows - len(tb))
                out += ["  " + a + "  " + b for a, b in zip(left, tb)]
            else:
                out += ["  " + a for a in left + under]
            out += kv_rows
            maw = self.model_at_work(r, w - 4, min(10, h - 3 - len(out) - 3))
            if maw:
                out += [""] + ["  " + x for x in maw]
        frac = min(1.0, at / n) if n else 0
        bw = w - 12
        fill = int(frac * bw)
        head = ""
        if status == "running" and fill < bw:                    # a shimmering head on the running bar
            head = "▓▒░"[: bw - fill]
            fill = min(fill, bw - len(head))
        rest = bw - fill - len(head)
        out += ["", f"  {st.POS}{'█' * fill}{head}{st.R}{st.D}{'·' * rest}{st.R} {int(frac * 100):3d}%"]
        return out

    def legend(self, cw: int, ref: Optional[float]) -> List[str]:
        """The chart's legend, on one line if it fits, else packed onto as few lines as fit the box."""
        st, tx = self.st, self.tx
        items = [f"{st.POS}━{st.R} {tx['l_dev']}", f"{st.D}━ {tx['l_train']}{st.R}"] + \
                ([f"{st.NEG}┄{st.R} {tx['l_ref']} {ref:+.2f}"] if ref is not None else [])
        for indent in (7, 1):
            room = cw - 4 - indent
            lines: List[str] = []
            for it in items:
                if lines and vlen(lines[-1]) + 3 + vlen(it) <= room:
                    lines[-1] += "   " + it
                else:
                    lines.append(it)
            if len(lines) <= 2 or indent == 1:
                return [" " * indent + x for x in lines]
        return []

    def chart_box(self, r: Dict[str, Any], cw: int, ch: int, leg: List[str]) -> List[str]:
        """The braille chart of the dev reward, the population mean and the Reconciler baseline, framed."""
        st, tx = self.st, self.tx
        n = r.get("iterations") or (r.get("config") or {}).get("iterations") or 1
        pts = r.get("points") or []
        dev = [(p["i"], p["dev"]["reward"]) for p in pts if p.get("dev")]
        trn = [(p["i"], p["train_mean"]) for p in pts if p.get("train_mean") is not None]
        ref = self.baseline.get("reconcile")
        plot_w = cw - 4 - 7
        series = []
        if ref is not None:
            series.append(([(0, ref), (max(n - 1, 1), ref)], "ref", True))
        series += [(trn, "train", False), (dev, "dev", False)]
        grid = chart(series, plot_w, ch, max(n - 1, 1))
        colour = {"dev": st.POS + st.B, "train": st.D, "ref": st.NEG + st.D, "": ""}
        rows = []
        for y, row in enumerate(grid):
            label = {0: "+1.0", ch - 1: "−1.0", round((ch - 1) / 2): " 0.0"}.get(y, "")
            s = "".join((colour[o] + c + st.R) if o else c for c, o in row)
            rows.append(st.D + f"{label:>5} " + ("┤" if label else "│") + st.R + s)
        rows.append(st.D + "      └" + "─" * plot_w + st.R)
        rows += leg
        return box(tx["chart"], rows, cw, st)

    def test_body(self, r: Dict[str, Any], w: int) -> List[str]:
        """The fresh test split of a finished training: the trained auditor against the Reconciler and the Intern,
        then what the auditor found and missed per error type. A spinner while it is being measured."""
        st, tx = self.st, self.tx
        test = r.get("test")
        if not test:
            spin = "⣾⣽⣻⢿⡿⣟⣯⣷"[int((time.monotonic() - self.t0) * 10) % 8]
            lines = wrap(tx["testing"], w - 2) or [""]
            return [st.POS + spin + st.R + " " + lines[0]] + ["  " + x for x in lines[1:]]
        if test.get("error"):
            return [st.NEG + tx["test_failed"] + st.R] + [st.D + x + st.R for x in wrap(str(test["error"]), w)[:2]]
        out = []
        for key in ("auditor", "reconcile", "random"):
            v = (test.get(key) or {}).get("reward")
            out.append(pad((st.B if key == "auditor" else st.D) + tx[key] + st.R, w - 5) + st.val(v))
        out.append("")
        return out + self.type_rows((test.get("analysis") or {}).get("by_type") or {}, w)

    def type_rows(self, by_type: Dict[str, Any], w: int) -> List[str]:
        """Found / missed per error type as small bars: `duplicates   ████░░ 14/20  6 missed`."""
        st, tx = self.st, self.tx
        keys = [t for t in ERR_TYPES if t in by_type] + sorted(t for t in by_type if t not in ERR_TYPES)
        if not keys:
            return [st.D + "—" + st.R]
        num = {t: (int((by_type[t] or {}).get("found", 0)), int((by_type[t] or {}).get("issues", 0))) for t in keys}
        cnt = {t: f"{f}/{n}" for t, (f, n) in num.items()}
        cw = max(len(c) for c in cnt.values())
        nw = 13
        bw = max(3, min(12, w - nw - cw - 1))
        out = []
        for t in keys:
            f, n = num[t]
            line = pad(st.D + (tx[t] if t in ERR_TYPES else t[:nw - 1]) + st.R, nw) + bar(f, n, bw, st) + " " + cnt[t].rjust(cw)
            if n > f and w - vlen(line) >= len(tx["missed"]) + 6:
                line += st.D + f"  {n - f} {tx['missed']}" + st.R
            out.append(line)
        return out

    def population(self, r: Dict[str, Any], w: int) -> Tuple[str, List[str]]:
        """Every candidate of the last finished iteration on a reward line from −1 to +1, as the trainer scored them
        (run.json points: scores, elite). Candidates in the same cell stack; the elite is blue. Runs recorded before
        the trainer kept the scores have no population box."""
        st, tx = self.st, self.tx
        pts = [p for p in (r.get("points") or []) if isinstance(p.get("scores"), list) and p["scores"]]
        if not pts:
            return tx["population"], [st.D + tx["pop_wait"] + st.R] if r.get("status") == "running" and not r.get("points") else []
        p = pts[-1]
        sc, el = p["scores"], set(p.get("elite") or [])
        cols: List[List[bool]] = [[] for _ in range(w)]
        for k in sorted(range(len(sc)), key=lambda k: k not in el):          # the elite first in each cell
            cols[max(0, min(w - 1, round((max(-1.0, min(1.0, sc[k])) + 1) / 2 * (w - 1))))].append(k in el)
        def row(level: int) -> str:
            out = []
            for c in cols:
                if len(c) > level:
                    out.append((st.POS + st.B + "●" if c[level] else st.D + "○") + st.R)
                else:
                    out.append(" ")
            return "".join(out)
        axis = "−1" + "0".center(w - 4, "─") + "+1"
        method = (r.get("config") or {}).get("method", "cem")
        keep = tx["pop_elite" if method == "cem" else "pop_top"].format(k=len(el))
        leg_a, leg_b = st.POS + "●" + st.R + st.D + " " + keep + st.R, st.D + "○ " + tx["pop_rest"] + st.R
        legend = [leg_a + "  " + leg_b] if vlen(leg_a) + 2 + vlen(leg_b) <= w else [leg_a, leg_b]
        rows = [row(2) if any(len(c) > 2 for c in cols) else None, row(1), row(0), st.D + axis + st.R,
                st.D + tx["pop_best"].format(b=f"{max(sc):+.2f}", w=f"{min(sc):+.2f}") + st.R] + legend
        return tx["pop_title"].format(i=p["i"] + 1), [x for x in rows if x is not None]

    def model_at_work(self, r: Dict[str, Any], w: int, rows: int) -> List[str]:
        """What the best candidate of the last iteration actually did (run.json "live": the trainer replays it on a
        training episode and the evaluator scores it): pages read per table, every finding with ✓ / ✗, the
        evaluator's line. Beside it, when there is room, the 20 weights of the model as σ(θ). At most `rows` lines."""
        st, tx = self.st, self.tx
        L = r.get("live")
        pts = [p for p in (r.get("points") or []) if isinstance(p.get("mu"), list)]
        if rows < 6 or (not L and not (r.get("status") == "running" and not r.get("points"))):
            return []
        ww = 2 * (16 + 7 + 5) + 2 + 4                                          # two columns of label, bar, value
        show_w = bool(pts) and rows >= 12 and w - ww - 2 >= 46
        aw = w - (ww + 2 if show_w else 0)
        iw = aw - 4
        body: List[str] = []
        if not L:
            body = [st.D + tx["first_it"] + st.R]
            title = tx["maw_wait"]
        elif L.get("error"):
            body = [st.NEG + str(L["error"])[: iw] + st.R]
            title = tx["maw_wait"]
        else:
            title = tx["maw"].format(i=L.get("i", 0) + 1, c=(L.get("candidate") or 0) + 1)
            pages, nrows = L.get("pages") or {}, L.get("rows") or {}
            mp = max([1] + [int(v or 0) for v in pages.values()])
            half = (iw - 2) // 2
            cells = []
            for t in ("fx", "invoices", "payments", "ledger"):
                pg = int(pages.get(t) or 0)
                name = pad(tx["t_" + t], 9)
                if pg:
                    bw = 6
                    k = max(1, round(bw * pg / mp))
                    val = tx["pages"].format(p=pg, r=nrows.get(t, 0))
                    cells.append(name + st.POS + "█" * k + st.R + st.D + "░" * (bw - k) + st.R + " " + st.D + val + st.R)
                else:
                    cells.append(st.D + name + "      " + " " + tx["not_read"] + st.R)
            if half >= 36:
                body += [pad(cells[0], half) + "  " + cells[1], pad(cells[2], half) + "  " + cells[3]]
            else:
                body += cells
            fs = L.get("findings") or []
            issues = L.get("issues", (L.get("tp") or 0) + (L.get("fn") or 0))
            room = max(1, rows - 2 - len(body) - 1)
            if not fs:
                body.append((st.POS if not issues else st.D) + (tx["clean_ok"] if not issues else tx["nothing"]) + st.R)
            for f in fs[: room if len(fs) <= room else room - 1]:
                ok = bool(f.get("matched"))
                amt = f.get("amount_minor")
                money = (f"{abs(amt) // 100:,}".replace(",", " ") + f".{abs(amt) % 100:02d} {f.get('currency') or ''}").strip() if isinstance(amt, int) else ""
                head = (st.POS + "✓" if ok else st.NEG + "✗") + st.R + " " + pad((st.NEG if not ok else "") + tx.get(f.get("type"), f.get("type") or "—") + st.R, 13)
                ids = ", ".join(f.get("ids") or [])
                body.append(pad(head + st.D + clip(ids, max(4, iw - 15 - len(money) - 2)) + st.R, iw - len(money)) + st.D + money + st.R)
            if len(fs) > room:
                body.append(st.D + tx["more"].format(n=len(fs) - room + 1) + st.R)
            ev1 = (st.B + tx["ev"] + ":" + st.R + " " + st.POS + f"{L.get('tp') or 0} {tx['correct']}" + st.R + st.D + " · " + st.R +
                   (st.NEG if L.get("fp") else st.D) + f"{L.get('fp') or 0} {tx['false']}" + st.R + st.D + " · " +
                   tx["missed_of"].format(fn=L.get("fn") or 0, n=issues) + st.R)
            ev2 = st.D + f"{L.get('steps', 0)} {tx['steps_n']}" + st.R + "  " + st.B + tx["reward"] + " " + st.R + st.val(L.get("reward"))
            if vlen(ev1) + 3 + vlen(ev2) <= iw:
                body.append(ev1 + st.D + " · " + st.R + ev2)
            else:                                   # the reward is the point: it never gets clipped away
                if len(body) >= rows - 3 and len(body) > 3:
                    body.pop()
                body += [ev1, ev2]
        body = body[: rows - 2]
        if not show_w:
            return box(title, body, aw, st)
        left = box(title, body + [""] * (rows - 2 - len(body)), aw, st)
        mu = pts[-1]["mu"]
        labels = tx["w_labels"].split("|")
        cells = []
        for d, v in enumerate(mu[:20]):
            sg = 1 / (1 + math.exp(-max(-60.0, min(60.0, float(v)))))
            k = round(sg * 5)
            cells.append(pad(st.D + clip(labels[d] if d < len(labels) else str(d), 15) + st.R, 16) +
                         (st.POS if sg > 0.5 else st.D) + "█" * k + st.R + st.D + "░" * (5 - k) + st.R + f" {sg:.2f}")
        wrows = [pad(cells[i], 28) + "  " + (cells[i + 10] if i + 10 < len(cells) else "") for i in range(10)]
        right = box(tx["weights"], wrows + [""] * (rows - 2 - len(wrows)), ww, st)
        right = (right + [" " * ww] * rows)[:rows]
        return [a + "  " + b for a, b in zip(left, right)]

    def draw_runs(self, w: int, h: int) -> List[str]:
        if self.replay is not None:
            return self.draw_replay(w, h)
        st, tx = self.st, self.tx
        runs = self.runs()
        out = [""]
        if not runs:
            return out + ["  " + st.D + tx["no_runs"] + st.R]
        self.sel = min(self.sel, len(runs) - 1)
        lw = min(60, max(36, w // 2 - 2))
        wide = w >= 90 and len(self.run_detail(runs[self.sel], w - lw - 8)) <= h - 1
        if not wide:                                      # narrow or short: a short list, the details under it
            lw = w - 4
            head, main, extra = self.run_detail_parts(runs[self.sel], (w - 6) // 2 if w >= 76 else w - 4)
            if w >= 76:
                cw = (w - 6) // 2
                extra = extra[1:] if extra[:1] == [""] else extra
                n = max(len(main), len(extra))
                main, extra = main + [""] * (n - len(main)), extra + [""] * (n - len(extra))
                detail = head + [pad(a, cw) + "  " + b for a, b in zip(main, extra)]
            else:
                detail = head + main + extra
            n_list = max(3, min(len(runs), h - 2 - len(detail)))
            top = max(0, self.sel - n_list + 1)
            left = [self.run_row(r, lw, top + i == self.sel) for i, r in enumerate(runs[top: top + n_list])]
            return out + ["  " + a for a in left] + [""] + ["  " + b for b in detail]
        top = max(0, self.sel - (h - 4) + 1)
        visible = runs[top: top + h - 3]
        left = [self.run_row(r, lw, top + i == self.sel) for i, r in enumerate(visible)]
        right = self.run_detail(runs[self.sel], w - lw - 8)
        for i in range(max(len(left), len(right))):
            a = left[i] if i < len(left) else ""
            b = right[i] if i < len(right) else ""
            out.append("  " + pad(a, lw) + "    " + b)
        return out

    def run_detail(self, r: Dict[str, Any], w: int) -> List[str]:
        head, main, extra = self.run_detail_parts(r, w)
        return head + main + extra

    def run_detail_parts(self, r: Dict[str, Any], w: int) -> Tuple[List[str], List[str], List[str]]:
        """A run's details: (its name and ids, the key numbers, the analysis or seed group), so a narrow screen can
        set the last two side by side."""
        st, tx = self.st, self.tx
        full = self.run(r["id"]) or r
        s = full.get("summary") or {}
        lab = 22 if w >= 50 else 18
        rows = [st.B + self.run_name(r) + st.R, st.D + r["id"] + st.R]
        if full.get("model_run"):
            rows.append(st.D + tx["model_of"] + ": " + st.R + full["model_run"])
        head, rows = rows + [""], []
        kv: List[Tuple[str, str]] = []
        if r.get("kind") == "training":
            cfg = full.get("config") or {}
            tr = ((full.get("test") or {}).get("auditor") or {}).get("reward")
            spin = "⣾⣽⣻⢿⡿⣟⣯⣷"[int((time.monotonic() - self.t0) * 10) % 8]
            kv = [(tx["best"], st.val(s.get("dev_best"))), (tx["last"], st.val(s.get("dev_last"))),
                  (tx["test_reward"], st.val(tr) if tr is not None else
                   (st.POS + spin + " " + tx["testing_state"] + st.R) if full.get("status_note") == "testing" else st.D + "—" + st.R),
                  (tx["data"], tx.get((cfg.get("dataset") or {}).get("preset", ""), "—")),
                  (tx["config"], f"{cfg.get('iterations', '?')} × {cfg.get('population', '?')} × {cfg.get('episodes_per_candidate', '?')}"),
                  (tx["seed"], str(cfg.get("seed", "—"))), (tx["episodes"], str(s.get("episodes", "—"))),
                  (tx["time"], fmt_time(s.get("seconds"), tx))]
            pts = [p["dev"]["reward"] for p in full.get("points") or [] if p.get("dev")]
            if pts:
                spark = "".join("▁▂▃▄▅▆▇█"[max(0, min(7, int((v + 1) / 2 * 7.99)))] for v in pts[-max(1, w - lab):])
                kv.append(("dev", st.POS + spark + st.R))
            extra = (self.group_rows(r, lab) if r.get("group") else []) + ["", st.D + tx["open_hint"] + st.R]
        else:
            kv = [(tx["reward"], st.val(s.get("reward"))), (tx["precision"], f"{s['precision']:.2f}" if "precision" in s else "—"),
                  (tx["recall"], f"{s['recall']:.2f}" if "recall" in s else "—"), ("F1", f"{s['f1']:.2f}" if "f1" in s else "—"),
                  (tx["steps"], str(s.get("steps", "—"))), (tx["episodes"], f"{s.get('episodes_done', 0)}/{len(full.get('episodes') or [])}"),
                  (tx["split"], str(r.get("split") or "—")), (tx["time"], fmt_time(s.get("seconds"), tx))]
            rw = [(e.get("score") or {}).get("reward") for e in full.get("episodes") or []]
            if rw:
                sep = " " if lab + 2 * len(rw) - 1 <= w else ""
                kv.append(("", sep.join((st.POS + "▮" + st.R) if (v or 0) > 0 else (st.NEG + "▮" + st.R) if v is not None else st.D + "▯" + st.R for v in rw)))
            extra = self.analysis_rows(full.get("analysis"), w, lab) + ["", st.D + tx["replay_hint"] + st.R]
        state = r.get("status") or ""
        rows.append(pad(st.D + tx["status"] + st.R, lab) + (st.NEG if state == "error" else "") + tx.get(state, state) + st.R)
        rows += [pad(st.D + k + st.R, lab) + v for k, v in kv]
        return head, rows, extra

    def group_rows(self, r: Dict[str, Any], lab: int) -> List[str]:
        """The seeds of a training's group: best dev and test reward of each, and their mean."""
        st, tx = self.st, self.tx
        mates = sorted((x for x in self.runs() if x.get("kind") == "training" and x.get("group") == r.get("group")),
                       key=lambda x: (x.get("seed") is None, x.get("seed") or 0))
        out = ["", st.B + tx["group_seeds"] + st.R, " " * lab + st.D + pad(tx["best_short"], 11) + tx["test"] + st.R]
        devs, tests = [], []
        for x in mates:
            d, t = (x.get("summary") or {}).get("dev_best"), x.get("test_reward")
            devs += [d] if d is not None else []
            tests += [t] if t is not None else []
            mark = st.B + "▸ " + st.R if x["id"] == r["id"] else "  "
            out.append(pad(mark + st.D + f"{tx['seed']} {x.get('seed', '?')}" + st.R, lab) + pad(st.val(d), 11) + st.val(t))
        if len(mates) > 1:
            mean = lambda v: sum(v) / len(v) if v else None
            out.append(pad("  " + st.D + tx["mean"] + st.R, lab) + pad(st.val(mean(devs)), 11) + st.val(mean(tests)))
        return out

    def analysis_rows(self, a: Optional[Dict[str, Any]], w: int, lab: int) -> List[str]:
        """An evaluation's measured failure analysis: found / missed per error type, the types the false findings
        claimed, and the reward by kind of episode."""
        st, tx = self.st, self.tx
        if not a:
            return []
        out = ["", st.B + tx["found_by_type"] + st.R]
        out += ["  " + x for x in self.type_rows(a.get("by_type") or {}, w - 2)]
        fb = a.get("false_by_type") or {}
        name = lambda t: tx[t] if t in ERR_TYPES or t == "invalid" else str(t)[:20]
        fl = " · ".join(f"{name(t)} {k}" for t, k in sorted(fb.items(), key=lambda kv: (-kv[1], kv[0])))
        out.append(pad(st.D + tx["false_by"] + st.R, lab) + (st.NEG + fl + st.R if fb else st.D + tx["none"] + st.R))
        bk = a.get("by_kind") or {}
        if bk:
            out.append(st.B + tx["by_kind"] + st.R)
            for k in list(KINDS) + sorted(x for x in bk if x not in KINDS):
                if k in bk:
                    out.append(pad("  " + st.D + tx.get("k_" + k, k) + st.R, lab) + pad(st.val(bk[k].get("reward")), 7)
                               + st.D + f"{bk[k].get('episodes', 0)} {tx['episodes']}" + st.R)
        return out

    def ep_label(self, label: str) -> str:
        """The harness's public episode label (written in Russian) in the UI's language."""
        if self.lang == "ru" or not label:
            return label or ""
        for ru, en in (("чистая", "clean"), ("взаимод.", "interacting"), ("смешанная", "mixed")):
            if label.startswith(ru):
                return en + label[len(ru):]
        m = re.match(r"^(\d+) ош\.$", label)
        return f"{m.group(1)} {'error' if m.group(1) == '1' else 'errors'}" if m else label

    def draw_replay(self, w: int, h: int) -> List[str]:
        """An evaluation step by step: the episodes on top (←→), the steps of the chosen one below (↑↓)."""
        st, tx = self.st, self.tx
        rp = self.replay or {}
        full = self.run(rp.get("id", "")) or {}
        row = next((x for x in self.runs() if x["id"] == rp.get("id")), full)
        title = st.B + tx["replay"] + " · " + self.run_name(row) + st.R
        rid = str(rp.get("id", ""))
        out = [""]
        if vlen(title) + 2 + len(rid) <= w - 4:
            out.append("  " + pad(title, w - 4 - len(rid)) + st.D + rid + st.R)
        else:
            out.append("  " + title)
        eps = full.get("episodes") or []
        if not eps:
            return out + ["", "  " + st.D + tx["no_steps"] + st.R]
        ep = rp["ep"] = max(0, min(rp.get("ep", 0), len(eps) - 1))
        chips = []
        for i, e in enumerate(eps):
            v = (e.get("score") or {}).get("reward")
            if i == ep:
                chips.append(st.INV + st.B + f"[{i + 1}]" + st.R)
            else:
                chips.append((st.POS if (v or 0) > 0 else st.NEG if v is not None else st.D) + f" {i + 1} " + st.R)
        room, a, b = w - 8, ep, ep + 1                      # a window of episode chips around the chosen one
        used = vlen(chips[ep])
        while True:
            grew = False
            if b < len(chips) and used + 1 + vlen(chips[b]) <= room:
                used, b, grew = used + 1 + vlen(chips[b]), b + 1, True
            if a > 0 and used + 1 + vlen(chips[a - 1]) <= room:
                a, grew = a - 1, True
                used += 1 + vlen(chips[a])
            if not grew:
                break
        out += ["", "  " + (st.D + "‹ " + st.R if a > 0 else "  ") + " ".join(chips[a:b]) + (st.D + " ›" + st.R if b < len(chips) else "")]
        e = eps[ep]
        sc = e.get("score") or {}
        info = [f"{tx['episode']} {ep + 1}/{len(eps)}", self.ep_label(e.get("label") or ""),
                f"{tx['reward']} " + st.val(sc.get("reward"))]
        if "f1" in sc:
            info.append(f"F1 {sc['f1']:.2f}")
        if e.get("steps") is not None:
            info.append(f"{e['steps']} {tx['steps_n']}")
        if e.get("status") not in (None, "done"):
            info.append(tx.get(e["status"], e["status"]))
        out += ["  " + (st.D + " · " + st.R).join(x for x in info if x), ""]
        steps = self.steps(rid, ep)
        if not steps:
            return out + ["  " + st.D + tx["no_steps"] + st.R]
        aw = max(6, w - 4 - 52)                               # NN tool args result rows left
        out.append("  " + st.D + " # " + "  " + pad(tx["c_tool"], 16) + "  " + pad(tx["c_args"], aw) + "  "
                   + pad(tx["c_ok"], 14) + "  " + tx["c_rows"].rjust(5) + " " + tx["c_left"].rjust(5) + st.R)
        vis = max(1, h - len(out) - 1)
        scroll = rp["scroll"] = max(0, min(rp.get("scroll", 0), len(steps) - vis))
        for s in steps[scroll: scroll + vis]:
            args = s.get("args") or {}
            a_txt = " ".join(f"{k}={'?' if v is None else v}" for k, v in args.items()) if isinstance(args, dict) else str(args)
            if s.get("truncated"):
                res = st.NEG + tx["truncated"] + st.R
            elif s.get("ok"):
                res = st.POS + "ok" + st.R
            else:
                res = st.NEG + str(s.get("error") or tx["error"]) + st.R
            num = lambda v: "—" if v is None else str(v)
            out.append("  " + f"{s.get('n', 0):>3}" + "  " + pad(str(s.get("tool") or "?"), 16) + "  " + pad(a_txt, aw) + "  "
                       + pad(res, 14) + "  " + num(s.get("rows")).rjust(5) + " " + num(s.get("left")).rjust(5))
        more = (" ↑" if scroll > 0 else "  ") + (" ↓" if scroll + vis < len(steps) else "")
        out.append("  " + st.D + f"{scroll + 1}–{min(len(steps), scroll + vis)} / {len(steps)}" + more + st.R)
        return out

    def draw_settings(self, w: int, h: int) -> List[str]:
        st, tx = self.st, self.tx
        lang = "  ".join((st.INV + " " + name + " " + st.R) if code == self.lang else (st.D + " " + name + " " + st.R)
                         for code, name in (("en", "English"), ("ru", "Русский")))
        ver = os.environ.get("AUDITGYM_BUILD") or tx["source"]
        rep = self.report
        if rep and rep.get("estimated_score"):
            checks = [c for a in (rep.get("areas") or {}).values() for c in a]
            rline = tx["report_line"].format(score=rep["estimated_score"].get("total"), ok=sum(1 for c in checks if c.get("passed")), n=len(checks))
        else:
            rline = tx["report_none"]
        rows = [("language", lang), ("version", ver), ("updates", tx["update_how"]), ("report", rline), ("data_dir", self.base or runs_dir())]
        body = [pad(st.D + tx[k] + st.R, 22) + v for k, v in rows]
        out = [""] + ["  " + line for line in box(tx["settings"], body, min(w - 4, 100), st)]
        t = time.monotonic() - self.t0
        mark = wordmark("", tick=min(len(TICK), int(((t + 3) % 6) * 7)))
        caption = [st.B + "AuditGym" + st.R, st.D + tx["tagline"] + st.R, st.D + beat(t, 24) + st.R, ""]
        out += [""] + ["  " + st.D + m.ljust(9) + st.R + "  " + c for m, c in zip(mark, caption)]
        return out


def main(argv: Optional[List[str]] = None) -> int:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("auditgym: the terminal UI needs an interactive terminal; see  auditgym --help", file=sys.stderr)
        return 2
    colour = not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
    app = App(colour=colour)
    with Terminal() as term:
        try:
            while True:
                w, h = shutil.get_terminal_size((100, 30))
                term.draw(app.render(w, h))
                if not all(app.handle(k) for k in term.keys(0.1)):
                    break
        except KeyboardInterrupt:
            if app.jobs.busy():
                app.jobs.stop_ev.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
