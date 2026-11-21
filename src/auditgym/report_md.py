"""A training run as a Markdown report: what was trained, how it learned on held-out dev, the final number on the
fresh test split next to the baselines, the measured failure analysis, honest limitations and how to reproduce it.
Written by the app's "Export report" (``Jobs.export``) to ``<run folder>/report.md``. Standard library only.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

TXT = {
    "en": {
        "title": "AuditGym training report", "run": "Run", "date": "Date", "env": "Environment version",
        "setup": "Setup", "method": "Method", "data": "Training episodes", "iterations": "Iterations",
        "population": "Candidates per iteration", "per_cand": "Episodes per candidate", "elite": "Elite fraction",
        "seed": "Seed", "episodes": "Training episodes played", "time": "Training time",
        "result": "Result", "split": "Episodes", "policy": "Policy", "reward": "Reward", "f1": "F1",
        "precision": "Precision", "recall": "Recall", "fp": "False findings / ep.", "steps": "Steps / ep.",
        "auditor": "Trained auditor (best on dev)", "reconcile": "Reconciler (hand-written rules)", "random": "Intern (random)",
        "dev": "dev: 10 held-out episodes, used to pick the best iteration",
        "test": "test: 20 fresh episodes (5 clean, 5 interacting, 10 with errors), never used for training or picking",
        "curve": "Learning curve (reward on dev)", "iteration": "Iteration", "pop_mean": "Population mean (training)",
        "seeds": "Same configuration on several seeds", "best_dev": "Best on dev", "on_test": "On test",
        "failures": "Failure analysis (test split)", "type": "Error type", "found": "Found", "missed": "Missed",
        "false": "False findings by claimed type", "near": "Near misses (right issue, rejected)", "none": "none",
        "kind": "By kind of episode", "clean": "clean companies", "interacting": "interacting errors", "errors": "ordinary errors",
        "limits": "Honest limitations",
        "l1": "The auditor is a small rule policy (20 parameters), not a neural network; training searches its parameters with {m} on CPU.",
        "l2": "Improvement is measured only on held-out episodes: dev picks the best iteration, test reports it once.",
        "l3": "The hand-written Reconciler is a strong baseline; matching it from a poor start is the result, not beating it.",
        "l4": "All companies and money are synthetic; this is a software exercise, not an audit opinion.",
        "repro": "Reproduce", "repro_t": "The same seed and configuration give the same curve:",
        "stopped": "The run was stopped before the last iteration.",
        "duplicate_invoice": "duplicate invoice", "payment_allocation": "payment allocation", "date_or_fx": "date or FX",
        "period_classification": "period classification", "invalid": "invalid",
        "mixed": "Mixed", "simple": "Simple errors",
    },
    "ru": {
        "title": "Отчёт об обучении AuditGym", "run": "Запуск", "date": "Дата", "env": "Версия среды",
        "setup": "Настройки", "method": "Метод", "data": "Эпизоды обучения", "iterations": "Итераций",
        "population": "Кандидатов на итерацию", "per_cand": "Эпизодов на кандидата", "elite": "Доля элиты",
        "seed": "Сид", "episodes": "Сыграно эпизодов обучения", "time": "Время обучения",
        "result": "Результат", "split": "Эпизоды", "policy": "Политика", "reward": "Награда", "f1": "F1",
        "precision": "Точность", "recall": "Полнота", "fp": "Ложных находок / эп.", "steps": "Шагов / эп.",
        "auditor": "Обученный аудитор (лучший на dev)", "reconcile": "Сверщик (ручные правила)", "random": "Стажёр (случайный)",
        "dev": "dev: 10 отложенных эпизодов, по ним выбирается лучшая итерация",
        "test": "test: 20 свежих эпизодов (5 чистых, 5 со взаимодействием, 10 с ошибками), не участвовали ни в обучении, ни в выборе",
        "curve": "Кривая обучения (награда на dev)", "iteration": "Итерация", "pop_mean": "Среднее популяции (обучение)",
        "seeds": "Та же конфигурация на нескольких сидах", "best_dev": "Лучшая на dev", "on_test": "На test",
        "failures": "Разбор ошибок (test)", "type": "Тип ошибки", "found": "Найдено", "missed": "Пропущено",
        "false": "Ложные находки по заявленному типу", "near": "Почти верные (та ошибка, но отклонены)", "none": "нет",
        "kind": "По видам эпизодов", "clean": "чистые компании", "interacting": "взаимодействующие ошибки", "errors": "обычные ошибки",
        "limits": "Честные ограничения",
        "l1": "Аудитор — небольшая политика правил (20 параметров), не нейросеть; обучение подбирает параметры методом {m} на CPU.",
        "l2": "Улучшение измеряется только на отложенных эпизодах: dev выбирает лучшую итерацию, test измеряет её один раз.",
        "l3": "Ручной Сверщик — сильная база; результат в том, чтобы дойти до его уровня с плохого старта, а не превзойти его.",
        "l4": "Все компании и деньги синтетические; это программная задача, а не аудиторское заключение.",
        "repro": "Воспроизвести", "repro_t": "Те же сид и конфигурация дают ту же кривую:",
        "stopped": "Запуск остановлен до последней итерации.",
        "duplicate_invoice": "дубль счёта", "payment_allocation": "разнесение платежа", "date_or_fx": "дата или курс",
        "period_classification": "отчётный период", "invalid": "некорректная",
        "mixed": "Смешанные", "simple": "Простые ошибки",
    },
}


def _f(v: Optional[float], d: int = 3, signed: bool = True) -> str:
    if v is None:
        return "—"
    return (f"{v:+.{d}f}" if signed else f"{v:.{d}f}").replace("-", "−")


def training_report(run: Dict[str, Any], group: List[Dict[str, Any]], lang: str = "en") -> str:
    t = TXT[lang]
    cfg = run.get("config") or {}
    s = run.get("summary") or {}
    method = "CEM" if cfg.get("method", "cem") == "cem" else "REINFORCE"
    out: List[str] = [f"# {t['title']}", ""]
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(run.get("started") or 0))
    out += [f"- {t['run']}: `{run.get('id')}`", f"- {t['date']}: {when}", f"- {t['env']}: {run.get('env_version', '—')}", ""]
    if run.get("status") == "stopped":
        out += [f"> {t['stopped']}", ""]
    out += [f"## {t['setup']}", "", "| | |", "|---|---|",
            f"| {t['method']} | {method} |", f"| {t['data']} | {t.get((cfg.get('dataset') or {}).get('preset', 'mixed'), '—')} |",
            f"| {t['iterations']} | {cfg.get('iterations')} |", f"| {t['population']} | {cfg.get('population')} |",
            f"| {t['per_cand']} | {cfg.get('episodes_per_candidate')} |", f"| {t['elite']} | {cfg.get('elite_frac')} |",
            f"| {t['seed']} | {cfg.get('seed')} |", f"| {t['episodes']} | {s.get('episodes')} |",
            f"| {t['time']} | {s.get('seconds')} s |", ""]

    best_dev = (run.get("best") or {}).get("dev") or {}
    test = run.get("test") or {}
    out += [f"## {t['result']}", "", f"- {t['dev']}", f"- {t['test']}", "",
            f"| {t['policy']} | {t['split']} | {t['reward']} | {t['f1']} | {t['precision']} | {t['recall']} | {t['fp']} | {t['steps']} |",
            "|---|---|---:|---:|---:|---:|---:|---:|"]

    def row(name: str, split: str, m: Dict[str, Any]) -> str:
        return (f"| {name} | {split} | {_f(m.get('reward'))} | {_f(m.get('f1'), 2, False)} | {_f(m.get('precision'), 2, False)} | "
                f"{_f(m.get('recall'), 2, False)} | {_f(m.get('fp'), 1, False)} | {_f(m.get('steps'), 1, False)} |")
    if best_dev:
        out.append(row(t["auditor"], "dev", best_dev))
    for key in ("auditor", "reconcile", "random"):
        if test.get(key):
            out.append(row(t[key], "test", test[key]))
    out.append("")

    pts = run.get("points") or []
    devs = [p for p in pts if p.get("dev")]
    if devs:
        out += [f"## {t['curve']}", "", f"| {t['iteration']} | dev {t['reward']} | dev F1 | {t['pop_mean']} |", "|---:|---:|---:|---:|"]
        out += [f"| {p['i'] + 1} | {_f(p['dev']['reward'])} | {_f(p['dev']['f1'], 2, False)} | {_f(p.get('train_mean'))} |" for p in devs]
        out.append("")

    if len(group) > 1:
        out += [f"## {t['seeds']}", "", f"| {t['seed']} | dev start | {t['best_dev']} | {t['on_test']} |", "|---:|---:|---:|---:|"]
        for g in sorted(group, key=lambda g: (g.get("config") or {}).get("seed", 0)):
            gs = g.get("summary") or {}
            out.append(f"| {(g.get('config') or {}).get('seed')} | {_f(gs.get('dev_start'))} | {_f(gs.get('dev_best'))} | "
                       f"{_f(((g.get('test') or {}).get('auditor') or {}).get('reward'))} |")
        out.append("")

    an = test.get("analysis")
    if an:
        out += [f"## {t['failures']}", "", f"| {t['type']} | {t['found']} | {t['missed']} |", "|---|---:|---:|"]
        for k, v in sorted(an.get("by_type", {}).items()):
            out.append(f"| {t.get(k, k)} | {v['found']} / {v['issues']} | {v['issues'] - v['found']} |")
        fb = an.get("false_by_type") or {}
        out += ["", f"**{t['false']}:** " + (", ".join(f"{t.get(k, k)} {n}" for k, n in sorted(fb.items())) or t["none"]), ""]
        bk = an.get("by_kind") or {}
        if bk:
            out += [f"**{t['kind']}:** " + ", ".join(f"{t.get(k, k)} {_f(v['reward'])} ({v['episodes']})" for k, v in sorted(bk.items())), ""]

    out += [f"## {t['limits']}", "", f"- {t['l1'].format(m=method)}", f"- {t['l2']}", f"- {t['l3']}", f"- {t['l4']}", ""]
    out += [f"## {t['repro']}", "", t["repro_t"], "", "```",
            f"python train/learn_rules.py --method {cfg.get('method', 'cem')} --seed {cfg.get('seed', 1)} --iterations {cfg.get('iterations')} "
            f"--population {cfg.get('population')} --episodes {cfg.get('episodes_per_candidate')} "
            f"--preset {(cfg.get('dataset') or {}).get('preset', 'mixed')} --eval-every {cfg.get('eval_every', 2)}", "```", ""]
    return "\n".join(out)
