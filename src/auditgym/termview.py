"""Terminal view of a harness run (design option C): a live trace of tool calls, then a score card.

On a real terminal it keeps a rolling window of the last steps and redraws it in place (ANSI escapes, no
curses); each episode collapses to one result line. Piped output, ``--plain`` or ``NO_COLOR`` get plain
lines: every step, no escapes, so logs and CI stay readable.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional

TABLES = {"fx": "курсы", "invoices": "счета", "payments": "платежи", "ledger": "главная книга"}
WINDOW = 8
STATUS = {"done": "завершён", "stopped": "остановлен", "error": "ошибка", "running": "идёт"}


def bar(v: float, n: int) -> str:
    """Reward in [-1, 1] as a bar of n cells: full blocks for the positive part, light shade for the rest."""
    k = max(0, min(n, round((v + 1) / 2 * n)))
    return "█" * k + "░" * (n - k)


def plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural: 1 эпизод, 2 эпизода, 5 эпизодов."""
    k = n % 100
    word = many if 11 <= k <= 14 else one if k % 10 == 1 else few if 2 <= k % 10 <= 4 else many
    return f"{n} {word}"


def fmt(v: Optional[float]) -> str:
    if v is None:
        return "  —  "
    v = round(v, 2) + 0.0  # no "−0.00"
    return ("−" if v < 0 else " ") + f"{abs(v):.2f}"


class TermView:
    def __init__(self, out=None, plain: bool = False) -> None:
        self.out = out or sys.stdout
        tty = hasattr(self.out, "isatty") and self.out.isatty()
        self.live = tty and not plain and not os.environ.get("NO_COLOR") and os.environ.get("TERM") != "dumb"
        if self.live and os.name == "nt":
            os.system("")  # enables ANSI escape processing in the Windows console
        self.width = min(shutil.get_terminal_size((100, 30)).columns, 110)
        self.window: List[str] = []
        self.drawn = 0
        self.total = 0
        self.compare: Dict[str, float] = {}

    # --- styling
    def c(self, code: str, s: str) -> str:
        return f"\x1b[{code}m{s}\x1b[0m" if self.live else s

    def dim(self, s: str) -> str:
        return self.c("2", s)

    def w(self, s: str = "") -> None:
        self.out.write(s + "\n")
        self.out.flush()

    def _clear_window(self) -> None:
        if self.live and self.drawn:
            self.out.write(f"\x1b[{self.drawn}F\x1b[J")
            self.drawn = 0

    def _draw_window(self, status: str) -> None:
        self._clear_window()
        lines = self.window[-WINDOW:] + [status]
        for ln in lines:
            self.w(ln)
        self.drawn = len(lines)

    # --- events from harness.run_split
    def __call__(self, e: Dict[str, Any]) -> None:
        getattr(self, "on_" + e["type"], lambda _e: None)(e)

    def on_run_start(self, e) -> None:
        r = e["run"]
        self.total = len(r["episodes"])
        self.w(self.c("1", "AUDITGYM") + self.dim(" ▸ run-agent ▸ ") + r["agent"] + self.dim(" ▸ ") + r["split"]
               + self.dim(" [закрытый режим]") + self.dim(f"   env {r['env_version']}"))
        self.w(self.dim(f"запуск {r['id']} · {plural(self.total, 'эпизод', 'эпизода', 'эпизодов')} · бюджет 100 шагов · агент не видит награду"))
        self.w()

    def on_episode_start(self, e) -> None:
        ep = e["episode"]
        self.window = []
        self.head = f"[{e['index'] + 1:>2}/{self.total}] #{ep['seed']} {ep['label']:<12} {ep.get('episode_id', '')}"
        if not self.live:
            self.w(self.head)
        if self.live:
            self._draw_window(self.dim("  начинаем…"))

    def on_step(self, e) -> None:
        a = e.get("args") or {}
        if e["tool"] == "submit":
            what = f"{a.get('findings')} находок" if a.get("findings") is not None else "неверная структура"
            res = "отправлено"
        elif e["tool"] == "list_records":
            what = f"{TABLES.get(a.get('table'), a.get('table'))} · {'далее' if a.get('cursor') else 'начало'}"
            res = f"{e['rows']} строк" if e["ok"] and e["rows"] is not None else (e["error"] or "")
        else:
            what = " ".join(f"{k}={v}" for k, v in a.items())[:40]
            res = "ок" if e["ok"] else (e["error"] or "")
        if e.get("truncated"):
            res = "бюджет исчерпан"
        tool = self.c("36" if e["tool"] != "submit" else "33", f"{str(e['tool'])[:14]:<14}")
        if not e["ok"] and not e.get("truncated"):
            res = self.c("31", res)
        num = self.dim("#%02d" % e["n"])
        line = f"  {num} {tool} {what:<34.34} {res:>16}  {self.dim('осталось ' + str(e['left']))}"
        if self.live:
            self.window.append(line)
            left = e["left"] if isinstance(e["left"], int) else 0
            status = self.dim("  " + self.head + "  бюджет ") + self.c("32", "█" * (left // 5)) + self.dim("░" * (20 - left // 5))
            self._draw_window(status)
        else:
            self.w(line)

    def on_episode_end(self, e) -> None:
        ep, s = e["episode"], e["episode"]["score"]
        self._clear_window()
        r = s.get("reward", 0.0)
        mark = self.c("32", "✓") if r > 0 else self.c("31", "✗")
        colour = "32" if r > 0.5 else ("33" if r > 0 else "31")
        self.w(f"{mark} {e['index'] + 1:>2}/{self.total} #{ep['seed']} {ep['label']:<12} {self.c(colour, bar(r, 20))} "
               f"{fmt(r)}  F1 {s.get('f1', 0):.2f}  TP {s.get('tp', 0)} FP {s.get('fp', 0)} FN {s.get('fn', 0)}  "
               + self.dim(f"{plural(ep['steps'], 'шаг', 'шага', 'шагов')} · {ep['seconds']:.2f} с"))

    def on_run_end(self, e) -> None:
        self._clear_window()
        r, s = e["run"], e["run"]["summary"]
        self.w()
        m = len(r["episodes"])
        gen = "эпизода" if m % 10 == 1 and m % 100 != 11 else "эпизодов"  # "из 1 эпизода", "из 10 эпизодов"
        self.w(self.c("1", "ИТОГ") + self.dim(f"  {r['agent']} на {r['split']} · {s.get('episodes_done', 0)} из {m} {gen} · {STATUS.get(r['status'], r['status'])}"))
        if r.get("error"):
            self.w(self.c("31", "ошибка: " + r["error"]))
        if s.get("not_scored"):
            self.w(self.c("31", f"  {plural(s['not_scored'], 'эпизод', 'эпизода', 'эпизодов')} без оценки находок: неверная структура ответа или исчерпан бюджет"))
        if s.get("episodes_done"):
            self.w(f"  награда {self.c('1', fmt(s['reward']).strip())} · точность {s['precision']:.2f} · полнота {s['recall']:.2f}"
                   f" · F1 {s['f1']:.2f} · ложных {s['fp']} · шагов {s['steps']:.1f} · {s['seconds']:.1f} с")
            rows = [(r["agent"] + " (этот запуск)", s["reward"])] + [(k, v) for k, v in self.compare.items() if k != r["agent"]]
            if len(rows) > 1:
                self.w(self.dim("  сравнение со средними из report.json:"))
                for name, v in sorted(rows, key=lambda x: -x[1]):
                    self.w(f"    {name:<26} {self.c('32' if v > 0 else '31', bar(v, 24))} {fmt(v)}")
        self.w(self.dim(f"  сохранено: {self.saved}"))
        app = "приложение AuditGym" if os.environ.get("AUDITGYM_DATA") else "python -m auditgym.cli ui"  # packaged build or checkout
        self.w(self.dim(f"  открыть в приложении: {app} → «Запуски»"))


def baseline_means(report_path: str) -> Dict[str, float]:
    """Mean reward per policy from report.json (the numbers the report page shows)."""
    try:
        with open(report_path, encoding="utf-8") as fh:
            rows = json.load(fh).get("policy_summary", [])
    except (OSError, ValueError):
        return {}
    out = {}
    for row in rows:
        vals = [v for k, v in row.items() if k != "policy" and isinstance(v, (int, float))]
        if vals:
            out[row["policy"]] = round(sum(vals) / len(vals), 3)
    return out
