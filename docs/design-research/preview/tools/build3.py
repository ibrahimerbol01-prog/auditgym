"""Newcomer-first preview (v3): less data up front, details on demand.

Usage: python3 -I build3.py <repo_dir> <out_dir>
Reuses tokens, icons, data and helpers from build2.py (everything above its page template).
"""
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
src = (here / "build2.py").read_text()
ns = {"__file__": str(here / "build2.py")}
exec(compile(src[: src.index('v = data["versions"]')], "build2.py", "exec"), ns)  # tokens, icons, data, helpers
g = ns
e, I, ru, money, data, rep, submit, ps, recon, steps = (g["e"], g["I"], g["ru"], g["money"], g["data"], g["rep"],
                                                        g["submit"], g["ps"], g["recon"], g["steps"])
out = Path(sys.argv[2])

CSS = g["CSS"] + r"""
/* v3 additions: newcomer-first */
.stepper{display:flex;align-items:center;gap:10px;font-size:13px;color:var(--txt3);flex-wrap:wrap}
.stepper span{display:inline-flex;align-items:center;gap:6px}
.stepper .ok{color:var(--pos)}
.stepper .dot{width:18px;height:1px;background:var(--line2)}
.stepper .now{color:var(--txt)}
.lead{font-size:16px;color:var(--txt2);margin:0;max-width:62ch}
.head h1{font-size:34px;margin:10px 0 8px}
.summary{border:1px solid var(--line);border-radius:var(--r-l);background:var(--s1);overflow:hidden}
.summary>details+details{border-top:1px solid var(--line)}
.summary summary{list-style:none;display:grid;grid-template-columns:16px 1fr auto 16px;gap:12px;align-items:center;padding:14px 16px;cursor:pointer}
.summary summary::-webkit-details-marker{display:none}
.summary summary:hover{background:var(--soft)}
.summary .ok{color:var(--pos)}
.summary .s{font-size:15px}.summary .s small{display:block;font-size:13px;color:var(--txt3)}
.summary .a{font:13.5px var(--mono);white-space:nowrap}.summary .a span{color:var(--txt3)}
.summary .chev{color:var(--txt3);transition:transform var(--t) var(--ease)}
.summary details[open] .chev{transform:rotate(90deg)}
.more{padding:0 16px 14px 44px;font-size:13px;color:var(--txt3)}
.more code{font:12px var(--mono);color:var(--txt2)}
.more p{margin:4px 0}
.result{padding:22px 24px;border:1px solid var(--line);border-radius:var(--r-l);background:var(--s1)}
.result .big{font:300 40px/1.15 var(--serif);margin:0}
.result .big b{font-weight:300;color:var(--pos)}
.result p{margin:8px 0 0;color:var(--txt2);font-size:14.5px}
.result details{margin-top:14px;font-size:13px;color:var(--txt3)}
.result details summary{cursor:pointer;color:var(--txt2);width:max-content}
.result details p{font:12.5px var(--mono);color:var(--txt3)}
.next{display:flex;flex-wrap:wrap;gap:10px}
.next .btn{height:40px;padding:0 18px;font-size:14px}
.card{border:1px solid var(--line);border-radius:var(--r-l);background:var(--s1);padding:18px}
.kpi{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.kpi .v{font:300 34px/1.1 var(--serif)}
.kpi .k{font-size:13px;color:var(--txt3)}
.explain-chart{font-size:13.5px;color:var(--txt2);margin:10px 0 0}
.spec summary{cursor:pointer;font-size:14px;color:var(--txt2);list-style:none;display:flex;align-items:center;gap:8px}
.spec summary::-webkit-details-marker{display:none}
.spec[open] summary .chev{transform:rotate(90deg)}
.spec .chev{color:var(--txt3);transition:transform var(--t) var(--ease)}
.spec .inner{display:flex;flex-direction:column;gap:28px;margin-top:20px}
.side .simple a{font-size:14px}
@media (max-width:760px){.head h1{font-size:27px}.result .big{font-size:32px}.kpi .v{font-size:28px}.stepper{gap:6px;font-size:12px}.stepper .dot{width:8px}.summary summary{grid-template-columns:16px 1fr 16px;row-gap:4px}.summary .a{grid-column:2;grid-row:2}.summary .chev{grid-column:3;grid-row:1}.more{padding-left:44px}.who .hint-m{display:none}}
"""

PLAIN = {"duplicate_invoice": "Один счёт выставлен дважды", "payment_allocation": "Деньги пришли, но не записаны на счёт",
         "date_or_fx": "Сумма пересчитана не по тому курсу", "period_classification": "Запись попала не в тот месяц"}
WHY = {"duplicate_invoice": "Те же клиент, строки и период услуг — значит, это дубль.",
       "payment_allocation": "Платёж ссылается на счёт, но остался в нераспределённых деньгах.",
       "date_or_fx": "Политика требует курс на дату счёта, а в книге использован другой.",
       "period_classification": "Дата счёта в одном периоде, а проводка — в другом."}

rows = []
for f in submit["findings"]:
    rows.append(
        f'<details><summary><span class="ok">{I["check"]}</span><span class="s">{PLAIN[f["type"]]}<small>{WHY[f["type"]]}</small></span>'
        f'<span class="a num">{money(f["claimed_amount_minor"], f["currency"])} <span>{e(f["currency"])}</span></span><span class="chev">{I["chev"]}</span></summary>'
        f'<div class="more"><p>Записи: <code>{" · ".join(e(x) for x in f["affected_ids"])}</code></p>'
        f'<p>Доказательства: <code>{" · ".join(e(x) for x in f["evidence_ids"])}</code></p></div></details>')

n_steps = len(steps)
n_read = n_steps - 1
n_find = len(submit["findings"])


def curve_simple():
    import math
    W, H, L, R, T, B = 372, 190, 8, 110, 16, 22
    x = lambda i: L + (W - L - R) * i / 50
    y = lambda v: T + (H - T - B) * (1 - (v + 1) / 2)
    out = [f'<line x1="{L}" x2="{W - R}" y1="{y(-1):.1f}" y2="{y(-1):.1f}" stroke="var(--line2)"/>',
           f'<line x1="{L}" x2="{W - R}" y1="{y(recon):.1f}" y2="{y(recon):.1f}" stroke="var(--rule)" stroke-dasharray="3 3"/>',
           f'<text x="{W - R + 8}" y="{y(recon) + 4:.1f}">простая сверка</text>',
           f'<text x="{L}" y="{H - 4}">начало</text><text x="{W - R}" y="{H - 4}" text-anchor="end">50 итераций</text>']
    pts = [(i, -1 + 1.72 / (1 + math.exp(-(i - 18) / 5))) for i in range(0, 51, 2)]
    out.append(f'<polyline points="{" ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)}" fill="none" stroke="var(--data)" stroke-width="2.2" stroke-dasharray="5 4" stroke-linecap="round"/>')
    out.append(f'<text x="{W - R + 8}" y="{y(pts[-1][1]) + 14:.1f}" style="fill:var(--data)">агент*</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Пример: как растёт оценка обучаемого агента на новых эпизодах">{"".join(out)}</svg>'


v = data["versions"]
cmd = f"python -m auditgym.cli run-agent --agent reconcile --episode {data['episode']}"
PAGE = f"""<!doctype html><html lang="ru" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AuditGym · превью v3</title><style>{g["font_css"]}{CSS}</style></head><body>
<a class="skip" href="#thread">К эпизоду</a>
<header class="top">
  <button class="btn ghost icon menu-btn" aria-label="Меню">{I["menu"]}</button>
  <div class="brand">{I["logo"]}AuditGym</div>
  <nav aria-label="Разделы"><a href="#" aria-current="page">Эпизоды</a><a href="#">Как это работает</a><a href="#">Для специалистов</a></nav>
  <span class="sp"></span>
  <button class="btn ghost" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'" aria-label="Сменить тему">{I["theme"]}<span class="theme-txt">Тема</span></button>
</header>
<nav class="tabs" aria-label="Вид"><a href="#thread" aria-current="page">Эпизод</a><a href="#graphs">Итог</a></nav>
<div class="app">
  <aside class="side" aria-label="Навигация">
    <button class="btn primary">{I["plus"]}Новый эпизод</button>
    <div><h2>Сейчас</h2><ul class="simple"><li><a href="#" aria-current="true">Пример: агент проверяет книги</a></li></ul></div>
    <div><h2>Что дальше</h2><ul class="simple"><li><a href="#">Попробовать самому</a></li><li><a href="#">Компания без ошибок</a></li><li><a href="#">Все 10 учебных эпизодов</a></li></ul></div>
    <div class="foot">Все компании и деньги вымышлены.<br>Работает без интернета.</div>
  </aside>
  <main class="thread" id="thread">
    <div class="scroll"><div class="col">
      <div class="head">
        <div class="stepper" aria-label="Ход эпизода"><span><span class="ok">{I["check"]}</span>Задача</span><i class="dot"></i><span><span class="ok">{I["check"]}</span>Проверка</span><i class="dot"></i><span><span class="ok">{I["check"]}</span>Выводы</span><i class="dot"></i><span class="now"><span class="ok">{I["check"]}</span>Оценка</span></div>
        <h1>Агент нашёл {n_find} ошибок и доказал каждую</h1>
        <p class="lead">Мы дали ИИ-агенту книги вымышленной компании со спрятанными ошибками. Он может только читать записи, и на всё у него 100 шагов. Потом мы сверяем его выводы со скрытым ответом.</p>
      </div>

      <section class="turn" aria-label="Что сделал агент"><div class="who"><span class="av">1</span><b>Агент прочитал книги</b> · {n_read} шагов</div>
        <div class="list"><details class="call"><summary><span class="ok">{I["check"]}</span><span class="t">Счета, платежи, курсы валют и главная книга</span><span class="c">{sum(s.get("rows", 0) for s in steps[:-1])} записей</span><span class="chev">{I["chev"]}</span></summary>
          <div class="peek"><p class="sig">Каждый шаг — одна страница записей до 50 строк. Агент ничего не меняет, только читает.</p></div></details></div></section>

      <section class="turn" aria-label="Что нашёл агент"><div class="who"><span class="av">2</span><b>Агент нашёл {n_find} ошибок</b><span class="hint-m"> · нажмите, чтобы увидеть доказательства</span></div>
        <div class="summary">{"".join(rows)}</div></section>

      <section class="turn" aria-label="Оценка"><div class="who"><span class="av">3</span><b>Проверка</b></div>
        <div class="result"><p class="big"><b>{rep["tp"]} из {n_find}</b> подтверждены</p>
          <p>Ложных обвинений нет, ничего не пропущено. Оценка эпизода — <b>{ru(rep["reward"], 2)}</b> из 1: за доказанные ошибки она растёт, за ложные падает, а каждый шаг стоит чуть-чуть.</p>
          <details><summary>Как считается оценка</summary><p>2 · F1 − 1 − 0,002 · шаги = 2 · {ru(rep["f1"], 2)} − 1 − 0,002 · {rep["inspection_steps"]} = {ru(rep["reward"])}</p></details></div></section>

      <div class="next"><button class="btn primary">Попробовать самому</button><button class="btn">Другой эпизод</button></div>
    </div></div>
    <div class="composer"><div><div class="cbox"><div class="cin"><label class="vh" for="act">Ваш ход</label>
      <input id="act" placeholder="Ваш ход: например, «покажи счета»"><button class="send" aria-label="Отправить">{I["send"]}</button></div></div></div></div>
  </main>
  <aside class="graphs" id="graphs" aria-label="Итог и обучение">
    <section class="card"><div class="kpi">
      <div><div class="v num">{rep["tp"]} / {n_find}</div><div class="k">ошибок доказано</div></div>
      <div><div class="v num">{n_steps}</div><div class="k">шагов из 100</div></div></div>
      <div class="bar" style="margin-top:16px"><i style="width:{n_steps}%"></i></div></section>
    <section class="panel"><div class="ph"><h2>Как агент учится</h2></div>
      {curve_simple()}
      <p class="explain-chart">Линия растёт — агент всё лучше находит ошибки в компаниях, которых раньше не видел.</p>
      <p class="illus">* Пока пример формы: настоящая кривая появится после обучения (T10).</p></section>
    <details class="spec"><summary><span class="chev">{I["chev"]}</span>Подробности для специалистов</summary><div class="inner">
      <section class="panel"><div class="ph"><h2>Метрики эпизода</h2><span class="code">T-2</span></div>
        <div class="stats"><div class="stat"><div class="v num">{ru(rep["reward"])}</div><div class="k">награда</div></div>
          <div class="stat"><div class="v num">{ru(rep["f1"], 2)}</div><div class="k">F1</div></div><div class="stat"><div class="v num">{rep["tp"]}·{rep["fp"]}·{rep["fn"]}</div><div class="k">TP · FP · FN</div></div>
          <div class="stat"><div class="v num">{ru(rep["precision"], 2)}</div><div class="k">точность</div></div><div class="stat"><div class="v num">{ru(rep["recall"], 2)}</div><div class="k">полнота</div></div>
          <div class="stat"><div class="v num">—</div><div class="k">токены</div></div></div></section>
      <section class="panel"><div class="ph"><h2>Базовые политики</h2><span class="code">T-3</span></div>{g["pol_table"]()}</section>
      <section class="panel"><div class="ph"><h2>Повторить в терминале</h2></div><div class="repro"><code>{e(cmd)}</code></div></section>
    </div></details>
  </aside>
</div></body></html>"""
(out / "preview_v3.html").write_text(PAGE)
print("ok", len(PAGE) // 1024, "KB")
