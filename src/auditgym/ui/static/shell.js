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
    const who = NAMES[r.agent] || (/^auditor-/.test(r.agent || "") ? `Аудитор · ${r.agent.endsWith("reinforce") ? "REINFORCE" : "CEM"}` : /^llm-/.test(r.agent || "") ? "LLM · " + r.agent.slice(4) : r.agent);
    name.textContent = training ? `Обучение · ${r.method === "reinforce" ? "REINFORCE" : "CEM"}${r.group ? " · сид " + r.seed : ""}` : `Оценка · ${who}`;
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

// ---- background: a quiet dot grid; the pointer is a magnifying glass that reads a hidden ledger under it and shows
// its figures enlarged. A click sends a ring of characters outward. Fast by design: every glyph is pre-rendered once,
// a frame only redraws the box around the pointer (well under 1 ms), and nothing is drawn while the pointer rests.
// Behind the content (cards cover it), off on small screens; under reduced motion the glass stays but rings are off.
(() => {
  if (matchMedia("(max-width: 860px)").matches) return;
  const STILL = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const CW = 14, CH = 18, LR = 118, LM = 1.65, FONT = '12px "JetBrains Mono", ui-monospace, monospace';
  const CHARS = "·0123456789.,-+:";
  const IDX = Object.fromEntries([...CHARS].map((c, i) => [c, i]));
  const cv = document.createElement("canvas"); cv.className = "ascii-field"; cv.setAttribute("aria-hidden", "true");
  document.body.prepend(cv);
  const ctx = cv.getContext("2d");
  let W = 0, H = 0, dpr = 1, S = 2, cols = 0, rows = 0, layer = null, atlas = {}, rim = "";
  let tx = -1e4, ty = -1e4, px = -1e4, py = -1e4, dirty = null, raf = 0, lastT = 0, ripples = [];
  const hash = (i, j) => { let h = (i * 374761393 + j * 668265263) >>> 0; h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0; return h ^ (h >>> 16); };
  const hasDot = (i, j) => hash(i, j) % 5 !== 0;
  const ledger = (i, j) => {                       // rows of accounting figures: "  4 812.50   -1 204.00"
    const o = hash(0, j) % 13, n = Math.floor((i + o) / 13), f = hash(n + 7, j);
    const cell = "  " + (hash(n, j) % 6 === 0 ? "-" : " ") + (1 + f % 9) + " " + (100 + (f >>> 4) % 900) + "." + (10 + (f >>> 12) % 90);
    return cell.charAt((i + o) % 13);
  };
  const tok = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const bake = (ink) => {
    const c = document.createElement("canvas"); c.width = CHARS.length * CW * S; c.height = CH * S;
    const x = c.getContext("2d"); x.scale(S, S); x.font = FONT; x.textAlign = "center"; x.textBaseline = "middle"; x.fillStyle = ink;
    [...CHARS].forEach((ch, i) => x.fillText(ch, i * CW + CW / 2, CH / 2));
    return c;
  };
  const glyph = (c, ch, ink, x, y, a, m = 1) => {
    const i = IDX[ch]; if (i == null) return;
    c.globalAlpha = a; const w = CW * m, h = CH * m;
    c.drawImage(atlas[ink], i * CW * S, 0, CW * S, CH * S, x - w / 2, y - h / 2, w, h);
  };
  const union = (a, b) => (!a ? b : !b ? a : { x0: Math.min(a.x0, b.x0), y0: Math.min(a.y0, b.y0), x1: Math.max(a.x1, b.x1), y1: Math.max(a.y1, b.y1) });
  const cells = (b, fn) => {
    const i0 = Math.max(0, Math.floor(b.x0 / CW)), i1 = Math.min(cols - 1, Math.ceil(b.x1 / CW));
    const j0 = Math.max(0, Math.floor(b.y0 / CH)), j1 = Math.min(rows - 1, Math.ceil(b.y1 / CH));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) fn(i, j, i * CW + CW / 2, j * CH + CH / 2);
  };
  function restore(r) {                            // put the static dots back, only inside the box that changed
    const x0 = Math.max(0, Math.floor(r.x0)), y0 = Math.max(0, Math.floor(r.y0)), x1 = Math.min(W, Math.ceil(r.x1)), y1 = Math.min(H, Math.ceil(r.y1));
    if (x1 <= x0 || y1 <= y0) return;
    ctx.globalAlpha = 1; ctx.clearRect(x0, y0, x1 - x0, y1 - y0);
    ctx.drawImage(layer, x0 * dpr, y0 * dpr, (x1 - x0) * dpr, (y1 - y0) * dpr, x0, y0, x1 - x0, y1 - y0);
  }
  function setup() {
    dpr = Math.min(2, devicePixelRatio || 1); S = dpr * 2;
    W = innerWidth; H = innerHeight; cols = Math.ceil(W / CW) + 1; rows = Math.ceil(H / CH) + 1;
    cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    rim = tok("--txt3"); atlas = { soft: bake(rim), strong: bake(tok("--txt")) };
    layer = document.createElement("canvas"); layer.width = W * dpr; layer.height = H * dpr;
    const l = layer.getContext("2d"); l.setTransform(dpr, 0, 0, dpr, 0, 0);
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) if (hasDot(i, j)) glyph(l, "·", "soft", i * CW + CW / 2, j * CH + CH / 2, 0.5);
    dirty = { x0: 0, y0: 0, x1: W, y1: H }; request();
  }
  const lensBox = () => (px < -1e3 ? null : { x0: px - LR - 4, y0: py - LR - 4, x1: px + LR + 4, y1: py + LR + 4 });
  const ringBox = () => { let b = null; for (const w of ripples) b = union(b, { x0: w.x - w.r - 30, y0: w.y - w.r - 30, x1: w.x + w.r + 30, y1: w.y + w.r + 30 }); return b; };
  function lens() {
    if (px < -1e3) return;
    ctx.save(); ctx.beginPath(); ctx.arc(px, py, LR, 0, 7); ctx.clip();
    ctx.clearRect(px - LR, py - LR, LR * 2, LR * 2);   // clear glass: the page shows through, no tint
    const r = LR / LM + CW;
    cells({ x0: px - r, y0: py - r, x1: px + r, y1: py + r }, (i, j, x, y) => {
      const ch = ledger(i, j), X = px + (x - px) * LM, Y = py + (y - py) * LM, u = Math.hypot(X - px, Y - py) / LR; if (u > 1.05) return;
      if (ch === " ") { if (hasDot(i, j)) glyph(ctx, "·", "soft", X, Y, 0.5, LM * 0.95); return; }   // the dot grid, magnified
      glyph(ctx, ch, u < 0.7 ? "strong" : "soft", X, Y, Math.max(0.12, 0.85 - 0.75 * u * u), LM * 0.95);
    });
    ctx.restore();
    ctx.strokeStyle = rim; ctx.lineWidth = 1; ctx.globalAlpha = 0.35; ctx.beginPath(); ctx.arc(px, py, LR - 0.5, 0, 7); ctx.stroke();
  }
  function rings(dt) {
    for (const w of ripples) {
      cells({ x0: w.x - w.r - 24, y0: w.y - w.r - 24, x1: w.x + w.r + 24, y1: w.y + w.r + 24 }, (i, j, x, y) => {
        const dx = x - w.x, dy = y - w.y, d = Math.hypot(dx, dy), band = Math.abs(d - w.r); if (band > 20) return;
        const k = (1 - band / 20) * w.a; if (k < 0.05 || Math.hypot(x - px, y - py) < LR) return;   // the glass stays clean
        ctx.clearRect(x - CW / 2, y - CH / 2, CW, CH);
        glyph(ctx, k > 0.6 ? "+" : k > 0.3 ? ":" : "·", k > 0.5 ? "strong" : "soft", x + dx / (d || 1) * 6 * k, y + dy / (d || 1) * 6 * k, 0.25 + 0.6 * k);
      });
      w.r += 0.75 * dt; w.a *= Math.pow(0.955, dt / 16.7);
    }
    ripples = ripples.filter((w) => w.a > 0.05 && w.r < Math.hypot(W, H));
  }
  function request() { if (!raf) raf = requestAnimationFrame(frame); }
  function frame(ms) {
    raf = 0; const dt = Math.min(50, lastT ? ms - lastT : 16.7); lastT = ms;
    if (document.hidden) return;
    px = tx; py = ty;
    const r = union(dirty, union(lensBox(), ringBox())); if (r) restore(r);
    lens(); rings(dt);
    dirty = union(lensBox(), ringBox());
    if (ripples.length) request();
  }
  addEventListener("pointermove", (e) => { tx = e.clientX; ty = e.clientY; request(); }, { passive: true });
  document.documentElement.addEventListener("pointerleave", () => { tx = ty = -1e4; request(); });
  if (!STILL) document.addEventListener("pointerdown", (e) => { ripples.push({ x: e.clientX, y: e.clientY, r: 0, a: 1 }); lastT = 0; request(); }, { passive: true });
  addEventListener("resize", setup);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { dirty = { x0: 0, y0: 0, x1: W, y1: H }; request(); } });
  new MutationObserver(setup).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  (document.fonts ? document.fonts.ready : Promise.resolve()).then(setup);
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

// ---- updates (desktop app only: the server answers /api/update there; elsewhere the request 404s and nothing shows)
(() => {
  if (!window.fetch) return;
  const short = (v) => String(v || "").replace(/ · built.*$/, "");
  fetch("/api/update", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).then((d) => {
    const u = d && d.update; if (!u || !u.available || !u.latest) return;
    const box = document.createElement("div"); box.className = "upd"; box.setAttribute("role", "status");
    const h = document.createElement("p"); h.className = "upd-h"; h.textContent = "Доступно обновление";
    const v = document.createElement("p"); v.className = "upd-v"; v.textContent = `${short(u.current).split(" @ ")[0]} → ${short(u.latest.version)}`;
    const b = document.createElement("button"); b.type = "button"; b.className = "btn primary small"; b.textContent = "Обновить сейчас";
    const msg = document.createElement("p"); msg.className = "upd-m"; msg.hidden = true;
    b.addEventListener("click", async () => {
      b.disabled = true; msg.hidden = false; msg.textContent = "Скачиваю и устанавливаю… приложение закроется и откроется само (около минуты).";
      try {
        const r = await (await fetch("/api/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
        if (!r.ok) { b.disabled = false; msg.textContent = r.error && r.error.code === "busy" ? "Сейчас идёт обучение или оценка: обновите, когда оно закончится." : "Не удалось начать обновление: " + ((r.error && r.error.message) || "ошибка"); }
      } catch { /* the app is closing for the update: expected */ }
    });
    box.append(h, v, b, msg);
    const foot = matchMedia("(min-width: 1100px)").matches && document.querySelector(".side-foot");
    if (foot) foot.prepend(box); else document.body.append(box);
  }).catch(() => { /* offline or not the desktop app */ });
})();

// ---- keyboard shortcuts on every page: g then a letter goes to a section, n starts a new training, ? lists them
(() => {
  const GO = { h: "/", t: "/train.html", r: "/runs.html", i: "/play.html", s: "/settings.html" };
  const LIST = [["g h", "Главная"], ["g t", "Обучение"], ["g r", "Запуски"], ["g i", "Расследование"], ["g s", "Настройки"],
    ["n", "Новое обучение (на странице «Запуски» — новый запуск)"], ["?", "Эта подсказка"], ["Esc", "Закрыть"]];
  let pending = 0, box = null;
  const typing = (e) => /INPUT|SELECT|TEXTAREA/.test((e.target && e.target.tagName) || "") || (e.target && e.target.isContentEditable) || document.querySelector("dialog[open]");
  const help = () => {
    if (box) { box.close(); return; }
    box = document.createElement("dialog");
    box.className = "kbd-help";
    box.setAttribute("aria-labelledby", "kbd-h");
    const h = document.createElement("h2"); h.id = "kbd-h"; h.textContent = "Клавиши";
    const dl = document.createElement("dl");
    for (const [k, v] of LIST) { const dt = document.createElement("dt"); for (const part of k.split(" ")) { const kb = document.createElement("kbd"); kb.textContent = part; dt.append(kb); } const dd = document.createElement("dd"); dd.textContent = v; dl.append(dt, dd); }
    box.append(h, dl);
    box.addEventListener("close", () => { box.remove(); box = null; });
    box.addEventListener("click", (e) => { if (e.target === box) box.close(); });
    document.body.append(box);
    box.showModal();
  };
  addEventListener("keydown", (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || (typing(e) && !box)) return;
    if (e.key === "?") { e.preventDefault(); help(); return; }
    if (pending && GO[e.key]) { e.preventDefault(); pending = 0; location.href = GO[e.key]; return; }
    pending = e.key === "g" ? setTimeout(() => { pending = 0; }, 1200) : 0;
    if (e.key === "n" && !/\/runs\.html$/.test(location.pathname)) { e.preventDefault(); location.href = "/train.html"; }
  });
})();
