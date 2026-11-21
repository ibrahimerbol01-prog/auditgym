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
