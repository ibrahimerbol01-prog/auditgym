"use strict";
// App shell shared by every page: the sidebar's «Недавние» list (latest trainings and evaluations).
(() => {
  const host = document.getElementById("side-recent");
  if (!host || !window.fetch) return;
  const NAMES = { oracle: "Эталон", reconcile: "Сверщик", random: "Стажёр", flag_all: "Паникёр" };
  const f2 = (v) => (v < 0 ? "−" : "") + Math.abs(v).toFixed(2);
  const item = (r) => {
    const training = r.kind === "training";
    const a = document.createElement("a");
    a.href = training ? "/train.html#run=" + encodeURIComponent(r.id) : "/runs.html#" + encodeURIComponent(r.id);
    const v = training ? r.summary && r.summary.dev_best : r.summary && r.summary.episodes_done ? r.summary.reward : null;
    const dot = document.createElement("i"); dot.className = "sr-dot " + (r.status === "running" ? "run" : v == null ? "" : v > 0 ? "pos" : "neg");
    const name = document.createElement("span"); name.className = "sr-n";
    name.textContent = training ? `Обучение · ${r.method === "reinforce" ? "REINFORCE" : "CEM"}` : `Оценка · ${NAMES[r.agent] || r.agent}`;
    const val = document.createElement("span"); val.className = "sr-v"; val.textContent = v == null ? "" : f2(v);
    a.append(dot, name, val);
    return a;
  };
  fetch("/api/runs", { cache: "no-store" }).then((r) => r.json()).then((d) => {
    const runs = (d.runs || []).slice(0, 7);
    if (!runs.length) return;
    const h = document.createElement("p"); h.className = "sr-h"; h.textContent = "Недавние";
    host.replaceChildren(h, ...runs.map(item));
  }).catch(() => { /* static preview without the API: no recents */ });
})();

// ---- small ASCII animations, shared by every page. Each <pre data-art="name"> gets a generator; .ascii-spin is a
// braille spinner. All pause when hidden and render one still frame under prefers-reduced-motion.
(() => {
  const STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pad = (s, n) => (s + " ".repeat(n)).slice(0, n);
  const ART = {
    // a heartbeat line scrolling left: the app is alive, offline, on the CPU
    beat(t) { const L = "▁▁▁▁▁▂▁▁▃▇▁▅▂▁▁▁▁▁▁▁▁▁▁▂▃▂▁▁"; const k = Math.floor(t * 9) % L.length; return (L.slice(k) + L.slice(0, k)).slice(0, 22); },
    // one error type at a time: a cursor walks down the ledger and ticks each row
    simple(t) { const n = Math.floor(t * 2.2) % 6; return [0, 1, 2, 3].map((i) => (i === n ? "▸ " : "  ") + ["────── ───", "──── ──────", "─────── ──", "─── ───────"][i] + (i < n ? " ✓" : "  ")).join("\n"); },
    // mixed books: rows of entries shuffle, one of them is wrong
    mixed(t) { const k = Math.floor(t * 2.5); return [0, 1, 2, 3].map((i) => { const s = (i * 7 + k * 3) % 5; return "  " + "▤ ".repeat(1 + ((i + k) % 3)) + (s === 0 ? "✕" : "·") + "  " + "▥".repeat(1 + s % 3); }).map((r) => pad(r, 16)).join("\n"); },
    // interacting errors: two boxes drift into each other and mask the overlap
    interacting(t) { const a = Math.round(2 + 2 * Math.sin(t * 1.6)), g = Array.from({ length: 4 }, () => Array(16).fill(" "));
      const box = (x, y, w, h) => { for (let i = 0; i < w; i++) for (let j = 0; j < h; j++) { const edge = j === 0 || j === h - 1 ? "─" : i === 0 || i === w - 1 ? "│" : null; if (!edge) continue; const c = g[y + j][x + i]; g[y + j][x + i] = c !== " " && c !== edge ? "┼" : edge; } };
      box(a, 0, 7, 3); box(14 - 7 - a + 2, 1, 7, 3); return g.map((r) => r.join("")).join("\n"); },
    // the empty runs page: a lens sweeps across ledger lines and reads them
    scan(t) { const x = Math.round((Math.sin(t * 1.3) + 1) / 2 * 30); return [0, 1, 2, 3, 4].map((j) => { let r = ""; for (let i = 0; i < 36; i++) { const near = Math.abs(i - x - 3) < 4 && j >= 1 && j <= 3; r += near ? "█" : (i + j * 5) % 7 === 0 ? " " : "─"; } return (j === 0 ? " ".repeat(x) + "╭─────╮" : j === 4 ? " ".repeat(x) + "╰──┬──╯" : r); }).join("\n") + "\n" + " ".repeat(x + 3) + "│"; },
  };
  const SPIN = "⣾⣽⣻⢿⡿⣟⣯⣷";
  // the sidebar heartbeat lives under the machine line on every page
  for (const f of document.querySelectorAll(".side-foot")) { const p = document.createElement("pre"); p.className = "ascii-beat"; p.dataset.art = "beat"; p.setAttribute("aria-hidden", "true"); f.prepend(p); }
  const els = () => [...document.querySelectorAll("pre[data-art]")];
  const draw = (t) => {
    for (const el of els()) { const g = ART[el.dataset.art]; if (g) el.textContent = g(el.matches(":hover") || el.closest(":hover.recipe") ? t * 2.2 : t); }
    for (const el of document.querySelectorAll(".ascii-spin")) el.textContent = SPIN[Math.floor(t * 10) % SPIN.length];
  };
  draw(1.3);
  if (STILL) return;
  let t = 1.3, last = 0;
  const loop = (ms) => { if (!document.hidden && ms - last > 60) { last = ms; t += 0.06; draw(t); } requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
})();

// ---- background: an ASCII "gravity field" that bends toward the pointer; a click sends a shockwave ring.
// Drawn on one canvas behind the content (cards cover it), faint by design, idles when the pointer rests,
// stops in hidden tabs, static under reduced motion, off on small screens.
(() => {
  if (matchMedia("(max-width: 860px)").matches) return;
  const STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const RAMP = " .:-=+*#%@";
  const cv = document.createElement("canvas"); cv.className = "ascii-field"; cv.setAttribute("aria-hidden", "true");
  document.body.prepend(cv);
  const ctx = cv.getContext("2d");
  const CW = 14, CH = 18, R = 190;                 // cell size, radius of the well (px)
  let W = 0, H = 0, dpr = 1, mx = -1e4, my = -1e4, tx = -1e4, ty = -1e4, lastMove = 0, ripples = [], ink = "#888", ink2 = "#333";
  const colours = () => { const cs = getComputedStyle(document.documentElement); ink = cs.getPropertyValue("--txt3").trim() || ink; ink2 = cs.getPropertyValue("--txt").trim() || ink2; };
  const size = () => { dpr = Math.min(2, devicePixelRatio || 1); W = innerWidth; H = innerHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.font = `12px "JetBrains Mono", ui-monospace, monospace`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; };
  const bands = [[], [], [], []];                   // batch glyphs by alpha level: few canvas state changes
  function draw(t) {
    ctx.clearRect(0, 0, W, H);
    for (const b of bands) b.length = 0;
    mx += (tx - mx) * 0.18; my += (ty - my) * 0.18;  // the well follows the pointer with a little lag
    for (let y = CH / 2; y < H + CH; y += CH) for (let x = CW / 2; x < W + CW; x += CW) {
      let dx = mx - x, dy = my - y; const r2 = dx * dx + dy * dy, r = Math.sqrt(r2) || 1;
      if (r < 20) continue;                          // event horizon: the very centre stays empty
      let f = R * R / (r2 + R * R * 0.35);           // ~1/r² with a soft core
      let px = x, py = y;
      if (f > 0.04) {                               // pull toward the pointer, with a slight orbital swirl
        const pull = Math.min(r * 0.55, 26 * f), sw = 0.35 * f;
        px += (dx / r) * pull - (dy / r) * pull * sw; py += (dy / r) * pull + (dx / r) * pull * sw;
      }
      for (const w of ripples) {                    // shockwave rings push characters outward
        const d = Math.hypot(x - w.x, y - w.y), k = Math.exp(-((d - w.r) ** 2) / 900) * w.a;
        if (k > 0.02) { px += (x - w.x) / (d || 1) * 10 * k; py += (y - w.y) / (d || 1) * 10 * k; f = Math.max(f, k * 1.6); }
      }
      const breathe = 0.5 + 0.5 * Math.sin(t * 0.6 + x * 0.013 + y * 0.021);
      const level = Math.min(9, Math.floor(f * 6 + (f < 0.08 ? breathe * 1.4 : 0)));
      if (level <= 0) continue;
      bands[Math.min(3, Math.floor(f * 3.2 + (level >= 2 ? 0.4 : 0)))].push(RAMP[level], px, py);
    }
    const alpha = [0.16, 0.28, 0.42, 0.6];
    bands.forEach((b, i) => { ctx.globalAlpha = alpha[i]; ctx.fillStyle = i >= 2 ? ink2 : ink; for (let k = 0; k < b.length; k += 3) ctx.fillText(b[k], b[k + 1], b[k + 2]); });
    ctx.globalAlpha = 1;
    ripples = ripples.filter((w) => (w.r += 9, w.a *= 0.955, w.a > 0.03));
  }
  addEventListener("pointermove", (e) => { tx = e.clientX; ty = e.clientY; lastMove = performance.now(); }, { passive: true });
  addEventListener("pointerleave", () => { tx = ty = -1e4; });
  document.addEventListener("pointerdown", (e) => { ripples.push({ x: e.clientX, y: e.clientY, r: 0, a: 1 }); lastMove = performance.now(); }, { passive: true });
  addEventListener("resize", size);
  new MutationObserver(colours).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  colours(); size(); draw(0);
  if (STILL) return;
  let last = 0;
  const loop = (ms) => {
    const busy = ms - lastMove < 1800 || ripples.length;
    if (!document.hidden && ms - last > (busy ? 33 : 120)) { last = ms; draw(ms / 1000); }
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
})();

// ---- page titles decode from random characters into place (the real text is set for assistive tech first)
(() => {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const GLYPHS = "░▒▓█#%@*+=-:.";
  for (const h of document.querySelectorAll("main h1")) {
    const text = h.textContent; if (!text.trim() || text.length > 60) continue;
    h.setAttribute("aria-label", text);
    const t0 = performance.now(), dur = 650;
    const step = (ms) => {
      const k = Math.min(1, (ms - t0) / dur), n = Math.floor(k * text.length);
      h.textContent = text.slice(0, n) + [...text.slice(n)].map((c) => (c === " " ? " " : GLYPHS[Math.floor(Math.random() * GLYPHS.length)])).join("");
      if (k < 1) requestAnimationFrame(step); else { h.textContent = text; h.removeAttribute("aria-label"); }
    };
    requestAnimationFrame(step);
  }
})();
