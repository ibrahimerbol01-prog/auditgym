"use strict";
// Home: "ready when you are". An ASCII ledger book turning in place, a launch bar that starts training directly
// (settings from the assistant/scout), and dataset recipes.
const $ = (id) => document.getElementById(id);

(() => { const b = $("theme"); const tc = document.querySelector('meta[name="theme-color"]'); const lbl = b.querySelector("span");
  const sync = () => { const dark = document.documentElement.dataset.theme === "dark"; b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема"); lbl.textContent = dark ? "Светлая" : "Тёмная"; tc.setAttribute("content", dark ? "#0e0e11" : "#f7f7f8"); };
  sync(); b.addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme; try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* private mode */ } sync(); }); })();

// ---- ASCII: a ray-marched ledger book (box with ruled pages), shaded with a character ramp
const RAMP = " .:-=+*#%@";
const COLS = 60, ROWS = 22;
function sdBox(p, b) { const q = p.map((v, i) => Math.abs(v) - b[i]); const o = Math.hypot(...q.map((v) => Math.max(v, 0))); return o + Math.min(Math.max(...q), 0); }
function scene(p, t) {
  const [ca, sa, cb, sb] = [Math.cos(t), Math.sin(t), Math.cos(0.95), Math.sin(0.95)];
  let [x, y, z] = p; [x, z] = [x * ca - z * sa, x * sa + z * ca]; [y, z] = [y * cb - z * sb, y * sb + z * cb];
  const pages = sdBox([x + 0.03, y, z], [1.0, 0.17, 0.72]) - 0.02;             // page block
  const top = sdBox([x, y - 0.2, z], [1.06, 0.03, 0.78]) - 0.01;                // front cover
  const bottom = sdBox([x, y + 0.2, z], [1.06, 0.03, 0.78]) - 0.01;             // back cover
  const spine = sdBox([x + 1.04, y, z], [0.04, 0.22, 0.78]) - 0.01;             // spine
  return Math.min(pages, top, bottom, spine);
}
function frame(t) {
  const L = [-0.45, 0.62, -0.64], out = [];
  for (let j = 0; j < ROWS; j++) {
    let row = "";
    for (let i = 0; i < COLS; i++) {
      const x = (i / COLS - 0.5) * 2.7, y = -(j / ROWS - 0.5) * 2.0;
      let z = -3, hit = false;
      for (let k = 0; k < 34; k++) { const d = scene([x, y, z], t); if (d < 0.008) { hit = true; break; } z += d; if (z > 3) break; }
      if (!hit) { row += " "; continue; }
      const e = 0.01, p = [x, y, z], n = [0, 1, 2].map((a) => { const p1 = p.slice(), p2 = p.slice(); p1[a] += e; p2[a] -= e; return scene(p1, t) - scene(p2, t); });
      const len = Math.hypot(...n) || 1, lum = Math.max(0, (n[0] * L[0] + n[1] * L[1] + n[2] * L[2]) / len);
      row += RAMP[Math.min(9, 1 + Math.floor(lum * 8.9))];
    }
    out.push(row);
  }
  return out.join("\n");
}
(() => {
  const el = $("ascii"); if (!el) return;
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let t = 0.7, on = true, last = 0;
  el.textContent = frame(t);
  if (still) return;
  new IntersectionObserver((es) => { on = es[0].isIntersecting; }).observe(el);
  document.addEventListener("visibilitychange", () => { on = !document.hidden; });
  const loop = (ms) => { if (on && ms - last > 33) { last = ms; t += 0.018; el.textContent = frame(t); } requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
})();

// ---- launch bar
const SIZES = { fast: { iterations: 12, population: 8, episodes_per_candidate: 2 }, std: { iterations: 30, population: 16, episodes_per_candidate: 4 }, deep: { iterations: 40, population: 24, episodes_per_candidate: 4 } };
fetch("/api/scout", { cache: "no-store" }).then((r) => r.json()).then((d) => {
  const sc = d.scout || {}, m = sc.machine || {}, rec = (sc.recommendation || {}).config;
  if (rec) SIZES.std = { iterations: rec.iterations, population: rec.population, episodes_per_candidate: rec.episodes_per_candidate };
  const est = (sc.recommendation || {}).est_seconds;
  $("l-hint").textContent = `${m.cpu_count ? m.cpu_count + " ядра · " : ""}${m.ram_gb ? m.ram_gb + " ГБ · " : ""}помощник: «Стандарт»${est ? ` ≈ ${Math.max(1, Math.round(est / 60))} мин` : ""}`;
}).catch(() => { $("l-hint").textContent = "только CPU · без сети"; });

for (const b of document.querySelectorAll(".recipe")) b.addEventListener("click", () => {
  $("l-data").value = b.dataset.preset;
  for (const o of document.querySelectorAll(".recipe")) o.classList.toggle("on", o === b);
  $("l-data").focus();
});
$("l-data").addEventListener("change", (e) => { for (const o of document.querySelectorAll(".recipe")) o.classList.toggle("on", o.dataset.preset === e.target.value); });
document.querySelector('.recipe[data-preset="mixed"]').classList.add("on");

$("launch-f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("l-err"); err.classList.add("hidden"); $("l-go").disabled = true;
  const body = { method: $("l-model").value, dataset: { preset: $("l-data").value }, ...SIZES[$("l-size").value] };
  try {
    const r = await (await fetch("/api/train", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
    if (r.ok) { location.href = "/train.html#run=" + encodeURIComponent(r.run); return; }
    err.textContent = r.error && r.error.code === "busy" ? "Уже идёт другое обучение или оценка — дождитесь его на странице «Обучение»." : "Не удалось запустить: " + ((r.error && r.error.message) || "ошибка");
  } catch { err.textContent = "Сервер недоступен: запустите приложение или python -m auditgym.cli ui."; }
  err.classList.remove("hidden"); $("l-go").disabled = false;
});
