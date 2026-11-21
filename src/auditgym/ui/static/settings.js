"use strict";
// Settings: theme, app version and updates (desktop app only), and the environment's verification report.
const $ = (id) => document.getElementById(id);

// ---- theme: the sidebar button and the segmented control stay in sync
(() => {
  const root = document.documentElement, b = $("theme"), lbl = b.querySelector("span"), tc = document.querySelector('meta[name="theme-color"]');
  const picks = document.querySelectorAll("[data-pick]");
  const sync = () => {
    const dark = root.dataset.theme === "dark";
    b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема"); lbl.textContent = dark ? "Светлая" : "Тёмная";
    tc.setAttribute("content", dark ? "#0e0e11" : "#f7f7f8");
    for (const p of picks) p.setAttribute("aria-pressed", String((p.dataset.pick === "dark") === dark));
  };
  const set = (dark) => { if (dark) root.dataset.theme = "dark"; else delete root.dataset.theme; try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* private mode */ } sync(); };
  b.addEventListener("click", () => set(root.dataset.theme !== "dark"));
  for (const p of picks) p.addEventListener("click", () => set(p.dataset.pick === "dark"));
  sync();
})();

// ---- version and updates (the desktop app answers /api/update; a source checkout or the plain server does not)
(() => {
  const ver = $("s-ver"), btn = $("s-check"), msg = $("s-msg");
  const short = (v) => String(v || "").replace(/ · built.*$/, "");
  let offer = null;
  const show = (u) => {
    ver.textContent = short(u.current);
    offer = u.available && u.latest ? u : null;
    if (offer) { msg.textContent = `Доступна новая версия: ${short(u.latest.version)}.`; btn.textContent = "Обновить сейчас"; btn.className = "btn primary small"; }
    else { msg.textContent = u.error && !u.latest ? u.error : "Установлена последняя версия."; btn.textContent = "Проверить обновления"; btn.className = "btn outline small"; }
  };
  const load = async (force) => {
    const r = await fetch("/api/update" + (force ? "?force=1" : ""), { cache: "no-store" });
    const d = r.status === 404 ? null : await r.json();
    if (r.status === 404 || !d || !d.update) { ver.textContent = "запуск из исходников"; msg.textContent = "Обновления встроены в приложение для компьютера; здесь — git pull."; btn.hidden = true; return; }
    show(d.update);
  };
  btn.addEventListener("click", async () => {
    btn.disabled = true;
    if (!offer) { msg.textContent = "Проверяю…"; try { await load(true); } catch { msg.textContent = "Не удалось проверить: нет сети?"; } btn.disabled = false; return; }
    msg.textContent = "Скачиваю и устанавливаю… приложение закроется и откроется само (около минуты).";
    try {
      const r = await (await fetch("/api/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
      if (!r.ok) { btn.disabled = false; msg.textContent = r.error && r.error.code === "busy" ? "Сейчас идёт обучение или оценка: обновите, когда оно закончится." : "Не удалось начать обновление: " + ((r.error && r.error.message) || "ошибка"); }
    } catch { /* the app is closing for the update: expected */ }
  });
  load(false).catch(() => { ver.textContent = "неизвестна"; });
})();

// ---- the report's headline next to its link
fetch("/data/report.json", { cache: "no-store" }).then((r) => r.json()).then((rep) => {
  const all = Object.values(rep.areas || {}).flat(), ok = all.filter((c) => c.passed).length;
  if (rep.estimated_score) $("s-rep").textContent = `${rep.estimated_score.total} из 100 по формулам брифа · пройдено ${ok} из ${all.length} проверок`;
}).catch(() => { /* no report.json yet: keep the description */ });
