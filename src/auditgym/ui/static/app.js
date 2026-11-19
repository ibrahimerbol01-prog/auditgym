"use strict";
// AuditGym Play page. Every action below is a real environment step via POST /step.
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); }
  for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
};
const EXP = { KZT: 2, USD: 2, EUR: 2, UZS: 2, GBP: 2, CNY: 2, JPY: 0, KWD: 3 };
const fmt = (minor, ccy) => { const e = EXP[ccy] ?? 2; const s = minor < 0 ? "-" : ""; const a = Math.abs(minor); if (!e) return s + a.toLocaleString("ru-RU"); return s + Math.floor(a / 10 ** e).toLocaleString("ru-RU") + "." + String(a % 10 ** e).padStart(e, "0"); };
const COLS = {
  ledger: ["row_id", "timestamp", "account", "debit_minor", "credit_minor", "entity_id", "invoice_id", "payment_id"],
  invoices: ["invoice_id", "doc_id", "entity_id", "issued_at", "currency", "total_minor"],
  payments: ["payment_id", "doc_id", "timestamp", "currency", "amount_minor", "invoice_refs"],
  fx: ["date", "source_currency", "target_currency", "rate"],
};
const S = { ep: null, steps: 0, table: null, pages: {}, sel: null, findings: [], draft: { aff: [], ev: [] } };

async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return r.json();
}
function toast(msg) { const t = el("div", { class: "toast", role: "status" }, msg); document.body.append(t); setTimeout(() => t.remove(), 2600); }

// ---------- start screen ----------
async function loadSplit(split) {
  document.querySelectorAll("[data-split]").forEach((b) => { const on = b.dataset.split === split; b.classList.toggle("on", on); b.setAttribute("aria-selected", on); });
  const tb = $("ep-rows"); tb.textContent = "";
  let spec;
  try { spec = await (await fetch(`/data/${split}.json`)).json(); } catch { tb.append(el("tr", {}, el("td", { colspan: 5 }, "конфигурации не найдены"))); return; }
  spec.episodes.forEach((e, i) => {
    const c = e.config; const kind = c.clean ? "чистая компания" : [...(c.interactions || []).map((x) => "взаимодействие " + x), c.errors ? "ошибки по конфигу" : "ошибки по умолчанию"].join(" · ");
    const cur = (c.base_currency || "KZT") + " · " + (c.foreign_currencies || ["USD", "EUR"]).join(" ");
    tb.append(el("tr", {},
      el("td", { class: "mono" }, `${split}-${String(i + 1).padStart(2, "0")}`), el("td", { class: "mono" }, e.seed), el("td", {}, kind), el("td", { class: "mono" }, cur),
      el("td", { class: "num" }, el("button", { class: "btn outline small", onclick: () => start(e.seed, c) }, "Открыть →"))));
  });
}
document.querySelectorAll("[data-split]").forEach((b) => b.addEventListener("click", () => loadSplit(b.dataset.split)));

async function start(seed, config) {
  const r = await api("/reset", { seed, config });
  if (!r.observation.ok) { toast(r.observation.error.message); return; }
  const res = r.observation.result;
  Object.assign(S, { ep: res, steps: 0, table: null, pages: {}, sel: null, findings: [], draft: { aff: [], ev: [] } });
  const m = res.manifest;
  $("ep-title").textContent = `${m.counts.ledger} проводок · ${m.counts.invoices} счетов · ${m.counts.payments} платежей · период ${m.period_start} → ${m.period_end}`;
  $("ep-sub").textContent = `${m.episode_id} · база ${m.base_currency} · ${m.timezone} (${res.policy.timezone_offset})`;
  $("f-ccy").value = m.base_currency;
  $("start").classList.add("hidden"); $("result").classList.add("hidden"); $("play").classList.remove("hidden");
  $("log").textContent = ""; $("records").textContent = ""; $("f-list").textContent = "";
  renderTabs(); renderBudget(); renderDraft(); renderRecord(); renderFindings(); $("calc-out").innerHTML = '<span class="muted">результат появится здесь</span>';
  window.scrollTo(0, 0);
}

// ---------- stepping ----------
async function step(action, label) {
  const r = await api("/step", { action });
  S.steps += 1; renderBudget();
  const o = r.observation;
  const ok = o && o.ok !== false && !(r.truncated);
  $("log").prepend(el("li", { class: "row", style: "flex-wrap:nowrap;gap:12px" }, el("span", { class: "muted", style: "width:38px" }, "#" + S.steps), el("span", { style: "width:120px" }, action.tool), el("span", { class: "muted", style: "flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, label || ""), el("span", { class: ok ? "ok" : "bad" }, ok ? "ok" : (o.error ? o.error.code : "truncated"))));
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
    t.append(el("button", { class: "tab" + (S.table === k ? " on" : ""), role: "tab", "aria-selected": S.table === k, onclick: () => openTable(k) }, v + " ", el("span", { class: "muted" }, n)));
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
  t.append(el("thead", {}, el("tr", {}, ...cols.map((c) => el("th", { class: /minor|rate/.test(c) ? "num" : "" }, c)))));
  const tb = el("tbody");
  for (const row of page.rows) {
    const id = rowId(S.table, row);
    const tr = el("tr", { class: S.sel && S.sel.id === id ? "sel" : "", tabindex: "0", onclick: () => select(S.table, row), onkeydown: (e) => { if (e.key === "Enter") select(S.table, row); } });
    for (const c of cols) {
      let v = row[c]; if (v === null || v === undefined) v = "—";
      if (/_minor$/.test(c) && typeof v === "number") v = fmt(v, c === "debit_minor" || c === "credit_minor" ? S.ep.manifest.base_currency : row.currency);
      if (Array.isArray(v)) v = v.join(", ");
      tr.append(el("td", { class: (/minor|rate/.test(c) ? "num " : "") + (/id|refs|date|timestamp|issued/.test(c) ? "mono" : "") }, v));
    }
    tb.append(tr);
  }
  t.append(tb);
}
$("prev").addEventListener("click", () => { const p = S.pages[S.table]; if (p.i > 0) { p.i -= 1; renderPage(); } });
$("next").addEventListener("click", async () => { const p = S.pages[S.table]; if (p.i < p.list.length - 1) { p.i += 1; renderPage(); return; } const c = p.list[p.i].next_cursor; if (c) await fetchPage(S.table, c); });
const rowId = (t, r) => t === "fx" ? `${r.date}|${r.source_currency}|${r.target_currency}` : r[{ ledger: "row_id", invoices: "invoice_id", payments: "payment_id" }[t]];

function select(table, row) { S.sel = { table, row, id: rowId(table, row) }; renderRecord(); renderPage(); }
function renderRecord() {
  const kv = $("rec-kv"); kv.textContent = "";
  if (!S.sel) { $("rec-doc").textContent = ""; kv.append(el("dt", {}, "—"), el("dd", {}, "выберите строку в таблице")); $("rec-id").textContent = ""; ["open-doc", "add-aff", "add-ev"].forEach((x) => ($(x).disabled = true)); return; }
  $("rec-id").textContent = `${S.sel.table} / ${S.sel.id}`;
  $("rec-doc").textContent = "";
  for (const [k, v] of Object.entries(S.sel.row)) {
    let dd;
    if (k === "line_items" && Array.isArray(v)) {
      const cur = S.sel.row.currency;
      dd = el("table", { class: "mini" }, el("tr", {}, el("th", {}, "позиция"), el("th", {}, "период"), el("th", { class: "num" }, "сумма")),
        ...v.map((li) => el("tr", {}, el("td", {}, li.description || "—"), el("td", {}, li.service_period ? `${li.service_period.start} → ${li.service_period.end}` : "—"), el("td", { class: "num" }, typeof li.amount_minor === "number" ? fmt(li.amount_minor, cur) : "—"))));
    } else if (/_minor$/.test(k) && typeof v === "number") {
      const cur = S.sel.table === "ledger" ? S.ep.manifest.base_currency : S.sel.row.currency;
      dd = el("span", {}, String(v), el("span", { class: "muted" }, `  = ${fmt(v, cur)}`));
    } else dd = typeof v === "object" && v !== null ? JSON.stringify(v) : v === null ? "null" : String(v);
    kv.append(el("dt", {}, k), el("dd", {}, dd));
  }
  $("open-doc").disabled = !S.sel.row.doc_id; $("add-aff").disabled = S.sel.table === "fx" || S.sel.table === "ledger"; $("add-ev").disabled = false;
}
$("open-doc").addEventListener("click", async () => {
  const r = await step({ tool: "get_document", args: { doc_id: S.sel.row.doc_id } }, S.sel.row.doc_id);
  if (r.observation.ok) { const box = $("rec-doc"); box.textContent = ""; box.append(el("div", { class: "doc" }, el("div", { class: "h" }, `[ ${S.sel.row.doc_id} ]`), el("pre", {}, JSON.stringify(r.observation.result, null, 2)))); }
});
$("add-aff").addEventListener("click", () => { if (!S.draft.aff.includes(S.sel.id) && S.draft.aff.length < 10) S.draft.aff.push(S.sel.id); renderDraft(); });
$("add-ev").addEventListener("click", () => { if (!S.draft.ev.includes(S.sel.id) && S.draft.ev.length < 10) S.draft.ev.push(S.sel.id); renderDraft(); });

$("calc-go").addEventListener("click", async () => {
  const expr = $("calc-in").value;
  const r = await step({ tool: "calculator", args: { expression: expr } }, expr);
  const out = $("calc-out"); out.textContent = ""; out.append(r.observation.ok ? el("span", {}, el("span", { class: "muted" }, expr + " = "), r.observation.result.value) : el("span", { class: "bad" }, "ошибка: " + r.observation.error.message));
});
$("calc-in").addEventListener("keydown", (e) => { if (e.key === "Enter") $("calc-go").click(); });

// ---------- findings ----------
function renderDraft() {
  const chips = (list, key) => { const box = $(key); box.textContent = ""; list.forEach((id, i) => box.append(el("button", { class: "idchip", title: "убрать", onclick: () => { list.splice(i, 1); renderDraft(); } }, id + " ×"))); };
  chips(S.draft.aff, "f-aff"); chips(S.draft.ev, "f-ev");
  $("f-ev-n").textContent = `${S.draft.ev.length} / 10`; $("find-count").textContent = `${S.findings.length} / 30`;
  const amt = $("f-amt").value.trim(); const ccy = $("f-ccy").value.trim().toUpperCase();
  $("f-amt-hint").textContent = amt === "" ? "" : /^\d+$/.test(amt) ? `= ${ccy} ${fmt(Number(amt), ccy)} · целое число ✓` : "сумма должна быть целым числом минорных единиц";
}
["f-amt", "f-ccy"].forEach((x) => $(x).addEventListener("input", renderDraft));
$("f-add").addEventListener("click", () => {
  const amt = $("f-amt").value.trim();
  if (!/^\d+$/.test(amt)) return toast("Сумма — целое число минорных единиц");
  if (!S.draft.aff.length) return toast("Добавьте хотя бы один затронутый ID");
  if (S.findings.length >= 30) return toast("Максимум 30 находок");
  S.findings.push({ type: $("f-type").value, affected_ids: [...S.draft.aff], claimed_amount_minor: Number(amt), currency: $("f-ccy").value.trim().toUpperCase(), evidence_ids: [...S.draft.ev], explanation: $("f-exp").value.slice(0, 1000) });
  S.draft = { aff: [], ev: [] }; $("f-amt").value = ""; $("f-exp").value = "";
  renderFindings(); renderDraft();
});
function renderFindings() {
  const ol = $("f-list"); ol.textContent = "";
  if (!S.findings.length) ol.append(el("li", { class: "empty" }, "пока нет находок — молчание на книгах с ошибками даёт −1"));
  S.findings.forEach((f, i) => ol.append(el("li", {}, el("span", { class: "t" }, f.type.split("_")[0]), el("span", { class: "d", title: f.affected_ids.join(", ") }, `${f.affected_ids.join(", ")} · ${f.currency} ${fmt(f.claimed_amount_minor, f.currency)} · ${f.evidence_ids.length} док.`), el("button", { class: "idchip plain", "aria-label": "удалить находку", onclick: () => { S.findings.splice(i, 1); renderFindings(); renderDraft(); } }, "×"))));
}
$("submit").addEventListener("click", async () => {
  if (!confirm(`Отправить ${S.findings.length} находок? Эпизод завершится.`)) return;
  const r = await step({ tool: "submit", args: { findings: { episode_id: S.ep.manifest.episode_id, findings: S.findings } } }, `${S.findings.length} находок`);
  if (r.terminated) showResult(r.observation.result.report, r.reward, false);
});

function showResult(rep, reward, truncated) {
  $("play").classList.add("hidden"); $("result").classList.remove("hidden"); window.scrollTo(0, 0);
  $("r-big").textContent = (reward >= 0 ? "+" : "") + reward.toFixed(3);
  $("r-mark").style.left = "50%"; requestAnimationFrame(() => setTimeout(() => ($("r-mark").style.left = `${((Math.max(-1, Math.min(1, reward)) + 1) / 2) * 100}%`), 60));
  const f1 = rep ? rep.f1 : 0, steps = rep ? rep.inspection_steps : S.steps;
  $("r-formula").textContent = truncated ? "лимит шагов: засчитано как пустой ответ" : `clip(2 × ${f1.toFixed(3)} − 1 − 0.002 × ${steps}, −1, 1)`;
  const tiles = $("r-tiles"); tiles.textContent = "";
  const t = (label, value, note) => tiles.append(el("div", { class: "card" }, el("div", { class: "muted", style: "font-size:12px;text-transform:uppercase;letter-spacing:.06em;font-weight:600" }, label), el("div", { class: "disp", style: "font-size:32px" }, value), el("div", { class: "muted", style: "font-size:13px" }, note)));
  if (rep && rep.status === "invalid_structure") { t("Статус", "−1", "неверная структура: " + (rep.error || "")); }
  t("Precision", rep ? rep.precision.toFixed(3) : "—", rep ? `${rep.tp} из ${rep.tp + rep.fp} находок совпали` : "");
  t("Recall", rep ? rep.recall.toFixed(3) : "—", rep ? `найдено ${rep.tp} из ${rep.tp + rep.fn}` : "");
  t("F1", rep ? f1.toFixed(3) : "—", "2·TP / (2·TP + FP + FN)");
  t("Шаги расследования", steps, "+ 1 отправка");
  t("Цена шагов", "−" + (0.002 * steps).toFixed(3), "0.002 за каждый шаг");
  t("Находок", S.findings.length, "максимум 30");
  const list = $("r-list"); list.textContent = "";
  (rep && rep.per_finding || []).forEach((pf) => { const f = S.findings[pf.index]; list.append(el("div", { class: "row", style: "border-top:1px solid var(--line);padding:8px 0" }, el("span", { class: "badge " + (pf.matched ? "lime" : "pink") }, pf.matched ? "✓ Совпала" : "✗ Не совпала"), el("span", { class: "mono" }, `${f.type} · ${f.affected_ids.join(", ")} · ${f.currency} ${fmt(f.claimed_amount_minor, f.currency)}`), el("span", { class: "muted" }, pf.matched ? "полный набор доказательств" : ""))); });
  if (!list.childNodes.length) list.append(el("div", { class: "muted" }, "Находок не было."));
}
$("again").addEventListener("click", () => { $("result").classList.add("hidden"); $("start").classList.remove("hidden"); window.scrollTo(0, 0); });
loadSplit("train").then(async () => {
  // Deep link for demos and the video: /?ep=train-5&table=ledger
  const q = new URLSearchParams(location.search); const ep = q.get("ep");
  if (!ep) return;
  const [split, n] = ep.split("-"); const spec = await (await fetch(`/data/${split}.json`)).json();
  const item = spec.episodes[Number(n) - 1]; if (!item) return;
  await start(item.seed, item.config);
  if (q.get("table")) await openTable(q.get("table"));
});
