"use strict";
// Home: "ready when you are". The ASCII logo with a shimmer, a launch bar that starts training directly
// (settings from the assistant/scout), and dataset recipes.
const $ = (id) => document.getElementById(id);

(() => { const b = $("theme"); const tc = document.querySelector('meta[name="theme-color"]'); const lbl = b.querySelector("span");
  const sync = () => { const dark = document.documentElement.dataset.theme === "dark"; b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема"); lbl.textContent = dark ? "Светлая" : "Тёмная"; tc.setAttribute("content", dark ? "#0e0e11" : "#f7f7f8"); };
  sync(); b.addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme; try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* private mode */ } sync(); }); })();

// ---- ASCII logo: the pixel mark and "AUDITGYM" in a 5x7 block font; a shimmer wave runs through the characters
const FONT = {
  A: [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"], U: ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
  D: ["####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."], I: ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"],
  T: ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."], G: [".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."],
  Y: ["#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."], M: ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
};
const MARK = ["######.", ".......", "###....", "......#", ".#...#.", "..#.#..", "...#..."];  // same as the logo
const BITS = (() => {  // 7 rows of 0/1; each glyph pixel becomes 2 characters wide
  const rows = MARK.map((r) => r + "....");
  for (const ch of "AUDITGYM") FONT[ch].forEach((r, i) => { rows[i] += r + ".."; });
  return rows.map((r) => [...r].flatMap((c) => [c === "#", c === "#"]));
})();
function frame(t) {
  return BITS.map((row, y) => row.map((on, x) => {
    const w = Math.sin(t * 2.2 - x * 0.16 + y * 0.35);          // a diagonal wave sweeping left to right
    if (on) return w > 0.9 ? "░" : w > 0.7 ? "▒" : w > 0.45 ? "▓" : "█";   // solid letters, a sheen passes over
    return w > 0.985 && (x + y) % 5 === 0 ? "·" : " ";
  }).join("")).join("\n");
}
(() => {
  const el = $("ascii"); if (!el) return;
  el.textContent = frame(0.6);
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  let on = true, last = 0, t = 0.6;
  new IntersectionObserver((es) => { on = es[0].isIntersecting; }).observe(el);
  document.addEventListener("visibilitychange", () => { on = !document.hidden; });
  const loop = (ms) => { if (on && ms - last > 40) { last = ms; t += 0.03; el.textContent = frame(t); } requestAnimationFrame(loop); };
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
