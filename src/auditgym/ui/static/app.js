"use strict";
// AuditGym Play page. Every action below is a real environment step via POST /step.
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); }
  for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
};
const SVGNS = "http://www.w3.org/2000/svg";
// A reviewer's tick mark: agree (сверено), foot (просуммировано), trace (прослежено), exc (расхождение).
const tm = (kind, label, cls = "") => { const s = document.createElementNS(SVGNS, "svg"); s.setAttribute("class", `tm ${cls} ${kind === "exc" ? "exc" : ""}`.trim()); s.setAttribute("viewBox", "0 0 16 16"); if (label) { s.setAttribute("role", "img"); s.setAttribute("aria-label", label); } else s.setAttribute("aria-hidden", "true"); const u = document.createElementNS(SVGNS, "use"); u.setAttribute("href", "#tm-" + kind); s.append(u); return s; };
const REF = { ledger: "A-1", invoices: "A-2", payments: "A-3", fx: "A-4" };
// Theme: graphite by default, warm paper on request; remembered when storage is available.
(() => { const b = document.getElementById("theme"); if (!b) return; const tc = document.querySelector('meta[name="theme-color"]'); const lbl = b.querySelector("span");
  const sync = () => { const light = document.documentElement.dataset.theme === "light"; b.setAttribute("aria-pressed", String(light)); b.setAttribute("aria-label", light ? "Тёмная тема «графит»" : "Светлая тема «бумага»"); if (lbl) lbl.textContent = light ? "Графит" : "Бумага"; if (tc) tc.setAttribute("content", light ? "#f1ece1" : "#131210"); };
  sync(); b.addEventListener("click", () => { const light = document.documentElement.dataset.theme !== "light"; if (light) document.documentElement.dataset.theme = "light"; else delete document.documentElement.dataset.theme; try { localStorage.setItem("ag-theme", light ? "light" : "dark"); } catch { /* private mode */ } sync(); }); })();
const EXP = { KZT: 2, USD: 2, EUR: 2, UZS: 2, GBP: 2, CNY: 2, JPY: 0, KWD: 3 };
const fmt = (minor, ccy) => { const e = EXP[ccy] ?? 2; const s = minor < 0 ? "-" : ""; const a = Math.abs(minor); if (!e) return s + a.toLocaleString("ru-RU"); return s + Math.floor(a / 10 ** e).toLocaleString("ru-RU") + "." + String(a % 10 ** e).padStart(e, "0"); };
const COLS = {
  ledger: ["row_id", "timestamp", "account", "debit_minor", "credit_minor", "entity_id", "invoice_id", "payment_id"],
  invoices: ["invoice_id", "doc_id", "entity_id", "issued_at", "currency", "total_minor"],
  payments: ["payment_id", "doc_id", "timestamp", "currency", "amount_minor", "invoice_refs"],
  fx: ["date", "source_currency", "target_currency", "rate"],
};
const REFS = {};
const S = { ep: null, steps: 0, table: null, pages: {}, sel: null, findings: [], draft: { aff: [], ev: [] }, docs: {} };
const REDUCED = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

// ---------- hero: the difference counts up once the case card has walked through the reconciliation ----------
(() => {
  const t = document.querySelector("[data-count]"); if (!t || REDUCED) return;
  const target = Number(t.dataset.count), final = t.textContent;
  const paren = final.trim().startsWith("(");
  const show = (minor) => { const a = Math.floor(minor / 100); const v = String(a).replace(/\B(?=(\d{3})+(?!\d))/g, " ") + "." + String(minor % 100).padStart(2, "0"); t.textContent = paren ? `(${v})` : v; };
  show(0);
  setTimeout(() => { const t0 = performance.now(); const tick = (now) => { const k = Math.min(1, (now - t0) / 600); const e = 1 - Math.pow(1 - k, 3); if (k < 1) { show(Math.round(target * e)); requestAnimationFrame(tick); } else t.textContent = final; }; requestAnimationFrame(tick); }, 2600);
})();

async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}
function toast(msg, kind) { document.querySelectorAll(".toast").forEach((x) => x.remove()); const t = el("div", { class: "toast" + (kind === "ok" ? " ok" : ""), role: kind === "ok" ? "status" : "alert" }, msg); document.body.append(t); setTimeout(() => t.remove(), 3200); }
const sign = (x, d = 3) => (x > 0 ? "+" : x < 0 ? "−" : "") + Math.abs(x).toFixed(d);

// ---------- policy schedule (W/P R-2) and the verify figure: real numbers from report.json ----------
const POL = { oracle: ["ORACLE", "Эталон", "знает ответ — потолок награды"], reconcile: ["RECONCILE", "Сверщик", "аккуратные правила сверки"], random: ["RANDOM", "Стажёр", "случайные находки"], flag_all: ["FLAG_ALL", "Паникёр", "обвиняет всё подряд"] };
const REPORT = fetch("/data/report.json").then((r) => r.json()).catch(() => null);
const meanOf = (p) => (p.clean + p.mixed + p.interacting) / 3;
const divBar = (v) => el("div", { class: "dv", "aria-hidden": "true" }, el("i", { class: v >= 0 ? "up" : "dn", style: `width:${Math.min(1, Math.abs(v)) * 50}%` }));
(async () => {
  const tb = document.querySelector("#tape tbody"); if (!tb) return;
  const r = await REPORT;
  if (!r) { tb.append(el("tr", {}, el("td", { colspan: 5, class: "note" }, "report.json не найден: запустите python -m auditgym.verify"))); return; }
  if (r.estimated_score && $("spec-verify")) $("spec-verify").textContent = Math.round(r.estimated_score.total);
  for (const p of r.policy_summary || []) {
    const v = meanOf(p); const n = POL[p.policy] || [p.policy.toUpperCase(), p.policy, ""];
    tb.append(el("tr", {}, el("td", {}, n[1]), el("td", { class: "code" }, n[0]), el("td", { class: "v " + (v >= 0 ? "up" : "dn") }, sign(v)), el("td", { class: "bar" }, divBar(v)), el("td", { class: "note" }, n[2])));
  }
})();

// ---------- start screen ----------
async function loadSplit(split) {
  document.querySelectorAll("[data-split]").forEach((b) => { const on = b.dataset.split === split; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1; });
  const tb = $("ep-rows"); const req = (loadSplit.req = (loadSplit.req || 0) + 1);
  tb.setAttribute("aria-busy", "true");
  let spec;
  try { spec = await (await fetch(`/data/${split}.json`)).json(); } catch { if (req === loadSplit.req) { tb.textContent = ""; tb.append(el("tr", {}, el("td", { colspan: 5, class: "empty-cell" }, "Конфигурации не найдены — запустите python -m auditgym.cli build-suite"))); } return; }
  if (req !== loadSplit.req) return; // a newer tab click won: never mix rows from two sets
  tb.textContent = ""; tb.removeAttribute("aria-busy");
  spec.episodes.forEach((e, i) => {
    const c = e.config; const name = `${split}-${String(i + 1).padStart(2, "0")}`;
    const kinds = c.clean ? [el("span", { class: "k clean" }, "чистая компания")] : [...(c.interactions || []).map((x) => el("span", { class: "k ix" }, "взаимодействие " + x)), el("span", { class: "k" }, c.errors ? "ошибки по конфигу" : "ошибки по умолчанию")];
    tb.append(el("tr", {},
      el("td", { class: "ep" }, name), el("td", { class: "seed" }, "seed " + e.seed), el("td", { class: "cfg" }, ...kinds),
      el("td", { class: "cur" }, el("b", {}, c.base_currency || "KZT"), " · " + (c.foreign_currencies || ["USD", "EUR"]).join(" ")),
      el("td", { class: "go" }, el("button", { class: "btn outline small", "aria-label": `Открыть эпизод ${name}`, onclick: () => start(e.seed, c) }, el("span", { class: "lbl" }, "Открыть"), el("span", { "aria-hidden": "true" }, "→")))));
  });
}
document.querySelectorAll("[data-split]").forEach((b) => b.addEventListener("click", () => loadSplit(b.dataset.split)));
// Arrow keys move between tabs in any tablist (WAI-ARIA tabs pattern).
document.addEventListener("keydown", (e) => {
  const tab = e.target.closest && e.target.closest('[role="tab"]'); if (!tab || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
  const tabs = [...tab.parentElement.querySelectorAll('[role="tab"]')]; let i = tabs.indexOf(tab);
  i = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
  e.preventDefault(); tabs[i].focus(); tabs[i].click();
});

async function start(seed, config) {
  const r = await api("/reset", { seed, config });
  if (!r.observation || !r.observation.ok) { toast(r.observation ? r.observation.error.message : "сервер недоступен"); return; }
  const res = r.observation.result;
  Object.assign(S, { ep: res, steps: 0, table: null, pages: {}, sel: null, findings: [], draft: { aff: [], ev: [] }, docs: {} });
  document.body.classList.add("playing");
  const m = res.manifest;
  $("ep-title").textContent = `${m.counts.ledger} проводок · ${m.counts.invoices} счетов · ${m.counts.payments} платежей · период ${m.period_start} → ${m.period_end}`;
  $("ep-sub").textContent = `${m.episode_id} · база ${m.base_currency} · ${m.timezone} (${res.policy.timezone_offset})`;
  $("f-ccy").value = m.base_currency;
  $("start").classList.add("hidden"); $("result").classList.add("hidden"); $("play").classList.remove("hidden");
  $("log").textContent = ""; $("records").textContent = ""; $("f-list").textContent = "";
  renderTabs(); renderBudget(); renderDraft(); renderRecord(); renderFindings(); $("calc-out").innerHTML = '<span class="muted">результат появится здесь</span>';
  window.scrollTo(0, 0); $("ep-title").setAttribute("tabindex", "-1"); $("ep-title").focus({ preventScroll: true });
  document.title = `AuditGym — ${m.episode_id}`;
}

// ---------- stepping ----------
async function step(action, label) {
  // One step at a time: a double click must never spend two steps.
  if (S.busy) return { observation: { ok: false, error: { code: "busy", message: "предыдущий шаг ещё выполняется" } } };
  S.busy = true; document.body.setAttribute("aria-busy", "true");
  let r;
  try { r = await api("/step", { action }); } catch { toast("Сервер недоступен — перезапустите python -m auditgym.cli ui"); return { observation: { ok: false, error: { code: "network", message: "сервер недоступен" } } }; }
  finally { S.busy = false; document.body.removeAttribute("aria-busy"); }
  S.steps += 1; renderBudget();
  const o = r.observation;
  const ok = o && o.ok !== false && !(r.truncated);
  $("log").querySelectorAll(".cur").forEach((x) => x.classList.remove("cur"));
  $("log").prepend(el("li", { class: "row cur", style: "flex-wrap:nowrap;gap:12px" }, el("span", { style: "width:34px;color:var(--txt3)" }, String(S.steps).padStart(2, "0")), el("span", { style: "width:112px;color:var(--txt)" }, action.tool), el("span", { style: "flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, label || ""), el("span", { class: ok ? "ok" : "bad" }, ok ? "ok" : (o.error ? o.error.code : "truncated"))));
  if (r.truncated) { showResult(null, r.reward, true); }
  return r;
}
function renderBudget() {
  const b = $("budget"); b.textContent = ""; const used = S.steps;
  b.classList.toggle("warn", used >= 80);
  for (let i = 0; i < 50; i++) b.append(el("i", { class: i < Math.ceil(used / 2) ? "used" : "" }));
  b.setAttribute("aria-label", `Использовано ${used} из 100 шагов`);
  $("budget-txt").innerHTML = `<span id="budget-n">${100 - used}</span> шагов осталось · ${used} использовано`;
}
function renderTabs() {
  const t = $("table-tabs"); t.textContent = "";
  const names = { ledger: "Ledger", invoices: "Invoices", payments: "Payments", fx: "FX" };
  for (const [k, v] of Object.entries(names)) {
    const n = S.ep.manifest.counts[k];
    t.append(el("button", { class: "tab" + (S.table === k ? " on" : ""), role: "tab", "aria-selected": String(S.table === k), tabindex: S.table === k || (!S.table && k === "ledger") ? "0" : "-1", "aria-label": `${v}, ${n} строк${S.pages[k] ? "" : ", 1 шаг"}`, onclick: () => openTable(k) }, el("span", { class: "ref" }, REF[k]), v, el("span", { class: "muted" }, n)));
  }
}
async function openTable(name) {
  S.table = name; renderTabs();
  if (!S.pages[name]) { S.pages[name] = { list: [], i: -1 }; await fetchPage(name, null); } else renderPage();
}
async function fetchPage(name, cursor) {
  const r = await step({ tool: "list_records", args: { table: name, cursor, limit: 50 } }, `${name} · ${cursor ? "cursor…" : "первая страница"}`);
  if (r.observation.ok) { const p = S.pages[name]; p.list.push(r.observation.result); p.i = p.list.length - 1; renderPage(); }
}
function renderPage() {
  const p = S.pages[S.table]; const page = p.list[p.i]; const cols = COLS[S.table];
  const off = p.i * 50; $("page-info").textContent = `строки ${off + 1}–${off + page.rows.length} из ${S.ep.manifest.counts[S.table]}`;
  $("prev").disabled = p.i <= 0; $("next").disabled = !page.next_cursor && p.i === p.list.length - 1;
  const t = $("records"); t.textContent = "";
  t.append(el("caption", { class: "sr-only" }, `Таблица ${S.table}, ${$("page-info").textContent}. Enter — выбрать строку.`));
  t.append(el("thead", {}, el("tr", {}, ...cols.map((c) => el("th", { scope: "col", class: /minor|rate/.test(c) ? "num" : "" }, c)))));
  const tb = el("tbody");
  for (const row of page.rows) {
    const id = rowId(S.table, row);
    const tr = el("tr", { class: S.sel && S.sel.id === id ? "sel" : "", tabindex: "0", "aria-selected": String(!!(S.sel && S.sel.id === id)), "data-id": id, onclick: () => select(S.table, row), onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(S.table, row); } else if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); const n = e.key === "ArrowDown" ? tr.nextElementSibling : tr.previousElementSibling; if (n) n.focus(); } } });
    for (const c of cols) tr.append(cell(c, row[c], row));
    tb.append(tr);
  }
  t.append(tb);
}
// One table cell. The values are exactly the environment's; spans only dim the less important parts.
function cell(c, v, row) {
  const num = /minor|rate/.test(c); const cls = (num ? "num " : "") + (/id|refs|date|timestamp|issued|account|currency/.test(c) ? "mono" : "") + (c === COLS[S.table][0] ? " id" : "");
  if (v === null || v === undefined || v === "") return el("td", { class: cls }, el("span", { class: "tz" }, "—"));
  if (/_minor$/.test(c) && typeof v === "number") {
    if (v === 0 && /debit|credit/.test(c)) return el("td", { class: cls }, el("span", { class: "tz" }, "0"));
    const s = fmt(Math.abs(v), c === "debit_minor" || c === "credit_minor" ? S.ep.manifest.base_currency : row.currency); const d = s.lastIndexOf(".");
    const parts = [d < 0 ? s : s.slice(0, d), ...(d < 0 ? [] : [el("span", { class: "dec" }, s.slice(d))])];
    return el("td", { class: cls }, ...(v < 0 ? ["(", ...parts, ")"] : parts)); // accounting convention: negatives in parentheses
  }
  if (Array.isArray(v)) v = v.join(", ");
  const m = typeof v === "string" && v.match(/^(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d)(.*)$/);
  if (m) return el("td", { class: cls }, m[1], el("span", { class: "tz" }, "T"), el("span", { class: "tm-s" }, m[2]), el("span", { class: "tz" }, m[3]));
  if (c === "currency") return el("td", { class: cls }, el("span", { class: "ccy" }, v));
  return el("td", { class: cls }, String(v));
}
$("prev").addEventListener("click", () => { const p = S.pages[S.table]; if (p.i > 0) { p.i -= 1; renderPage(); } });
$("next").addEventListener("click", async () => { const p = S.pages[S.table]; if (p.i < p.list.length - 1) { p.i += 1; renderPage(); return; } const c = p.list[p.i].next_cursor; if (c) await fetchPage(S.table, c); });
const rowId = (t, r) => t === "fx" ? `${r.date}|${r.source_currency}|${r.target_currency}` : r[{ ledger: "row_id", invoices: "invoice_id", payments: "payment_id" }[t]];

function select(table, row) {
  S.sel = { table, row, id: rowId(table, row) }; renderRecord(); renderPage();
  const back = document.querySelector(`#records tr[data-id="${CSS.escape(S.sel.id)}"]`); if (back) back.focus({ preventScroll: true });
}
function renderRecord() {
  const kv = $("rec-kv"); kv.textContent = "";
  if (!S.sel) { $("rec-doc").textContent = ""; kv.append(el("dt", {}, "—"), el("dd", {}, "выберите строку в таблице")); $("rec-id").textContent = ""; ["open-doc", "add-aff", "add-ev"].forEach((x) => ($(x).disabled = true)); return; }
  $("rec-id").textContent = `${S.sel.table} / ${S.sel.id}`;
  $("rec-doc").textContent = "";
  for (const [k, v] of Object.entries(S.sel.row)) {
    let dd;
    if (k === "line_items" && Array.isArray(v)) {
      const cur = S.sel.row.currency;
      // Stacked, never clipped: description and amount on one line, the service period under it.
      dd = el("ol", { class: "li" }, ...v.map((li) => el("li", {}, el("span", { class: "li-d" }, li.description || "—"), el("b", {}, typeof li.amount_minor === "number" ? fmt(li.amount_minor, cur) : "—"),
        el("span", { class: "li-p" }, li.service_period ? `${li.service_period.start} → ${li.service_period.end}` : "период не указан"))));
    } else if (/_minor$/.test(k) && typeof v === "number") {
      const cur = S.sel.table === "ledger" ? S.ep.manifest.base_currency : S.sel.row.currency;
      dd = el("span", {}, String(v), el("span", { class: "muted" }, `  = ${fmt(v, cur)}`));
    } else dd = typeof v === "object" && v !== null ? JSON.stringify(v) : v === null ? "null" : String(v);
    kv.append(el("dt", { class: k === "line_items" ? "wide-k" : "" }, k), el("dd", { class: k === "line_items" ? "wide" : "" }, dd));
  }
  const doc = S.sel.row.doc_id; const seen = doc && S.docs[doc];
  $("open-doc").disabled = !doc || !!seen; $("open-doc").textContent = seen ? "Документ открыт ✓" : "Документ · 1 шаг";
  $("add-aff").disabled = S.sel.table === "fx" || S.sel.table === "ledger"; $("add-ev").disabled = false;
  if (seen) showDoc(doc, S.docs[doc], false);
}
// An opened document stays in memory: reading it again never spends another step.
function showDoc(id, d, open) {
  const box = $("rec-doc"); box.textContent = "";
  const pre = el("pre", { id: "doc-pre" }, docText(d));
  const tog = el("button", { class: "doc-t", "aria-expanded": String(open), "aria-controls": "doc-pre", onclick: () => { const o = tog.getAttribute("aria-expanded") !== "true"; tog.setAttribute("aria-expanded", String(o)); wrap.classList.toggle("open", o); tog.textContent = o ? "Свернуть" : "Развернуть"; } }, open ? "Свернуть" : "Развернуть");
  const wrap = el("div", { class: "doc" + (open ? " open" : "") }, el("div", { class: "h" }, el("span", { class: "wpref" }, "B-1"), el("b", {}, id), el("span", {}, d && d.kind ? String(d.kind) : "документ"), tog), pre);
  box.append(wrap);
}
$("open-doc").addEventListener("click", async () => {
  const id = S.sel.row.doc_id;
  const r = await step({ tool: "get_document", args: { doc_id: id } }, id);
  if (r.observation.ok) { S.docs[id] = r.observation.result; renderRecord(); }
});
// A document as a printed statement: aligned "key  value" lines, line items indented. Same data as the JSON.
function docText(d) {
  if (!d || typeof d !== "object") return JSON.stringify(d, null, 2);
  const keys = Object.keys(d).filter((k) => !Array.isArray(d[k]) || !d[k].length || typeof d[k][0] !== "object"); const w = Math.max(...keys.map((k) => k.length), 8) + 2;
  const val = (k, v) => (/_minor$/.test(k) && typeof v === "number" ? `${v}   = ${fmt(v, d.currency || "")}` : typeof v === "object" && v !== null ? JSON.stringify(v) : String(v));
  const out = keys.map((k) => k.padEnd(w) + val(k, d[k]));
  for (const [k, list] of Object.entries(d)) if (Array.isArray(list) && list.length && typeof list[0] === "object") {
    out.push("", `${k} (${list.length})`);
    list.forEach((it, i) => { out.push(`  ${String(i + 1).padStart(2, "0")}`); for (const [a, b] of Object.entries(it)) out.push("      " + a.padEnd(Math.max(w - 4, a.length + 2)) + (a === "service_period" && b ? `${b.start} → ${b.end}` : val(a, b))); });
  }
  return out.join("\n");
}
const addTo = (list, label) => { if (list.includes(S.sel.id)) return toast(`${S.sel.id} уже в списке «${label}»`); if (list.length >= 10) return toast("Не больше 10 ID"); list.push(S.sel.id); REFS[S.sel.id] = REF[S.sel.table]; renderDraft(); toast(`${S.sel.id} → ${label}`, "ok"); };
$("add-aff").addEventListener("click", () => addTo(S.draft.aff, "затронутые"));
$("add-ev").addEventListener("click", () => addTo(S.draft.ev, "доказательства"));

$("calc-go").addEventListener("click", async () => {
  const expr = $("calc-in").value.trim(); if (!expr) { $("calc-in").focus(); return toast("Введите выражение"); }
  const r = await step({ tool: "calculator", args: { expression: expr } }, expr);
  const out = $("calc-out"); out.textContent = ""; out.append(r.observation.ok ? el("div", {}, el("div", { class: "muted" }, expr), el("div", { class: "res" }, tm("foot", "просуммировано"), r.observation.result.value)) : el("span", { class: "bad" }, "ошибка: " + r.observation.error.message));
});
$("calc-in").addEventListener("keydown", (e) => { if (e.key === "Enter") $("calc-go").click(); });

// ---------- findings ----------
function renderDraft() {
  const chips = (list, key) => { const box = $(key); box.textContent = ""; if (!list.length) box.append(el("span", { class: "muted" }, "пусто — выберите запись и «+»")); list.forEach((id, i) => box.append(el("button", { class: "idchip", "aria-label": `убрать ${id}`, onclick: () => { list.splice(i, 1); renderDraft(); } }, ...(REFS[id] ? [el("span", { class: "xref" }, REFS[id])] : []), id, el("span", { "aria-hidden": "true" }, "×")))); };
  chips(S.draft.aff, "f-aff"); chips(S.draft.ev, "f-ev");
  $("f-ev-n").textContent = `${S.draft.ev.length} / 10`; $("find-count").textContent = `${S.findings.length} / 30`;
  const amt = $("f-amt").value.trim(); const ccy = $("f-ccy").value.trim().toUpperCase();
  const good = /^\d{1,18}$/.test(amt); const h = $("f-amt-hint");
  h.textContent = amt === "" ? "" : good ? `= ${fmt(Number(amt), ccy)} ${ccy} · целое число минорных единиц` : "сумма — целое число минорных единиц, без точки и пробелов";
  h.className = "hint " + (amt === "" ? "" : good ? "ok" : "bad"); $("f-amt").setAttribute("aria-invalid", String(amt !== "" && !good));
}
["f-amt", "f-ccy"].forEach((x) => $(x).addEventListener("input", renderDraft));
$("f-ccy").addEventListener("input", () => { const c = $("f-ccy"); const v = c.value.toUpperCase().replace(/[^A-Z]/g, ""); if (v !== c.value) c.value = v; });
$("f-add").addEventListener("click", () => {
  const amt = $("f-amt").value.trim();
  if (!/^\d{1,18}$/.test(amt)) { $("f-amt").focus(); return toast("Сумма — целое число минорных единиц"); }
  if (!/^[A-Z]{3}$/.test($("f-ccy").value.trim().toUpperCase())) { $("f-ccy").focus(); return toast("Валюта — три буквы, например KZT"); }
  if (!S.draft.aff.length) return toast("Добавьте хотя бы один затронутый ID");
  if (S.findings.length >= 30) return toast("Максимум 30 находок");
  S.findings.push({ type: $("f-type").value, affected_ids: [...S.draft.aff], claimed_amount_minor: Number(amt), currency: $("f-ccy").value.trim().toUpperCase(), evidence_ids: [...S.draft.ev], explanation: $("f-exp").value.slice(0, 1000) });
  S.draft = { aff: [], ev: [] }; $("f-amt").value = ""; $("f-exp").value = "";
  renderFindings(); renderDraft(); toast(`Находка №${S.findings.length} добавлена`, "ok");
});
function renderFindings() {
  const ol = $("f-list"); ol.textContent = "";
  if (!S.findings.length) ol.append(el("li", { class: "empty" }, "пока нет находок — молчание на книгах с ошибками даёт −1"));
  S.findings.forEach((f, i) => ol.append(el("li", {}, el("span", { class: "t" }, `C-1.${i + 1}`), el("span", { class: "d", title: f.affected_ids.join(", ") }, `${f.type} · ${f.affected_ids.join(", ")} · ${fmt(f.claimed_amount_minor, f.currency)} ${f.currency}`), el("button", { class: "idchip plain", "aria-label": "удалить находку", onclick: () => { S.findings.splice(i, 1); renderFindings(); renderDraft(); } }, "×"),
  el("span", { class: "r" }, f.evidence_ids.length ? "доказательства: " + [...new Set(f.evidence_ids.map((x) => REFS[x] || "?"))].sort().join(" / ") + ` · ${f.evidence_ids.length} ID` : "без доказательств"))));
}
$("submit").addEventListener("click", async () => {
  const d = $("confirm");
  $("confirm-p").textContent = S.findings.length ? `${S.findings.length} ${S.findings.length === 1 ? "находка" : S.findings.length < 5 ? "находки" : "находок"} уйдут в оценщик. Эпизод завершится, изменить ответ будет нельзя.` : "Список пуст. Пустой ответ на книгах с ошибками даёт −1, на чистых — +1. Эпизод завершится.";
  const ok = await new Promise((res) => { const y = () => { cleanup(); d.close(); res(true); }; const n = () => { cleanup(); d.close(); res(false); }; const c = () => { cleanup(); res(false); };
    const cleanup = () => { $("confirm-yes").removeEventListener("click", y); $("confirm-no").removeEventListener("click", n); d.removeEventListener("cancel", c); };
    $("confirm-yes").addEventListener("click", y); $("confirm-no").addEventListener("click", n); d.addEventListener("cancel", c); d.showModal(); $("confirm-yes").focus(); });
  if (!ok) { $("submit").focus(); return; }
  const r = await step({ tool: "submit", args: { findings: { episode_id: S.ep.manifest.episode_id, findings: S.findings } } }, `${S.findings.length} находок`);
  if (r.terminated) showResult(r.observation.result.report, r.reward, false);
});

function showResult(rep, reward, truncated) {
  document.querySelectorAll(".toast").forEach((x) => x.remove());
  document.body.classList.remove("playing");
  $("play").classList.add("hidden"); $("result").classList.remove("hidden"); window.scrollTo(0, 0);
  $("r-big").textContent = sign(reward); $("r-big").className = "big " + (reward > 0 ? "pos" : reward < 0 ? "neg" : "");
  const box = $("r-big").closest(".reward"); box.classList.toggle("is-pos", reward > 0); box.classList.toggle("is-neg", reward < 0);
  $("r-verdict").replaceChildren(tm(reward > 0 ? "agree" : "exc", "", "lg"), truncated ? "Лимит шагов исчерпан" : reward >= 0.9 ? "Все ошибки доказаны" : reward > 0 ? "Больше доказано, чем ошибочно заявлено" : "Ответ не принёс награды");
  $("r-big").setAttribute("tabindex", "-1"); $("r-big").focus({ preventScroll: true });
  $("r-mark").style.left = "50%"; requestAnimationFrame(() => setTimeout(() => ($("r-mark").style.left = `${((Math.max(-1, Math.min(1, reward)) + 1) / 2) * 100}%`), 60));
  const f1 = rep ? rep.f1 : 0, steps = rep ? rep.inspection_steps : S.steps;
  // The reward footed like a schedule: components, a single rule, the total over a double rule.
  const fr = (a, b, cls = "") => el("div", { class: "fr " + cls }, el("span", {}, a), el("b", {}, b));
  const num3 = (x) => (x < 0 ? "−" : "+") + Math.abs(x).toFixed(3);
  $("r-formula").replaceChildren(...(truncated ? [fr("лимит шагов", "пустой ответ"), fr("награда", sign(reward), "tot")] : [
    fr(`2 × F1 (${f1.toFixed(3)})`, num3(2 * f1)), fr("− 1", "−1.000"), fr(`− 0.002 × ${steps} шагов`, num3(-0.002 * steps)), fr("награда, clip −1 … +1", sign(reward), "tot")]));
  const tiles = $("r-tiles"); tiles.textContent = "";
  const t = (label, value, note) => tiles.append(el("div", { class: "card" }, el("div", { class: "tl" }, label), el("div", { class: "disp" }, value), el("div", { class: "tn" }, note)));
  if (rep && rep.status === "invalid_structure") { t("Статус", "−1", "неверная структура: " + (rep.error || "")); }
  t("Точность · precision", rep ? rep.precision.toFixed(3) : "—", rep ? `совпало ${rep.tp} из ${rep.tp + rep.fp}` : "");
  t("Полнота · recall", rep ? rep.recall.toFixed(3) : "—", rep ? `найдено ${rep.tp} из ${rep.tp + rep.fn}` : "");
  t("F1", rep ? f1.toFixed(3) : "—", "2·TP / (2·TP + FP + FN)");
  t("Шаги расследования", steps, "+ 1 отправка");
  t("Цена шагов", "−" + (0.002 * steps).toFixed(3), "0.002 за каждый шаг");
  t("Находок", S.findings.length, "максимум 30");
  renderBench(reward);
  const list = $("r-list"); list.textContent = "";
  (rep && rep.per_finding || []).forEach((pf) => { const f = S.findings[pf.index]; list.append(el("div", {}, el("span", { class: "badge " + (pf.matched ? "lime" : "pink") }, tm(pf.matched ? "agree" : "exc", ""), pf.matched ? "Совпала" : "Не совпала"), el("span", { class: "wpref" }, `C-1.${pf.index + 1}`), el("span", { class: "mono" }, `${f.type} · ${f.affected_ids.join(", ")} · ${fmt(f.claimed_amount_minor, f.currency)} ${f.currency}`), el("span", { class: "muted small" }, f.evidence_ids.length ? "доказательства: " + [...new Set(f.evidence_ids.map((x) => REFS[x] || "?"))].sort().join(" / ") : ""))); });
  if (!list.childNodes.length) list.append(el("div", { class: "muted" }, "Находок не было."));
}
async function renderBench(reward) {
  const b = $("r-bench"); b.textContent = ""; const r = await REPORT; if (!r) return;
  const rows = [["Вы · этот эпизод", "you", reward], ...(r.policy_summary || []).map((p) => [(POL[p.policy] || [0, p.policy])[1], p.policy, meanOf(p)])];
  for (const [name, code, v] of rows) b.append(el("div", { class: "bn" + (code === "you" ? " you" : "") }, el("span", { class: "nm" }, name, code === "you" ? "" : el("code", { class: "muted small" }, code)), divBar(v), el("span", { class: "vv " + (v > 0 ? "ok" : v < 0 ? "bad" : "") }, sign(v))));
}
$("again").addEventListener("click", () => { $("result").classList.add("hidden"); $("start").classList.remove("hidden"); document.title = "AuditGym — тренажёр аудита для ИИ-агентов"; window.scrollTo(0, 0); });
loadSplit("train").then(async () => {
  // Deep link for demos and the video: /?ep=train-5&table=ledger
  const q = new URLSearchParams(location.search); const ep = q.get("ep");
  if (!ep) return;
  const [split, n] = ep.split("-"); const spec = await (await fetch(`/data/${split}.json`)).json();
  const item = spec.episodes[Number(n) - 1]; if (!item) return;
  await start(item.seed, item.config);
  if (q.get("table")) await openTable(q.get("table"));
  const want = q.get("row"); // a deep link from the hero case: select the cited row (free, no step)
  if (want && S.table) { const row = ((S.pages[S.table] && S.pages[S.table].list[S.pages[S.table].i] || {}).rows || []).find((r) => rowId(S.table, r) === want); if (row) { select(S.table, row); const tr = document.querySelector(`#records tr[data-id="${CSS.escape(want)}"]`); if (tr) tr.scrollIntoView({ block: "center" }); } }
});
