"""Three layout options for AuditGym as a local training harness (A workspace, B training console, C terminal trace).

Usage: python3 -I build_harness.py <repo_dir> <out_dir>

Reads the recorded reconcile run (docs/design-research/preview/tools/data.json) and the public dev config.
Real numbers: baselines (oracle, reconcile, random), the 16-step reconcile trajectory, per-episode reconcile
results, reconcile recall by error type. Illustrative until T10 lands: the learning curves of the learned auditor
(train/curve.json does not exist yet); every page says so. No libraries, no network.
"""
import base64
import json
import math
import random
import sys
from pathlib import Path

repo, out = Path(sys.argv[1]), Path(sys.argv[2])
data = json.loads((repo / "docs/design-research/preview/tools/data.json").read_text())
dev = json.loads((repo / "configs/dev.json").read_text())
fonts_dir = repo / "src/auditgym/ui/static/fonts"

FONTS = [("Inter", w, f"inter-{s}-{w}-normal") for w in (400, 500, 600) for s in ("latin", "cyrillic")] + \
        [("JetBrains Mono", w, f"jetbrains-mono-{s}-{w}-normal") for w in (400, 600) for s in ("latin", "cyrillic")]
LATIN = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+2500-259F,U+25A0-25FF,U+FEFF,U+FFFD"
CYR = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"
font_css = "\n".join(
    f'@font-face{{font-family:"{fam}";font-weight:{w};font-display:block;src:url(data:font/woff2;base64,'
    f'{base64.b64encode((fonts_dir / f"{f}.woff2").read_bytes()).decode()}) format("woff2");unicode-range:{CYR if "cyrillic" in f else LATIN}}}'
    for fam, w, f in FONTS)


def label(cfg):
    """Episode label from the public config only (never from the hidden answer)."""
    if cfg.get("clean"):
        extra = [c for c in cfg.get("foreign_currencies", []) if c not in ("EUR", "USD")]
        return "чистая" + (" · " + "/".join(extra) if extra else "")
    if cfg.get("interactions"):
        return "взаимод. " + "+".join(cfg["interactions"])
    n = sum(cfg.get("errors", {}).values())
    if n:
        return f"{n} ош." + (" · большая" if cfg.get("n_invoices", 0) >= 80 else "")
    return "смешанная"


# ---- illustrative learning curves (deterministic) until train/curve.json exists
ITERS = 40


def curve(seed, tau, top, start=-1.0):
    r = random.Random(seed)
    rows = []
    for i in range(ITERS + 1):
        k = 1 - math.exp(-i / tau)
        dv = start + (top - start) * k + r.gauss(0, 0.045) * (1 - 0.5 * k)
        rows.append({"i": i, "dev": round(max(-1, min(1, dv)), 3), "train": round(max(-1, min(1, dv + 0.06 * k + r.gauss(0, 0.03))), 3),
                     "f1": round(max(0, min(1, 0.05 + 0.85 * k + r.gauss(0, 0.03))), 3),
                     "steps": round(64 - 40 * k + r.gauss(0, 1.6), 1), "fp": round(max(0, 6.5 * (1 - k) + r.gauss(0, 0.35)), 2),
                     "invalid": round(max(0, 0.22 * (1 - k) + r.gauss(0, 0.012)), 3), "sigma": round(0.9 * math.exp(-i / 16) + 0.05, 3)})
    return rows


runs = [
    {"id": "learn_rules-cem-s1", "method": "CEM", "seed": 1, "color": "c1", "status": "running", "at": 25, "rows": curve(1, 9.0, 0.74)},
    {"id": "learn_rules-cem-s2", "method": "CEM", "seed": 2, "color": "c2", "status": "done", "at": ITERS, "rows": curve(2, 10.0, 0.70)},
    {"id": "learn_rules-reinforce-s1", "method": "REINFORCE", "seed": 1, "color": "c3", "status": "done", "at": ITERS, "rows": curve(3, 15.0, 0.55)},
]
ps = {p["policy"]: p for p in data["policy_summary"]}
mean = lambda p: round(sum(ps[p][k] for k in ("clean", "mixed", "interacting")) / 3, 3)
rr = data["reconcile_runs"]
baselines = [{"id": "oracle", "reward": mean("oracle"), "note": "знает ответ, потолок"},
             {"id": "reconcile", "reward": mean("reconcile"), "note": "правила, написанные вручную",
              "steps": round(sum(r["steps"] for r in rr) / len(rr), 1)},
             {"id": "random", "reward": mean("random"), "note": "случайные действия"}]
r_dev = random.Random(7)
episodes = []
for e in dev["episodes"]:
    rw = round(max(-1, min(1, 0.62 + r_dev.gauss(0, 0.18))), 2)
    episodes.append({"seed": e["seed"], "label": label(e["config"]), "reward": rw, "steps": int(22 + r_dev.random() * 16)})
steps = data["steps"]
traj = [{"n": s["step"], "tool": s["tool"], "table": s.get("table"), "rows": s.get("rows"), "left": s.get("remaining")} for s in steps]
sub = steps[-1]
fa = data["failure_analysis"]["reconcile_rules_recall_by_type"]
payload = {"iters": ITERS, "runs": runs, "baselines": baselines, "dev": episodes, "traj": traj,
           "submit": {"found": len(sub["findings"]), **{k: sub["report"][k] for k in ("tp", "fp", "fn", "reward", "precision", "recall", "f1")}},
           "episode": data["episode"], "recon_runs": rr, "recall": fa, "versions": data["versions"]}

SHARED_CSS = r"""
:root{--bg:#f7f7f5;--panel:#fff;--ink:#151517;--ink2:#3b3b40;--mute:#67676d;--line:#e6e5e1;--line2:#d6d5d0;--soft:#f0efec;
--pos:#1d7348;--neg:#b42318;--c1:#2563eb;--c2:#d9480f;--c3:#7c3aed;--base:#8a8a90;--focus:#2563eb}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#111113;--panel:#18181b;--ink:#ededef;--ink2:#cfcfd4;--mute:#9b9ba2;
--line:#29292e;--line2:#36363c;--soft:#202024;--pos:#3fb97a;--neg:#f0625a;--c1:#6b9cf5;--c2:#f08c4a;--c3:#a98af7;--base:#8a8a90}}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:var(--bg);color:var(--ink);font:13px/1.45 Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.mono{font-family:"JetBrains Mono",ui-monospace,monospace;font-feature-settings:"zero" 0}
button{font:inherit;color:inherit;cursor:pointer}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.ch text{font:10.5px "JetBrains Mono",monospace;fill:var(--mute)}
.ch .grid{stroke:var(--line);stroke-width:1}
.ch .ref{stroke-width:1.25;stroke-dasharray:4 4;opacity:.9}
.ch .reflab{font-size:10px}
.ch .hov{stroke:var(--ink);stroke-opacity:.35;stroke-width:1}
.ch .ln{stroke-linejoin:round;stroke-linecap:round}
.illus{font-size:11px;color:var(--mute)}
.dot{display:inline-block;width:8px;height:8px;border-radius:2px;vertical-align:middle}
.c1{--c:var(--c1)}.c2{--c:var(--c2)}.c3{--c:var(--c3)}
@keyframes pulse{50%{opacity:.35}}
.live{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--pos);animation:pulse 1.4s infinite}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

SHARED_JS = r"""
const D = __DATA__;
const NS = "http://www.w3.org/2000/svg";
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function el(tag, attrs, parent) { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
const f2 = v => (v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
const f1 = v => v.toFixed(1);
const BUS = [];  // charts listening to the shared hover position (iteration)
function smooth(pts, a) { if (!a) return pts; let s = pts[0][1]; return pts.map(p => (s = a * s + (1 - a) * p[1], [p[0], s])); }
// Line chart. o = {series:[{name,color,pts,dash,w}], xmax, ymin, ymax, yticks, xticks, refs:[{y,label,color}], h, fmt, legend}
function chart(host, o) {
  const W = Math.max(260, host.clientWidth), H = o.h || 170, m = { l: 38, r: 12, t: 10, b: 22 };
  host.innerHTML = "";
  const s = el("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "ch", role: "img", "aria-label": o.aria || "" }, host);
  const X = x => m.l + x / o.xmax * (W - m.l - m.r), Y = y => m.t + (o.ymax - y) / (o.ymax - o.ymin) * (H - m.t - m.b);
  for (const t of o.yticks) { el("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: "grid" }, s); el("text", { x: m.l - 6, y: Y(t) + 3.5, "text-anchor": "end" }, s).textContent = (o.fmt || f2)(t); }
  for (const t of o.xticks || [0, 10, 20, 30, 40]) el("text", { x: X(t), y: H - 6, "text-anchor": "middle" }, s).textContent = t;
  for (const r of o.refs || []) { el("line", { x1: m.l, x2: W - m.r, y1: Y(r.y), y2: Y(r.y), class: "ref", stroke: r.color || css("--base") }, s);
    el("text", { x: W - m.r - 4, y: r.below ? Y(r.y) + 12 : Y(r.y) - 4, "text-anchor": "end", class: "reflab" }, s).textContent = r.label; }
  const paths = [];
  for (const se of o.series) {
    if (!se.pts.length) continue;
    const d = se.pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(Math.max(o.ymin, Math.min(o.ymax, p[1]))).toFixed(1)).join(" ");
    const p = el("path", { d, class: "ln", fill: "none", stroke: se.color, "stroke-width": se.w || 1.8 }, s);
    if (se.dash) p.setAttribute("stroke-dasharray", se.dash);
    if (se.raw) p.setAttribute("stroke-opacity", ".22");
    paths.push(p);
    if (se.head) { const q = se.pts[se.pts.length - 1]; el("circle", { cx: X(q[0]), cy: Y(q[1]), r: 3.2, fill: se.color }, s); }
  }
  if (o.animate && !RM) for (const p of paths) { const L = p.getTotalLength(); p.style.strokeDasharray = L; p.style.strokeDashoffset = L;
    p.getBoundingClientRect(); p.style.transition = "stroke-dashoffset 1.1s cubic-bezier(.3,.7,.2,1)"; p.style.strokeDashoffset = 0;
    setTimeout(() => { p.style.strokeDasharray = ""; p.style.transition = ""; }, 1200); }
  const hv = el("line", { y1: m.t, y2: H - m.b, class: "hov", visibility: "hidden" }, s);
  const dots = o.series.filter(se => !se.raw).map(se => ({ se, c: el("circle", { r: 3, fill: se.color, visibility: "hidden" }, s) }));
  const api = { show(x) { if (x == null) { hv.setAttribute("visibility", "hidden"); dots.forEach(d => d.c.setAttribute("visibility", "hidden")); o.legend && o.legend(null); return; }
      hv.setAttribute("x1", X(x)); hv.setAttribute("x2", X(x)); hv.setAttribute("visibility", "visible");
      const vals = [];
      for (const d of dots) { const p = d.se.pts.find(q => q[0] === x); if (p) { d.c.setAttribute("cx", X(x)); d.c.setAttribute("cy", Y(p[1])); d.c.setAttribute("visibility", "visible"); vals.push([d.se, p[1]]); } else d.c.setAttribute("visibility", "hidden"); }
      o.legend && o.legend(x, vals); } };
  s.addEventListener("mousemove", ev => { const r = s.getBoundingClientRect(); const x = Math.round((ev.clientX - r.left - m.l) / (W - m.l - m.r) * o.xmax);
    const xx = Math.max(0, Math.min(o.xmax, x)); BUS.forEach(b => b.show(xx)); });
  s.addEventListener("mouseleave", () => BUS.forEach(b => b.show(null)));
  BUS.push(api); o.legend && o.legend(null);
  return api;
}
function rowsOf(run, upto) { return run.rows.slice(0, (upto == null ? run.at : upto) + 1); }
"""


def page(title, body_css, body_html, body_js, theme=None):
    attr = f' data-theme="{theme}"' if theme else ""
    return (f'<!doctype html><html lang="ru"{attr}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title><style>{font_css}\n{SHARED_CSS}\n{body_css}</style></head><body>{body_html}"
            f"<script>{SHARED_JS.replace('__DATA__', json.dumps(payload, ensure_ascii=False))}\n{body_js}</script></body></html>")


# ======================================================================= A: workspace
A_CSS = r"""
.app{display:grid;grid-template-columns:272px 1fr;grid-template-rows:48px 1fr;height:100vh}
.top{grid-column:1/-1;display:flex;align-items:center;gap:18px;padding:0 16px;border-bottom:1px solid var(--line);background:var(--panel)}
.logo{font-weight:600;letter-spacing:-.01em;display:flex;align-items:center;gap:8px}.logo b{font:600 12px "JetBrains Mono";border:1.5px solid var(--ink);border-radius:4px;padding:0 4px}
.crumb{color:var(--mute)}.crumb span{color:var(--ink)}
.tabs{display:flex;gap:2px;margin-left:12px}.tabs button{border:0;background:none;padding:6px 10px;border-radius:6px;color:var(--mute)}
.tabs button[aria-selected=true]{background:var(--soft);color:var(--ink);font-weight:500}
.sp{flex:1}.state{color:var(--mute);display:flex;align-items:center;gap:8px}
.btn{border:1px solid var(--line2);background:var(--panel);border-radius:7px;padding:6px 12px;font-weight:500}
.btn.pri{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.rail{border-right:1px solid var(--line);background:var(--panel);overflow:auto;padding:14px 12px;display:flex;flex-direction:column;gap:18px}
.rail h4{margin:0 0 8px;font-size:11px;font-weight:500;color:var(--mute);letter-spacing:.02em;display:flex;justify-content:space-between}
.search{width:100%;border:1px solid var(--line2);border-radius:7px;padding:7px 10px;background:var(--bg);color:var(--ink);font:inherit}
.run{display:grid;grid-template-columns:16px 1fr auto;gap:8px;align-items:center;padding:6px 6px;border-radius:6px}
.run:hover{background:var(--soft)}
.run input{appearance:none;width:13px;height:13px;border-radius:3px;border:1.5px solid var(--c);margin:0;background:var(--c)}
.run input:not(:checked){background:none}
.run .nm{font:12px "JetBrains Mono";white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.run .meta{font-size:11px;color:var(--mute)}.run .v{font:12px "JetBrains Mono";text-align:right}
.ref .nm{color:var(--ink2)}.ref input{border-color:var(--base);background:var(--base)}
.ctl{display:grid;grid-template-columns:1fr auto;gap:6px 10px;align-items:center;font-size:12px}
.ctl input[type=range]{grid-column:1/-1;width:100%;accent-color:var(--ink)}
.ctl select{font:inherit;border:1px solid var(--line2);border-radius:6px;padding:3px 6px;background:var(--panel);color:var(--ink)}
.envbox{margin-top:auto;font-size:11px;color:var(--mute);border-top:1px solid var(--line);padding-top:12px;line-height:1.7}
main{overflow:auto;padding:16px 20px 40px}
.banner{font-size:12px;color:var(--mute);background:var(--soft);border-radius:8px;padding:8px 12px;margin-bottom:14px}
details{margin-bottom:18px}summary{list-style:none;cursor:pointer;display:flex;align-items:baseline;gap:10px;padding:4px 0 10px}
summary::-webkit-details-marker{display:none}summary h3{margin:0;font-size:13px;font-weight:600}summary .c{color:var(--mute);font-size:12px}
summary::before{content:"▾";color:var(--mute);font-size:11px}details:not([open]) summary::before{content:"▸"}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 12px 8px;min-width:0}
.panel header{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px}
.panel h5{margin:0;font-size:12.5px;font-weight:600}.panel .key{font:11px "JetBrains Mono";color:var(--mute)}
.panel .hint{font-size:11.5px;color:var(--mute);margin:0 0 6px}
.lg{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:11.5px;min-height:18px;color:var(--mute)}.lg span{white-space:nowrap}
.lg b{font:500 11.5px "JetBrains Mono";color:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:12px;background:var(--panel);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}th{font-weight:500;color:var(--mute);font-size:11.5px;background:var(--soft)}
td.n,th.n{text-align:right;font-family:"JetBrains Mono"}tr:last-child td{border-bottom:0}
.st{font-size:11px;padding:2px 7px;border-radius:99px;background:var(--soft)}.st.run{color:var(--pos)}
"""

A_HTML = r"""
<div class="app">
 <header class="top">
  <div class="logo"><b>AG</b>AuditGym</div>
  <div class="crumb">auditgym-rl / <span>рабочая область</span></div>
  <nav class="tabs" role="tablist"><button role="tab" aria-selected="true">Графики</button><button role="tab">Запуски</button><button role="tab">Эпизоды</button><button role="tab">Система</button></nav>
  <div class="sp"></div>
  <div class="state"><span class="live"></span><span id="st">1 запуск идёт · итерация 25/40</span></div>
  <button class="btn pri">Новый запуск</button>
 </header>
 <aside class="rail">
  <input class="search" placeholder="Фильтр запусков" aria-label="Фильтр запусков">
  <div><h4><span>ЗАПУСКИ</span><span>dev</span></h4><div id="runs"></div></div>
  <div><h4><span>ЭТАЛОНЫ (реальные, report.json)</span></h4><div id="refs"></div></div>
  <div class="ctl"><h4 style="grid-column:1/-1;margin:0"><span>ОТОБРАЖЕНИЕ</span></h4>
   <span>Сглаживание</span><span class="mono" id="smv">0.6</span><input type="range" id="sm" min="0" max="0.95" step="0.05" value="0.6" aria-label="Сглаживание">
   <span>Ось X</span><select aria-label="Ось X"><option>итерация</option><option>эпизоды</option><option>время</option></select>
  </div>
  <div class="envbox mono">env 1.0.0 · schema 1.0<br>train: свежие сиды (не dev)<br>dev: 10 эпизодов · закрытый режим<br>127.0.0.1 · офлайн</div>
 </aside>
 <main>
  <div class="banner">Кривые обучения — иллюстрация, пока нет <span class="mono">train/curve.json</span> (T10). Эталонные линии oracle / reconcile / random — реальные.</div>
  <details open><summary><h3>Оценка на dev</h3><span class="c">отложенные эпизоды, агент не видит награду · 4 графика</span></summary>
   <div class="grid2">
    <div class="panel"><header><h5>Награда на dev</h5><span class="key">eval/reward</span></header><p class="hint">Главная метрика: выше — лучше, 1.00 — идеально.</p><div id="g-dev"></div><div class="lg" id="l-dev"></div></div>
    <div class="panel"><header><h5>F1 находок</h5><span class="key">eval/f1</span></header><p class="hint">Баланс точности и полноты найденных ошибок.</p><div id="g-f1"></div><div class="lg" id="l-f1"></div></div>
    <div class="panel"><header><h5>Шагов на эпизод</h5><span class="key">eval/steps</span></header><p class="hint">Бюджет 100. Меньше шагов при той же награде — эффективнее.</p><div id="g-steps"></div><div class="lg" id="l-steps"></div></div>
    <div class="panel"><header><h5>Ложные находки на эпизод</h5><span class="key">eval/fp</span></header><p class="hint">Каждая ложная находка снижает награду.</p><div id="g-fp"></div><div class="lg" id="l-fp"></div></div>
   </div></details>
  <details open><summary><h3>Обучение</h3><span class="c">новые сгенерированные эпизоды · 3 графика</span></summary>
   <div class="grid3">
    <div class="panel"><header><h5>Награда на train</h5><span class="key">train/reward</span></header><div id="g-train"></div><div class="lg" id="l-train"></div></div>
    <div class="panel"><header><h5>Недопустимые действия</h5><span class="key">train/invalid</span></header><div id="g-inv"></div><div class="lg" id="l-inv"></div></div>
    <div class="panel"><header><h5>Разброс параметров σ</h5><span class="key">train/sigma</span></header><div id="g-sig"></div><div class="lg" id="l-sig"></div></div>
   </div></details>
  <details open><summary><h3>Запуски</h3><span class="c">последняя оценка на dev</span></summary>
   <table><thead><tr><th>Запуск</th><th>Метод</th><th class="n">Сид</th><th class="n">Итерация</th><th class="n">Награда dev</th><th class="n">F1</th><th class="n">Шагов</th><th class="n">FP</th><th>Статус</th></tr></thead><tbody id="tb"></tbody></table>
  </details>
 </main>
</div>
"""

A_JS = r"""
const on = new Set(D.runs.map(r => r.id)); let SM = 0.6;
const runsEl = document.getElementById("runs"), refsEl = document.getElementById("refs");
function legendFor(id, key, fmt) { const L = document.getElementById(id); return (x, vals) => {
  if (x == null) { L.innerHTML = D.runs.filter(r => on.has(r.id)).map(r => { const v = rowsOf(r).at(-1)[key]; return `<span><i class="dot" style="background:var(--${r.color})"></i> ${r.id.replace("learn_rules-", "")} <b>${fmt(v)}</b></span>`; }).join(""); return; }
  L.innerHTML = `<span>итерация <b>${x}</b></span>` + vals.map(([se, v]) => `<span><i class="dot" style="background:${se.color}"></i> ${se.name} <b>${fmt(v)}</b></span>`).join(""); }; }
function draw(anim) {
  BUS.length = 0;
  const ser = (key) => D.runs.filter(r => on.has(r.id)).flatMap(r => { const pts = rowsOf(r).map(q => [q.i, q[key]]);
    const c = css("--" + r.color); return SM ? [{ name: r.id.replace("learn_rules-", ""), color: c, pts: pts, raw: 1, w: 1.2 }, { name: r.id.replace("learn_rules-", ""), color: c, pts: smooth(pts, SM), head: r.status === "running" }]
      : [{ name: r.id.replace("learn_rules-", ""), color: c, pts, head: r.status === "running" }]; });
  const B = Object.fromEntries(D.baselines.map(b => [b.id, b]));
  chart(document.getElementById("g-dev"), { series: ser("dev"), xmax: D.iters, ymin: -1.05, ymax: 1.05, yticks: [-1, -0.5, 0, 0.5, 1], animate: anim, h: 190,
    refs: [{ y: B.reconcile.reward, label: "reconcile " + f2(B.reconcile.reward) }, { y: B.random.reward, label: "random −1.00" }], legend: legendFor("l-dev", "dev", f2) });
  chart(document.getElementById("g-f1"), { series: ser("f1"), xmax: D.iters, ymin: 0, ymax: 1.02, yticks: [0, .25, .5, .75, 1], animate: anim, h: 190, refs: [{ y: 1, label: "reconcile 1.00" }], legend: legendFor("l-f1", "f1", f2) });
  chart(document.getElementById("g-steps"), { series: ser("steps"), xmax: D.iters, ymin: 0, ymax: 80, yticks: [0, 20, 40, 60, 80], fmt: v => v, animate: anim, h: 160, refs: [{ y: B.reconcile.steps, label: "reconcile " + B.reconcile.steps }], legend: legendFor("l-steps", "steps", f1) });
  chart(document.getElementById("g-fp"), { series: ser("fp"), xmax: D.iters, ymin: 0, ymax: 8, yticks: [0, 2, 4, 6, 8], fmt: v => v, animate: anim, h: 160, refs: [{ y: 0, label: "reconcile 0" }], legend: legendFor("l-fp", "fp", f1) });
  chart(document.getElementById("g-train"), { series: ser("train"), xmax: D.iters, ymin: -1.05, ymax: 1.05, yticks: [-1, 0, 1], animate: anim, h: 140, legend: legendFor("l-train", "train", f2) });
  chart(document.getElementById("g-inv"), { series: ser("invalid"), xmax: D.iters, ymin: 0, ymax: .3, yticks: [0, .1, .2, .3], animate: anim, h: 140, legend: legendFor("l-inv", "invalid", f2) });
  chart(document.getElementById("g-sig"), { series: ser("sigma"), xmax: D.iters, ymin: 0, ymax: 1, yticks: [0, .5, 1], animate: anim, h: 140, legend: legendFor("l-sig", "sigma", f2) });
  document.getElementById("tb").innerHTML = D.runs.map(r => { const q = rowsOf(r).at(-1); return `<tr><td class="mono"><i class="dot" style="background:var(--${r.color})"></i> ${r.id}</td><td>${r.method}</td><td class="n">${r.seed}</td><td class="n">${r.at}/${D.iters}</td><td class="n">${f2(q.dev)}</td><td class="n">${f2(q.f1)}</td><td class="n">${f1(q.steps)}</td><td class="n">${f1(q.fp)}</td><td><span class="st ${r.status === "running" ? "run" : ""}">${r.status === "running" ? "● идёт" : "готово"}</span></td></tr>`; }).join("")
   + D.baselines.map(b => `<tr><td class="mono" style="color:var(--mute)">${b.id}</td><td>эталон</td><td class="n">—</td><td class="n">—</td><td class="n">${f2(b.reward)}</td><td class="n">—</td><td class="n">${b.steps || "—"}</td><td class="n">—</td><td><span class="st">${b.note}</span></td></tr>`).join("");
}
runsEl.innerHTML = D.runs.map(r => `<label class="run ${r.color}"><input type="checkbox" checked data-id="${r.id}" aria-label="${r.id}"><div><div class="nm">${r.id}</div><div class="meta">${r.method} · сид ${r.seed} · ${r.status === "running" ? "<span style='color:var(--pos)'>идёт " + r.at + "/" + D.iters + "</span>" : "готово"}</div></div><span class="v" data-v="${r.id}"></span></label>`).join("");
refsEl.innerHTML = D.baselines.map(b => `<label class="run ref"><input type="checkbox" checked disabled aria-label="${b.id}"><div><div class="nm">${b.id}</div><div class="meta">${b.note}</div></div><span class="v">${f2(b.reward)}</span></label>`).join("");
function vals() { D.runs.forEach(r => document.querySelector(`[data-v="${r.id}"]`).textContent = f2(rowsOf(r).at(-1).dev)); }
runsEl.addEventListener("change", e => { const id = e.target.dataset.id; e.target.checked ? on.add(id) : on.delete(id); draw(false); });
document.getElementById("sm").addEventListener("input", e => { SM = +e.target.value; document.getElementById("smv").textContent = SM.toFixed(2); draw(false); });
vals(); draw(true);
addEventListener("resize", () => draw(false));
// the running run advances one iteration every 2.4 s
const live = D.runs.find(r => r.status === "running");
if (!RM) setInterval(() => { if (live.at >= D.iters) return; live.at++; document.getElementById("st").textContent = `1 запуск идёт · итерация ${live.at}/${D.iters}`; vals(); draw(false); }, 2400);
"""

# ======================================================================= B: training console
B_CSS = r"""
.app{display:grid;grid-template-columns:232px 1fr;height:100vh}
.side{background:var(--panel);border-right:1px solid var(--line);padding:14px 10px;display:flex;flex-direction:column;gap:4px;overflow:auto}
.logo{font-weight:600;display:flex;align-items:center;gap:8px;padding:2px 8px 14px}.logo b{font:600 12px "JetBrains Mono";border:1.5px solid var(--ink);border-radius:4px;padding:0 4px}
.side h6{margin:14px 8px 4px;font-size:10.5px;font-weight:500;color:var(--mute);letter-spacing:.06em}
.side a{display:flex;justify-content:space-between;align-items:center;padding:6px 8px;border-radius:6px;color:var(--ink2);text-decoration:none}
.side a:hover{background:var(--soft)}.side a[aria-current]{background:var(--soft);color:var(--ink);font-weight:500}
.side a small{color:var(--mute);font:11px "JetBrains Mono"}.side .ok{color:var(--pos)}
.foot{margin-top:auto;font:11px/1.7 "JetBrains Mono";color:var(--mute);padding:10px 8px 0;border-top:1px solid var(--line)}
main{overflow:auto;padding:18px 28px 40px;position:relative}
.head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.crumb{color:var(--mute)}.crumb span{color:var(--ink);font-family:"JetBrains Mono"}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;padding:3px 10px;border-radius:99px;background:color-mix(in srgb,var(--pos) 12%,transparent);color:var(--pos);font-weight:500}
.sp{flex:1}.btn{border:1px solid var(--line2);background:var(--panel);border-radius:7px;padding:6px 12px;font-weight:500}.btn.pri{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.tabs{display:flex;gap:18px;border-bottom:1px solid var(--line);margin:14px 0 18px}.tabs button{border:0;background:none;padding:8px 0;color:var(--mute);border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs button[aria-selected=true]{color:var(--ink);border-color:var(--ink);font-weight:500}
.row{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:16px;align-items:start}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px}
.big{display:flex;align-items:baseline;gap:14px}.big .pct{font:600 44px/1 "JetBrains Mono";letter-spacing:-.03em}.big .sub{color:var(--mute)}
.bar{display:grid;grid-template-columns:repeat(40,1fr);gap:2px;margin:12px 0 18px}.bar i{height:8px;border-radius:2px;background:var(--line)}.bar i.d{background:var(--ink)}.bar i.n{background:var(--ink);animation:pulse 1.4s infinite}
.card h3{margin:0 0 2px;font-size:14px;font-weight:600}.card p.cap{margin:0 0 10px;color:var(--mute);font-size:12.5px;max-width:70ch}
.lg{display:flex;gap:16px;font-size:12px;color:var(--mute);margin-top:4px;flex-wrap:wrap}.lg b{font:500 12px "JetBrains Mono";color:var(--ink)}
dl{display:grid;grid-template-columns:auto 1fr;gap:9px 14px;margin:0;font-size:12.5px}dt{color:var(--mute)}dd{margin:0;text-align:right;font-family:"JetBrains Mono";font-size:12px;white-space:nowrap}dt{white-space:nowrap}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:16px}.tile{background:var(--soft);border-radius:9px;padding:10px 12px}
.tile .v{font:600 20px "JetBrains Mono";letter-spacing:-.02em}.tile .k{font-size:11.5px;color:var(--mute)}
.tile .d{font:11px "JetBrains Mono";color:var(--mute)}
.acts{display:flex;flex-direction:column;gap:8px;margin-top:16px}.acts .btn{width:100%;text-align:center}
h2.sec{font-size:14px;margin:26px 0 4px;font-weight:600}.sec+p{margin:0 0 12px;color:var(--mute);font-size:12.5px}
.eps{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.ep{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.ep .t{display:flex;justify-content:space-between;font-size:11.5px;color:var(--mute)}.ep .t b{font:500 11px "JetBrains Mono";color:var(--ink2)}
.ep .r{font:600 18px "JetBrains Mono";margin:6px 0 6px}.ep .m{height:4px;border-radius:2px;background:var(--line);position:relative;overflow:hidden}
.ep .m i{position:absolute;top:0;bottom:0;left:50%;background:var(--ink)}.ep .m i.neg{background:var(--neg)}
.ep .s{font-size:11px;color:var(--mute);margin-top:6px}
.cmp{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:4px}.cmp td{padding:7px 0;border-bottom:1px solid var(--line)}.cmp td.n{text-align:right;font-family:"JetBrains Mono"}
.cmp .barc{width:46%;padding:0 14px}.cmp .bb{height:6px;border-radius:3px;background:var(--line);position:relative}.cmp .bb i{position:absolute;top:0;bottom:0;border-radius:3px}
.illus{margin-top:8px}
.drawer{position:fixed;top:0;right:0;bottom:0;width:400px;background:var(--panel);border-left:1px solid var(--line);box-shadow:-16px 0 40px rgba(0,0,0,.08);
 padding:20px 22px;overflow:auto;transform:translateX(100%);transition:transform .28s cubic-bezier(.3,.7,.2,1)}
.drawer.open{transform:none}.drawer h3{margin:0 0 4px;font-size:16px}.drawer>p{margin:0 0 16px;color:var(--mute);font-size:12.5px}
.opt{display:block;border:1px solid var(--line2);border-radius:10px;padding:10px 12px;margin-bottom:8px;cursor:pointer}
.opt:has(input:checked){border-color:var(--ink);box-shadow:0 0 0 1px var(--ink)}.opt input{margin-right:8px;accent-color:var(--ink)}
.opt b{font-weight:600}.opt small{display:block;color:var(--mute);margin:2px 0 0 22px;font-size:12px}
.fld{display:grid;grid-template-columns:1fr 120px;align-items:center;gap:10px;margin:10px 0}.fld label{font-size:12.5px}.fld label small{display:block;color:var(--mute);font-size:11.5px}
.fld input,.fld select{font:12px "JetBrains Mono";border:1px solid var(--line2);border-radius:7px;padding:6px 8px;background:var(--bg);color:var(--ink);width:100%}
.fld input[disabled]{opacity:.7}
.grp{font-size:10.5px;letter-spacing:.06em;color:var(--mute);margin:18px 0 4px;font-weight:500}
.cmd{font:12px/1.5 "JetBrains Mono";background:var(--soft);border-radius:8px;padding:10px 12px;margin:14px 0;white-space:pre-wrap;overflow-wrap:break-word}
.cmd::before{content:"Та же команда в терминале";display:block;font:500 10.5px Inter;letter-spacing:.04em;color:var(--mute);margin-bottom:4px}
"""

B_HTML = r"""
<div class="app">
 <nav class="side" aria-label="Разделы">
  <div class="logo"><b>AG</b>AuditGym</div>
  <h6>СРЕДА</h6>
  <a href="#">Эпизоды <small>10 + 10</small></a>
  <a href="#">Проверка среды <small class="ok">100/100 ✓</small></a>
  <h6>ОБУЧЕНИЕ</h6>
  <a href="#" aria-current="page">Запуски <small>3</small></a>
  <a href="#" id="newrun">Новый запуск <small>N</small></a>
  <h6>ОЦЕНКА АГЕНТОВ</h6>
  <a href="#">Подключить агента</a>
  <a href="#">Таблица результатов</a>
  <h6>ОТЧЁТ</h6>
  <a href="#">report.json</a>
  <div class="foot">офлайн · 127.0.0.1<br>env 1.0.0 · schema 1.0<br>python 3.11</div>
 </nav>
 <main>
  <div class="head"><div class="crumb">Обучение / <span>learn_rules-cem-s1</span></div><span class="pill"><span class="live"></span>Идёт обучение</span><div class="sp"></div>
   <button class="btn">Остановить</button><button class="btn pri" id="nr2">Новый запуск</button></div>
  <nav class="tabs" role="tablist"><button role="tab" aria-selected="true">Обзор</button><button role="tab">Эпизоды</button><button role="tab">Журнал</button><button role="tab">Конфигурация</button></nav>
  <div class="row">
   <section class="card">
    <div class="big"><span class="pct" id="pct">62%</span><span class="sub" id="psub">итерация 25 из 40 · осталось ≈ 4 мин</span></div>
    <div class="bar" id="bar" aria-hidden="true"></div>
    <h3>Награда на отложенных эпизодах</h3>
    <p class="cap">Агент учится на новых сгенерированных эпизодах и ни разу не видит эти 10. Пунктир — с чем сравнивать: правила, написанные вручную (reconcile), и случайный агент.</p>
    <div id="g"></div>
    <div class="lg" id="lg"></div>
    <div class="illus">Кривая — иллюстрация до T10 (<span class="mono">train/curve.json</span>). Эталоны — реальные.</div>
   </section>
   <aside class="card">
    <dl>
     <dt>Статус</dt><dd style="color:var(--pos)">идёт</dd>
     <dt>Длительность</dt><dd id="dur">6 мин 15 с</dd>
     <dt>Метод</dt><dd>CEM · 24 параметра</dd>
     <dt>Сид</dt><dd>1</dd>
     <dt>Обучение на</dt><dd>свежих сидах</dd>
     <dt>Оценка</dt><dd>10 dev · закрытый</dd>
     <dt>Награда видна агенту</dt><dd>только train</dd>
     <dt>Версия среды</dt><dd>1.0.0</dd>
    </dl>
    <div class="tiles">
     <div class="tile"><div class="k">Награда dev</div><div class="v" id="t-dev">0.62</div><div class="d" id="t-dd">+0.04 за итерацию</div></div>
     <div class="tile"><div class="k">F1</div><div class="v" id="t-f1">0.80</div><div class="d">из 1.00</div></div>
     <div class="tile"><div class="k">Шагов</div><div class="v" id="t-st">29</div><div class="d">бюджет 100</div></div>
     <div class="tile"><div class="k">Ложных</div><div class="v" id="t-fp">0.9</div><div class="d">на эпизод</div></div>
    </div>
    <div class="acts"><button class="btn">Открыть отчёт</button><button class="btn">Экспорт curve.json</button></div>
   </aside>
  </div>
  <h2 class="sec">Эпизоды dev на последней оценке</h2><p>Тип эпизода берётся только из публичной конфигурации. Ответы и разметка ошибок не показываются.</p>
  <div class="eps" id="eps"></div>
  <h2 class="sec">Сравнение</h2><p>Средняя награда на dev. Эталоны посчитаны на реальных прогонах (report.json).</p>
  <div class="card" style="padding:8px 18px"><table class="cmp" id="cmp"></table></div>
 </main>
 <aside class="drawer" id="drawer" aria-label="Новый запуск">
  <h3>Новый запуск</h3><p>Что будем запускать? Результат появится в «Запусках», а оценка всегда идёт на 10 отложенных эпизодах.</p>
  <label class="opt"><input type="radio" name="k"><b>Обучить встроенного аудитора</b><small>Небольшая модель правил, учится за ≈ 10 мин на ноутбуке</small></label>
  <label class="opt"><input type="radio" name="k" checked><b>Проверить своего агента</b><small>Любая программа: общается со средой через stdin/stdout</small></label>
  <label class="opt"><input type="radio" name="k"><b>Базовая политика</b><small>oracle, reconcile или random — для сравнения</small></label>
  <div class="grp">АГЕНТ</div>
  <div class="fld" style="grid-template-columns:1fr"><label>Команда<small>любая программа, которая читает наблюдения из stdin и пишет действия в stdout</small></label><input value="python examples/llm_agent.py" aria-label="Команда"></div>
  <div class="fld"><label>Модель<small>локально через Ollama</small></label><select aria-label="Модель"><option>qwen2.5:1.5b</option><option>llama3.2:3b</option></select></div>
  <div class="fld"><label>Температура<small>0 — всегда одинаково</small></label><input type="number" value="0.2" step="0.1" min="0" max="2" aria-label="Температура"></div>
  <div class="fld"><label>Макс. токенов на шаг</label><input type="number" value="512" step="64" aria-label="Макс. токенов на шаг"></div>
  <div class="grp">ОЦЕНКА</div>
  <div class="fld"><label>Эпизоды<small>отложенные, агент их не видел</small></label><select aria-label="Эпизоды"><option>dev · 10</option><option>train · 10</option></select></div>
  <div class="fld"><label>Режим<small>агент не видит награду</small></label><input value="закрытый" disabled aria-label="Режим"></div>
  <div class="fld"><label>Шагов на эпизод<small>бюджет среды</small></label><input value="100" disabled aria-label="Шагов на эпизод"></div>
  <div class="cmd">python -m auditgym.cli run-agent --cmd "python examples/llm_agent.py --model qwen2.5:1.5b --temperature 0.2 --max-tokens 512" --split dev</div>
  <div style="display:flex;gap:8px"><button class="btn" id="cancel" style="flex:1">Отмена</button><button class="btn pri" style="flex:2">Запустить</button></div>
 </aside>
</div>
"""

B_JS = r"""
const run = D.runs[0]; const B = Object.fromEntries(D.baselines.map(b => [b.id, b]));
function render(anim) {
  BUS.length = 0;
  const rows = rowsOf(run), last = rows.at(-1), prev = rows.at(-2);
  const pct = Math.round(run.at / D.iters * 100);
  document.getElementById("pct").textContent = pct + "%";
  document.getElementById("psub").textContent = `итерация ${run.at} из ${D.iters} · осталось ≈ ${Math.max(0, Math.round((D.iters - run.at) * 0.25))} мин`;
  document.getElementById("bar").innerHTML = Array.from({ length: D.iters }, (_, i) => `<i class="${i < run.at ? "d" : i === run.at ? "n" : ""}"></i>`).join("");
  const pts = rows.map(q => [q.i, q.dev]);
  const lg = document.getElementById("lg");
  chart(document.getElementById("g"), { series: [{ name: "dev", color: css("--c1"), pts: pts, raw: 1, w: 1.2 }, { name: "этот запуск", color: css("--c1"), pts: smooth(pts, 0.5), head: 1, w: 2.2 }],
    xmax: D.iters, ymin: -1.05, ymax: 1.05, yticks: [-1, -0.5, 0, 0.5, 1], h: 250, animate: anim,
    refs: [{ y: B.reconcile.reward, label: "reconcile (правила) " + f2(B.reconcile.reward) }, { y: B.random.reward, label: "random −1.00" }],
    legend: (x, v) => { lg.innerHTML = x == null ? `<span>итерация <b>${run.at}</b></span><span>награда dev <b>${f2(last.dev)}</b></span><span>train <b>${f2(last.train)}</b></span>`
      : `<span>итерация <b>${x}</b></span>` + v.map(([s, y]) => `<span>${s.name} <b>${f2(y)}</b></span>`).join(""); } });
  document.getElementById("t-dev").textContent = f2(last.dev);
  const dd = last.dev - prev.dev; document.getElementById("t-dd").textContent = "Δ " + (dd >= 0 ? "+" : "−") + Math.abs(dd).toFixed(2) + " за итерацию";
  document.getElementById("t-f1").textContent = f2(last.f1); document.getElementById("t-st").textContent = Math.round(last.steps); document.getElementById("t-fp").textContent = f1(last.fp);
  const s = run.at * 15; document.getElementById("dur").textContent = `${Math.floor(s / 60)} мин ${s % 60} с`;
  const rowsC = [["oracle", B.oracle.reward, "var(--base)", "знает ответ — потолок"], ["reconcile", B.reconcile.reward, "var(--base)", "правила, написанные вручную"],
    ["learn_rules-cem-s1", last.dev, "var(--c1)", "этот запуск, итерация " + run.at], ["random", B.random.reward, "var(--base)", "случайные действия"]];
  document.getElementById("cmp").innerHTML = rowsC.map(([n, v, c, note]) => `<tr><td><span class="mono">${n}</span><br><small style="color:var(--mute)">${note}</small></td><td class="barc"><div class="bb"><i style="left:${v < 0 ? (50 + v * 50) : 50}%;width:${Math.abs(v) * 50}%;background:${c}"></i><i style="left:50%;width:1px;background:var(--mute)"></i></div></td><td class="n">${f2(v)}</td></tr>`).join("");
}
document.getElementById("eps").innerHTML = D.dev.map(e => `<div class="ep"><div class="t"><span>${e.label}</span><b>#${e.seed}</b></div><div class="r">${f2(e.reward)}</div><div class="m"><i class="${e.reward < 0 ? "neg" : ""}" style="${e.reward < 0 ? `left:${50 + e.reward * 50}%;width:${-e.reward * 50}%` : `width:${e.reward * 50}%`}"></i></div><div class="s">${e.steps} шагов</div></div>`).join("");
render(true); addEventListener("resize", () => render(false));
if (!RM) setInterval(() => { if (run.at < D.iters) { run.at++; render(false); } }, 2400);
const dr = document.getElementById("drawer");
for (const id of ["newrun", "nr2"]) document.getElementById(id).addEventListener("click", e => { e.preventDefault(); dr.classList.add("open"); });
document.getElementById("cancel").addEventListener("click", () => dr.classList.remove("open"));
addEventListener("keydown", e => { if (e.key === "Escape") dr.classList.remove("open"); if (e.key === "n" && e.target === document.body) dr.classList.add("open"); });
if (location.hash === "#new") dr.classList.add("open");
"""

# ======================================================================= C: terminal trace (ASCII motion)
C_CSS = r"""
:root{--tb:#0d0d0f;--tp:#141417;--tl:#26262b;--tx:#e6e6e9;--tm:#8e8e96;--td:#5c5c63;--tg:#4cc38a;--tr:#f0625a;--ty:#e5b454;--tc:#7aa7f7}
body{background:var(--tb);color:var(--tx);font:13px/1.5 "JetBrains Mono",ui-monospace,monospace}
.term{display:grid;grid-template-rows:auto 1fr auto;height:100vh}
.bar{display:flex;gap:18px;align-items:center;padding:8px 16px;border-bottom:1px solid var(--tl);background:var(--tp);white-space:nowrap;overflow:hidden}
.bar .b{font-weight:600}.bar .m{color:var(--tm)}.bar .g{color:var(--tg)}.sp{flex:1}
.cols{display:grid;grid-template-columns:290px minmax(0,1fr) 440px;min-height:0}
.pane{border-right:1px solid var(--tl);overflow:hidden;display:flex;flex-direction:column;min-height:0}.pane:last-child{border-right:0}
.pane h4{margin:0;padding:10px 14px 6px;font-size:11px;font-weight:600;color:var(--tm);letter-spacing:.08em;display:flex;justify-content:space-between}
.pane h4 span:last-child{color:var(--td);font-weight:400}
.list{padding:0 8px 8px}.it{display:grid;grid-template-columns:14px 1fr auto;gap:8px;padding:3px 6px;border-radius:4px;white-space:nowrap}
.it.cur{background:#1d1d22}.it .s{color:var(--td)}.it.ok .s{color:var(--tg)}.it.cur .s{color:var(--ty)}
.it .r{color:var(--tm)}.it .bars{color:var(--tg);letter-spacing:-1px}.it .bars i{color:var(--tl);font-style:normal}
.sub{color:var(--td);font-size:11.5px;padding:0 14px}
.stream{flex:1;overflow:hidden;padding:4px 16px 12px;position:relative}
.ln{display:grid;grid-template-columns:38px 110px minmax(0,1fr) 190px;gap:10px;white-space:nowrap;opacity:0;transform:translateY(4px);transition:opacity .25s,transform .25s}
.ln.in{opacity:1;transform:none}.ln .n{color:var(--td)}.ln .t{color:var(--tc)}.ln .a{color:var(--tx);overflow:hidden;text-overflow:ellipsis}.ln .k{color:var(--tm);text-align:right}
.ln.sub2 .t{color:var(--ty)}.res{margin-top:10px;border:1px solid var(--tl);border-radius:6px;padding:10px 12px;opacity:0;transition:opacity .4s}.res.in{opacity:1}
.res .g{color:var(--tg)}.res .m{color:var(--tm)}
.art{position:absolute;right:12px;bottom:8px;color:var(--td);font-size:9px;line-height:9px;white-space:pre;pointer-events:none}
.budget{display:flex;align-items:center;gap:10px;padding:2px 16px 8px;color:var(--tm);font-size:12px}
.budget .odo{color:var(--tx)}
.odo{display:inline-flex;overflow:hidden;height:1.15em;line-height:1.15em;vertical-align:bottom}.odo .reel span{display:block;height:1.15em}.odo .reel{display:flex;flex-direction:column;transition:transform .6s cubic-bezier(.3,.7,.2,1)}
.big{padding:4px 14px 2px;display:flex;align-items:baseline;gap:12px}.big .odo{font-size:44px;height:1.15em;line-height:1.15em;font-weight:600;letter-spacing:-.04em}
.big .m{color:var(--tm);font-size:12px}
pre.plot{margin:0;padding:6px 14px 4px;font-size:12px;line-height:13px;color:var(--tm)}
pre.plot .y{color:var(--td)}pre.plot .c{color:var(--tc)}pre.plot .b{color:var(--ty)}pre.plot .r{color:var(--tr)}
.kv{padding:2px 14px;font-size:12px;color:var(--tm)}.kv b{color:var(--tx);font-weight:400}
.rec{padding:0 14px 8px;font-size:12px}.rec div{display:grid;grid-template-columns:170px 1fr 52px;gap:8px;white-space:nowrap}
.rec .k{color:var(--tm)}.rec .v{color:var(--tg);letter-spacing:-1px}.rec .v i{color:var(--tl);font-style:normal}.rec .n{text-align:right;color:var(--tx)}
.cmdl{border-top:1px solid var(--tl);background:var(--tp);padding:8px 16px;display:flex;flex-direction:column;gap:4px}
.cmdl .p{color:var(--tg)}.caret{display:inline-block;width:8px;height:15px;background:var(--tx);vertical-align:-2px;animation:blink 1s steps(1) infinite}
@keyframes blink{50%{opacity:0}}.keys{color:var(--td);font-size:12px}.keys b{color:var(--tm);font-weight:400}
.illus{color:var(--td);font-size:11px;padding:2px 14px 8px}
"""

C_HTML = r"""
<div class="term">
 <div class="bar"><span class="b">AUDITGYM</span><span class="m">run-agent ▸ reconcile ▸ dev [закрытый режим]</span><span class="g">● live</span><span class="sp"></span>
  <span class="m">эпизод <span id="epn">5</span>/9</span><span class="m">127.0.0.1:8000</span><span class="m">env 1.0.0</span></div>
 <div class="cols">
  <section class="pane">
   <h4><span>ЭПИЗОДЫ DEV</span><span>reconcile</span></h4>
   <div class="list" id="eps"></div>
   <h4><span>ЗАПУСКИ</span><span>обучение</span></h4>
   <div class="list" id="runs"></div>
   <div class="sub" style="margin-top:auto;padding-bottom:12px">Тип эпизода — из публичной конфигурации. Ответы не показываются.</div>
  </section>
  <section class="pane">
   <h4><span>ТРАЕКТОРИЯ <span style="color:var(--tx)" id="epid"></span></span><span>шаг · инструмент · аргументы · результат</span></h4>
   <div class="budget">бюджет шагов <span class="odo" id="odo-b"></span> / 100 <span id="bbar" style="color:var(--tg);letter-spacing:-1px"></span></div>
   <div class="stream" id="stream"><pre class="art" id="art" aria-hidden="true"></pre></div>
  </section>
  <section class="pane">
   <h4><span>НАГРАДА ЭПИЗОДА</span><span>после submit</span></h4>
   <div class="big"><span class="odo" id="odo-r"></span><span class="m" id="rm">ждём submit…</span></div>
   <div class="kv" id="kv">&nbsp;</div>
   <h4><span>ОБУЧЕНИЕ learn_rules-cem-s1</span><span>dev награда / итерация</span></h4>
   <pre class="plot" id="plot"></pre>
   <div class="illus">кривая — иллюстрация до T10 · эталоны реальные</div>
   <h4><span>ПОЛНОТА ПО ТИПАМ ОШИБОК</span><span>reconcile, весь dev</span></h4>
   <div class="rec" id="rec"></div>
  </section>
 </div>
 <div class="cmdl">
  <div><span class="p">$</span> python -m auditgym.cli run-agent --cmd "python -m auditgym.policies.reconcile" --split dev <span class="caret"></span></div>
  <div class="keys"><b>n</b> новый запуск · <b>p</b> пауза · <b>←→</b> эпизоды · <b>r</b> отчёт · <b>t</b> обучение · <b>?</b> помощь · <b>q</b> выход</div>
 </div>
</div>
"""

C_JS = r"""
// odometer: each digit is a reel of 0-9 that rolls to its value
function odo(host, text) { host.innerHTML = ""; for (const ch of text) { if (!/[0-9]/.test(ch)) { const s = document.createElement("span"); s.textContent = ch; host.appendChild(s); continue; }
  const w = document.createElement("span"); w.className = "odo"; const r = document.createElement("span"); r.className = "reel"; r.innerHTML = "0123456789".split("").map(d => `<span>${d}</span>`).join("");
  w.appendChild(r); host.appendChild(w); requestAnimationFrame(() => requestAnimationFrame(() => r.style.transform = `translateY(${-(+ch) * 1.15}em)`)); } }
function odoSet(host, text) { const reels = host.querySelectorAll(".reel"); const digits = text.replace(/[^0-9]/g, "");
  if (reels.length !== digits.length) return odo(host, text); reels.forEach((r, i) => r.style.transform = `translateY(${-(+digits[i]) * 1.15}em)`); }
const blocks = (v, n) => { const k = Math.round(Math.max(0, Math.min(1, v)) * n); return "█".repeat(k) + "<i>" + "░".repeat(n - k) + "</i>"; };
const TABLES = { fx: "курсы", invoices: "счета", payments: "платежи", ledger: "главная книга" };
const eps = D.recon_runs; const curIdx = eps.findIndex(e => e.episode === D.episode);
document.getElementById("eps").innerHTML = eps.map((e, i) => `<div class="it ${i < curIdx ? "ok" : i === curIdx ? "cur" : ""}"><span class="s">${i < curIdx ? "✓" : i === curIdx ? "▶" : "·"}</span><span>${e.episode.slice(0, 11)}…</span><span class="${i < curIdx ? "bars" : "r"}">${i < curIdx ? blocks(e.reward, 6) + " " + e.reward.toFixed(2) : i === curIdx ? "идёт" : "в очереди"}</span></div>`).join("");
document.getElementById("runs").innerHTML = D.runs.map(r => `<div class="it ${r.status === "running" ? "cur" : "ok"}"><span class="s">${r.status === "running" ? "▶" : "✓"}</span><span>${r.id.replace("learn_rules-", "")}</span><span class="r">${r.at}/${D.iters}</span></div>`).join("");
document.getElementById("epid").textContent = D.episode;
// ASCII training plot: dev reward per iteration as columns, reconcile baseline as a dashed row
function plot(upto) {
  const run = D.runs[0], rows = run.rows.slice(0, upto + 1), H = 11, W = D.iters + 1;
  const B = D.baselines.find(b => b.id === "reconcile").reward;
  const yOf = v => Math.round((1 - (v + 1) / 2) * (H - 1));
  const g = Array.from({ length: H }, () => Array(W).fill(" "));
  for (let x = 0; x < W; x += 2) g[yOf(B)][x] = "<span class=b>-</span>";
  for (let x = 0; x < W; x++) g[yOf(0)][x] = g[yOf(0)][x] === " " ? "<span class=y>·</span>" : g[yOf(0)][x];
  rows.forEach((q, x) => { const top = yOf(q.dev); for (let y = top; y <= yOf(-1); y++) g[y][x] = y === top ? "<span class=c>█</span>" : "<span class=y>░</span>"; });
  const lab = y => { const v = 1 - 2 * y / (H - 1); return (v >= 0 ? " " : "") + v.toFixed(1).replace("-", "−"); };
  return g.map((r, y) => `<span class=y>${(y % 5 === 0 ? lab(y) : "    ").padStart(5)} │</span>${r.join("")}`).join("\n")
    + `\n<span class=y>      └${"─".repeat(W)}\n       0         10        20        30        40  итерация</span>\n<span class=c>█</span> learn_rules-cem-s1   <span class=b>- -</span> reconcile ${B.toFixed(2)}`;
}
const rec = D.recall, names = { duplicate_invoice: "дубликаты счетов", payment_allocation: "разнесение платежей", date_or_fx: "даты и курсы", period_classification: "период" };
document.getElementById("rec").innerHTML = Object.entries(rec).map(([k, v]) => `<div><span class="k">${names[k] || k}</span><span class="v">${blocks(v.found / v.issues, 14)}</span><span class="n">${v.found}/${v.issues}</span></div>`).join("");
// little rotating ASCII ledger block (SDF raymarch, same ramp as preview v4)
const RAMP = " .:-=+*#%@";
function art(t) { const C = 34, R = 15, out = []; const ca = Math.cos(t), sa = Math.sin(t), cb = Math.cos(.55), sb = Math.sin(.55);
  const sd = p => { let [x, y, z] = p; [x, z] = [x * ca - z * sa, x * sa + z * ca]; [y, z] = [y * cb - z * sb, y * sb + z * cb];
    const q = [Math.abs(x) - .9, Math.abs(y) - .55, Math.abs(z) - .7]; return Math.hypot(Math.max(q[0], 0), Math.max(q[1], 0), Math.max(q[2], 0)) + Math.min(Math.max(q[0], q[1], q[2]), 0) - .04; };
  for (let j = 0; j < R; j++) { let row = ""; for (let i = 0; i < C; i++) { const x = (i / C - .5) * 3.2, y = -(j / R - .5) * 2.4; let z = -3, hit = false;
    for (let k = 0; k < 28; k++) { const d = sd([x, y, z]); if (d < .01) { hit = true; break; } z += d; if (z > 3) break; }
    if (!hit) { row += " "; continue; } const e = .01, p = [x, y, z]; const n = [0, 1, 2].map(a => { const p1 = p.slice(), p2 = p.slice(); p1[a] += e; p2[a] -= e; return sd(p1) - sd(p2); });
    const L = Math.hypot(...n); const l = Math.max(0, (n[0] * -.45 + n[1] * .62 + n[2] * -.64) / L); row += RAMP[Math.min(9, 1 + Math.floor(l * 8.9))]; } out.push(row); }
  return out.join("\n"); }
let tA = 0; const artEl = document.getElementById("art");
function tickArt() { artEl.textContent = art(tA); tA += .045; }
// stream the real 16-step trajectory
const stream = document.getElementById("stream"); const odoB = document.getElementById("odo-b"), odoR = document.getElementById("odo-r");
odo(odoB, "100"); odo(odoR, "0.00");
let k = 0; let pl = 0; const plotEl = document.getElementById("plot");
function step() {
  if (k >= D.traj.length) return finish();
  const s = D.traj[k]; const d = document.createElement("div"); d.className = "ln" + (s.tool === "submit" ? " sub2" : "");
  const args = s.tool === "submit" ? `findings: ${D.submit.found} находок с доказательствами` : `table="${s.table}" cursor=${s.n > 1 && D.traj[k - 1].table === s.table ? "next" : "start"}`;
  const res = s.tool === "submit" ? "оценено" : `${s.rows} строк · ${TABLES[s.table]}`;
  d.innerHTML = `<span class="n">#${String(s.n).padStart(2, "0")}</span><span class="t">${s.tool}</span><span class="a">${args}</span><span class="k">${res}</span>`;
  stream.insertBefore(d, artEl); requestAnimationFrame(() => d.classList.add("in"));
  odoSet(odoB, String(s.left)); document.getElementById("bbar").innerHTML = blocks(s.left / 100, 20);
  k++;
}
function finish() {
  const r = D.submit; const res = document.createElement("div"); res.className = "res";
  res.innerHTML = `<span class="g">✓ оценено</span>  TP ${r.tp}  FP ${r.fp}  FN ${r.fn}   точность ${r.precision.toFixed(2)}  полнота ${r.recall.toFixed(2)}  F1 ${r.f1.toFixed(2)}<br><span class="m">награда = качество находок − штраф за шаги · ${D.traj.length} шагов из 100</span>`;
  stream.insertBefore(res, artEl); requestAnimationFrame(() => res.classList.add("in"));
  odoSet(odoR, r.reward.toFixed(2)); document.getElementById("rm").textContent = "из 1.00 · reconcile на этом эпизоде";
  document.getElementById("kv").innerHTML = `найдено <b>${r.found}</b> · подтверждено <b>${r.tp}</b> · ложных <b>${r.fp}</b> · пропущено <b>${r.fn}</b>`;
  const cur = document.querySelectorAll("#eps .it")[curIdx]; cur.className = "it ok";
  cur.innerHTML = `<span class="s">✓</span><span>${D.episode.slice(0, 11)}…</span><span class="bars">${blocks(r.reward, 6)} ${r.reward.toFixed(2)}</span>`;
  done = true;
}
let done = false;
if (RM) { while (k < D.traj.length) step(); finish(); plotEl.innerHTML = plot(D.runs[0].at); tickArt(); }
else {
  const iv = setInterval(() => { if (done) return clearInterval(iv); step(); }, 420);
  setInterval(tickArt, 60);
  const ip = setInterval(() => { plotEl.innerHTML = plot(pl); if (pl >= D.runs[0].at) clearInterval(ip); pl++; }, 70);
}
"""

out.mkdir(parents=True, exist_ok=True)
(out / "option-a-workspace.html").write_text(page("AuditGym · вариант A · рабочая область", A_CSS, A_HTML, A_JS), encoding="utf-8")
(out / "option-b-console.html").write_text(page("AuditGym · вариант B · консоль обучения", B_CSS, B_HTML, B_JS), encoding="utf-8")
(out / "option-c-terminal.html").write_text(page("AuditGym · вариант C · терминал", C_CSS, C_HTML, C_JS, theme="dark"), encoding="utf-8")
print("wrote 3 options to", out)
