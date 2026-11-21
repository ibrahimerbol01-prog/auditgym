"use strict";
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); } for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k))); return e; };
const AREAS = [["contract", "Контракт и изоляция", 25, "проверок"], ["data", "Данные и эталон", 25, "эпизодов"], ["reward", "Надёжность награды", 25, "проверок"], ["repro", "Воспроизводимость", 15, "пар"], ["engineering", "Инженерия и объяснение", 10, "критериев"]];
const RANK = { oracle: ["Эталон", "gold"], reconcile: ["Сверщик", "lime"], random: ["Стажёр", "dim"], flag_all: ["Паникёр", "pink"] };
const SVGNS = "http://www.w3.org/2000/svg";
const tm = (kind, label, cls = "") => { const s = document.createElementNS(SVGNS, "svg"); s.setAttribute("class", `tm ${cls} ${kind === "exc" ? "exc" : ""}`.trim()); s.setAttribute("viewBox", "0 0 16 16"); if (label) { s.setAttribute("role", "img"); s.setAttribute("aria-label", label); } else s.setAttribute("aria-hidden", "true"); const u = document.createElementNS(SVGNS, "use"); u.setAttribute("href", "#tm-" + kind); s.append(u); return s; };
(() => { const b = document.getElementById("theme"); if (!b) return; const tc = document.querySelector('meta[name="theme-color"]'); const lbl = b.querySelector("span");
  const sync = () => { const dark = document.documentElement.dataset.theme === "dark"; b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема"); if (lbl) lbl.textContent = dark ? "Светлая" : "Тёмная"; if (tc) tc.setAttribute("content", dark ? "#0e0e11" : "#f7f7f8"); };
  sync(); b.addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme; try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* private mode */ } sync(); }); })();
const sgn = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(3);
const divBar = (v) => el("div", { class: "dv", "aria-hidden": "true" }, el("i", { class: v >= 0 ? "up" : "dn", style: `width:${Math.min(1, Math.abs(v)) * 50}%` }));

async function main() {
  let rep;
  try { rep = await (await fetch("/data/report.json")).json(); } catch { $("areas").append(el("div", { class: "card" }, el("div", { class: "an" }, "report.json не найден"), el("div", { class: "au" }, "запустите python -m auditgym.verify"))); return; }
  $("ver").textContent = `ENV ${rep.versions.env} · Python ${rep.versions.python} · без сети`;
  $("rv-sec").textContent = `${rep.seconds} с · Python ${rep.versions.python}`; $("rv-by").textContent = rep.independent_verifier ? "независимый верификатор — сходится" : "независимый верификатор — не запускался";
  $("est").textContent = rep.estimated_score.total;
  const all = Object.values(rep.areas).flat(); const okN = all.filter((c) => c.passed).length;
  $("seal-n").replaceChildren(tm(okN === all.length ? "agree" : "exc", ""), `пройдено ${okN} из ${all.length} проверок`);
  const keys = { contract: "contract_isolation", data: "data_reference", reward: "reward_reliability", repro: "reproducibility", engineering: "engineering" };
  for (const [k, name, max, unit] of AREAS) {
    const checks = rep.areas[k]; const pass = checks.filter((c) => c.passed).length;
    const cells = el("div", { class: "cells", role: "img", "aria-label": `${pass} из ${checks.length} пройдено` }, ...checks.map((c) => { const m = tm(c.passed ? "agree" : "exc", ""); const ti = document.createElementNS(SVGNS, "title"); ti.textContent = `${c.id}: ${c.name}${c.error ? " — " + c.error : ""}`; m.prepend(ti); return m; }));
    $("areas").append(el("div", { class: "card" }, el("div", { class: "an" }, el("span", { class: "wpref" }, `R-1.${AREAS.findIndex((a) => a[0] === k) + 1}`), name),
      el("div", { class: "av" + (pass === checks.length ? " full" : "") }, (+rep.estimated_score[keys[k]]).toFixed(1), el("small", {}, "/ " + max)),
      cells, el("div", { class: "au" }, `${pass} / ${checks.length} ${unit}`)));
  }
  const groups = ["clean", "mixed", "interacting"];
  const t = $("pol");
  t.append(el("thead", {}, el("tr", {}, el("th", {}, "Политика · звание"), el("th", { class: "num" }, "Средняя"), el("th", { class: "num" }, "Чистые"), el("th", { class: "num" }, "Смешанные"), el("th", { class: "num" }, "Взаимодействие"), el("th", { class: "num" }, "F1"), el("th", { class: "num" }, "Шаги"), el("th", { class: "num" }, "Время"))));
  const tb = el("tbody");
  for (const s of rep.policy_summary) {
    const rows = rep.policies.filter((r) => r.policy === s.policy);
    const avg = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0) / rows.length;
    const mean = (s.clean + s.mixed + s.interacting) / 3;
    tb.append(el("tr", {}, el("td", { class: "pn" }, el("span", { class: "badge " + RANK[s.policy][1] }, RANK[s.policy][0]), el("code", {}, s.policy)),
      el("td", { class: "num" }, el("div", { class: "mb" }, divBar(mean), el("b", { class: mean > 0 ? "ok" : "bad", style: "font-weight:500" }, sgn(mean)))),
      ...groups.map((g) => el("td", { class: "num mono " + (s[g] > 0 ? "ok" : s[g] < 0 ? "bad" : "") }, sgn(s[g]))), el("td", { class: "num" }, avg("f1").toFixed(2)), el("td", { class: "num" }, avg("steps").toFixed(1)), el("td", { class: "num muted" }, avg("seconds").toFixed(2) + " с")));
  }
  t.append(tb);
  $("pol-sub").textContent = `${rep.policies.length / 4} эпизодов на политику`;
  const fa = rep.failure_analysis.reconcile_rules_recall_by_type;
  for (const [type, v] of Object.entries(fa)) {
    const rec = v.issues ? v.found / v.issues : 1;
    $("fa").append(el("div", { class: "fa-row" }, el("div", { class: "row" }, el("span", { class: "mono" }, type), el("b", {}, `${rec.toFixed(2)} · ${v.found}/${v.issues}`)), el("div", { class: "b" }, el("i", { style: `width:${rec * 100}%;background:${rec >= 0.9 ? "var(--pos)" : rec >= 0.6 ? "var(--lilac)" : "var(--pink)"}` }))));
  }
  const NAMES = { duplicates_by_amount_only: "дубли только по сумме", utc_dates_instead_of_company_tz: "даты по UTC, а не по компании", any_unapplied_cash_is_an_error: "любой нераспределённый кэш = ошибка", findings_without_evidence: "находки без доказательств", "careful_rules (reference)": "аккуратные правила (эталон)" };
  const tr = rep.failure_analysis.naive_tricks || {};
  if (Object.keys(tr).length) {
    $("fa").append(el("div", { class: "fa-sub" }, "Наивные трюки против ловушек · награда −1 … +1"));
    for (const [k, v] of Object.entries(tr)) {
      const w = Math.max(0, (v.mean_reward + 1) / 2) * 100;
      $("fa").append(el("div", { class: "fa-row" }, el("div", { class: "row" }, el("span", {}, NAMES[k] || k), el("b", {}, sgn(v.mean_reward) + ` · FP ${v.fp} · FN ${v.fn}`)), el("div", { class: "b" }, el("i", { style: `width:${w}%;background:${v.mean_reward > 0.9 ? "var(--pos)" : v.mean_reward > 0 ? "var(--lilac)" : "var(--pink)"}` }))));
    }
  }
  $("fz").textContent = `Фаззинг конфигураций: ${rep.fuzz.valid_episodes_ok} валидных эпизодов без ошибок, ${rep.fuzz.rejected_with_bounded_error} конфигов отклонены с понятной ошибкой, сбоев: ${rep.fuzz.failures.length}. Ложных срабатываний правил: ${rep.failure_analysis.reconcile_false_positives}.`;
  await loadTraj();
}

let T = [], view = [], pos = 0, timer = null;
async function loadTraj() {
  try { const txt = await (await fetch("/data/trajectories.jsonl")).text(); T = txt.split("\n").filter(Boolean).map((l) => JSON.parse(l)); } catch { T = []; }
  const pols = [...new Set(T.map((x) => x.policy || "policy"))];
  $("pick-pol").replaceChildren(...pols.map((p) => el("option", { value: p }, (RANK[p] ? RANK[p][0] + " · " : "") + p)));
  $("pick-pol").value = pols.includes("reconcile") ? "reconcile" : pols[0];
  fillEps();
}
function fillEps() {
  const p = $("pick-pol").value; const eps = [...new Set(T.filter((x) => (x.policy || "policy") === p).map((x) => x.episode_id))];
  $("pick-ep").replaceChildren(...eps.map((e) => el("option", { value: e }, e))); select();
}
function stopPlay() {
  if (timer) { clearInterval(timer); timer = null; }
  $("b-play").textContent = "▶";
  $("b-play").setAttribute("aria-label", "Воспроизвести");
}
function select() {
  stopPlay();
  const p = $("pick-pol").value, e = $("pick-ep").value;
  view = T.filter((x) => (x.policy || "policy") === p && x.episode_id === e).sort((a, b) => a.step - b.step);
  pos = 0; $("scrub").max = Math.max(view.length - 1, 0); render();
}
const short = (c) => (c && c.length > 12 ? c.slice(0, 4) + "…" + c.slice(-4) : c);
// One step in words: the tool and the arguments that matter.
function stepLabel(a) {
  const g = a.args || {};
  if (a.tool === "list_records") return `${g.table} · ${g.cursor ? "→ " + short(g.cursor) : "стр. 1"}`;
  if (a.tool === "get_record") return `${g.table || ""} / ${g.record_id || g.id || ""}`;
  if (a.tool === "get_document") return g.doc_id || "";
  if (a.tool === "calculator") return g.expression || "";
  if (a.tool === "submit") { const n = ((g.findings || {}).findings || []).length; return n ? `${n} ${n === 1 ? "находка" : n < 5 ? "находки" : "находок"}` : "пустой ответ"; }
  return JSON.stringify(g).slice(0, 60);
}
const cellv = (v) => (v === null || v === undefined ? "—" : Array.isArray(v) ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : x)).join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v));
const kvList = (obj) => el("dl", { class: "kv" }, ...Object.entries(obj).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, cellv(v))]));
const stat = (label, value, cls) => el("div", { class: "os" }, el("span", {}, label), el("b", { class: cls || "" }, value));
// An observation as the agent would read it: rows as a table, records as key-value, a result as a summary.
function obsView(s) {
  const o = s.observation || {}; const a = s.action; const box = el("div", { class: "ov" });
  if (o.ok === false) { box.append(el("div", { class: "ov-err" }, el("b", {}, (o.error && o.error.code) || "error"), " ", (o.error && o.error.message) || "")); return box; }
  const res = o.result || {};
  if (a.tool === "list_records" && Array.isArray(res.rows)) {
    const rows = res.rows; const cols = rows.length ? Object.keys(rows[0]) : [];
    const shown = rows.slice(0, 8);
    box.append(el("div", { class: "scroll" }, el("table", { class: "grid ot" }, el("thead", {}, el("tr", {}, ...cols.map((c) => el("th", { scope: "col", class: /minor|rate/.test(c) ? "num" : "" }, c)))),
      el("tbody", {}, ...shown.map((r) => el("tr", {}, ...cols.map((c) => el("td", { class: /minor|rate/.test(c) ? "num" : "" }, cellv(r[c])))))))));
    box.append(el("div", { class: "ov-foot" }, `${rows.length} строк на странице` + (rows.length > shown.length ? ` · показаны первые ${shown.length}` : ""), el("span", { class: "mono" }, res.next_cursor ? `next_cursor ${short(res.next_cursor)}` : "последняя страница")));
  } else if (a.tool === "calculator") {
    box.append(el("div", { class: "ov-calc" }, el("span", { class: "mono muted" }, (a.args.expression || "") + " ="), el("b", {}, cellv(res.value))));
  } else if (a.tool === "submit" && res.report) {
    const p = res.report; const pf = p.per_finding || [];
    box.append(el("div", { class: "ov-sum" }, stat("Награда", sgn(p.reward), p.reward > 0 ? "ok" : p.reward < 0 ? "bad" : ""), stat("Precision", (+p.precision).toFixed(3)), stat("Recall", (+p.recall).toFixed(3)), stat("F1", (+p.f1).toFixed(3)),
      stat("TP · FP · FN", `${p.tp} · ${p.fp} · ${p.fn}`), stat("Шаги", String(p.inspection_steps))));
    box.append(el("div", { class: "ov-pf" }, el("span", { class: "muted small" }, pf.length ? "Находки:" : `Пустой ответ · статус ${p.status}`), ...pf.map((f) => el("span", { class: "badge " + (f.matched ? "lime" : "pink") }, tm(f.matched ? "agree" : "exc", ""), `№${f.index + 1}`))));
  } else box.append(kvList(res));
  return box;
}
let raw = false;
function render() {
  const ol = $("steps"); ol.textContent = "";
  view.forEach((s, i) => { const a = s.action;
    const li = el("li", { tabindex: "0", "aria-current": i === pos ? "step" : "false", onclick: () => { pos = i; render(); }, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pos = i; render(); } } },
      el("span", { class: "sn" }, String(s.step).padStart(2, "0")), el("span", { class: "st" }, a.tool), el("span", { class: "sa" }, stepLabel(a)));
    ol.append(li); });
  const cur = ol.querySelector('[aria-current="step"]'); if (cur && ol.scrollHeight > ol.clientHeight) ol.scrollTop = Math.max(0, cur.offsetTop - ol.offsetTop - ol.clientHeight / 2);
  $("scrub").value = pos;
  $("b-prev").disabled = pos <= 0;
  $("b-next").disabled = pos >= view.length - 1;
  const s = view[pos]; const obs = $("obs"); obs.textContent = "";
  if (!s) { $("obs-meta").textContent = ""; obs.append(el("div", { class: "muted small" }, "Нет траекторий: запустите python -m auditgym.verify")); return; }
  $("obs-meta").replaceChildren(el("b", {}, `#${s.step} ${s.action.tool}`), el("span", {}, `reward ${s.reward}`), el("span", {}, s.terminated ? "завершён" : s.truncated ? "обрезан" : `осталось ${(s.observation || {}).remaining_steps ?? "—"}`));
  if (raw) { const o = JSON.parse(JSON.stringify(s.observation)); obs.append(el("pre", { class: "raw" }, JSON.stringify({ action: s.action, observation: o, reward: s.reward, terminated: s.terminated, truncated: s.truncated }, null, 2))); }
  else obs.append(obsView(s));
}
$("obs-raw").addEventListener("click", () => { raw = !raw; $("obs-raw").setAttribute("aria-pressed", String(raw)); render(); });
$("pick-pol").addEventListener("change", fillEps); $("pick-ep").addEventListener("change", select);
$("scrub").addEventListener("input", (e) => { pos = +e.target.value; render(); });
$("b-prev").addEventListener("click", () => { pos = Math.max(0, pos - 1); render(); });
$("b-next").addEventListener("click", () => { pos = Math.min(view.length - 1, pos + 1); render(); });
$("b-play").addEventListener("click", () => { if (timer) { stopPlay(); return; } if (pos >= view.length - 1) pos = 0; $("b-play").textContent = "❚❚"; $("b-play").setAttribute("aria-label", "Пауза"); timer = setInterval(() => { if (pos >= view.length - 1) { stopPlay(); return; } pos += 1; render(); }, 700); });
main();
