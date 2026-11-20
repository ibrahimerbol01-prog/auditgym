"""Build a self-contained UI preview (chat thread + graphs sidebar) and a terminal mock-up.

Usage: python3 -I build.py <repo_dir> <out_dir>
All numbers come from the repo (trajectories.jsonl, report.json, configs/train.json) via data.json,
except the training curve, which is drawn as an explicitly labelled illustration (train/curve.json does not exist yet).
"""
import base64
import html
import json
import sys
from pathlib import Path

repo, out = Path(sys.argv[1]), Path(sys.argv[2])
data = json.loads((out / "data.json").read_text())
train_cfg = json.loads((repo / "configs" / "train.json").read_text())
fonts_dir = repo / "src" / "auditgym" / "ui" / "static" / "fonts"

FONTS = [
    ("Source Serif 4", 300, "source-serif-4-latin-300-normal"), ("Source Serif 4", 300, "source-serif-4-cyrillic-300-normal"),
    ("Source Serif 4", 400, "source-serif-4-latin-400-normal"), ("Source Serif 4", 400, "source-serif-4-cyrillic-400-normal"),
    ("Inter", 400, "inter-latin-400-normal"), ("Inter", 400, "inter-cyrillic-400-normal"),
    ("Inter", 500, "inter-latin-500-normal"), ("Inter", 500, "inter-cyrillic-500-normal"),
    ("Inter", 600, "inter-latin-600-normal"), ("Inter", 600, "inter-cyrillic-600-normal"),
    ("JetBrains Mono", 400, "jetbrains-mono-latin-400-normal"), ("JetBrains Mono", 400, "jetbrains-mono-cyrillic-400-normal"),
]
LATIN = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
CYR = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"
font_css = []
for fam, w, f in FONTS:
    b64 = base64.b64encode((fonts_dir / f"{f}.woff2").read_bytes()).decode()
    rng = CYR if "cyrillic" in f else LATIN
    font_css.append(f'@font-face{{font-family:"{fam}";font-weight:{w};font-display:block;src:url(data:font/woff2;base64,{b64}) format("woff2");unicode-range:{rng}}}')
font_css = "\n".join(font_css)

# Tokens copied from src/auditgym/ui/static/style.css (both themes).
TOKENS = """
:root{--t-fast:120ms;--t:200ms;
  --bg:#131210;--s1:#191816;--s2:#1f1e1b;--s3:#282622;--deep:#0f0e0c;
  --line:#2c2a26;--line2:#3d3a34;--rule:#5a554c;
  --txt:#efe9dc;--txt2:#aea797;--txt3:#958d7f;
  --gold:#cfb07a;--gold2:#e4cf9f;--gold-ink:#16120a;
  --pos:#79c39c;--neg:#f2826f;--info:#9fb2c8;
  --gold-soft:rgba(207,176,122,.11);--gold-line:rgba(207,176,122,.42);
  --pos-soft:rgba(121,195,156,.12);--neg-soft:rgba(242,130,111,.12);
  --hair:rgba(239,233,220,.05);--hair2:rgba(239,233,220,.09);
  --r:3px;--r-l:4px;
  --serif:"Source Serif 4",Georgia,serif;--body:"Inter",system-ui,sans-serif;--mono:"JetBrains Mono",ui-monospace,Consolas,monospace}
[data-theme=light]{
  --bg:#f1ece1;--s1:#faf7f0;--s2:#ece6d9;--s3:#e3dccd;--deep:#f5f1e8;
  --line:#ddd5c5;--line2:#c9bfac;--rule:#8f8574;
  --txt:#1d1a15;--txt2:#4b453b;--txt3:#5f584c;
  --gold:#6a4c14;--gold2:#5a400f;--gold-ink:#fdfaf3;
  --pos:#2c6a49;--neg:#a8321f;--info:#3d5470;
  --gold-soft:rgba(106,76,20,.08);--gold-line:rgba(106,76,20,.35);
  --pos-soft:rgba(44,106,73,.09);--neg-soft:rgba(168,50,31,.08);
  --hair:rgba(29,26,21,.035);--hair2:rgba(29,26,21,.07);color-scheme:light}
"""

CSS = TOKENS + r"""
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--txt);font-family:var(--body);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased}
button,input{font:inherit;color:inherit}
.mono{font-family:var(--mono);font-size:13px}
.num{font-variant-numeric:tabular-nums lining-nums}
.serif{font-family:var(--serif)}
a{color:var(--gold);text-underline-offset:3px}
:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.skip{position:absolute;left:-9999px}.skip:focus{left:12px;top:8px;z-index:9;background:var(--s1);padding:6px 10px}
/* top bar */
.top{display:flex;align-items:center;gap:28px;height:56px;padding:0 20px;border-bottom:1px solid var(--line);background:var(--bg);position:sticky;top:0;z-index:5}
.brand{display:flex;align-items:center;gap:10px;font-family:var(--serif);font-size:20px}
.brand svg{width:22px;height:22px}
.top nav{display:flex;gap:22px;font-size:14px;color:var(--txt2)}
.top nav a{color:var(--txt2);text-decoration:none;padding:17px 0;border-bottom:2px solid transparent}
.top nav a[aria-current]{color:var(--txt);border-color:var(--gold)}
.top .sp{flex:1}
.ver{font-family:var(--mono);font-size:12px;color:var(--txt3)}
.btn{display:inline-flex;align-items:center;gap:8px;height:34px;padding:0 14px;border:1px solid var(--line2);border-radius:var(--r);background:transparent;cursor:pointer;font-size:13.5px;transition:border-color var(--t-fast),background var(--t-fast)}
.btn:hover{border-color:var(--rule)}
.btn.primary{background:var(--gold);border-color:var(--gold);color:var(--gold-ink);font-weight:600}
.btn.primary:hover{background:var(--gold2)}
.menu-btn{display:none}
/* three panes */
.app{display:grid;grid-template-columns:248px minmax(0,1fr) 440px;min-height:calc(100vh - 56px)}
.side{border-right:1px solid var(--line);padding:16px 12px;display:flex;flex-direction:column;gap:18px;background:var(--bg)}
.side h2{font:500 12px/1 var(--body);color:var(--txt3);margin:0 8px 8px}
.side ul{list-style:none;margin:0;padding:0}
.side li a{display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:var(--r);color:var(--txt2);text-decoration:none;font-size:13.5px}
.side li a:hover{background:var(--hair2);color:var(--txt)}
.side li a[aria-current]{background:var(--s2);color:var(--txt)}
.side li .tag{margin-left:auto;font-size:11.5px;color:var(--txt3)}
.side .foot{margin-top:auto;font-family:var(--mono);font-size:11.5px;color:var(--txt3);padding:0 8px}
/* thread */
.thread{display:flex;flex-direction:column;min-width:0}
.scroll{flex:1;padding:28px 32px 24px;display:flex;flex-direction:column;align-items:center}
.col{width:100%;max-width:760px;display:flex;flex-direction:column;gap:22px}
.wp{display:flex;gap:14px;align-items:flex-start;padding-bottom:16px;border-bottom:1px solid var(--line)}
.ref{flex:none;display:inline-flex;flex-direction:column;align-items:center;justify-content:center;min-width:42px;height:42px;border:1px solid var(--gold-line);border-radius:var(--r);color:var(--gold);font:600 12.5px/1.1 var(--mono)}
.ref small{font-size:9px;color:var(--txt3);font-weight:400}
.wp h1{font:400 26px/1.2 var(--serif);margin:0 0 4px}
.wp .meta{font-size:12.5px;color:var(--txt2);display:flex;flex-wrap:wrap;gap:4px 16px}
.wp .meta b{font-weight:500;color:var(--txt);font-family:var(--mono);font-size:12px}
.explain{border:1px solid var(--line);border-left:2px solid var(--gold);border-radius:var(--r);padding:12px 14px;background:var(--s1);font-size:14px;color:var(--txt2)}
.explain strong{color:var(--txt);font-weight:600}
.term{border-bottom:1px dotted var(--txt3);cursor:help}
.msg{display:flex;gap:12px}
.who{flex:none;width:28px;height:28px;border-radius:var(--r);border:1px solid var(--line2);display:grid;place-items:center;font:600 12px var(--mono);color:var(--txt2)}
.who.agent{border-color:var(--gold-line);color:var(--gold)}
.body{flex:1;min-width:0}
.name{font-size:12.5px;color:var(--txt3);margin-bottom:6px}
.name b{color:var(--txt2);font-weight:500}
.task{font-size:15px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.chip{font-size:12.5px;padding:3px 9px;border:1px solid var(--line2);border-radius:var(--r);color:var(--txt2)}
.calls{border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.call{border-top:1px solid var(--line)}
.call:first-child{border-top:0}
.call summary{list-style:none;display:grid;grid-template-columns:18px 1fr auto;gap:10px;align-items:center;padding:9px 12px;cursor:pointer;font-size:14px}
.call summary::-webkit-details-marker{display:none}
.call summary:hover{background:var(--hair)}
.call summary .chev{color:var(--txt3);transition:transform var(--t)}
.call[open] summary .chev{transform:rotate(90deg)}
.call .what b{font-weight:500}
.call .sig{display:block;font-family:var(--mono);font-size:12px;color:var(--txt3)}
.call .cnt{font-family:var(--mono);font-size:12px;color:var(--txt3);text-align:right}
.peek{padding:4px 12px 12px 40px;overflow-x:auto}
table.mini{border-collapse:collapse;font-family:var(--mono);font-size:12px;width:100%}
table.mini th{font:500 11.5px var(--body);color:var(--txt3);text-align:left;padding:6px 10px 6px 0;border-bottom:1px solid var(--rule)}
table.mini td{padding:5px 10px 5px 0;border-bottom:1px solid var(--line);white-space:nowrap}
table.mini td.r{text-align:right}
.findings{display:flex;flex-direction:column;gap:8px}
.f{display:grid;grid-template-columns:22px 1fr auto;gap:10px;padding:12px 14px;border:1px solid var(--line);border-radius:var(--r);background:var(--s1)}
.tm{width:18px;height:18px;flex:none}.f .tm{color:var(--pos);margin-top:2px}
.f .ty{font-weight:600;font-size:14px}
.f .ids{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}
.idc{font-family:var(--mono);font-size:12px;padding:1px 7px;border:1px solid var(--line2);border-radius:var(--r);color:var(--txt)}
.idc.ev{color:var(--txt2);border-style:dashed}
.f .ex{font-size:13px;color:var(--txt2);font-style:italic}
.f .amt{font-family:var(--mono);font-size:14px;text-align:right;white-space:nowrap}
.f .amt span{color:var(--txt3);font-size:12px}
.lbl{font-size:11.5px;color:var(--txt3)}
.verdict{border:1px solid var(--gold-line);border-radius:var(--r);padding:16px 18px;background:var(--gold-soft);display:grid;grid-template-columns:1fr auto;gap:8px 18px;align-items:end}
.verdict .big{font:300 46px/1 var(--serif)}
.verdict .formula{font-family:var(--mono);font-size:12.5px;color:var(--txt2);grid-column:1/-1;border-top:1px solid var(--gold-line);padding-top:10px}
.ticks{display:flex;gap:10px;align-items:center;color:var(--pos);font-size:13px}
.bridge{display:flex;align-items:center;gap:10px;border:1px dashed var(--line2);border-radius:var(--r);padding:10px 12px;font-size:13px;color:var(--txt2)}
.bridge code{flex:1;min-width:0;overflow-x:auto;white-space:nowrap;font-family:var(--mono);font-size:12.5px;color:var(--txt)}
.composer{position:sticky;bottom:0;padding:12px 32px 18px;background:var(--bg);border-top:1px solid var(--line);display:flex;justify-content:center}
.cbox{width:100%;max-width:760px;border:1px solid var(--line2);border-radius:var(--r-l);background:var(--s1);padding:10px 12px}
.cbox label{display:block;font-size:12px;color:var(--txt3);margin-bottom:4px}
.cbox input{width:100%;border:0;background:transparent;outline:none;font-size:15px;padding:4px 0}
.crow{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:8px}
.crow .sp{flex:1}
.act{font-size:12.5px;height:28px;padding:0 10px;border:1px solid var(--line2);border-radius:var(--r);background:transparent;cursor:pointer;color:var(--txt2)}
.act:hover{border-color:var(--rule);color:var(--txt)}
.adv{font-size:12.5px;color:var(--txt3)}
/* graphs sidebar */
.graphs{border-left:1px solid var(--line);padding:20px 20px 28px;display:flex;flex-direction:column;gap:22px;background:var(--deep)}
.panel h2{display:flex;align-items:center;gap:10px;font:400 18px/1.2 var(--serif);margin:0 0 4px}
.panel h2 .code{font:600 11.5px var(--mono);color:var(--gold);border:1px solid var(--gold-line);border-radius:var(--r);padding:2px 6px}
.panel .sub{font-size:12.5px;color:var(--txt3);margin:0 0 12px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.stat{background:var(--s1);padding:10px 12px}
.stat .v{font:300 28px/1.1 var(--serif)}
.stat .k{font-size:12px;color:var(--txt3)}
.stat.wide{grid-column:span 3;display:grid;grid-template-columns:auto 1fr;gap:4px 14px;align-items:center}
.bar{height:6px;background:var(--s3);border-radius:2px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--gold)}
.note{font-size:12px;color:var(--txt3)}
.illus{font-size:12px;color:var(--txt2);border:1px dashed var(--line2);border-radius:var(--r);padding:6px 10px;margin-top:8px}
svg text{font-family:var(--mono);font-size:11px;fill:var(--txt3)}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:12px;color:var(--txt2);margin-top:6px}
.legend i{display:inline-block;width:16px;height:0;border-top:2px solid;vertical-align:middle;margin-right:6px}
.types{display:flex;flex-direction:column;gap:8px}
.types .row{display:grid;grid-template-columns:1fr 64px;gap:10px;align-items:center;font-size:13px}
.types .row .bar{grid-column:1/-1}
.tabs{display:none}
table.pol{width:100%;border-collapse:collapse;font-size:13px}
table.pol th{font:500 12px var(--body);color:var(--txt3);text-align:right;padding:6px 0 6px 10px;border-bottom:1px solid var(--rule)}
table.pol th:first-child,table.pol td:first-child{text-align:left;padding-left:0}
table.pol td{font-family:var(--mono);text-align:right;padding:7px 0 7px 10px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
table.pol td.neg{color:var(--neg)}
table.pol td .who2{font-family:var(--body);color:var(--txt2)}
/* responsive */
@media (max-width:1180px){.app{grid-template-columns:220px minmax(0,1fr)}.graphs{grid-column:1/-1;border-left:0;border-top:1px solid var(--line)}}
@media (max-width:760px){
  .top{gap:12px;padding:0 12px}.top nav,.ver{display:none}.menu-btn{display:inline-flex}
  .app{grid-template-columns:1fr}.side{display:none}
  .scroll{padding:16px 16px 12px}.composer{padding:10px 12px 12px}
  .tabs{display:flex;border-bottom:1px solid var(--line);padding:0 16px;gap:20px;font-size:14px}
  .tabs a{padding:10px 0;color:var(--txt2);text-decoration:none;border-bottom:2px solid transparent}
  .tabs a[aria-current]{color:var(--txt);border-color:var(--gold)}
  .graphs{padding:16px}
  .wp h1{font-size:22px}.f{grid-template-columns:20px 1fr}.f .amt{grid-column:2;text-align:left}
  .verdict .big{font-size:38px}
}
"""

TYPE_RU = {"duplicate_invoice": "Дубль счёта", "payment_allocation": "Нераспределённый платёж",
           "date_or_fx": "Неверная дата или курс", "period_classification": "Неверный отчётный период"}
TYPE_HELP = {"duplicate_invoice": "Один и тот же счёт выставлен дважды: тот же контрагент, строки и период услуг.",
             "payment_allocation": "Деньги пришли, но не привязаны к счёту полностью или частично.",
             "date_or_fx": "Сумма в книге посчитана по курсу не той даты, что требует политика.",
             "period_classification": "Проводка попала не в тот отчётный период."}
TABLE_RU = {"fx": ("A-4", "курсы валют"), "invoices": ("A-2", "счета"), "payments": ("A-3", "платежи"), "ledger": ("A-1", "главную книгу")}
EXP = {"USD": 2, "EUR": 2, "KZT": 2, "JPY": 0}
e = html.escape


def money(minor, ccy):
    exp = EXP.get(ccy, 2)
    s = f"{minor / 10 ** exp:,.{exp}f}".replace(",", " ").replace(".", ",")
    return s


def ru_num(x, d=3):
    return f"{x:.{d}f}".replace(".", ",").replace("-", "−")


steps = data["steps"]
reads = [s for s in steps if s["tool"] == "list_records"]
submit = steps[-1]
rep = submit["report"]
groups = []
for s in reads:
    if groups and groups[-1]["table"] == s["table"]:
        g = groups[-1]; g["pages"] += 1; g["rows"] += s["rows"]; g["last"] = s["step"]
    else:
        groups.append({"table": s["table"], "pages": 1, "rows": s["rows"], "first": s["step"], "last": s["step"], "sample": s["sample"]})


def peek_table(g):
    rows = g["sample"][:3]
    if g["table"] == "fx":
        head = ["дата", "из", "в", "курс"]
        body = [[r["date"], r["source_currency"], r["target_currency"], r["rate"]] for r in rows]
        right = {3}
    elif g["table"] == "invoices":
        head = ["счёт", "контрагент", "выставлен", "сумма", ""]
        body = [[r["invoice_id"], r["entity_id"], r["issued_at"][:10], money(r["total_minor"], r["currency"]), r["currency"]] for r in rows]
        right = {3}
    elif g["table"] == "payments":
        head = ["платёж", "дата", "сумма", "", "счета"]
        body = [[r["payment_id"], r["timestamp"][:10], money(r["amount_minor"], r["currency"]), r["currency"], ", ".join(r["invoice_refs"] or ["null"])] for r in rows]
        right = {2}
    else:
        head = ["строка", "счёт", "дебет", "кредит", ""]
        body = [[r["row_id"], r["account"], money(r["debit_minor"], r["currency"]) if r["debit_minor"] else "", money(r["credit_minor"], r["currency"]) if r["credit_minor"] else "", r["currency"]] for r in rows]
        right = {2, 3}
    th = "".join(f"<th>{e(h)}</th>" for h in head)
    trs = "".join("<tr>" + "".join(f'<td class="{"r" if i in right else ""}">{e(str(c))}</td>' for i, c in enumerate(row)) + "</tr>" for row in body)
    return f'<div class="peek"><table class="mini"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table><p class="note">Первые 3 строки из {g["rows"]} — так выглядит ответ инструмента.</p></div>'


TM = '<svg class="tm" viewBox="0 0 18 18" aria-hidden="true"><path d="M3 9.5l4 4L15 4" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>'

calls_html = []
for i, g in enumerate(groups):
    code, noun = TABLE_RU[g["table"]]
    span = f'шаг {g["first"]}' if g["first"] == g["last"] else f'шаги {g["first"]}–{g["last"]}'
    pages = f'{g["pages"]} стр.'
    calls_html.append(
        f'<details class="call"{" open" if g["table"] == "invoices" else ""}><summary><span class="chev" aria-hidden="true">›</span>'
        f'<span class="what">Прочитал <b>{noun}</b> <span class="lbl">{code}</span>'
        f'<span class="sig">list_records("{g["table"]}", limit=50) × {g["pages"]}</span></span>'
        f'<span class="cnt">{g["rows"]} строк · {pages}<br>{span}</span></summary>{peek_table(g)}</details>')

findings_html = []
for f in submit["findings"]:
    ids = "".join(f'<span class="idc">{e(x)}</span>' for x in f["affected_ids"])
    ev = "".join(f'<span class="idc ev" title="доказательство">{e(x)}</span>' for x in f["evidence_ids"])
    findings_html.append(
        f'<div class="f">{TM}<div><div class="ty"><span class="term" title="{e(TYPE_HELP[f["type"]])}">{TYPE_RU[f["type"]]}</span></div>'
        f'<div class="ids">{ids}</div><div class="ids"><span class="lbl">доказательства:</span> {ev}</div>'
        f'<div class="ex">«{e(f["explanation"])}»</div></div>'
        f'<div class="amt num">{money(f["claimed_amount_minor"], f["currency"])} <span>{e(f["currency"])}</span></div></div>')

# sidebar data
ps = {p["policy"]: p for p in data["policy_summary"]}
recon_mean = sum(ps["reconcile"][g] for g in ("clean", "mixed", "interacting")) / 3
fa = data["failure_analysis"]["reconcile_rules_recall_by_type"]
types_html = "".join(
    f'<div class="row"><span>{TYPE_RU[t]}</span><span class="mono num" style="text-align:right">{v["found"]} / {v["issues"]}</span>'
    f'<div class="bar"><i style="width:{100 * v["found"] / v["issues"]:.0f}%"></i></div></div>' for t, v in fa.items())


def curve_svg():
    W, H, L, R, T, B = 400, 230, 34, 10, 12, 26
    x = lambda i: L + (W - L - R) * i / 50
    y = lambda v: T + (H - T - B) * (1 - (v + 1) / 2)
    grid = "".join(f'<line x1="{L}" x2="{W - R}" y1="{y(v)}" y2="{y(v)}" stroke="var(--line)"/><text x="{L - 6}" y="{y(v) + 4}" text-anchor="end">{ru_num(v, 1)}</text>' for v in (-1, -0.5, 0, 0.5, 1))
    xt = "".join(f'<text x="{x(i)}" y="{H - 8}" text-anchor="middle">{i}</text>' for i in (0, 10, 20, 30, 40, 50))
    base = (f'<line x1="{L}" x2="{W - R}" y1="{y(1)}" y2="{y(1)}" stroke="var(--pos)" stroke-dasharray="2 4"/>'
            f'<line x1="{L}" x2="{W - R}" y1="{y(recon_mean)}" y2="{y(recon_mean)}" stroke="var(--gold)" stroke-width="1.5"/>'
            f'<line x1="{L}" x2="{W - R}" y1="{y(-1)}" y2="{y(-1)}" stroke="var(--neg)" stroke-dasharray="2 4"/>')
    # illustrative shape only: a smooth rise; NOT data
    import math
    pts = [(i, -1 + 1.75 / (1 + math.exp(-(i - 18) / 5))) for i in range(0, 51, 2)]
    dev = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in pts)
    trn = " ".join(f"{x(i):.1f},{y(min(1, v + 0.06)):.1f}" for i, v in pts)
    ill = (f'<polyline points="{trn}" fill="none" stroke="var(--txt3)" stroke-width="1.5" stroke-dasharray="5 4"/>'
           f'<polyline points="{dev}" fill="none" stroke="var(--info)" stroke-width="2" stroke-dasharray="5 4"/>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Иллюстрация формы кривой обучения с настоящими базовыми линиями">'
            f'{grid}{xt}{base}{ill}<text x="{W - R}" y="{y(recon_mean) - 6}" text-anchor="end" style="fill:var(--gold)">reconcile {ru_num(recon_mean)}</text></svg>')


def bars_svg():
    W, rowh, L = 400, 26, 86
    pols = ["oracle", "reconcile", "random", "flag_all"]
    groups_ = [("clean", "чистые"), ("mixed", "смешанные"), ("interacting", "взаимодейств.")]
    H = len(pols) * (rowh * 3 + 12) + 20
    zero = L + (W - L - 10) / 2
    sc = (W - L - 10) / 2
    out = [f'<line x1="{zero}" x2="{zero}" y1="0" y2="{H - 18}" stroke="var(--rule)"/>',
           f'<text x="{zero - sc}" y="{H - 4}">−1</text><text x="{zero}" y="{H - 4}" text-anchor="middle">0</text><text x="{zero + sc}" y="{H - 4}" text-anchor="end">+1</text>']
    yy = 0
    for p in pols:
        out.append(f'<text x="0" y="{yy + 14}" style="fill:var(--txt2)">{p}</text>')
        for gi, (g, gl) in enumerate(groups_):
            v = ps[p][g]
            y0 = yy + gi * rowh + 4
            w = abs(v) * sc
            x0 = zero if v >= 0 else zero - w
            col = "var(--gold)" if v >= 0 else "var(--neg)"
            out.append(f'<rect x="{x0:.1f}" y="{y0}" width="{max(w, 1):.1f}" height="14" fill="{col}" opacity=".85"/>')
            out.append(f'<text x="{(zero - 6) if v >= 0 else (zero + 6)}" y="{y0 + 11}" text-anchor="{"end" if v >= 0 else "start"}">{gl}</text>' if False else "")
            lab_x = (x0 + w + 6) if v >= 0 else (x0 - 6)
            anchor = "start" if v >= 0 else "end"
            out.append(f'<text x="{lab_x:.1f}" y="{y0 + 11}" text-anchor="{anchor}" style="fill:var(--txt2)">{ru_num(v, 2)} {gl}</text>')
        yy += rowh * 3 + 12
    return f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Награда базовых политик по группам эпизодов">{"".join(out)}</svg>'


def policy_table():
    names = {"oracle": "oracle · максимум", "reconcile": "reconcile · сверка", "random": "random · случайный", "flag_all": "flag_all · атака"}
    def cell(v):
        txt = f"{abs(v):.2f}".replace(".", ",")
        return f'<td class="neg">({txt})</td>' if v < 0 else f"<td>{txt}</td>"
    rows = "".join(f'<tr><td><span class="who2">{names[p]}</span></td>' + "".join(cell(ps[p][g]) for g in ("clean", "mixed", "interacting")) + "</tr>"
                   for p in ("oracle", "reconcile", "random", "flag_all"))
    return f'<table class="pol"><thead><tr><th>политика</th><th>чистые</th><th>смешанные</th><th>взаимодейств.</th></tr></thead><tbody>{rows}</tbody></table>'


def train_list():
    items = []
    for i, ep in enumerate(train_cfg["episodes"][:10], 1):
        c = ep["config"]
        if c.get("clean"):
            tag = "чистая"
        elif c.get("interactions"):
            tag = "взаимод. " + "+".join(c["interactions"])
        elif c.get("errors"):
            tag = f"{sum(c['errors'].values())} ош."
        else:
            tag = "по умолчанию"
        items.append(f'<li><a href="#">train-{i:02d}<span class="tag">{tag}</span></a></li>')
    return "".join(items)


steps_used = len(steps)
cmd = f"python -m auditgym.cli run-agent --agent reconcile --episode {data['episode']}"
v = data["versions"]

PAGE = f"""<!doctype html><html lang="ru" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AuditGym · превью интерфейса</title>
<style>{font_css}
{CSS}</style></head><body>
<a class="skip" href="#thread">К ходу эпизода</a>
<header class="top">
  <button class="btn menu-btn" aria-label="Меню">☰</button>
  <div class="brand"><svg viewBox="0 0 22 22" aria-hidden="true"><rect x="1.5" y="1.5" width="19" height="19" rx="2" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M5 8h12M5 12h7" stroke="currentColor" stroke-width="1.1" opacity=".6"/><path d="M12 15.5l2 2 4.5-5" fill="none" stroke="var(--gold)" stroke-width="1.6"/></svg>AuditGym</div>
  <nav aria-label="Разделы"><a href="#" aria-current="page">Эпизоды</a><a href="#">Отчёт</a><a href="#">Для специалистов: терминал</a></nav>
  <span class="sp"></span>
  <span class="ver">ENV {e(v["env"])} · Python 3.11 · без сети</span>
  <button class="btn" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">◐ Бумага / графит</button>
</header>
<div class="tabs" role="tablist"><a href="#thread" aria-current="page">Ход эпизода</a><a href="#graphs">Графики</a></div>
<div class="app">
  <aside class="side" aria-label="Эпизоды и повторы">
    <button class="btn primary">+ Новый эпизод</button>
    <div><h2>Сейчас открыт</h2><ul><li><a href="#" aria-current="true">{e(data["episode"][:14])}…<span class="tag">reconcile</span></a></li></ul></div>
    <div><h2>Эпизоды для обучения</h2><ul>{train_list()}</ul></div>
    <div><h2>Повторы базовых политик</h2><ul>
      <li><a href="#">reconcile<span class="tag">сверка</span></a></li><li><a href="#">random<span class="tag">случайный</span></a></li>
      <li><a href="#">flag_all<span class="tag">атака</span></a></li><li><a href="#">oracle<span class="tag">максимум</span></a></li></ul></div>
    <div class="foot">verify {ru_num(data["estimated_score"]["total"], 0)}/100 · schema {e(v["schema"])} · config {e(v["config"])}</div>
  </aside>

  <main class="thread" id="thread">
    <div class="scroll"><div class="col">
      <div class="wp"><span class="ref">L-2<small>W/P</small></span><div>
        <h1>Ход эпизода</h1>
        <div class="meta"><span>Клиент <b>{e(data["episode"])}</b></span><span>Подготовил <b>reconcile</b></span><span>Проверил <b>оценщик</b></span><span>Режим <b>открытый</b></span></div></div></div>

      <div class="explain"><strong>Что вы видите.</strong> ИИ-агент проверяет книги вымышленной компании. Каждая строка ниже — один его шаг: вызов
      инструмента только для чтения. В конце агент сдаёт <span class="term" title="Вывод = тип ошибки, затронутые записи, сумма, валюта и доказательства.">выводы</span>,
      а оценщик сверяет их со скрытым эталоном. Награда даётся только за доказанное.</div>

      <div class="msg"><span class="who" aria-hidden="true">§</span><div class="body"><div class="name"><b>Задача</b> · первое наблюдение</div>
        <div class="task">Найдите ошибки в книгах за отчётный период и докажите каждую записями. Пять инструментов только для чтения, не больше 100 шагов.</div>
        <div class="chips">{"".join(f'<span class="chip term" title="{e(TYPE_HELP[t])}">{TYPE_RU[t]}</span>' for t in TYPE_RU)}</div></div></div>

      <div class="msg"><span class="who agent" aria-hidden="true">R</span><div class="body"><div class="name"><b>Агент reconcile</b> · скриптовая сверка · шаги 1–15</div>
        <div class="calls">{"".join(calls_html)}</div></div></div>

      <div class="msg"><span class="who agent" aria-hidden="true">R</span><div class="body"><div class="name"><b>Агент reconcile</b> · шаг {submit["step"]} · <span class="lbl">C-1</span> выводы</div>
        <div class="findings">{"".join(findings_html)}</div></div></div>

      <div class="msg"><span class="who" aria-hidden="true">✓</span><div class="body"><div class="name"><b>Оценщик</b> · <span class="lbl">C-2</span> заключение</div>
        <div class="verdict"><div><div class="lbl">Награда за эпизод</div><div class="big num">{ru_num(rep["reward"])}</div></div>
          <div class="ticks">{TM} {rep["tp"]} из {len(submit["findings"])} выводов подтверждены · ложных {rep["fp"]} · пропущено {rep["fn"]}</div>
          <div class="formula">награда = 2·F1 − 1 − 0,002·шаги = 2·{ru_num(rep["f1"], 2)} − 1 − 0,002·{rep["inspection_steps"]} = {ru_num(rep["reward"])}</div></div></div></div>

      <div class="bridge"><span>Повторить в терминале:</span><code>{e(cmd)}</code><button class="btn">Копировать</button></div>
      <p class="note" style="margin:-14px 0 0">Команда появится вместе с задачей T12; сейчас это макет.</p>
    </div></div>

    <div class="composer"><div class="cbox">
      <label for="act">Ваш ход (режим игры)</label>
      <input id="act" placeholder="Например: открыть INV-W6-1720 или посчитать 20120.00 × 503.695">
      <div class="crow"><button class="act">Открыть запись</button><button class="act">Документ</button><button class="act">Калькулятор</button><button class="act">Сдать выводы</button>
        <span class="sp"></span><span class="adv">Продвинутые настройки ▸</span></div></div></div>
  </main>

  <aside class="graphs" id="graphs" aria-label="Графики обучения и телеметрия">
    <section class="panel"><h2><span class="code">T-2</span>Телеметрия прогона</h2><p class="sub">Этот эпизод, после сдачи выводов</p>
      <div class="stats">
        <div class="stat"><div class="v num">{ru_num(rep["reward"])}</div><div class="k">награда</div></div>
        <div class="stat"><div class="v num">{ru_num(rep["f1"], 2)}</div><div class="k"><span class="term" title="F1 — баланс точности и полноты: 1,00 значит всё найдено и ничего лишнего.">F1</span></div></div>
        <div class="stat"><div class="v num">{rep["tp"]}/{rep["fp"]}/{rep["fn"]}</div><div class="k">TP / FP / FN</div></div>
        <div class="stat"><div class="v num">{ru_num(rep["precision"], 2)}</div><div class="k"><span class="term" title="Точность: какая доля выводов оказалась верной.">точность</span></div></div>
        <div class="stat"><div class="v num">{ru_num(rep["recall"], 2)}</div><div class="k"><span class="term" title="Полнота: какая доля скрытых ошибок найдена.">полнота</span></div></div>
        <div class="stat"><div class="v num">—</div><div class="k">токены · скриптовый агент</div></div>
        <div class="stat wide"><span class="k">шаги</span><span class="mono num" style="text-align:right">{steps_used} из 100</span><div class="bar" style="grid-column:1/-1"><i style="width:{steps_used}%"></i></div></div>
      </div>
      <p class="note">Время агента не записано в trajectories.jsonl — появится, когда прогон идёт вживую.</p></section>

    <section class="panel"><h2><span class="code">T-1</span>Кривая обучения</h2><p class="sub">Награда на отложенных dev-эпизодах по итерациям</p>
      {curve_svg()}
      <div class="legend"><span><i style="border-color:var(--info);border-top-style:dashed"></i>dev (отложенные)</span><span><i style="border-color:var(--txt3);border-top-style:dashed"></i>train</span>
        <span><i style="border-color:var(--gold)"></i>reconcile</span><span><i style="border-color:var(--pos);border-top-style:dotted"></i>oracle</span><span><i style="border-color:var(--neg);border-top-style:dotted"></i>random</span></div>
      <p class="illus">Пунктир — только форма для примера: настоящая кривая появится из <span class="mono">train/curve.json</span> (задача T10). Базовые линии — настоящие, из report.json.</p></section>

    <section class="panel"><h2><span class="code">T-3</span>Базовые политики</h2><p class="sub">Средняя награда по группам эпизодов · report.json · отрицательные — в скобках</p>{policy_table()}</section>

    <section class="panel"><h2><span class="code">T-4</span>Найдено по типам ошибок</h2><p class="sub">reconcile · все эпизоды verify</p><div class="types">{types_html}</div></section>
  </aside>
</div></body></html>"""
(out / "preview.html").write_text(PAGE)

# ---------- terminal mock-up for specialists (numbers: real reconcile runs from trajectories.jsonl)
runs = data["reconcile_runs"]
lines = [
    "$ python -m auditgym.cli run-agent --agent reconcile --mode closed --max-steps 100 --seed 0",
    f"AuditGym {v['env']} · schema {v['schema']} · config {v['config']} · Python 3.11 · offline · runtime deps: none",
    "agent  reconcile (scripted: temperature/top-p/max-tokens not used)",
    "",
    f"{'episode':<22}{'steps':>6}{'reward':>9}{'P':>7}{'R':>7}{'F1':>7}{'TP':>5}{'FP':>4}{'FN':>4}  mark",
    "─" * 81,
]
for r in runs:
    mark = "✓ clean, silent" if (r["tp"] + r["fn"]) == 0 else ("✓ all proved" if r["fn"] == 0 and r["fp"] == 0 else "⊗ exception")
    lines.append(f"{r['episode']:<22}{r['steps']:>6}{r['reward']:>9.3f}{r['p']:>7.2f}{r['r']:>7.2f}{r['f1']:>7.2f}{r['tp']:>5}{r['fp']:>4}{r['fn']:>4}  {mark}")
n = len(runs)
lines += ["─" * 81,
          f"{'mean (' + str(n) + ' episodes)':<22}{sum(r['steps'] for r in runs) / n:>6.1f}{sum(r['reward'] for r in runs) / n:>9.3f}{'':>21}{sum(r['tp'] for r in runs):>5}{sum(r['fp'] for r in runs):>4}{sum(r['fn'] for r in runs):>4}",
          "",
          "marks: ✓ agreed (all findings proved, nothing extra)   ⊗ exception (miss or false finding)",
          "",
          "$ python -m auditgym.cli run-agent --help",
          "  --agent {random,reconcile,flag_all,ollama:<model>,cmd:<program>}",
          "  --split {train,dev}  --episode ID  --repeats K        which episodes, how many times",
          "  --mode {open,closed}  --max-steps N (<= 100)  --seed N",
          "  --temperature T  --top-p P  --max-tokens N  --token-budget N   LLM agents only",
          "  --json                                                          machine-readable output",
          ]
term = "\n".join(lines)
(out / "terminal.txt").write_text(term + "\n")
TERM_PAGE = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>AuditGym terminal mock-up</title>
<style>{font_css}
body{{margin:0;background:#0f0e0c;color:#efe9dc;font-family:"JetBrains Mono",monospace;font-size:14px}}
.win{{margin:24px;border:1px solid #3d3a34;border-radius:4px;overflow:hidden}}
.bar{{background:#1f1e1b;padding:8px 12px;color:#958d7f;font-size:12px;border-bottom:1px solid #3d3a34}}
pre{{margin:0;padding:16px 18px;line-height:1.55;white-space:pre}}
.c{{color:#cfb07a}} .ok{{color:#79c39c}} .d{{color:#958d7f}}
.note{{margin:0 24px 24px;color:#958d7f;font-family:Inter,sans-serif;font-size:13px}}</style></head><body>
<div class="win"><div class="bar">terminal — auditgym (mock-up for specialists)</div><pre>{e(term).replace("$ ", '<span class="c">$ </span>').replace("✓", '<span class="ok">✓</span>')}</pre></div>
<p class="note">Mock-up: the run-agent command is proposed in task T12 and does not exist yet. The table numbers are real reconcile runs from trajectories.jsonl.</p></body></html>"""
(out / "terminal.html").write_text(TERM_PAGE)
print("ok", len(PAGE) // 1024, "KB")
