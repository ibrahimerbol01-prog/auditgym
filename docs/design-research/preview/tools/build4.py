"""Preview v4: AuditGym home in an ASCII motion language (inspired by halftone 3D motion, rebuilt in characters).

Usage: python3 -I build4.py <repo_dir> <out_dir>      (reads data.json next to this script's output folder)

Everything is drawn live in plain JavaScript: a small ray-marcher renders 3D shapes (ledger block, coin, sphere)
as characters, numbers roll like an odometer, a character field reacts to the cursor, a big number dissolves in,
and a character landscape drifts in the footer. No libraries, no network. Under prefers-reduced-motion every
piece renders one still frame.
"""
import base64
import json
import sys
from pathlib import Path

repo, out = Path(sys.argv[1]), Path(sys.argv[2])
data = json.loads((out / "data.json").read_text())
fonts_dir = repo / "src" / "auditgym" / "ui" / "static" / "fonts"

FONTS = [("Inter", 400, "inter-latin-400-normal"), ("Inter", 400, "inter-cyrillic-400-normal"),
         ("Inter", 500, "inter-latin-500-normal"), ("Inter", 500, "inter-cyrillic-500-normal"),
         ("Inter", 600, "inter-latin-600-normal"), ("Inter", 600, "inter-cyrillic-600-normal"),
         ("Inter", 700, "inter-latin-700-normal"), ("Inter", 700, "inter-cyrillic-700-normal"),
         ("JetBrains Mono", 400, "jetbrains-mono-latin-400-normal"), ("JetBrains Mono", 400, "jetbrains-mono-cyrillic-400-normal")]
LATIN = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
CYR = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"
font_css = "\n".join(
    f'@font-face{{font-family:"{fam}";font-weight:{w};font-display:block;src:url(data:font/woff2;base64,'
    f'{base64.b64encode((fonts_dir / f"{f}.woff2").read_bytes()).decode()}) format("woff2");unicode-range:{CYR if "cyrillic" in f else LATIN}}}'
    for fam, w, f in FONTS)

# ---- real numbers and public record IDs from one recorded reconcile run (data.json)
steps = data["steps"]
submit = steps[-1]
rep = submit["report"]
records = sum(s.get("rows", 0) for s in steps[:-1])
ids = []
for s in steps[:-1]:
    for r in s["sample"]:
        rid = r.get("row_id") or r.get("invoice_id") or r.get("payment_id") or (r.get("date") and f'{r["date"]}|{r["source_currency"]}|{r["target_currency"]}')
        label = {"ledger": "главная книга", "invoices": "счёт", "payments": "платёж", "fx": "курс"}[s["table"]]
        if rid:
            ids.append(f"{rid} · {label}")
evidence = sorted({x for f in submit["findings"] for x in f["evidence_ids"]})
payload = {"reward": f'{rep["reward"]:.3f}'.replace(".", ","), "tp": rep["tp"], "found": len(submit["findings"]),
           "steps": len(steps), "records": records, "ids": ids, "evidence": evidence}

HTML = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AuditGym · превью v4 (ASCII motion)</title><style>
__FONTS__
:root{--bg:#fbfbfa;--s1:#f3f3f1;--ink:#151517;--txt2:#55555c;--txt3:#6b6b73;--line:#e3e3e0;--ascii:#151517;--ascii-dim:#a6a6ad;
  --pos:#2b744c;--neg:#ad3a28;--chip:#151517;--chip-ink:#fbfbfa;--mono:"JetBrains Mono",ui-monospace,Consolas,monospace;
  --sans:"Inter",system-ui,sans-serif;--ease:cubic-bezier(.2,.7,.1,1)}
@media (prefers-color-scheme:dark){:root{--bg:#0e0e10;--s1:#17171a;--ink:#ededef;--txt2:#b4b4ba;--txt3:#909097;--line:#26262b;
  --ascii:#ededef;--ascii-dim:#55555c;--pos:#72c294;--neg:#ec8a78;--chip:#ededef;--chip-ink:#0e0e10}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
a{color:inherit}.wrap{max-width:1180px;margin:0 auto;padding:0 32px}
pre.ascii{margin:0;font:12px/1.0 var(--mono);color:var(--ascii);letter-spacing:0;white-space:pre;user-select:none}
:focus-visible{outline:2px solid var(--ink);outline-offset:3px;border-radius:6px}
/* nav */
nav.top{position:sticky;top:0;z-index:5;background:color-mix(in srgb,var(--bg) 92%,transparent);border-bottom:1px solid transparent}
nav.top .wrap{display:flex;align-items:center;gap:28px;height:60px}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;letter-spacing:-.01em}
.brand i{font:700 12px/1 var(--mono);border:1.5px solid var(--ink);border-radius:6px;padding:4px 5px}
nav.top .links{display:flex;gap:22px;font-size:14px;color:var(--txt2)}nav.top .links a{text-decoration:none}
nav.top .links a:hover{color:var(--ink)}.sp{flex:1}
.btn{display:inline-flex;align-items:center;gap:8px;height:38px;padding:0 16px;border-radius:9px;border:1px solid var(--ink);background:var(--ink);color:var(--bg);font:600 14px var(--sans);text-decoration:none;cursor:pointer;transition:opacity .15s}
.btn:hover{opacity:.85}.btn.ghost{background:transparent;color:var(--ink);border-color:transparent}.btn.ghost:hover{opacity:1;text-decoration:underline}
/* hero */
.hero{position:relative;overflow:hidden;min-height:640px;display:grid;place-items:center;text-align:center}
.hero .art{position:absolute;inset:0;display:flex;align-items:center;justify-content:space-between;padding:0 2%;pointer-events:none}
.hero .art pre{opacity:.95}
.hero .copy{position:relative;z-index:2;max-width:640px;padding:40px 16px}
.hero h1{font:700 64px/1.02 var(--sans);letter-spacing:-.035em;margin:0 0 18px}
.hero p{font-size:17px;color:var(--txt2);margin:0 auto 26px;max-width:520px}
.hero p b{color:var(--ink);font-weight:600}
.cta{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.intro .art{animation:pull 1.8s var(--ease) both}
.intro .copy>*{animation:rise .9s var(--ease) both}.intro .copy>*:nth-child(2){animation-delay:.12s}.intro .copy>*:nth-child(3){animation-delay:.24s}
.intro .copy{animation:fade 1s .7s var(--ease) both}
@keyframes pull{from{transform:scale(2.6);filter:blur(5px);opacity:.35}to{transform:none;filter:none;opacity:1}}
@keyframes rise{from{transform:translateY(14px);opacity:0}to{transform:none;opacity:1}}
@keyframes fade{from{opacity:0}to{opacity:1}}
/* statement with odometer */
section{padding:96px 0}
.statement{font:500 40px/1.2 var(--sans);letter-spacing:-.025em;max-width:900px;margin:0}
.statement .dim{color:var(--txt3)}
.odo{display:inline-flex;vertical-align:bottom;font-variant-numeric:tabular-nums;height:1.2em;overflow:hidden}
.odo .reel{display:inline-block;transition:transform 1.4s var(--ease)}.odo .reel span{display:block;height:1.2em}
.odo .fix{display:inline-block}
/* interactive character field */
.field{position:relative;margin-top:44px;border-radius:14px;background:var(--s1);padding:22px;overflow:hidden;cursor:crosshair}
.field pre{color:var(--ascii-dim)}
.field .chip{position:absolute;pointer-events:none;background:var(--chip);color:var(--chip-ink);font:500 12px var(--mono);padding:5px 9px;border-radius:999px;white-space:nowrap;transform:translate(14px,-130%);opacity:0;transition:opacity .2s}
.field.on .chip{opacity:1}
.cap{font:12px var(--mono);color:var(--txt3);margin:10px 2px 0}
/* how it works */
.how{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-top:40px}
.step{border-top:1px solid var(--line);padding-top:18px}
.step .n{font:12px var(--mono);color:var(--txt3)}.step h3{font:600 20px var(--sans);letter-spacing:-.015em;margin:6px 0 6px}
.step p{margin:0 0 16px;color:var(--txt2);font-size:15px}
.step pre{min-height:220px;display:grid;place-items:center}
.step.done pre{color:var(--pos)}
h2{font:700 40px/1.1 var(--sans);letter-spacing:-.03em;margin:0}
.lead{color:var(--txt2);max-width:560px;margin:12px 0 0}
/* big number */
.score{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:center}
.score .meta{font-size:15px;color:var(--txt2)}.score .meta b{color:var(--ink);font-weight:600}
.score .formula{font:13px var(--mono);color:var(--txt3);margin-top:14px}
/* final cta + footer */
.final{text-align:center}.final h2{font-size:48px}.final .cta{margin-top:22px}
footer{position:relative;overflow:hidden;padding-top:40px}
footer .cols{display:flex;gap:48px;flex-wrap:wrap;font-size:13px;color:var(--txt3);padding-bottom:30px}
footer .cols b{display:block;color:var(--ink);font-weight:600;margin-bottom:6px}
footer pre.ascii{color:var(--ascii-dim)}
.note{font:12px var(--mono);color:var(--txt3)}
@media (max-width:820px){.hero h1{font-size:42px}.statement{font-size:28px}.how{grid-template-columns:1fr}.score{grid-template-columns:1fr}
  .hero{display:block;min-height:0;padding-top:24px}.hero .art{position:static;justify-content:center;padding:0}.hero .art pre{font-size:8px}
  .hero .art pre:last-child{display:none}nav.top .links,nav.top .btn.ghost{display:none}.btn{white-space:nowrap}h2,.final h2{font-size:32px}
  .wrap{padding:0 16px}section{padding:64px 0}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style></head><body>
<nav class="top" aria-label="Главное"><div class="wrap">
  <div class="brand"><i aria-hidden="true">AG</i>AuditGym</div>
  <div class="links"><a href="#how">Как это работает</a><a href="#score">Оценка</a><a href="#">Для специалистов</a></div>
  <span class="sp"></span><a class="btn ghost" href="#">Отчёт</a><a class="btn" href="#">Начать эпизод</a>
</div></nav>

<header class="hero intro" id="top">
  <div class="art" aria-hidden="true"><pre class="ascii" id="obj-ledger"></pre><pre class="ascii" id="obj-coin"></pre></div>
  <div class="copy">
    <h1>Тренажёр аудита для ИИ-агентов</h1>
    <p>Вымышленные компании со <b>спрятанными ошибками</b> в книгах. Агент читает записи, сдаёт выводы с доказательствами и получает оценку <b>только за доказанное</b>.</p>
    <div class="cta"><a class="btn" href="#">Начать эпизод →</a><a class="btn ghost" href="#how">Как это работает →</a></div>
  </div>
</header>

<section aria-label="Результат примера"><div class="wrap">
  <p class="statement">Агент проверил <span class="odo" data-to="__RECORDS__"></span> записей, нашёл <span class="odo" data-to="__FOUND__"></span> ошибок и доказал каждую <span class="dim">— за <span class="odo" data-to="__STEPS__"></span> шагов из 100.</span></p>
  <div class="field" id="field" aria-label="Записи эпизода: наведите курсор"><pre class="ascii" id="field-pre" aria-hidden="true"></pre><span class="chip" id="chip"></span></div><p class="cap">наведите курсор · настоящие публичные записи эпизода</p>
</div></section>

<section id="how"><div class="wrap">
  <h2>Как это работает</h2><p class="lead">Три шага одного эпизода. Каждое действие агента — один шаг из ста.</p>
  <div class="how">
    <div class="step"><div class="n">01</div><h3>Агент читает книги</h3><p>Счета, платежи, курсы и главная книга — только чтение.</p><pre class="ascii" id="obj-step1" aria-hidden="true"></pre></div>
    <div class="step"><div class="n">02</div><h3>Сдаёт выводы</h3><p>Тип ошибки, записи, сумма и доказательства.</p><pre class="ascii" id="obj-step2" aria-hidden="true"></pre></div>
    <div class="step done"><div class="n">03</div><h3>Оценщик проверяет</h3><p>Сверка со скрытым ответом. Подсказок по ходу нет.</p><pre class="ascii" id="obj-step3" aria-hidden="true"></pre></div>
  </div>
</div></section>

<section id="score"><div class="wrap score">
  <pre class="ascii" id="big-num" aria-hidden="true"></pre>
  <div><h2>Оценка эпизода</h2>
    <p class="meta"><b>__TP__ из __FOUND__</b> выводов подтверждены, ложных обвинений нет. За доказанное оценка растёт, за ложное падает, каждый шаг стоит чуть-чуть.</p>
    <p class="formula">2 · F1 − 1 − 0,002 · __INSP__ = __REWARD__</p></div>
</div></section>

<section class="final"><div class="wrap">
  <h2>Найдёте ошибки быстрее агента?</h2>
  <div class="cta"><a class="btn" href="#">Попробовать самому</a><a class="btn ghost" href="#">Для специалистов: терминал →</a></div>
</div></section>

<footer><div class="wrap">
  <div class="cols"><div><b>AuditGym</b>Все компании и деньги вымышлены.<br>Работает без интернета.</div><div><b>Разделы</b>Эпизоды · Отчёт · Терминал</div><div><b>Версия</b>ENV 1.0.0 · verify 100/100</div></div>
  <p class="note">превью v4 · дизайн-предложение, не подключено к среде</p>
</div><pre class="ascii" id="dunes" aria-hidden="true"></pre></footer>

<script>
"use strict";
const DATA = __DATA__;
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const RAMP = " .:-=+*#%@";

/* ---------- tiny vector + SDF helpers ---------- */
const len3 = (x, y, z) => Math.hypot(x, y, z);
function rot(p, ax, ay) {            // rotate around X then Y
  let [x, y, z] = p, c = Math.cos(ax), s = Math.sin(ax);
  [y, z] = [y * c - z * s, y * s + z * c];
  c = Math.cos(ay); s = Math.sin(ay);
  [x, z] = [x * c + z * s, -x * s + z * c];
  return [x, y, z];
}
const sdBox = (p, bx, by, bz, r) => { const qx = Math.abs(p[0]) - bx, qy = Math.abs(p[1]) - by, qz = Math.abs(p[2]) - bz;
  return len3(Math.max(qx, 0), Math.max(qy, 0), Math.max(qz, 0)) + Math.min(Math.max(qx, Math.max(qy, qz)), 0) - r; };
const sdTorus = (p, R, r) => Math.hypot(Math.hypot(p[0], p[2]) - R, p[1]) - r;
const sdCyl = (p, r, h) => { const dx = Math.hypot(p[0], p[2]) - r, dy = Math.abs(p[1]) - h;
  return Math.min(Math.max(dx, dy), 0) + Math.hypot(Math.max(dx, 0), Math.max(dy, 0)); };
const sdSphere = (p, r) => len3(p[0], p[1], p[2]) - r;
const mix = (a, b, k) => a + (b - a) * k;

/* Ray-march an SDF into characters. Cells are ~2x taller than wide, so y steps are doubled. */
function renderSDF(cols, rows, sdf, span) {
  const s = span / cols, out = [], L = [-0.45, 0.62, -0.64], e = 0.012;
  for (let j = 0; j < rows; j++) {
    let line = "";
    for (let i = 0; i < cols; i++) {
      const x = (i + 0.5 - cols / 2) * s, y = (rows / 2 - j - 0.5) * s * 2;
      let t = 0, hit = false;
      for (let k = 0; k < 36; k++) { const d = sdf([x, y, -3 + t]); if (d < 0.004) { hit = true; break; } t += d; if (t > 6) break; }
      if (!hit) { line += " "; continue; }
      const p = [x, y, -3 + t];
      const nx = sdf([p[0] + e, p[1], p[2]]) - sdf([p[0] - e, p[1], p[2]]);
      const ny = sdf([p[0], p[1] + e, p[2]]) - sdf([p[0], p[1] - e, p[2]]);
      const nz = sdf([p[0], p[1], p[2] + e]) - sdf([p[0], p[1], p[2] - e]);
      const nl = len3(nx, ny, nz) || 1;
      const lum = 0.12 + 0.88 * Math.max(0, (nx * L[0] + ny * L[1] + nz * L[2]) / nl);
      line += RAMP[1 + Math.min(RAMP.length - 2, Math.floor(lum * (RAMP.length - 1)))];
    }
    out.push(line);
  }
  return out.join("\n");
}

/* ---------- animation loop: only pieces on screen are drawn, ~30 fps ---------- */
const pieces = [];
function piece(el, draw) { if (!el) return; const p = { el, draw, on: false }; pieces.push(p);
  new IntersectionObserver(es => { p.on = es[0].isIntersecting; }, { rootMargin: "120px" }).observe(el); draw(0); }
let last = 0;
function loop(now) { if (now - last > 33) { last = now; const t = now / 1000; for (const p of pieces) if (p.on) p.draw(t); } requestAnimationFrame(loop); }

/* hero: a ledger block and a coin, slowly turning and floating */
piece(document.getElementById("obj-ledger"), t => {
  document.getElementById("obj-ledger").textContent = renderSDF(64, 36, p => {
    const q = rot([p[0], p[1] - 0.06 * Math.sin(t * 1.1), p[2]], 0.5 + 0.15 * Math.sin(t * 0.7), t * 0.45);
    return sdBox(q, 0.62, 0.42, 0.5, 0.06);
  }, 3.1);
});
piece(document.getElementById("obj-coin"), t => {
  document.getElementById("obj-coin").textContent = renderSDF(64, 36, p => {
    const q = rot([p[0], p[1] + 0.07 * Math.sin(t * 0.9), p[2]], 1.1 + 0.2 * Math.sin(t * 0.6), t * 0.6);
    return Math.min(sdTorus(q, 0.62, 0.16), sdCyl(q, 0.5, 0.05));
  }, 3.1);
});

/* how it works: records (block) -> finding (sphere) -> verified (ring), each morphing gently */
const stepShapes = [
  (q, k) => mix(sdBox(q, 0.55, 0.5, 0.55, 0.05), sdBox(q, 0.7, 0.18, 0.5, 0.05), k),
  (q, k) => mix(sdBox(q, 0.5, 0.5, 0.5, 0.05), sdSphere(q, 0.66), k),
  (q, k) => mix(sdSphere(q, 0.6), sdTorus(q, 0.58, 0.18), k),
];
stepShapes.forEach((shape, i) => {
  const el = document.getElementById("obj-step" + (i + 1));
  piece(el, t => {
    const k = REDUCED ? 1 : 0.5 + 0.5 * Math.sin(t * 0.8 + i);
    el.textContent = renderSDF(46, 24, p => shape(rot(p, 0.55, t * 0.5 + i), k), 2.6);
  });
});

/* rolling counters */
function buildOdo(el) {
  const to = String(el.dataset.to);
  el.textContent = "";
  for (const ch of to) {
    if (/\d/.test(ch)) { const r = document.createElement("span"); r.className = "reel";
      r.innerHTML = "0123456789".split("").map(d => `<span>${d}</span>`).join(""); r.dataset.d = ch; el.appendChild(r); }
    else { const f = document.createElement("span"); f.className = "fix"; f.textContent = ch; el.appendChild(f); }
  }
  el.setAttribute("aria-label", to);
  const go = () => [...el.querySelectorAll(".reel")].forEach((r, i) => { r.style.transitionDelay = (i * 0.09) + "s"; r.style.transform = `translateY(-${r.dataset.d * 1.2}em)`; });
  if (REDUCED) go(); else new IntersectionObserver((es, o) => { if (es[0].isIntersecting) { go(); o.disconnect(); } }, { threshold: 0.6 }).observe(el);
}
document.querySelectorAll(".odo").forEach(buildOdo);

/* interactive character field: characters grow near the cursor; a chip names the record under it */
(() => {
  const box = document.getElementById("field"), pre = document.getElementById("field-pre"), chip = document.getElementById("chip");
  let cols = 100, rows = 15, mx = -99, my = -99, cw = 7.2, ch = 12;
  function size() { const probe = document.createElement("span"); probe.textContent = "M".repeat(10); probe.style.font = getComputedStyle(pre).font;
    probe.style.position = "absolute"; probe.style.visibility = "hidden"; document.body.appendChild(probe);
    cw = probe.getBoundingClientRect().width / 10; ch = parseFloat(getComputedStyle(pre).lineHeight) || 12; probe.remove();
    cols = Math.max(20, Math.floor((box.clientWidth - 44) / cw)); }
  size(); addEventListener("resize", size);
  box.addEventListener("pointermove", e => { const r = pre.getBoundingClientRect(); mx = (e.clientX - r.left) / cw; my = (e.clientY - r.top) / ch;
    box.classList.add("on"); const b = box.getBoundingClientRect(); chip.style.left = (e.clientX - b.left) + "px"; chip.style.top = (e.clientY - b.top) + "px";
    const idx = (Math.floor(my) * cols + Math.floor(mx)) >>> 0; chip.textContent = DATA.ids.length ? DATA.ids[idx % DATA.ids.length] : ""; });
  box.addEventListener("pointerleave", () => { box.classList.remove("on"); mx = my = -99; });
  piece(pre, t => {
    let s = "";
    for (let j = 0; j < rows; j++) { for (let i = 0; i < cols; i++) {
      const d = Math.hypot(i + 0.5 - mx, (j + 0.5 - my) * 2);
      const wave = REDUCED ? 0 : 0.6 * Math.sin(i * 0.35 + j * 0.6 + t * 2.2);
      const v = d < 1.6 ? 9 : d < 3 ? 7 : d < 4.6 ? 5 : d < 6.4 ? 3 : (wave > 0.45 ? 2 : 1);
      s += RAMP[v]; } s += "\n"; }
    pre.textContent = s;
  });
})();

/* big number: the episode score sampled from canvas text into characters, dissolving in once */
(() => {
  const el = document.getElementById("big-num"); if (!el) return;
  const cols = 72, rows = 16, cv = document.createElement("canvas"); cv.width = cols * 4; cv.height = rows * 8;
  const g = cv.getContext("2d"); g.fillStyle = "#000"; g.textBaseline = "middle"; g.textAlign = "center";
  function fit() { let px = Math.round(cv.height * 0.95); g.font = "700 " + px + "px Inter, sans-serif";
    const w = g.measureText(DATA.reward).width; if (w > cv.width * 0.94) { px = Math.floor(px * cv.width * 0.94 / w); g.font = "700 " + px + "px Inter, sans-serif"; } }
  let mask = null, start = null;
  function sample() { fit(); g.clearRect(0, 0, cv.width, cv.height); g.fillText(DATA.reward, cv.width / 2, cv.height * 0.54);
    const px = g.getImageData(0, 0, cv.width, cv.height).data; mask = [];
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) { let a = 0;
      for (let y = 0; y < 8; y += 2) for (let x = 0; x < 4; x++) a += px[((j * 8 + y) * cv.width + i * 4 + x) * 4 + 3];
      mask.push(a / (16 * 255)); } }
  document.fonts.ready.then(() => { sample(); });
  new IntersectionObserver(es => { if (es[0].isIntersecting && start === null) start = performance.now() / 1000; }, { threshold: 0.4 }).observe(el);
  piece(el, t => {
    if (!mask) return;
    const k = REDUCED ? 1 : start === null ? 0 : Math.min(1, (t - start) / 1.6);
    let s = "";
    for (let j = 0; j < rows; j++) { for (let i = 0; i < cols; i++) { const a = mask[j * cols + i];
      const noise = (Math.sin(i * 12.9898 + j * 78.233) * 43758.5453) % 1;
      if (a < 0.08 || Math.abs(noise) > k) { s += a > 0.08 && Math.abs(noise) < k + 0.15 ? "." : " "; continue; }
      const flick = REDUCED ? 0 : (Math.sin(t * 6 + i * 0.7 + j) > 0.93 ? 1 : 0);
      s += RAMP[Math.min(9, 3 + Math.floor(a * 6) + flick)]; } s += "\n"; }
    el.textContent = s;
  });
})();

/* footer: drifting character dunes with parallax */
(() => {
  const el = document.getElementById("dunes"); if (!el) return;
  piece(el, t => {
    const cols = Math.max(60, Math.floor(innerWidth / 7.2)), rows = 26, drift = REDUCED ? 0 : t * 0.6 + scrollY * 0.02;
    const ridge = (x, a, f, ph, base) => base - a * (0.55 * Math.sin(x * f + ph) + 0.3 * Math.sin(x * f * 2.3 + ph * 1.7) + 0.15 * Math.sin(x * f * 5.1 - ph));
    let s = "";
    for (let j = 0; j < rows; j++) { for (let i = 0; i < cols; i++) {
      const far = ridge(i + drift * 0.5, 5, 0.05, 1.2, 11), near = ridge(i + drift, 7, 0.035, 0.3, 19);
      if (j >= near) { const d = j - near; s += d < 1 ? "#" : d < 2.5 ? "+" : d < 4.5 ? ":" : "."; }
      else if (j >= far) { const d = j - far; s += d < 1 ? "*" : d < 3 ? "-" : "."; }
      else s += " "; } s += "\n"; }
    el.textContent = s;
  });
})();

if (!REDUCED) requestAnimationFrame(loop);
</script></body></html>"""

page = (HTML.replace("__FONTS__", font_css).replace("__DATA__", json.dumps(payload, ensure_ascii=False))
        .replace("__RECORDS__", str(payload["records"])).replace("__FOUND__", str(payload["found"]))
        .replace("__STEPS__", str(payload["steps"])).replace("__TP__", str(payload["tp"])).replace("__INSP__", str(rep["inspection_steps"])).replace("__REWARD__", payload["reward"]))
(out / "preview_v4.html").write_text(page)
print("ok", len(page) // 1024, "KB", "| ids:", len(ids), "| records:", records)
