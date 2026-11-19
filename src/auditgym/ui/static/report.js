"use strict";
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); } for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k))); return e; };
const AREAS = [["contract", "Контракт и изоляция", 25, "проверок"], ["data", "Данные и эталон", 25, "эпизодов"], ["reward", "Надёжность награды", 25, "проверок"], ["repro", "Воспроизводимость", 15, "пар"], ["engineering", "Инженерия и объяснение", 10, "критериев"]];
const RANK = { oracle: ["Эталон", "lime"], reconcile: ["Сверщик", "lilac"], random: ["Стажёр", "dim"], flag_all: ["Паникёр", "pink"] };
const sgn = (x) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(3);

async function main() {
  let rep;
  try { rep = await (await fetch("/data/report.json")).json(); } catch { $("areas").append(el("div", { class: "card" }, "report.json не найден: запустите python -m auditgym.verify")); return; }
  $("ver").textContent = `report.json · ENV ${rep.versions.env} · Python ${rep.versions.python} · ${rep.seconds} с`;
  $("est").textContent = rep.estimated_score.total;
  const keys = { contract: "contract_isolation", data: "data_reference", reward: "reward_reliability", repro: "reproducibility", engineering: "engineering" };
  for (const [k, name, max, unit] of AREAS) {
    const checks = rep.areas[k]; const pass = checks.filter((c) => c.passed).length;
    const cells = el("div", { class: "cells", role: "img", "aria-label": `${pass} из ${checks.length}` }, ...checks.map((c) => el("i", { class: c.passed ? "" : "f", title: `${c.id}: ${c.name}${c.error ? " — " + c.error : ""}` })));
    $("areas").append(el("div", { class: "card", style: "display:flex;flex-direction:column;gap:10px" }, el("div", { style: "font-weight:700;min-height:42px" }, name),
      el("div", {}, el("span", { class: "disp", style: `font-size:30px;color:${pass === checks.length ? "var(--lime)" : "var(--txt)"}` }, (+rep.estimated_score[keys[k]]).toFixed(1)), el("span", { class: "muted" }, " / " + max)),
      cells, el("div", { class: "mono muted", style: "font-size:12px" }, `${pass} / ${checks.length} ${unit}`)));
  }
  const groups = ["clean", "mixed", "interacting"];
  const t = $("pol");
  t.append(el("thead", {}, el("tr", {}, el("th", {}, "Политика · звание"), el("th", { class: "num" }, "Чистые"), el("th", { class: "num" }, "Смешанные"), el("th", { class: "num" }, "Взаимодействие"), el("th", { class: "num" }, "F1"), el("th", { class: "num" }, "Шаги"), el("th", { class: "num" }, "Время"))));
  const tb = el("tbody");
  for (const s of rep.policy_summary) {
    const rows = rep.policies.filter((r) => r.policy === s.policy);
    const avg = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0) / rows.length;
    tb.append(el("tr", {}, el("td", {}, el("span", { class: "badge " + RANK[s.policy][1] }, RANK[s.policy][0]), " ", el("span", { class: "mono" }, s.policy)),
      ...groups.map((g) => el("td", { class: "num mono" }, sgn(s[g]))), el("td", { class: "num" }, avg("f1").toFixed(2)), el("td", { class: "num" }, avg("steps").toFixed(1)), el("td", { class: "num muted" }, avg("seconds").toFixed(2) + " с")));
  }
  t.append(tb);
  $("pol-sub").textContent = `${rep.policies.length / 4} эпизодов на политику · средняя награда`;
  const fa = rep.failure_analysis.reconcile_rules_recall_by_type;
  for (const [type, v] of Object.entries(fa)) {
    const rec = v.issues ? v.found / v.issues : 1;
    $("fa").append(el("div", {}, el("div", { class: "row", style: "justify-content:space-between;font-size:13px" }, el("span", { class: "mono" }, type), el("b", {}, `${rec.toFixed(2)} · ${v.found}/${v.issues}`)), el("div", { class: "b" }, el("i", { style: `width:${rec * 100}%;background:${rec >= 0.9 ? "var(--lime)" : rec >= 0.6 ? "var(--lilac)" : "var(--pink)"}` }))));
  }
  const NAMES = { duplicates_by_amount_only: "дубли только по сумме", utc_dates_instead_of_company_tz: "даты по UTC, а не по компании", any_unapplied_cash_is_an_error: "любой нераспределённый кэш = ошибка", findings_without_evidence: "находки без доказательств", "careful_rules (reference)": "аккуратные правила (эталон)" };
  const tr = rep.failure_analysis.naive_tricks || {};
  if (Object.keys(tr).length) {
    $("fa").append(el("div", { class: "muted", style: "font-size:13px;margin-top:6px" }, "Наивные трюки против отвлекающих случаев · средняя награда (−1 … +1)"));
    for (const [k, v] of Object.entries(tr)) {
      const w = Math.max(0, (v.mean_reward + 1) / 2) * 100;
      $("fa").append(el("div", {}, el("div", { class: "row", style: "justify-content:space-between;font-size:13px" }, el("span", {}, NAMES[k] || k), el("b", { class: "mono" }, sgn(v.mean_reward) + ` · FP ${v.fp} · FN ${v.fn}`)), el("div", { class: "b" }, el("i", { style: `width:${w}%;background:${v.mean_reward > 0.9 ? "var(--lime)" : v.mean_reward > 0 ? "var(--lilac)" : "var(--pink)"}` }))));
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
function select() {
  const p = $("pick-pol").value, e = $("pick-ep").value;
  view = T.filter((x) => (x.policy || "policy") === p && x.episode_id === e).sort((a, b) => a.step - b.step);
  pos = 0; $("scrub").max = Math.max(view.length - 1, 0); render();
}
function render() {
  const ol = $("steps"); ol.textContent = "";
  view.forEach((s, i) => { const a = s.action; const args = a.tool === "submit" ? `${a.args.findings.findings.length} находок` : JSON.stringify(a.args).slice(0, 60);
    const li = el("li", { class: "row", style: `flex-wrap:nowrap;gap:10px;padding:4px 6px;border-radius:10px 3px;cursor:pointer;${i === pos ? "background:rgba(184,242,92,.12);box-shadow:inset 3px 0 0 var(--lime)" : ""}`, onclick: () => { pos = i; render(); } },
      el("span", { class: "muted", style: "width:34px" }, "#" + s.step), el("span", { style: "width:100px" }, a.tool), el("span", { class: "muted", style: "flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, args));
    ol.append(li); });
  $("scrub").value = pos;
  const s = view[pos]; if (!s) { $("obs").textContent = "нет траекторий"; return; }
  const o = JSON.parse(JSON.stringify(s.observation)); if (o.result && Array.isArray(o.result.rows) && o.result.rows.length > 3) { o.result.rows = [...o.result.rows.slice(0, 3), `… ещё ${o.result.rows.length - 3} строк`]; }
  $("obs").textContent = `reward ${s.reward}  terminated ${s.terminated}  truncated ${s.truncated}\n` + JSON.stringify(o, null, 2);
}
$("pick-pol").addEventListener("change", fillEps); $("pick-ep").addEventListener("change", select);
$("scrub").addEventListener("input", (e) => { pos = +e.target.value; render(); });
$("b-prev").addEventListener("click", () => { pos = Math.max(0, pos - 1); render(); });
$("b-next").addEventListener("click", () => { pos = Math.min(view.length - 1, pos + 1); render(); });
$("b-play").addEventListener("click", () => { if (timer) { clearInterval(timer); timer = null; $("b-play").textContent = "▶"; return; } $("b-play").textContent = "❚❚"; timer = setInterval(() => { if (pos >= view.length - 1) { clearInterval(timer); timer = null; $("b-play").textContent = "▶"; return; } pos += 1; render(); }, 700); });
main();
