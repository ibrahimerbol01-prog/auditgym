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
