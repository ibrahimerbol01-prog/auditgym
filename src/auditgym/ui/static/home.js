"use strict";
// Home: the Launch screen. Shows the latest training's best held-out reward with a mini curve, if there is one.
const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const f2 = (v) => (v < 0 ? "−" : "") + Math.abs(v).toFixed(2);

(() => { const b = $("theme"); const tc = document.querySelector('meta[name="theme-color"]'); const lbl = b.querySelector("span");
  const sync = () => { const dark = document.documentElement.dataset.theme === "dark"; b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема"); lbl.textContent = dark ? "Светлая" : "Тёмная"; tc.setAttribute("content", dark ? "#0e0e11" : "#f7f7f8"); };
  sync(); b.addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme; try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* private mode */ } sync(); }); })();

function spark(host, values) {  // held-out reward per evaluation, −1..1, one 2px line and an end dot
  const W = 220, H = 44, X = (i) => 4 + (i / Math.max(1, values.length - 1)) * (W - 8), Y = (v) => 4 + ((1 - v) / 2) * (H - 8);
  const s = document.createElementNS(SVGNS, "svg"); s.setAttribute("viewBox", `0 0 ${W} ${H}`); s.setAttribute("width", W); s.setAttribute("height", H);
  const z = document.createElementNS(SVGNS, "line"); Object.entries({ x1: 0, x2: W, y1: Y(0), y2: Y(0), class: "z" }).forEach(([k, v]) => z.setAttribute(k, v)); s.append(z);
  const p = document.createElementNS(SVGNS, "path"); p.setAttribute("d", values.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1)).join(" ")); s.append(p);
  const c = document.createElementNS(SVGNS, "circle"); const n = values.length - 1; Object.entries({ cx: X(n), cy: Y(values[n]), r: 4 }).forEach(([k, v]) => c.setAttribute(k, v)); s.append(c);
  host.replaceChildren(s);
}

(async () => {
  try {
    const list = (await (await fetch("/api/runs", { cache: "no-store" })).json()).runs || [];
    const t = list.find((r) => r.kind === "training");
    if (!t) return;
    const run = (await (await fetch("/api/runs/" + encodeURIComponent(t.id), { cache: "no-store" })).json()).run;
    const devs = (run.points || []).filter((p) => p.dev).map((p) => p.dev.reward);
    const best = run.summary && run.summary.dev_best;
    if (best != null) $("last-v").textContent = f2(best);
    $("last-d").textContent = `лучшая награда на dev · ${run.method === "reinforce" ? "REINFORCE" : "CEM"} · ${run.status === "running" ? "идёт" : "итераций " + (run.points || []).length}`;
    $("last-card").href = "/train.html#run=" + encodeURIComponent(run.id);
    if (devs.length > 1) spark($("last-spark"), devs);
  } catch { /* no server API (static preview): the card keeps its placeholder */ }
})();
