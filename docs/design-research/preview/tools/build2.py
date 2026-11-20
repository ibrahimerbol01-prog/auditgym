"""Polished, neutral UI preview (v2). Usage: python3 -I build2.py <repo_dir> <out_dir>

Same real data as v1 (data.json from trajectories.jsonl and report.json); the training curve is still an explicit
illustration because train/curve.json does not exist yet.
"""
import base64
import html
import json
import math
import sys
from pathlib import Path

repo, out = Path(sys.argv[1]), Path(sys.argv[2])
data = json.loads((out / "data.json").read_text())
train_cfg = json.loads((repo / "configs" / "train.json").read_text())
fonts_dir = repo / "src" / "auditgym" / "ui" / "static" / "fonts"
e = html.escape

FONTS = [("Source Serif 4", 300, "source-serif-4-latin-300-normal"), ("Source Serif 4", 300, "source-serif-4-cyrillic-300-normal"),
         ("Source Serif 4", 400, "source-serif-4-latin-400-normal"), ("Source Serif 4", 400, "source-serif-4-cyrillic-400-normal"),
         ("Inter", 400, "inter-latin-400-normal"), ("Inter", 400, "inter-cyrillic-400-normal"),
         ("Inter", 500, "inter-latin-500-normal"), ("Inter", 500, "inter-cyrillic-500-normal"),
         ("Inter", 600, "inter-latin-600-normal"), ("Inter", 600, "inter-cyrillic-600-normal"),
         ("JetBrains Mono", 400, "jetbrains-mono-latin-400-normal"), ("JetBrains Mono", 400, "jetbrains-mono-cyrillic-400-normal")]
LATIN = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
CYR = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"
font_css = "\n".join(
    f'@font-face{{font-family:"{fam}";font-weight:{w};font-display:block;src:url(data:font/woff2;base64,'
    f'{base64.b64encode((fonts_dir / f"{f}.woff2").read_bytes()).decode()}) format("woff2");unicode-range:{CYR if "cyrillic" in f else LATIN}}}'
    for fam, w, f in FONTS)

CSS = r"""
/* Neutral tokens (proposal). Every text colour passes WCAG AA on --bg, --s1 and --s2 in both themes. */
:root{--t-fast:120ms;--t:200ms;--ease:cubic-bezier(.4,0,.2,1);
  --bg:#111113;--s1:#17171a;--s2:#1e1e22;--s3:#26262b;--line:#25252a;--line2:#33333a;--rule:#4a4a52;
  --txt:#ececef;--txt2:#b4b4ba;--txt3:#909097;--data:#9db3d4;--pos:#72c294;--neg:#ec8a78;
  --btn:#ececef;--btn-ink:#111113;--focus:#9db3d4;--soft:rgba(236,236,239,.05);
  --r:6px;--r-l:12px;--serif:"Source Serif 4",Georgia,serif;--body:"Inter",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Consolas,monospace}
[data-theme=light]{--bg:#f7f7f8;--s1:#ffffff;--s2:#f0f0f2;--s3:#e6e6e9;--line:#e4e4e7;--line2:#d4d4d8;--rule:#a1a1aa;
  --txt:#18181b;--txt2:#4f4f57;--txt3:#66666e;--data:#3d5a87;--pos:#2b744c;--neg:#ad3a28;
  --btn:#18181b;--btn-ink:#ffffff;--focus:#3d5a87;--soft:rgba(24,24,27,.04);color-scheme:light}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.6 var(--body);-webkit-font-smoothing:antialiased;font-feature-settings:"cv11","ss01"}
button,input{font:inherit;color:inherit}
svg{display:block}
.mono{font-family:var(--mono);font-size:12.5px;font-feature-settings:normal}
.num{font-variant-numeric:tabular-nums lining-nums}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px;border-radius:4px}
.skip{position:absolute;left:-9999px}.skip:focus{left:12px;top:8px;z-index:9;background:var(--s1);padding:6px 10px}
.vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.ic{width:16px;height:16px;flex:none}
/* buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:34px;padding:0 14px;border:1px solid var(--line2);border-radius:var(--r);
  background:transparent;cursor:pointer;font-size:13.5px;font-weight:500;color:var(--txt);transition:background var(--t-fast) var(--ease),border-color var(--t-fast) var(--ease)}
.btn:hover{background:var(--soft);border-color:var(--rule)}
.btn.primary{background:var(--btn);border-color:var(--btn);color:var(--btn-ink)}
.btn.primary:hover{opacity:.9}
.btn.ghost{border-color:transparent;color:var(--txt2)}
.btn.ghost:hover{color:var(--txt);background:var(--soft)}
.btn.icon{width:34px;padding:0}
/* top bar */
.top{display:flex;align-items:center;gap:24px;height:52px;padding:0 16px 0 20px;border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:5}
.brand{display:flex;align-items:center;gap:9px;font:500 16px var(--body);letter-spacing:-.01em}
.top nav{display:flex;gap:4px;font-size:14px}
.top nav a{color:var(--txt2);text-decoration:none;padding:6px 10px;border-radius:var(--r)}
.top nav a:hover{color:var(--txt);background:var(--soft)}
.top nav a[aria-current]{color:var(--txt);background:var(--s2)}
.sp{flex:1}
.ver{font:12px var(--mono);color:var(--txt3)}
.menu-btn{display:none}
/* panes */
.app{display:grid;grid-template-columns:252px minmax(0,1fr) 420px;min-height:calc(100vh - 52px)}
.side{border-right:1px solid var(--line);padding:16px 12px;display:flex;flex-direction:column;gap:22px}
.side h2{font:500 12px/1 var(--body);color:var(--txt3);margin:0 10px 6px}
.side ul{list-style:none;margin:0;padding:0}
.side li a{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:var(--r);color:var(--txt2);text-decoration:none;font-size:13.5px;transition:background var(--t-fast)}
.side li a:hover{background:var(--soft);color:var(--txt)}
.side li a[aria-current]{background:var(--s2);color:var(--txt)}
.side .tag{margin-left:auto;font-size:12px;color:var(--txt3)}
.side .foot{margin-top:auto;padding:0 10px;font:11.5px/1.6 var(--mono);color:var(--txt3)}
/* thread */
.thread{display:flex;flex-direction:column;min-width:0}
.scroll{flex:1;padding:40px 40px 32px;display:flex;justify-content:center}
.col{width:100%;max-width:720px;display:flex;flex-direction:column;gap:32px}
.eyebrow{font:12px var(--mono);color:var(--txt3)}
.head h1{font:400 30px/1.2 var(--serif);letter-spacing:-.01em;margin:6px 0 12px}
.meta{display:flex;flex-wrap:wrap;gap:6px 24px;font-size:13px;color:var(--txt3)}
.meta b{font-weight:500;color:var(--txt2)}
.note-box{display:flex;gap:12px;padding:14px 16px;background:var(--s1);border:1px solid var(--line);border-radius:var(--r-l);font-size:14px;color:var(--txt2)}
.note-box .ic{margin-top:3px;color:var(--txt3)}
.note-box b{color:var(--txt);font-weight:500}
.term{text-decoration:underline dotted var(--rule);text-underline-offset:3px;cursor:help}
.turn{display:flex;flex-direction:column;gap:10px}
.who{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--txt3)}
.who .av{width:22px;height:22px;border-radius:6px;background:var(--s2);border:1px solid var(--line2);display:grid;place-items:center;font:500 11px var(--mono);color:var(--txt2)}
.who b{color:var(--txt);font-weight:500}
.task{font-size:16px;line-height:1.6}
.types{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:13.5px;color:var(--txt2)}
.types span::before{content:"";display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--rule);margin:0 8px 2px 0}
.list{border:1px solid var(--line);border-radius:var(--r-l);overflow:hidden;background:var(--s1)}
.call+.call{border-top:1px solid var(--line)}
.call summary{list-style:none;display:grid;grid-template-columns:16px 1fr auto 16px;gap:12px;align-items:center;padding:11px 14px;cursor:pointer;transition:background var(--t-fast)}
.call summary::-webkit-details-marker{display:none}
.call summary:hover{background:var(--soft)}
.call .ok{color:var(--pos)}
.call .t{font-size:14px}.call .t span{color:var(--txt3)}
.call .c{font:12px var(--mono);color:var(--txt3);text-align:right}
.call .chev{color:var(--txt3);transition:transform var(--t) var(--ease)}
.call[open] .chev{transform:rotate(90deg)}
.peek{padding:2px 14px 14px 42px;overflow-x:auto}
.peek .sig{font:12px var(--mono);color:var(--txt3);margin:0 0 8px}
table.mini{border-collapse:collapse;font:12px var(--mono);width:100%}
table.mini th{font:500 12px var(--body);color:var(--txt3);text-align:left;padding:6px 12px 6px 0;border-bottom:1px solid var(--line2)}
table.mini td{padding:6px 12px 6px 0;border-bottom:1px solid var(--line);white-space:nowrap;color:var(--txt2)}
table.mini td.r,table.mini th.r{text-align:right}
.find{display:grid;grid-template-columns:16px 1fr auto;gap:4px 12px;padding:14px 16px}
.find+.find{border-top:1px solid var(--line)}
.find .ok{color:var(--pos);margin-top:4px}
.find .ty{font-weight:500}
.find .amt{font:13.5px var(--mono);text-align:right;white-space:nowrap}
.find .amt span{color:var(--txt3)}
.find .ids,.find .ev,.find .ex{grid-column:2/-1;font-size:13px}
.find .ids{font-family:var(--mono);font-size:12.5px;color:var(--txt2)}
.find .ev{color:var(--txt3)}.find .ev code{font:12px var(--mono);color:var(--txt2)}
.find .ex{color:var(--txt3)}
.verdict{display:grid;grid-template-columns:auto 1fr;gap:6px 28px;align-items:end;padding:20px 22px;border:1px solid var(--line);border-radius:var(--r-l);background:var(--s1)}
.verdict .k{font-size:12.5px;color:var(--txt3)}
.verdict .big{font:300 52px/1 var(--serif)}
.verdict .ticks{display:flex;align-items:center;gap:8px;font-size:14px;color:var(--txt2);padding-bottom:6px}
.verdict .ticks .ok{color:var(--pos)}
.verdict .formula{grid-column:1/-1;font:12.5px var(--mono);color:var(--txt3);padding-top:12px;margin-top:8px;border-top:1px solid var(--line)}
.repro{display:flex;align-items:center;gap:12px;font-size:13px;color:var(--txt3)}
.repro code{flex:1;min-width:0;overflow-x:auto;white-space:nowrap;font:12.5px var(--mono);color:var(--txt2);padding:7px 10px;background:var(--s1);border:1px solid var(--line);border-radius:var(--r)}
/* composer */
.composer{position:sticky;bottom:0;padding:12px 40px 20px;background:var(--bg);display:flex;justify-content:center}
.composer>div{width:100%;max-width:720px}
.cbox{width:100%;max-width:720px;border:1px solid var(--line2);border-radius:16px;background:var(--s1);padding:10px 10px 10px 16px;transition:border-color var(--t-fast)}
.cbox:focus-within{border-color:var(--rule)}
.cin{display:flex;align-items:center;gap:10px}
.cin input{flex:1;min-width:0;border:0;background:transparent;outline:none;font-size:15px;padding:6px 0}
.cin input::placeholder{color:var(--txt3)}
.send{width:34px;height:34px;border-radius:10px;border:0;background:var(--btn);color:var(--btn-ink);display:grid;place-items:center;cursor:pointer}
.crow{display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin-top:6px}
.crow .btn{height:28px;padding:0 10px;font-size:12.5px}
.hint{font-size:12px;color:var(--txt3);text-align:center;margin-top:8px}
/* graphs */
.graphs{border-left:1px solid var(--line);padding:28px 24px 40px;display:flex;flex-direction:column;gap:36px}
.panel .ph{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:4px}
.panel h2{font:500 15px var(--body);margin:0}
.panel .code{font:11.5px var(--mono);color:var(--txt3)}
.panel .sub{font-size:12.5px;color:var(--txt3);margin:0 0 14px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:20px 16px}
.stat .v{font:300 30px/1.1 var(--serif)}
.stat .k{font-size:12.5px;color:var(--txt3);margin-top:2px}
.steps{grid-column:1/-1}
.steps .row{display:flex;justify-content:space-between;font-size:12.5px;color:var(--txt3);margin-bottom:6px}
.steps .row b{font:500 12.5px var(--mono);color:var(--txt2)}
.bar{height:4px;background:var(--s3);border-radius:2px;overflow:hidden}.bar i{display:block;height:100%;background:var(--data);border-radius:2px}
.fine{font-size:12px;color:var(--txt3);margin:12px 0 0}
svg text{font:11px var(--mono);fill:var(--txt3)}
.illus{font-size:12px;color:var(--txt3);margin:10px 0 0}
table.pol{width:100%;border-collapse:collapse;font-size:13px}
table.pol th{font:500 12px var(--body);color:var(--txt3);text-align:right;padding:0 0 8px 8px;border-bottom:1px solid var(--line2)}
table.pol td{font:12.5px var(--mono);text-align:right;padding:8px 0 8px 8px;border-bottom:1px solid var(--line);color:var(--txt2)}
table.pol th:first-child,table.pol td:first-child{text-align:left;padding-left:0;font-family:var(--body);font-size:13px}
table.pol td.neg{color:var(--neg)}
.found{display:flex;flex-direction:column;gap:12px}
.found .row{display:grid;grid-template-columns:1fr auto;gap:6px 12px;font-size:13px;color:var(--txt2)}
.found .row b{font:500 12.5px var(--mono);color:var(--txt)}
.found .bar{grid-column:1/-1}
.tabs{display:none}
@media (max-width:1180px){.app{grid-template-columns:220px minmax(0,1fr)}.graphs{grid-column:1/-1;border-left:0;border-top:1px solid var(--line)}}
@media (max-width:760px){
  .top{gap:8px;padding:0 8px 0 4px}.top nav,.ver,.theme-txt{display:none}.menu-btn{display:inline-flex}
  .app{grid-template-columns:1fr}.side{display:none}
  .tabs{display:flex;gap:4px;padding:8px 12px;border-bottom:1px solid var(--line)}
  .tabs a{flex:1;text-align:center;padding:6px 0;border-radius:var(--r);color:var(--txt2);text-decoration:none;font-size:14px}
  .tabs a[aria-current]{background:var(--s2);color:var(--txt)}
  .scroll{padding:24px 16px}.col{gap:26px}.head h1{font-size:26px}
  .composer{padding:8px 12px 12px}.crow{display:none}.hint{display:none}
  .find{grid-template-columns:16px 1fr}.find .amt{grid-column:2;text-align:left}
  .verdict{grid-template-columns:1fr}.verdict .big{font-size:44px}
  .graphs{padding:24px 16px}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

I = {
    "check": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 4.8" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "chev": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "info": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.3" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 7.2v4M8 4.8v.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    "send": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V3.5M3.8 7.5L8 3.3l4.2 4.2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "copy": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="5.5" width="7.5" height="7.5" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M10.5 3H4.5A1.5 1.5 0 0 0 3 4.5v6" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>',
    "theme": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.8" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 2.2a5.8 5.8 0 0 1 0 11.6z" fill="currentColor"/></svg>',
    "menu": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.5 4.5h11M2.5 8h11M2.5 11.5h11" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    "plus": '<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    "logo": '<svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><rect x="1.5" y="1.5" width="17" height="17" rx="4" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M5.5 10.3l3 3 6-6.4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>',
}

TYPE_RU = {"duplicate_invoice": "Дубль счёта", "payment_allocation": "Нераспределённый платёж",
           "date_or_fx": "Неверная дата или курс", "period_classification": "Неверный отчётный период"}
TYPE_HELP = {"duplicate_invoice": "Один и тот же счёт выставлен дважды: тот же контрагент, строки и период услуг.",
             "payment_allocation": "Деньги пришли, но не привязаны к счёту полностью или частично.",
             "date_or_fx": "Сумма в книге посчитана по курсу не той даты, что требует политика.",
             "period_classification": "Проводка попала не в тот отчётный период."}
TABLE_RU = {"fx": ("A-4", "курсы валют"), "invoices": ("A-2", "счета"), "payments": ("A-3", "платежи"), "ledger": ("A-1", "главную книгу")}


def money(minor, ccy):
    exp = 0 if ccy == "JPY" else 2
    return f"{minor / 10 ** exp:,.{exp}f}".replace(",", " ").replace(".", ",")


def ru(x, d=3):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


steps = data["steps"]
submit = steps[-1]
rep = submit["report"]
groups = []
for s in steps[:-1]:
    if groups and groups[-1]["table"] == s["table"]:
        g = groups[-1]; g["pages"] += 1; g["rows"] += s["rows"]; g["last"] = s["step"]
    else:
        groups.append({"table": s["table"], "pages": 1, "rows": s["rows"], "first": s["step"], "last": s["step"], "sample": s["sample"]})


def peek(g):
    rows = g["sample"][:3]
    t = g["table"]
    if t == "fx":
        head, right, body = ["дата", "из", "в", "курс"], {3}, [[r["date"], r["source_currency"], r["target_currency"], r["rate"]] for r in rows]
    elif t == "invoices":
        head, right, body = ["счёт", "контрагент", "выставлен", "сумма"], {3}, [[r["invoice_id"], r["entity_id"], r["issued_at"][:10], f'{money(r["total_minor"], r["currency"])} {r["currency"]}'] for r in rows]
    elif t == "payments":
        head, right, body = ["платёж", "дата", "сумма", "счета"], {2}, [[r["payment_id"], r["timestamp"][:10], f'{money(r["amount_minor"], r["currency"])} {r["currency"]}', ", ".join(r["invoice_refs"] or ["null"])] for r in rows]
    else:
        head, right, body = ["строка", "счёт", "дебет", "кредит"], {2, 3}, [[r["row_id"], r["account"], money(r["debit_minor"], r["currency"]) if r["debit_minor"] else "", money(r["credit_minor"], r["currency"]) if r["credit_minor"] else ""] for r in rows]
    th = "".join(f'<th class="{"r" if i in right else ""}">{h}</th>' for i, h in enumerate(head))
    tb = "".join("<tr>" + "".join(f'<td class="{"r" if i in right else ""}">{e(str(c))}</td>' for i, c in enumerate(row)) + "</tr>" for row in body)
    sig = f'list_records("{t}", cursor, limit=50) × {g["pages"]}'
    return f'<div class="peek"><p class="sig">{sig}</p><table class="mini"><thead><tr>{th}</tr></thead><tbody>{tb}</tbody></table><p class="fine">Первые 3 строки из {g["rows"]}.</p></div>'


calls = []
for g in groups:
    code, noun = TABLE_RU[g["table"]]
    span = f'шаг {g["first"]}' if g["first"] == g["last"] else f'шаги {g["first"]}–{g["last"]}'
    calls.append(f'<details class="call"{" open" if g["table"] == "invoices" else ""}><summary><span class="ok">{I["check"]}</span>'
                 f'<span class="t">Прочитал {noun} <span>· {code}</span></span><span class="c">{g["rows"]} строк · {span}</span>'
                 f'<span class="chev">{I["chev"]}</span></summary>{peek(g)}</details>')

finds = []
for f in submit["findings"]:
    finds.append(f'<div class="find"><span class="ok">{I["check"]}</span><span class="ty"><span class="term" title="{e(TYPE_HELP[f["type"]])}">{TYPE_RU[f["type"]]}</span></span>'
                 f'<span class="amt num">{money(f["claimed_amount_minor"], f["currency"])} <span>{e(f["currency"])}</span></span>'
                 f'<span class="ids">{" · ".join(e(x) for x in f["affected_ids"])}</span>'
                 f'<span class="ev">Доказательства: <code>{" · ".join(e(x) for x in f["evidence_ids"])}</code></span>'
                 f'<span class="ex">{e(f["explanation"])}</span></div>')

ps = {p["policy"]: p for p in data["policy_summary"]}
recon = sum(ps["reconcile"][g] for g in ("clean", "mixed", "interacting")) / 3


def curve():
    W, H, L, R, T, B = 372, 214, 30, 104, 18, 24
    x = lambda i: L + (W - L - R) * i / 50
    y = lambda v: T + (H - T - B) * (1 - (v + 1) / 2)
    out = []
    for v in (-1, -0.5, 0, 0.5, 1):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--line)"/><text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{ru(v, 1)}</text>')
    for i in (0, 25, 50):
        out.append(f'<text x="{x(i):.1f}" y="{H - 6}" text-anchor="middle">{i}</text>')
    for v, name, dash in ((1, "oracle", "2 3"), (recon, "reconcile", ""), (-1, "random", "2 3")):
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--rule)" stroke-dasharray="{dash}"/>')
    labels = [(1, "oracle 1,0", -4), (recon, f"reconcile {ru(recon, 2)}", 12), (-1, "random −1,0", 4)]
    for v, lab, dy in labels:
        out.append(f'<text x="{W - R + 8}" y="{y(v) + dy:.1f}">{lab}</text>')
    pts = [(i, -1 + 1.72 / (1 + math.exp(-(i - 18) / 5))) for i in range(0, 51, 2)]
    out.append(f'<polyline points="{" ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)}" fill="none" stroke="var(--data)" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round"/>')
    out.append(f'<text x="{x(50) - 4:.1f}" y="{y(pts[-1][1]) + 16:.1f}" text-anchor="end" style="fill:var(--data)">dev*</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Пример формы кривой обучения на отложенных эпизодах и настоящие базовые линии">{"".join(out)}</svg>'


def pol_table():
    names = {"oracle": "oracle", "reconcile": "reconcile", "random": "random", "flag_all": "flag_all"}
    cell = lambda v: f'<td class="neg">({abs(v):.2f})</td>'.replace(".", ",") if v < 0 else f"<td>{v:.2f}</td>".replace(".", ",")
    rows = "".join(f"<tr><td>{names[p]}</td>" + "".join(cell(ps[p][g]) for g in ("clean", "mixed", "interacting")) + "</tr>" for p in names)
    return f'<table class="pol"><thead><tr><th>Политика</th><th>чистые</th><th>смешанные</th><th>взаимод.</th></tr></thead><tbody>{rows}</tbody></table>'


fa = data["failure_analysis"]["reconcile_rules_recall_by_type"]
found = "".join(f'<div class="row"><span>{TYPE_RU[t]}</span><b class="num">{v["found"]}/{v["issues"]}</b><div class="bar"><i style="width:{100 * v["found"] / v["issues"]:.0f}%"></i></div></div>' for t, v in fa.items())


def train_list():
    items = []
    for i, ep in enumerate(train_cfg["episodes"][:10], 1):
        c = ep["config"]
        tag = "чистая" if c.get("clean") else ("взаимод. " + "+".join(c["interactions"]) if c.get("interactions") else (f"{sum(c['errors'].values())} ош." if c.get("errors") else "смешанная"))
        items.append(f'<li><a href="#">train-{i:02d}<span class="tag">{tag}</span></a></li>')
    return "".join(items)


v = data["versions"]
n_steps = len(steps)
cmd = f"python -m auditgym.cli run-agent --agent reconcile --episode {data['episode']}"
PAGE = f"""<!doctype html><html lang="ru" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AuditGym · превью v2</title><style>{font_css}{CSS}</style></head><body>
<a class="skip" href="#thread">К ходу эпизода</a>
<header class="top">
  <button class="btn ghost icon menu-btn" aria-label="Меню">{I["menu"]}</button>
  <div class="brand">{I["logo"]}AuditGym</div>
  <nav aria-label="Разделы"><a href="#" aria-current="page">Эпизоды</a><a href="#">Отчёт</a><a href="#">Терминал</a></nav>
  <span class="sp"></span><span class="ver">v{e(v["env"])} · offline</span>
  <button class="btn ghost" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'" aria-label="Сменить тему">{I["theme"]}<span class="theme-txt">Тема</span></button>
</header>
<nav class="tabs" aria-label="Вид"><a href="#thread" aria-current="page">Эпизод</a><a href="#graphs">Графики</a></nav>
<div class="app">
  <aside class="side" aria-label="Эпизоды">
    <button class="btn primary">{I["plus"]}Новый эпизод</button>
    <div><h2>Открыт</h2><ul><li><a href="#" aria-current="true">{e(data["episode"][:15])}…<span class="tag">reconcile</span></a></li></ul></div>
    <div><h2>Эпизоды для обучения</h2><ul>{train_list()}</ul></div>
    <div><h2>Базовые политики</h2><ul><li><a href="#">reconcile<span class="tag">сверка</span></a></li><li><a href="#">random<span class="tag">случайный</span></a></li>
      <li><a href="#">flag_all<span class="tag">атака</span></a></li><li><a href="#">oracle<span class="tag">максимум</span></a></li></ul></div>
    <div class="foot">verify {ru(data["estimated_score"]["total"], 0)}/100<br>schema {e(v["schema"])} · config {e(v["config"])}</div>
  </aside>
  <main class="thread" id="thread">
    <div class="scroll"><div class="col">
      <div class="head"><div class="eyebrow">L-2 · ход эпизода</div><h1>Сверка книг вымышленной компании</h1>
        <div class="meta"><span>Эпизод <b class="mono">{e(data["episode"])}</b></span><span>Агент <b>reconcile</b></span><span>Режим <b>открытый</b></span></div></div>
      <div class="note-box">{I["info"]}<div><b>Как читать эту страницу.</b> ИИ-агент проверяет книги вымышленной компании. Каждая строка — один его шаг с инструментом только для чтения.
        В конце он сдаёт <span class="term" title="Вывод — тип ошибки, затронутые записи, сумма, валюта и доказательства.">выводы</span>, и оценщик сверяет их со скрытым эталоном. Награда — только за доказанное.</div></div>
      <section class="turn" aria-label="Задача"><div class="who"><span class="av">§</span><b>Задача</b> · первое наблюдение</div>
        <div class="task">Найдите ошибки в книгах за отчётный период и докажите каждую записями. Пять инструментов только для чтения, не больше 100 шагов.</div>
        <div class="types">{"".join(f'<span class="term" title="{e(TYPE_HELP[t])}">{TYPE_RU[t]}</span>' for t in TYPE_RU)}</div></section>
      <section class="turn" aria-label="Шаги агента"><div class="who"><span class="av">R</span><b>reconcile</b> · шаги 1–{n_steps - 1}</div><div class="list">{"".join(calls)}</div></section>
      <section class="turn" aria-label="Выводы"><div class="who"><span class="av">R</span><b>reconcile</b> · шаг {submit["step"]} · выводы <span class="mono">C-1</span></div><div class="list">{"".join(finds)}</div></section>
      <section class="turn" aria-label="Заключение оценщика"><div class="who"><span class="av">{I["check"]}</span><b>Оценщик</b> · заключение <span class="mono">C-2</span></div>
        <div class="verdict"><div><div class="k">Награда за эпизод</div><div class="big num">{ru(rep["reward"])}</div></div>
          <div class="ticks"><span class="ok">{I["check"]}</span>{rep["tp"]} из {len(submit["findings"])} выводов подтверждены · ложных {rep["fp"]} · пропущено {rep["fn"]}</div>
          <div class="formula">2 · F1 − 1 − 0,002 · шаги = 2 · {ru(rep["f1"], 2)} − 1 − 0,002 · {rep["inspection_steps"]} = {ru(rep["reward"])}</div></div></section>
      <div class="repro"><span>Повторить в терминале</span><code>{e(cmd)}</code><button class="btn icon" aria-label="Копировать команду">{I["copy"]}</button></div>
    </div></div>
    <div class="composer"><div><div class="cbox"><div class="cin"><label class="vh" for="act">Ваш ход</label>
        <input id="act" placeholder="Ваш ход: например, «открыть INV-W6-1720»"><button class="send" aria-label="Отправить">{I["send"]}</button></div>
      <div class="crow"><button class="btn ghost">Открыть запись</button><button class="btn ghost">Документ</button><button class="btn ghost">Калькулятор</button><button class="btn ghost">Сдать выводы</button><span class="sp"></span><button class="btn ghost">Настройки</button></div></div>
      <p class="hint">Каждое действие тратит один шаг из 100. Подсказок о правильности по ходу нет.</p></div></div>
  </main>
  <aside class="graphs" id="graphs" aria-label="Графики и телеметрия">
    <section class="panel"><div class="ph"><h2>Телеметрия прогона</h2><span class="code">T-2</span></div><p class="sub">Этот эпизод, после сдачи выводов</p>
      <div class="stats">
        <div class="stat"><div class="v num">{ru(rep["reward"])}</div><div class="k">награда</div></div>
        <div class="stat"><div class="v num">{ru(rep["f1"], 2)}</div><div class="k"><span class="term" title="Баланс точности и полноты. 1,00 — всё найдено, лишнего нет.">F1</span></div></div>
        <div class="stat"><div class="v num">{rep["tp"]}·{rep["fp"]}·{rep["fn"]}</div><div class="k">TP · FP · FN</div></div>
        <div class="stat"><div class="v num">{ru(rep["precision"], 2)}</div><div class="k"><span class="term" title="Какая доля выводов оказалась верной.">точность</span></div></div>
        <div class="stat"><div class="v num">{ru(rep["recall"], 2)}</div><div class="k"><span class="term" title="Какая доля скрытых ошибок найдена.">полнота</span></div></div>
        <div class="stat"><div class="v num">—</div><div class="k">токены</div></div>
        <div class="steps"><div class="row"><span>Шаги</span><b class="num">{n_steps} / 100</b></div><div class="bar"><i style="width:{n_steps}%"></i></div></div>
      </div><p class="fine">Токены — у скриптового агента их нет. Время агента не записано в trajectories.jsonl.</p></section>
    <section class="panel"><div class="ph"><h2>Кривая обучения</h2><span class="code">T-1</span></div><p class="sub">Награда на отложенных dev-эпизодах по итерациям</p>
      {curve()}<p class="illus">* Пунктир — пример формы. Настоящая кривая появится из <span class="mono">train/curve.json</span> (T10); базовые линии — из report.json.</p></section>
    <section class="panel"><div class="ph"><h2>Базовые политики</h2><span class="code">T-3</span></div><p class="sub">Средняя награда по группам эпизодов</p>{pol_table()}</section>
    <section class="panel"><div class="ph"><h2>Найдено по типам ошибок</h2><span class="code">T-4</span></div><p class="sub">reconcile · все эпизоды verify</p><div class="found">{found}</div></section>
  </aside>
</div></body></html>"""
(out / "preview_v2.html").write_text(PAGE)

# terminal mock-up, neutral palette
term = (out / "terminal.txt").read_text().rstrip("\n")
TERM = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>AuditGym terminal mock-up</title><style>{font_css}
body{{margin:0;background:#0c0c0e;color:#e4e4e7;font:14px/1.6 "JetBrains Mono",monospace}}
.win{{margin:24px;border:1px solid #2a2a30;border-radius:12px;overflow:hidden;background:#111113}}
.bar{{display:flex;gap:8px;align-items:center;padding:10px 14px;border-bottom:1px solid #2a2a30;color:#909097;font:12px Inter,sans-serif}}
.bar i{{width:10px;height:10px;border-radius:50%;background:#2e2e34}}
pre{{margin:0;padding:18px 20px;white-space:pre}} .p{{color:#9db3d4}} .ok{{color:#72c294}}
.note{{margin:0 24px 24px;color:#909097;font:13px Inter,sans-serif}}</style></head><body>
<div class="win"><div class="bar"><i></i><i></i><i></i><span style="margin-left:8px">auditgym — terminal (mock-up for specialists)</span></div>
<pre>{e(term).replace("$ ", '<span class="p">$ </span>').replace("✓", '<span class="ok">✓</span>')}</pre></div>
<p class="note">Mock-up: run-agent is proposed in task T12 and does not exist yet. Table numbers are real reconcile runs from trajectories.jsonl.</p></body></html>"""
(out / "terminal_v2.html").write_text(TERM)
print("ok", len(PAGE) // 1024, "KB")
