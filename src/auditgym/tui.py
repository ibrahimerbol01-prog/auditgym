"""Terminal UI: the desktop app's flow in a terminal. `auditgym` with no arguments (on a terminal) or `auditgym tui`.

Four sections, switched with Tab or 1-4: Home (start a training: model, data, size), Training (live telemetry:
a braille chart of the dev reward, the population mean and the Reconciler baseline, with the key numbers next to
it), Runs (every training and evaluation, with details; evaluate a built-in policy) and Settings (language,
version, updates, the verification report). It drives the same harness as the app (auditgym.harness.Jobs), so runs
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

from .harness import Jobs, list_runs, read_run, runs_dir

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
        "running": "running", "done": "done", "stopped": "stopped", "error": "error",
        "iteration": "iteration {i}/{n}",
        "chart": "Reward on held-out dev episodes", "l_dev": "dev reward", "l_train": "population mean", "l_ref": "Reconciler",
        "best": "best (dev)", "last": "last (dev)", "vs": "vs Reconciler", "f1": "F1 (dev)", "fp": "false findings / ep.",
        "steps": "steps / ep.", "elapsed": "elapsed", "eta": "left", "episodes": "episodes",
        "k_train": "s stop   Tab section   q quit", "k_train_done": "n new training   Tab section   q quit",
        "no_train": "No training yet. Start one on Home (press 1).",
        "waiting": "waiting for the first dev check",
        "k_runs": "↑↓ select   Enter open   e evaluate a policy   Tab section   q quit",
        "eval_ask": "Evaluate on 10 dev episodes: 1 Reconciler · 2 Intern · 3 Alarmist · Esc cancel",
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
        "running": "идёт", "done": "завершено", "stopped": "остановлено", "error": "ошибка",
        "iteration": "итерация {i}/{n}",
        "chart": "Награда на отложенных dev-эпизодах", "l_dev": "награда dev", "l_train": "среднее популяции", "l_ref": "Сверщик",
        "best": "лучшая (dev)", "last": "последняя (dev)", "vs": "против Сверщика", "f1": "F1 (dev)", "fp": "ложных находок / эп.",
        "steps": "шагов / эп.", "elapsed": "прошло", "eta": "осталось", "episodes": "эпизодов",
        "k_train": "s стоп   Tab раздел   q выход", "k_train_done": "n новое обучение   Tab раздел   q выход",
        "no_train": "Обучений пока нет. Запустите на главной (клавиша 1).",
        "waiting": "ждём первую проверку на dev",
        "k_runs": "↑↓ выбор   Enter открыть   e оценить политику   Tab раздел   q выход",
        "eval_ask": "Оценка на 10 dev-эпизодах: 1 Сверщик · 2 Стажёр · 3 Паникёр · Esc отмена",
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
    },
}
TABS = ("home", "train", "runs", "settings")
MODELS = ("cem", "reinforce")
DATASETS = ("mixed", "simple", "interacting")
SIZES = {"fast": {"iterations": 12, "population": 8, "episodes_per_candidate": 2},
         "std": {"iterations": 30, "population": 16, "episodes_per_candidate": 4},
         "deep": {"iterations": 40, "population": 24, "episodes_per_candidate": 4}}
POLICIES = ("reconcile", "random", "flag_all")

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

    def glyph(self, i: int, j: int, t: float, lens: Tuple[float, float, float]) -> Tuple[str, str]:
        st = self.st
        cx, cy, r = lens
        inside = lambda a, b: math.hypot((a - cx) / 2, b - cy) < r
        if inside(i, j):
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

    def compose(self, line: str, j: int, n: int, w: int, t: float, lens: Tuple[float, float, float]) -> str:
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
SINGLE = {"\r": "enter", "\n": "enter", "\t": "tab", "\x1b": "esc", "\x03": "ctrl-c"}


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
        self.pick = {"model": 0, "data": 0, "size": 1}
        self.sel = 0
        self.ask_eval = False
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
            self._runs, self._runs_at = list_runs(self.base), time.monotonic()
        return self._runs

    def run(self, run_id: str) -> Optional[Dict[str, Any]]:
        at, r = self._run_cache.get(run_id, (0.0, None))
        if time.monotonic() - at > 0.5:
            r = read_run(run_id, self.base)
            self._run_cache[run_id] = (time.monotonic(), r)
        return r

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
        if self.ask_eval:
            self.ask_eval = False
            if k in ("1", "2", "3"):
                self.start_eval(POLICIES[int(k) - 1])
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
        names = ("model", "data", "size")
        opts = {"model": MODELS, "data": DATASETS, "size": tuple(SIZES)}
        if k == "up":
            self.field = (self.field - 1) % 4
        elif k == "down":
            self.field = (self.field + 1) % 4
        elif k in ("left", "right") and self.field < 3:
            f = names[self.field]
            self.pick[f] = (self.pick[f] + (1 if k == "right" else -1)) % len(opts[f])
        elif k == "enter":
            self.start_training()

    def key_train(self, k: str) -> None:
        r = self.current_training()
        if k == "s" and r and r.get("status") == "running":
            self.jobs.stop(r["id"])
        elif k == "n":
            self.tab, self.field = 0, 3

    def key_runs(self, k: str) -> None:
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
                self.train_id, self.tab = r["id"], 1

    def key_settings(self, k: str) -> None:
        if k in ("left", "right", "enter"):
            self.lang = "ru" if self.lang == "en" else "en"
            save_lang(self.lang)

    # ---- actions
    def start_training(self) -> None:
        body = {"method": MODELS[self.pick["model"]], "dataset": {"preset": DATASETS[self.pick["data"]]},
                **SIZES[tuple(SIZES)[self.pick["size"]]]}
        res = self.jobs.start_train(body)
        if res.get("ok"):
            self.train_id, self.tab, self.msg = res["run"], 1, ""
            self._runs_at = 0.0
        else:
            err = res.get("error") or {}
            self.msg, self.msg_at = (self.tx["busy"] if err.get("code") == "busy" else self.tx["failed"].format(msg=err.get("message", "?"))), time.monotonic()

    def start_eval(self, policy: str) -> None:
        res = self.jobs.start(policy, "dev")
        if res.get("ok"):
            self.msg, self.msg_at, self._runs_at, self.sel = self.tx["started"].format(id=res["run"]), time.monotonic(), 0.0, 0
        else:
            err = res.get("error") or {}
            self.msg, self.msg_at = (self.tx["busy"] if err.get("code") == "busy" else self.tx["failed"].format(msg=err.get("message", "?"))), time.monotonic()

    def current_training(self) -> Optional[Dict[str, Any]]:
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
            lines[2:h - 2] = [self.bg.compose(line, j, n, w, now, lens) for j, line in enumerate(lines[2:h - 2])]
        keys = {"home": "k_home", "train": "k_train", "runs": "k_runs", "settings": "k_settings"}[TABS[self.tab]]
        if TABS[self.tab] == "train":
            r = self.current_training()
            keys = "k_train" if r and r.get("status") == "running" else "k_train_done"
        if self.msg and not self.quitting and time.monotonic() - self.msg_at > 5:
            self.msg = ""
        note = self.msg or (tx["eval_ask"] if self.ask_eval else "")
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
            out += ["", "  " + st.B + tx["ready"] + st.R, "  " + st.D + tx["sub"] + st.R, ""]
        m = self.machine
        mline = tx["machine"].format(cpu=cores(m["cpu_count"], self.lang), ram=m["ram_gb"]) if m.get("cpu_count") and m.get("ram_gb") else tx["machine_q"]
        size_key = tuple(SIZES)[self.pick["size"]]
        sz = SIZES[size_key]
        rows = [
            ("model", tx[MODELS[self.pick["model"]]], tx[MODELS[self.pick["model"]] + "_d"]),
            ("data", tx[DATASETS[self.pick["data"]]], tx[DATASETS[self.pick["data"]] + "_d"]),
            ("size", tx[size_key], tx["size_d"].format(it=sz["iterations"], pop=sz["population"], ep=sz["episodes_per_candidate"],
                                                     total=sz["iterations"] * sz["population"] * sz["episodes_per_candidate"])),
        ]
        bw = min(w - 4, 92)
        wide = bw >= 88                                   # room for a hint next to every field
        body = []
        for i, (key, val, desc) in enumerate(rows):
            on = i == self.field
            sel = (st.INV + " ‹ " + val + " › " + st.R) if on else ("   " + val + "   ")
            body.append(pad((st.B + "▸ " + st.R if on else "  ") + pad(st.D + tx[key] + st.R, 9) + sel, 36) + (st.D + desc + st.R if wide else ""))
        body.append("" if wide else "  " + st.D + (rows[self.field][2] if self.field < 3 else "") + st.R)
        go = " ⏎ " + tx["start"] + " "
        body.append(pad(st.D + mline + st.R, bw - 4 - vlen(go) - 2) + ((st.INV + st.B + go + st.R) if self.field == 3 else st.B + go + st.R))
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
        out += ["", "  " + st.B + tx["recent"] + st.R]
        runs = self.runs()[: max(0, min(5, h - len(out) - 1))]
        if not runs:
            out.append("  " + st.D + tx["no_runs"] + st.R)
        for r in runs:
            out.append("  " + self.run_row(r, min(w - 4, 92)))
        return out

    def run_name(self, r: Dict[str, Any]) -> str:
        tx = self.tx
        if r.get("kind") == "training":
            return f"{tx['training']} · {'REINFORCE' if r.get('method') == 'reinforce' else 'CEM'}"
        return f"{tx['evaluation']} · {tx.get(r.get('agent') or '', r.get('agent') or '?')}"

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
        line = pad(left, max(0, w - vlen(right))) + right
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
        spin = "⣾⣽⣻⢿⡿⣟⣯⣷"[int((time.monotonic() - self.t0) * 10) % 8]
        title = f"{tx['training']} · {tx[cfg.get('method', 'cem')]} · {tx.get((cfg.get('dataset') or {}).get('preset', 'mixed'), '')}"
        state = (st.POS + spin + " " + tx["running"] + st.R) if status == "running" else \
            ((st.NEG if status == "error" else st.D) + tx.get(status, status) + st.R)
        right = f"{tx['iteration'].format(i=at, n=n)}  {state}"
        out = ["", "  " + pad(st.B + title + st.R, max(0, w - 4 - vlen(right))) + right, ""]

        dev = [(p["i"], p["dev"]["reward"]) for p in pts if p.get("dev")]
        trn = [(p["i"], p["train_mean"]) for p in pts if p.get("train_mean") is not None]
        ref = self.baseline.get("reconcile")
        side_w = 30 if w >= 90 else 0
        cw = max(20, w - 4 - side_w - (2 if side_w else 0))
        ch = max(5, min(16, h - 12))
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
        legend = f"{st.POS}━{st.R} {tx['l_dev']}   {st.D}━ {tx['l_train']}{st.R}" + (f"   {st.NEG}┄{st.R} {tx['l_ref']} {ref:+.2f}" if ref is not None else "")
        rows.append("       " + legend)
        left = box(tx["chart"], rows, cw, st)

        s = r.get("summary") or {}
        last_dev = next((p["dev"] for p in reversed(pts) if p.get("dev")), None)
        best = s.get("dev_best")
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
            (tx["episodes"], str(sum(p.get("episodes", 0) for p in pts))),
            (tx["elapsed"], fmt_time(elapsed, tx)),
            (tx["eta"], ("≈ " + fmt_time(eta, tx)) if eta is not None else "—"),
        ]
        if side_w:
            right_box = box(tx["train"], [pad(st.D + k + st.R, side_w - 4 - vlen(v)) + v for k, v in kv], side_w, st)
            right_box += box(tx["population"], self.population(cfg, at, status, side_w - 4), side_w, st)
            right_box += [""] * (len(left) - len(right_box))
            out += ["  " + a + "  " + b for a, b in zip(left, right_box)]
        else:
            out += ["  " + a for a in left] + ["  " + pad(st.D + k + st.R, 24) + v for k, v in kv]
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

    def population(self, cfg: Dict[str, Any], at: int, status: str, w: int) -> List[str]:
        """The CEM population in ASCII: every candidate of this iteration, the elite in blue. While training runs, a
        cursor walks through the candidates as they are evaluated."""
        st, tx = self.st, self.tx
        p = int(cfg.get("population") or 16)
        k = max(1, round(p * float(cfg.get("elite_frac") or 0.25)))
        per = max(4, (w - 1) // 2)
        t = time.monotonic() - self.t0
        cur = int(t * 6) % (p + 4) if status == "running" else p
        elite = set(sorted(range(p), key=lambda i: _h(i, at + 1))[:k])
        cells = []
        for i in range(p):
            if i < cur:
                cells.append(st.POS + st.B + "●" + st.R if i in elite else st.D + "○" + st.R)
            elif i == cur:
                cells.append(st.B + "⣾⣽⣻⢿⡿⣟⣯⣷"[int(t * 10) % 8] + st.R)
            else:
                cells.append(st.D + "·" + st.R)
        rows = [" ".join(cells[j:j + per]) for j in range(0, p, per)]
        method = cfg.get("method", "cem")
        rows.append(st.D + (tx["elite"].format(k=k, p=p) if method == "cem" else tx["samples"].format(p=p)) + st.R)
        return rows

    def draw_runs(self, w: int, h: int) -> List[str]:
        st, tx = self.st, self.tx
        runs = self.runs()
        out = [""]
        if not runs:
            return out + ["  " + st.D + tx["no_runs"] + st.R]
        self.sel = min(self.sel, len(runs) - 1)
        lw = min(60, max(36, w // 2 - 2)) if w >= 90 else w - 4
        top = max(0, self.sel - (h - 4) + 1)
        visible = runs[top: top + h - 3]
        left = [self.run_row(r, lw, top + i == self.sel) for i, r in enumerate(visible)]
        right: List[str] = []
        if w >= 90:
            right = self.run_detail(runs[self.sel], w - lw - 8)
        else:                                             # narrow: the details go under the list
            return out + ["  " + a for a in left] + [""] + ["  " + b for b in self.run_detail(runs[self.sel], w - 4)]
        for i in range(max(len(left), len(right))):
            a = left[i] if i < len(left) else ""
            b = right[i] if i < len(right) else ""
            out.append("  " + pad(a, lw) + "    " + b)
        return out

    def run_detail(self, r: Dict[str, Any], w: int) -> List[str]:
        st, tx = self.st, self.tx
        full = self.run(r["id"]) or r
        s = full.get("summary") or {}
        rows = [st.B + self.run_name(r) + st.R, st.D + r["id"] + st.R, ""]
        kv: List[Tuple[str, str]] = []
        if r.get("kind") == "training":
            cfg = full.get("config") or {}
            kv = [(tx["best"], st.val(s.get("dev_best"))), (tx["last"], st.val(s.get("dev_last"))),
                  (tx["data"], tx.get((cfg.get("dataset") or {}).get("preset", ""), "—")),
                  (tx["config"], f"{cfg.get('iterations', '?')} × {cfg.get('population', '?')} × {cfg.get('episodes_per_candidate', '?')}"),
                  (tx["seed"], str(cfg.get("seed", "—"))), (tx["episodes"], str(s.get("episodes", "—"))),
                  (tx["time"], fmt_time(s.get("seconds"), tx))]
            pts = [p["dev"]["reward"] for p in full.get("points") or [] if p.get("dev")]
            if pts:
                spark = "".join("▁▂▃▄▅▆▇█"[max(0, min(7, int((v + 1) / 2 * 7.99)))] for v in pts[-(w - 4):])
                kv.append(("dev", st.POS + spark + st.R))
            tail = ["", st.D + tx["open_hint"] + st.R]
        else:
            kv = [(tx["reward"], st.val(s.get("reward"))), (tx["precision"], f"{s['precision']:.2f}" if "precision" in s else "—"),
                  (tx["recall"], f"{s['recall']:.2f}" if "recall" in s else "—"), ("F1", f"{s['f1']:.2f}" if "f1" in s else "—"),
                  (tx["steps"], str(s.get("steps", "—"))), (tx["episodes"], f"{s.get('episodes_done', 0)}/{len(full.get('episodes') or [])}"),
                  (tx["split"], str(r.get("split") or "—")), (tx["time"], fmt_time(s.get("seconds"), tx))]
            rw = [(e.get("score") or {}).get("reward") for e in full.get("episodes") or []]
            if rw:
                kv.append(("", " ".join((st.POS + "▮" + st.R) if (v or 0) > 0 else (st.NEG + "▮" + st.R) if v is not None else st.D + "▯" + st.R for v in rw)))
            tail = []
        state = r.get("status") or ""
        rows.append(pad(st.D + tx["status"] + st.R, 22) + (st.NEG if state == "error" else "") + tx.get(state, state) + st.R)
        rows += [pad(st.D + k + st.R, 22) + v for k, v in kv] + tail
        return rows

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
