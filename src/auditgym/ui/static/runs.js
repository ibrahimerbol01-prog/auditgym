"use strict";
// Runs page (design option B): saved harness runs, a live console for the selected run, and "New run".
// Reads /api/runs (served by auditgym.harness.Jobs) and /data/report.json, /data/curve.json. Built-in policies
// start from here; an external agent is started from the terminal (the page only builds the command).
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); } for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k))); return e; };
const SVGNS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}, parent) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.append(e); return e; };
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
const NAMES = { oracle: "Эталон", reconcile: "Сверщик", random: "Стажёр", flag_all: "Паникёр" };
const STATUS = { running: ["идёт", "lime"], done: ["завершён", "dim"], stopped: ["остановлен", "gold"], error: ["ошибка", "pink"] };
const TABLES = { fx: "курсы", invoices: "счета", payments: "платежи", ledger: "главная книга" };
const f2 = (v) => (v == null || Number.isNaN(v) ? "—" : (Math.round(v * 100) / 100 + 0 < 0 ? "−" : "") + Math.abs(v).toFixed(2));
const plural = (n, a, b, c) => { const k = n % 100, d = n % 10; return `${n} ${k >= 11 && k <= 14 ? c : d === 1 ? a : d >= 2 && d <= 4 ? b : c}`; };
const agentName = (a) => (NAMES[a] ? `${NAMES[a]} · ${a}` : a);
const when = (t) => (t ? new Date(t * 1000).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
const dur = (s) => (s < 60 ? `${s.toFixed(1)} с` : `${Math.floor(s / 60)} мин ${Math.round(s % 60)} с`);

const animated = new Set();  // bars already grown once (only a newly scored episode animates)
let runs = [], current = null, run = null, base = {}, curve = null, tab = "ov", logEp = 0, timer = null, drawnFor = "";

// theme toggle (same as the other pages)
(() => { const b = $("theme"); const tc = document.querySelector('meta[name="theme-color"]'); const lbl = b.querySelector("span");
  const sync = () => { const dark = document.documentElement.dataset.theme === "dark"; b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема"); lbl.textContent = dark ? "Светлая" : "Тёмная"; tc.setAttribute("content", dark ? "#0e0e11" : "#f7f7f8"); };
  sync(); b.addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme; try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* private mode */ } sync(); drawnFor = ""; render(); }); })();

async function getJSON(url) { const r = await fetch(url, { cache: "no-store" }); if (!r.ok) throw new Error(url + " " + r.status); return r.json(); }
async function postJSON(url, body) { const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); return r.json(); }

async function loadStatic() {
  try { const rep = await getJSON("/data/report.json"); for (const row of rep.policy_summary || []) { const v = Object.entries(row).filter(([k, x]) => k !== "policy" && typeof x === "number").map(([, x]) => x); if (v.length) base[row.policy] = v.reduce((a, b) => a + b, 0) / v.length; } } catch { /* report.json is optional */ }
  try { curve = (await getJSON("/api/curve")).curve; } catch { curve = null; }
}

async function refresh() {
  let data;
  try { data = await getJSON("/api/runs"); } catch { $("runs-hint").textContent = "Сервер запусков недоступен: откройте страницу через python -m auditgym.cli ui."; return; }
  runs = data.runs || [];
  const want = decodeURIComponent(location.hash.slice(1));
  if (!current || !runs.some((r) => r.id === current)) current = runs.some((r) => r.id === want) ? want : (runs[0] && runs[0].id) || null;
  renderList();
  if (current) { const d = await getJSON("/api/runs/" + encodeURIComponent(current)).catch(() => null); run = d && d.run; } else run = null;
  render();
  if (tab === "log" && run) await loadLog();
  clearTimeout(timer);
  timer = setTimeout(refresh, run && run.status === "running" ? 700 : 4000);
}

function strip(rewards) {  // one tiny bar per episode, above or below a hairline zero
  const w = el("span", { class: "ri-strip", "aria-hidden": "true" });
  for (const v of rewards) w.append(el("span", { class: "sl" }, el("i", { class: v == null ? "" : v > 0 ? "pos" : "neg", style: v == null ? "height:0" : `height:${Math.max(2, Math.abs(v) * 9)}px;${v > 0 ? "bottom:50%" : "top:50%"}` })));
  return w;
}

function renderList() {
  const ol = $("run-list"); ol.replaceChildren();
  for (const r of runs) {
    const s = r.summary || {}; const [st, cls] = STATUS[r.status] || [r.status, "dim"];
    const b = el("button", { class: "run-i" + (r.id === current ? " on" : ""), "aria-current": r.id === current ? "true" : "false", onclick: () => { current = r.id; location.hash = r.id; drawnFor = ""; refresh(); } },
      el("span", { class: "ri-top" }, el("b", {}, agentName(r.agent)), el("span", { class: "badge " + cls }, (r.status === "running" ? "● " : "") + st)),
      el("span", { class: "ri-sub" }, `${r.split} · ${s.episodes_done || 0}/${r.episodes} · ${when(r.started)}`),
      el("span", { class: "ri-v mono " + (s.episodes_done ? (s.reward > 0 ? "pos" : "neg") : "") }, s.episodes_done ? f2(s.reward) : "—"),
      strip(r.rewards || []));
    ol.append(el("li", {}, b));
  }
}

const tick = (kind) => { const t = svg("svg", { class: "tm sm " + (kind === "exc" ? "exc" : "") + " p", viewBox: "0 0 16 16", "aria-hidden": "true" }); svg("use", { href: "#tm-" + kind }, t); return t; };
const row = (k, v, cls = "") => el("div", { class: "fr " + cls }, el("span", {}, k), el("b", {}, v));
const tile = (label, value, note, cls = "") => el("div", { class: "card" }, el("span", { class: "tl" }, label), el("span", { class: "disp " + cls }, value), el("span", { class: "tn" }, note));

function render() {
  $("empty").classList.toggle("hidden", !!run);
  $("detail").classList.toggle("hidden", !run);
  if (!run) return;
  const eps = run.episodes || [], done = eps.filter((e) => e.score).length, s = run.summary || {};
  const [st, cls] = STATUS[run.status] || [run.status, "dim"];
  $("d-id").textContent = run.id;
  $("d-status").className = "badge " + cls; $("d-status").textContent = (run.status === "running" ? "● " : "") + st;
  $("d-stop").classList.toggle("hidden", run.status !== "running");
  const cur = eps.find((e) => e.status === "running");
  const gen = eps.length % 10 === 1 && eps.length % 100 !== 11 ? "эпизода" : "эпизодов";
  const big = $("s-big"); big.textContent = done ? f2(s.reward) : "—"; big.className = "big " + (done ? (s.reward > 0 ? "pos" : "neg") : "");
  $("s-mark").style.left = done ? `${(s.reward + 1) * 50}%` : "50%";
  const good = done && s.reward > 0;
  $("s-verdict").replaceChildren(...(run.status === "running"
    ? [el("span", { class: "live-dot", "aria-hidden": "true" }), `Идёт эпизод ${cur ? cur.index + 1 : done + 1} из ${eps.length}` + (cur ? ` · #${cur.seed} ${cur.label}` : "")]
    : done ? [tick(good ? "agree" : "exc"), good ? `Награда на ${eps.filter((e) => e.score && e.score.reward > 0).length} из ${eps.length} ${gen}` : "Агент не заработал награды"]
      : [run.status === "error" ? "Запуск прервался с ошибкой" : "Ни один эпизод не завершён"]));
  $("s-verdict").classList.toggle("neg", done > 0 && !good);
  $("d-segs").replaceChildren(...eps.map((e) => el("i", { class: e.score ? (e.score.reward > 0 ? "pos" : "neg") : e.status === "running" ? "now" : "" })));
  $("s-formula").replaceChildren(
    row("эпизодов оценено", `${done} из ${eps.length}`), row("верных · ложных · пропусков", done ? `${s.tp ?? 0} · ${s.fp ?? 0} · ${s.fn ?? 0}` : "—"),
    row("шагов в среднем (бюджет 100)", done ? s.steps.toFixed(1) : "—"), row("средняя награда", done ? f2(s.reward) : "—", "tot"));
  $("s-tiles").replaceChildren(
    tile("Точность", done ? f2(s.precision) : "—", done ? `precision · ${s.tp ?? 0} из ${(s.tp ?? 0) + (s.fp ?? 0)} верны` : "precision"),
    tile("Полнота", done ? f2(s.recall) : "—", done ? `recall · ${s.tp ?? 0} из ${(s.tp ?? 0) + (s.fn ?? 0)} найдены` : "recall"),
    tile("F1", done ? f2(s.f1) : "—", "все находки запуска"),
    tile("Ложные находки", done ? String(s.fp ?? 0) : "—", "каждая снижает награду", done && s.fp ? "neg" : ""),
    tile("Шагов в среднем", done ? s.steps.toFixed(1) : "—", "из 100 на эпизод"),
    tile("Время агента", s.seconds != null ? dur(s.seconds) : "—", run.pace ? `плюс показ ${Math.round(run.pace * 1000)} мс на шаг` : "без пауз"));
  $("d-split").textContent = `${run.split} · закрытый режим`;
  $("d-agent").textContent = "агент " + run.agent;
  const secs = ((run.finished || Date.now() / 1000) - run.started);
  const kv = [["Запуск", run.id], ["Эпизоды", `${run.split} · ${eps.length}`], ["Режим", "закрытый: агент не видит награду"], ["Версия среды", run.env_version], ["Начат", when(run.started)], ["Длительность", dur(Math.max(0, secs))]];
  $("d-kv").replaceChildren(...kv.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v))));
  drawChart(eps);
  $("d-eps").replaceChildren(...eps.map((e) => {
    const r = e.score ? e.score.reward : null;
    const t = el("button", { class: "ep-t " + (e.score ? (r > 0 ? "pos" : "neg") : e.status), onclick: () => { logEp = e.index; setTab("log"); } },
      el("span", { class: "et-h" }, el("span", {}, e.label), el("span", { class: "mono" }, "#" + e.seed)),
      el("span", { class: "et-v mono" }, r == null ? (e.status === "running" ? "идёт…" : "в очереди") : f2(r)),
      el("span", { class: "et-m" }, el("i", { style: r == null ? "width:0" : r >= 0 ? `left:50%;width:${r * 50}%` : `left:${50 + r * 50}%;width:${-r * 50}%` })),
      el("span", { class: "et-s" }, ...(e.score ? [tick(r > 0 ? "agree" : "exc"), `${plural(e.steps, "шаг", "шага", "шагов")} · ложных ${e.score.fp ?? 0}`] : [" "])));
    t.setAttribute("aria-label", `${e.label}, сид ${e.seed}: ${r == null ? "нет оценки" : "награда " + f2(r)}. Открыть журнал`);
    return el("li", {}, t);
  }));
  const rows = [[(NAMES[run.agent] || run.agent) + " · этот запуск", done ? s.reward : null, true]].concat(Object.entries(base).map(([k, v]) => [k === run.agent ? `${NAMES[k]} · report.json` : agentName(k), v, false]));
  rows.sort((a, b) => (b[1] ?? -9) - (a[1] ?? -9));
  $("d-cmp").replaceChildren(...rows.map(([n, v, me]) => el("div", { class: "bn" + (me ? " you" : "") }, el("span", { class: "nm" }, n),
    el("span", { class: "zb" }, el("i", { class: v != null && v < 0 ? "neg" : "", style: v == null ? "width:0" : v >= 0 ? `left:50%;width:${v * 50}%` : `left:${50 + v * 50}%;width:${-v * 50}%` }), el("b", {})),
    el("span", { class: "vv " + (v == null ? "" : v > 0 ? "ok" : "bad") }, f2(v)))));
  drawTraining();
}

function axes(host, W, H, m, ymin, ymax) {
  host.replaceChildren(); const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H, class: "ch", role: "img" }, host);
  const Y = (v) => m.t + ((ymax - v) / (ymax - ymin)) * (H - m.t - m.b);
  for (const t of [-1, -0.5, 0, 0.5, 1]) { svg("line", { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), class: t === 0 ? "zero" : "grid" }, s); svg("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, s).textContent = f2(t); }
  return { s, Y };
}

function drawChart(eps) {
  const host = $("d-chart"), W = Math.max(320, host.clientWidth || 640), H = 248, m = { l: 44, r: W < 480 ? 64 : 96, t: 14, b: 42 };
  const key = run.id + "|" + W + "|" + eps.map((e) => (e.score ? e.score.reward : e.status)).join(",");
  if (key === drawnFor) return;
  drawnFor = key;
  const { s, Y } = axes(host, W, H, m, -1, 1);
  s.setAttribute("aria-label", "Награда по эпизодам: " + eps.map((e) => (e.score ? `${e.label} ${f2(e.score.reward)}` : `${e.label} нет оценки`)).join("; "));
  for (const [k, v] of Object.entries(base)) { if (k === run.agent || !["reconcile", "random"].includes(k)) continue;
    svg("line", { x1: m.l, x2: W - m.r + 4, y1: Y(v), y2: Y(v), class: "ref" }, s);
    const lab = svg("text", { x: W - m.r + 8, y: Y(v) + 4, class: "ref-l" }, s);  // in the right gutter, never on a bar
    lab.append(svg("tspan", { x: W - m.r + 8 }), svg("tspan", { x: W - m.r + 8, dy: 13 }));
    lab.firstChild.textContent = NAMES[k]; lab.lastChild.textContent = f2(v); }
  const n = Math.max(eps.length, 1), slot = (W - m.l - m.r) / n, bw = Math.min(46, slot * 0.56);
  eps.forEach((e, i) => {
    const x = m.l + slot * i + (slot - bw) / 2;
    svg("text", { x: x + bw / 2, y: H - 6, "text-anchor": "middle" }, s).textContent = i + 1;
    if (!e.score) { if (e.status === "running") svg("rect", { x, y: Y(1), width: bw, height: Y(-1) - Y(1), class: "slot-now" }, s); return; }
    const v = e.score.reward, y0 = Y(0), y1 = Y(v);
    const r = svg("rect", { x, width: bw, y: Math.min(y0, y1), height: Math.max(1, Math.abs(y1 - y0)), class: v >= 0 ? "b-pos" : "b-neg" }, s);
    const ak = run.id + ":" + i;
    if (!RM && !animated.has(ak)) { animated.add(ak); r.style.transformOrigin = `${x}px ${y0}px`; r.style.transform = "scaleY(0)"; requestAnimationFrame(() => requestAnimationFrame(() => { r.style.transition = "transform .55s cubic-bezier(.3,.7,.2,1)"; r.style.transform = "scaleY(1)"; })); }
    if (slot >= 38) svg("text", { x: x + bw / 2, y: v >= 0 ? y1 - 6 : y1 + 14, "text-anchor": "middle", class: "b-l" }, s).textContent = f2(v);
  });
}

function drawTraining() {
  const host = $("train-chart");
  host.classList.toggle("hidden", !curve);
  if (!curve || !Array.isArray(curve.points || curve)) {
    host.replaceChildren(); $("train-note").replaceChildren("Тренер ещё не запускался. Кривая награды на отложенных эпизодах появится здесь, когда он запишет ", el("code", {}, "train/curve.json"), ".");
    return;
  }
  const pts = (curve.points || curve).map((p) => [p.iteration, p.dev_reward]).filter((p) => p.every(Number.isFinite));
  const W = Math.max(320, host.clientWidth || 640), H = 200, m = { l: 44, r: 14, t: 12, b: 26 };
  const { s, Y } = axes(host, W, H, m, -1, 1); const xmax = Math.max(1, ...pts.map((p) => p[0]));
  const X = (x) => m.l + (x / xmax) * (W - m.l - m.r);
  if (base.reconcile != null) { svg("line", { x1: m.l, x2: W - m.r, y1: Y(base.reconcile), y2: Y(base.reconcile), class: "ref" }, s); svg("text", { x: W - m.r - 4, y: Y(base.reconcile) - 6, "text-anchor": "end", class: "ref-l" }, s).textContent = "Сверщик " + f2(base.reconcile); }
  svg("path", { d: pts.map((p, i) => (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(" "), class: "ln" }, s);
  s.setAttribute("aria-label", `Награда на dev по итерациям: от ${f2(pts[0][1])} до ${f2(pts[pts.length - 1][1])}`);
  $("train-note").textContent = `${plural(pts.length, "точка", "точки", "точек")} из train/curve.json · награда на отложенных эпизодах`;
}

async function loadLog() {
  const eps = run.episodes || [];
  const sel = $("log-ep");
  if (sel.options.length !== eps.length || sel.dataset.run !== run.id) { sel.dataset.run = run.id; sel.replaceChildren(...eps.map((e) => el("option", { value: e.index }, `${e.index + 1}. #${e.seed} ${e.label}`))); }
  sel.value = String(logEp);
  const e = eps[logEp]; if (!e) return;
  const d = await getJSON(`/api/runs/${encodeURIComponent(run.id)}/steps?episode=${logEp}`).catch(() => ({ steps: [] }));
  const steps = d.steps || [];
  $("log-meta").textContent = e.score ? `награда ${f2(e.score.reward)} · ${plural(e.steps, "шаг", "шага", "шагов")} · TP ${e.score.tp ?? 0} FP ${e.score.fp ?? 0} FN ${e.score.fn ?? 0}` : e.status === "running" ? "идёт…" : "ещё не начат";
  const ol = $("log");
  const old = ol.children.length;
  if (old > steps.length || ol.dataset.k !== run.id + ":" + logEp) { ol.replaceChildren(); ol.dataset.k = run.id + ":" + logEp; }
  for (const st of steps.slice(ol.children.length)) {
    const a = st.args || {};
    const what = st.tool === "submit" ? (a.findings == null ? "неверная структура" : plural(a.findings, "находка", "находки", "находок")) : st.tool === "list_records" ? `${TABLES[a.table] || a.table} · ${a.cursor ? "далее" : "начало"}` : Object.entries(a).map(([k, v]) => `${k}=${v}`).join(" ");
    const res = st.truncated ? "бюджет исчерпан" : st.tool === "submit" ? "отправлено" : st.ok ? (st.rows != null ? plural(st.rows, "строка", "строки", "строк") : "ок") : st.error;
    ol.append(el("li", { class: (st.ok ? "" : "bad ") + (st.tool === "submit" ? "sub" : "") }, el("span", { class: "n" }, "#" + String(st.n).padStart(2, "0")), el("span", { class: "t" }, st.tool), el("span", { class: "a" }, what), el("span", { class: "r" }, res), el("span", { class: "l" }, "осталось " + st.left)));
  }
}

function setTab(t) {
  tab = t;
  for (const [id, pane, key] of [["tab-ov", "pane-ov", "ov"], ["tab-log", "pane-log", "log"]]) { $(id).setAttribute("aria-selected", String(t === key)); $(pane).classList.toggle("hidden", t !== key); }
  if (t === "log" && run) loadLog();
}
$("tab-ov").addEventListener("click", () => setTab("ov"));
$("tab-log").addEventListener("click", () => setTab("log"));
$("log-ep").addEventListener("change", (e) => { logEp = +e.target.value; loadLog(); });
$("d-stop").addEventListener("click", async () => { await postJSON(`/api/runs/${encodeURIComponent(run.id)}/stop`, {}); refresh(); });

// ---- new run dialog
const dlg = $("dlg");
const kind = () => document.querySelector('input[name="kind"]:checked').value;
function cmdline() {
  if (kind() === "cmd") return `python -m auditgym.cli run-agent --name ${($("f-model").value.split(":")[0] || "llm").replace(/[^\w.-]/g, "")} --cmd "python examples/llm_agent.py --model ${$("f-model").value} --temperature ${$("f-temp").value} --max-tokens ${$("f-tok").value}" --split ${$("f-split2").value}`;
  const lim = $("f-limit").value; const pace = +$("f-pace").value;
  return `python -m auditgym.cli run-agent --policy ${$("f-policy").value} --split ${$("f-split").value}${lim ? " --limit " + lim : ""}${pace ? " --pace " + pace : ""}`;
}
function syncDlg() {
  const k = kind();
  $("f-builtin").classList.toggle("hidden", k !== "builtin"); $("f-cmd").classList.toggle("hidden", k !== "cmd");
  $("dlg-go").classList.toggle("hidden", k !== "builtin"); $("dlg-copy").classList.toggle("hidden", k !== "cmd");
  $("f-why").textContent = k === "cmd" ? "Свою программу запускайте из терминала: страница в браузере не запускает чужой код. Результат появится в этом списке." : "Режим всегда закрытый, бюджет — 100 шагов на эпизод. Так же считает жюри.";
  $("f-cmdline").textContent = (k === "cmd" ? "" : "то же в терминале:\n") + cmdline();
}
for (const id of ["k-builtin", "k-cmd", "f-policy", "f-split", "f-limit", "f-pace", "f-model", "f-temp", "f-tok", "f-split2"]) $(id).addEventListener("input", syncDlg);
const openDlg = (k) => { $(k === "cmd" ? "k-cmd" : "k-builtin").checked = true; $("f-err").classList.add("hidden"); syncDlg(); dlg.showModal(); };
$("new-run").addEventListener("click", () => openDlg("builtin"));
$("empty-new").addEventListener("click", () => openDlg("cmd"));
$("dlg-cancel").addEventListener("click", () => dlg.close());
$("dlg-copy").addEventListener("click", async () => { try { await navigator.clipboard.writeText(cmdline()); $("dlg-copy").textContent = "Скопировано"; setTimeout(() => ($("dlg-copy").textContent = "Скопировать команду"), 1500); } catch { /* clipboard blocked: the command is visible to copy by hand */ } });
async function start(policy, split, limit, pace) {
  const res = await postJSON("/api/runs", { policy, split, limit: limit ? +limit : null, pace });
  if (!res.ok) { $("f-err").textContent = res.error.code === "busy" ? "Уже идёт другой запуск. Дождитесь его или остановите." : "Не удалось запустить: " + res.error.message; $("f-err").classList.remove("hidden"); return false; }
  current = res.run; location.hash = res.run; drawnFor = ""; setTab("ov"); refresh(); return true;
}
$("dlg-go").addEventListener("click", async () => { if (await start($("f-policy").value, $("f-split").value, $("f-limit").value, +$("f-pace").value)) dlg.close(); });
$("empty-run").addEventListener("click", () => start("reconcile", "dev", null, 0.06));
addEventListener("keydown", (e) => { if (e.key === "n" && !dlg.open && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); openDlg("builtin"); } });
addEventListener("hashchange", () => { const id = decodeURIComponent(location.hash.slice(1)); if (id && id !== current) { current = id; drawnFor = ""; refresh(); } });
addEventListener("resize", () => { drawnFor = ""; render(); });
loadStatic().then(refresh);
