"use strict";
// Training page: a four-step wizard (model, data, setup assistant, launch) and the live telemetry dashboard of a
// training run (#run=<id>). Reads /api/scout, /api/runs, /api/runs/<id>, /data/report.json; writes only through
// POST /api/train, /api/runs/<id>/stop and /api/train/<id>/curve (contract: docs/TRAINING_API.md).
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else e.setAttribute(k, v); } for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k))); return e; };
const SVGNS = "http://www.w3.org/2000/svg";
const svg = (tag, attrs = {}, parent) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.append(e); return e; };
const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
const PRESETS = { mixed: "смешанные", simple: "простые", interacting: "с взаимодействиями" };
const METHODS = { cem: "CEM", reinforce: "REINFORCE" };
const STATUS = { running: ["идёт", "lime"], done: ["завершено", "dim"], stopped: ["остановлено", "gold"], error: ["ошибка", "pink"] };
const LIMITS = { iterations: [2, 200, 1], population: [4, 64, 1], episodes_per_candidate: [1, 10, 1], seed: [0, 1000000, 1], elite_frac: [0.05, 0.5, 0], eval_every: [1, 20, 1], pace: [0, 0.5, 0] };
const FIELDS = { iterations: "f-iter", population: "f-pop", episodes_per_candidate: "f-epc", seed: "f-seed", elite_frac: "f-elite", eval_every: "f-every", pace: "f-pace" };
const FIELD_NAMES = { iterations: "Итераций", population: "Популяция", episodes_per_candidate: "Эпизодов на кандидата", seed: "Сид", elite_frac: "Доля элиты", eval_every: "Проверка на dev", pace: "Темп показа" };
const DEFAULTS = { method: "cem", iterations: 30, population: 16, episodes_per_candidate: 4, elite_frac: 0.25, seed: 1, eval_every: 2, pace: 0, dataset: { preset: "mixed" } };
const MINUS = "−";
const num = (v, d = 2) => (v == null || !Number.isFinite(v) ? "—" : (Math.round(v * 10 ** d) / 10 ** d < 0 ? MINUS : "") + Math.abs(v).toFixed(d));
const f2 = (v) => num(v, 2);
const sgn = (v) => (v == null || !Number.isFinite(v) ? "—" : (v >= 0 ? "+" : MINUS) + Math.abs(v).toFixed(2));
const plural = (n, a, b, c) => { const k = n % 100, d = n % 10; return `${n} ${k >= 11 && k <= 14 ? c : d === 1 ? a : d >= 2 && d <= 4 ? b : c}`; };
const thin = (n) => String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
const when = (t) => (t ? new Date(t * 1000).toLocaleString((window.AG_LANG === "en" ? "en-GB" : "ru-RU"), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
const dur = (s) => (s == null || !Number.isFinite(s) ? "—" : s < 60 ? `${s.toFixed(s < 10 ? 1 : 0)} с` : `${Math.floor(s / 60)} мин ${String(Math.round(s % 60)).padStart(2, "0")} с`);

let step = 1, scout = null, scoutState = "loading", base = { reconcile: 0.97, random: -1 }, recent = [];
let runId = null, run = null, timer = null, wasRunning = false;

// ---- theme toggle (same as the other pages; charts follow the CSS tokens, nothing to redraw)
(() => { const b = $("theme"); const tc = document.querySelector('meta[name="theme-color"]'); const lbl = b.querySelector("span");
  const sync = () => { const dark = document.documentElement.dataset.theme === "dark"; b.setAttribute("aria-pressed", String(dark)); b.setAttribute("aria-label", dark ? "Светлая тема" : "Тёмная тема"); lbl.textContent = dark ? "Светлая" : "Тёмная"; tc.setAttribute("content", dark ? "#0e0e11" : "#f7f7f8"); };
  sync(); b.addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; if (dark) document.documentElement.dataset.theme = "dark"; else delete document.documentElement.dataset.theme; try { localStorage.setItem("ag-theme", dark ? "dark" : "light"); } catch { /* private mode */ } sync(); }); })();

// every request resolves to {status, body}; status 0 means the server did not answer
async function api(url, opts = {}) {
  try {
    const r = await fetch(url, { cache: "no-store", ...opts });
    let body = null; try { body = await r.json(); } catch { body = null; }
    return { status: r.status, body };
  } catch { return { status: 0, body: null }; }
}
const post = (url, body) => api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
const NO_SERVER = "Сервер не отвечает: откройте страницу через python -m auditgym.cli ui.";

async function loadBaselines() {  // reference lines: the base policies' mean reward from report.json (fallback: the contract's figures)
  const { status, body } = await api("/data/report.json");
  if (status !== 200 || !body) return;
  for (const row of body.policy_summary || []) {
    const v = Object.entries(row).filter(([k, x]) => k !== "policy" && typeof x === "number").map(([, x]) => x);
    if (v.length && (row.policy === "reconcile" || row.policy === "random")) base[row.policy] = v.reduce((a, b) => a + b, 0) / v.length;
  }
}

// =====================================================================================================  wizard
function readCfg() {
  const c = { method: document.querySelector('input[name="method"]:checked').value, dataset: { preset: document.querySelector('input[name="preset"]:checked').value } };
  for (const [k, id] of Object.entries(FIELDS)) c[k] = $(id).value.trim() === "" ? NaN : Number($(id).value);
  return c;
}
function validate(c) {
  const bad = [];
  for (const [k, [lo, hi, int]] of Object.entries(LIMITS)) {
    const v = c[k], ok = Number.isFinite(v) && v >= lo && v <= hi && (!int || Number.isInteger(v));
    $(FIELDS[k]).setAttribute("aria-invalid", String(!ok));
    if (!ok) bad.push(`${FIELD_NAMES[k]}: ${int ? "целое " : ""}от ${String(lo).replace(".", ",")} до ${String(hi).replace(".", ",")}`);
  }
  return bad;
}
function writeCfg(c) {
  const m = c.method === "reinforce" ? "m-rf" : "m-cem"; $(m).checked = true;
  const p = { mixed: "d-mixed", simple: "d-simple", interacting: "d-inter" }[(c.dataset || {}).preset]; if (p) $(p).checked = true;
  for (const [k, id] of Object.entries(FIELDS)) if (c[k] != null) $(id).value = c[k];
  syncSummary();
}
const work = (c) => c.iterations * c.population * c.episodes_per_candidate;
function estSeconds(c) {
  const rec = scout && scout.recommendation;
  if (!rec || !Number.isFinite(rec.est_seconds) || !Number.isFinite(work(c))) return null;
  const rc = { ...DEFAULTS, ...(rec.config || {}) };
  return rec.est_seconds * work(c) / Math.max(1, work(rc)) + (c.pace || 0) * c.iterations;
}
function terminalCmd(c) { return `python train/learn_rules.py --seed ${Number.isFinite(c.seed) ? c.seed : 1} --iterations ${Number.isFinite(c.iterations) ? c.iterations : 30} --method ${c.method}`; }

function syncSummary() {
  const c = readCfg(), est = estSeconds(c);
  const per = c.population * c.episodes_per_candidate;
  const rows = [["Метод", `Аудитор · ${METHODS[c.method]}`], ["Учебные эпизоды", PRESETS[c.dataset.preset]],
    ["Итераций", Number.isFinite(c.iterations) ? c.iterations : "—"], ["Популяция × эпизоды", Number.isFinite(per) ? `${c.population} × ${c.episodes_per_candidate} = ${per}` : "—"],
    ["Всего эпизодов", Number.isFinite(work(c)) ? thin(work(c)) : "—"], ["Сид", Number.isFinite(c.seed) ? c.seed : "—"],
    ["Проверка на dev", Number.isFinite(c.eval_every) ? `каждые ${c.eval_every} итер.` : "—"], ["Оценка времени", est == null ? "после помощника" : "≈ " + dur(est)]];
  $("sum").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
  const nonDefault = c.population !== DEFAULTS.population || c.episodes_per_candidate !== DEFAULTS.episodes_per_candidate || c.dataset.preset !== "mixed" || c.elite_frac !== DEFAULTS.elite_frac || c.eval_every !== DEFAULTS.eval_every;
  document.querySelector(".sum-cmd-l").textContent = nonDefault ? "в терминале (остальные настройки — по умолчанию)" : "то же в терминале";
  $("sum-cmd").textContent = terminalCmd(c);
  $("go-train").textContent = Number.isFinite(work(c)) ? `${plural(c.iterations, "итерация", "итерации", "итераций")} по ${plural(per, "эпизоду", "эпизода", "эпизодов")} (${PRESETS[c.dataset.preset]}, сид ${c.seed}) — награда видна только тренеру` : "проверьте настройки на шаге 2";
  $("go-eval").textContent = Number.isFinite(c.eval_every) ? `лучшая политика каждые ${plural(c.eval_every, "итерацию", "итерации", "итераций")} на 10 отложенных эпизодах dev, закрытый режим` : "—";
  $("go-est").textContent = est == null ? "Время обучения оценит помощник на шаге 3." : `Оценка времени: ≈ ${dur(est)} на этом компьютере.`;
}

function setStep(n) {
  step = n;
  for (let i = 1; i <= 4; i++) {
    $("p-" + i).classList.toggle("hidden", i !== n);
    const b = $("st-" + i); b.classList.toggle("done", i < n); b.classList.toggle("on", i === n);
    if (i === n) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
  }
  $("back").disabled = n === 1;
  $("next").classList.toggle("hidden", n === 4);
  $("go").classList.toggle("hidden", n !== 4);
  $("foot-n").textContent = `Шаг ${n} из 4`;

}
function leaveStep2() {
  const bad = validate(readCfg());
  $("f-err").textContent = bad.length ? "Проверьте: " + bad.join("; ") + "." : "";
  $("f-err").classList.toggle("hidden", !bad.length);
  return !bad.length;
}
function goStep(n) { if (n > 2 && step <= 2 && !leaveStep2()) { setStep(2); return; } setStep(n); }
$("next").addEventListener("click", () => goStep(Math.min(4, step + 1)));
$("back").addEventListener("click", () => setStep(Math.max(1, step - 1)));
for (let i = 1; i <= 4; i++) $("st-" + i).addEventListener("click", () => goStep(i));
document.querySelectorAll("#p-1 input, #p-2 input").forEach((i) => i.addEventListener("input", () => { if (i.getAttribute("aria-invalid") === "true") validate(readCfg()); syncSummary(); }));

// ---- setup assistant (scout)
function llmCmd(name) { return `python -m auditgym.cli run-agent --name ${(name.split(":")[0] || "llm").replace(/[^\w.-]/g, "")} --cmd "python examples/llm_agent.py --model ${name}" --split dev`; }
async function copy(text, btn) {
  try { await navigator.clipboard.writeText(text); const t = btn.textContent; btn.textContent = "Скопировано"; setTimeout(() => (btn.textContent = t), 1500); }
  catch { btn.textContent = "Выделите и скопируйте"; }
}
function renderModels() {
  const ul = $("llm-list"), note = $("llm-note"); ul.replaceChildren();
  const ol = scout && scout.ollama;
  if (!scout) { note.textContent = scoutState === "loading" ? "Ищем модели через помощника…" : "Помощник недоступен, поэтому локальные модели не найдены. Любую модель Ollama можно оценить из терминала:"; }
  else if (!ol || !ol.available) note.textContent = "Ollama не найдена на этом компьютере. Для обучения она не нужна; подключить её можно позже, чтобы оценить LLM-агента.";
  else if (!(ol.models || []).length) note.textContent = "Ollama работает, но моделей пока нет (ollama pull qwen2.5:1.5b).";
  else note.textContent = "Веса LLM здесь не обучаются: их можно только оценить на тех же эпизодах dev. Браузер не запускает внешние программы — скопируйте команду в терминал.";
  const models = scout && ol && ol.available ? ol.models || [] : scoutState === "error" ? [{ name: "qwen2.5:1.5b", generic: true }] : [];
  const pick = scout && scout.recommendation ? scout.recommendation.evaluate_llm : null;
  for (const m of models.slice(0, 3)) {
    const cmd = llmCmd(m.name);
    const btn = el("button", { class: "btn outline small", "aria-label": `Скопировать команду для ${m.name}` }, "Скопировать");
    btn.addEventListener("click", () => copy(cmd, btn));
    const meta = m.generic ? "пример" : [m.params, m.quant, m.size_gb != null ? `${String(m.size_gb).replace(".", ",")} ГБ` : null].filter(Boolean).join(" · ");
    ul.append(el("li", {}, el("div", { class: "llm-t" }, el("b", { class: "mono" }, m.name), el("span", { class: "muted small" }, meta), m.name === pick ? el("span", { class: "rec-tag" }, "советует помощник") : ""),
      el("code", { class: "llm-cmd" }, cmd), btn));
  }
}
function renderScout() {
  renderModels();
  const st = $("sc-state");
  $("sc-body").classList.toggle("hidden", !scout);
  $("sc-apply").disabled = !scout; $("sc-explain").disabled = !scout;
  st.classList.remove("hidden");
  if (!scout) { st.textContent = scoutState === "loading" ? "Спрашиваем помощника…" : "Помощник пока недоступен — настройки можно выбрать вручную на шагах 1 и 2. Значения по умолчанию подходят для обычного ноутбука."; syncSummary(); return; }
  st.textContent = ""; st.classList.add("hidden");
  const m = scout.machine || {}, gpu = (m.gpu || []).map((g) => g.name + (g.vram_gb ? ` · ${g.vram_gb} ГБ` : "")).join(", ");
  const ol = scout.ollama || {};
  const rows = [["Система", m.os || "—"], ["Python", m.python || "—"], ["Процессор", m.cpu_count ? plural(m.cpu_count, "ядро", "ядра", "ядер") : "—"],
    ["Память", m.ram_gb != null ? `${String(m.ram_gb).replace(".", ",")} ГБ` : "—"], ["Видеокарта", gpu || "нет — и не нужна"],
    ["Ollama", ol.available ? plural((ol.models || []).length, "модель", "модели", "моделей") : "не найдена"]];
  $("sc-machine").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
  const rec = scout.recommendation || {}, c = { ...DEFAULTS, ...(rec.config || {}) };
  $("sc-rec").replaceChildren(el("b", {}, `${METHODS[c.method] || c.method} · ${plural(c.iterations, "итерация", "итерации", "итераций")}`),
    el("span", {}, `популяция ${c.population} × ${c.episodes_per_candidate} эп. · ${PRESETS[(c.dataset || {}).preset] || "смешанные"}`),
    el("span", { class: "sc-est" }, Number.isFinite(rec.est_seconds) ? `≈ ${dur(rec.est_seconds)} на этом компьютере` : ""));
  const why = (rec.reasons || []).map((r) => el("li", {}, r));
  if (rec.evaluate_llm) why.push(el("li", {}, `Для оценки (не обучения) подойдёт ${rec.evaluate_llm} — команда на шаге 1.`));
  $("sc-why").replaceChildren(...why);
  syncSummary();
}
async function loadScout(explain = false) {
  const { status, body } = await api("/api/scout" + (explain ? "?explain=1" : ""));
  if (status === 200 && body && body.ok && body.scout) { scout = body.scout; scoutState = "ok"; return true; }
  if (!explain) { scout = null; scoutState = "error"; }
  return false;
}
$("sc-apply").addEventListener("click", () => {
  if (!scout || !scout.recommendation) return;
  writeCfg({ ...DEFAULTS, ...scout.recommendation.config, seed: Number($("f-seed").value) || DEFAULTS.seed });
  validate(readCfg()); $("f-err").classList.add("hidden");
  $("sc-applied").textContent = "Применено — проверьте на шаге 4";
});
$("sc-explain").addEventListener("click", async () => {
  const box = $("sc-expl"), b = $("sc-explain");
  b.disabled = true; box.classList.remove("hidden"); box.classList.remove("bad"); box.textContent = "Спрашиваем локальную модель… это может занять несколько секунд.";
  const ok = await loadScout(true);
  b.disabled = false;
  const text = ok && scout.explanation;
  if (ok) renderScout();
  box.textContent = text || "Локальная модель не ответила, поэтому объяснения нет. Причины выше помощник составил сам, без LLM.";
  box.classList.toggle("bad", !text);
});

// ---- recent trainings
async function loadRecent() {
  const { status, body } = await api("/api/runs");
  const note = $("rec-note");
  if (status !== 200 || !body || !body.ok) { recent = []; note.textContent = "Список недоступен. " + NO_SERVER; note.classList.remove("hidden"); $("recent").replaceChildren(); return; }
  recent = (body.runs || []).filter((r) => r.kind === "training");
  note.textContent = recent.length ? "" : "Пока нет обучений — первое появится здесь.";
  note.classList.toggle("hidden", !!recent.length);
  $("recent").replaceChildren(...recent.slice(0, 8).map((r) => {
    const [st, cls] = STATUS[r.status] || [r.status, "dim"], s = r.summary || {};
    const at = Math.min(r.at ?? 0, r.iterations ?? Infinity);  // finished iterations
    return el("li", {}, el("button", { class: "run-i" + (r.id === runId ? " on" : ""), "aria-label": `Открыть обучение ${r.id}`, onclick: () => openRun(r.id) },
      el("span", { class: "ri-top" }, el("b", {}, `Аудитор · ${METHODS[r.method] || r.method || r.model}`), el("span", { class: "badge " + cls }, st)),
      el("span", { class: "ri-sub" }, `${at}/${r.iterations ?? "?"} итер. · ${when(r.started)}`),
      el("span", { class: "ri-v mono" }, f2(s.dev_best))));
  }));
}

// ---- launch
$("go").addEventListener("click", async () => {
  const err = $("go-err"), c = readCfg(), bad = validate(c);
  if ($("f-seeds").checked && Number.isFinite(c.seed)) c.seeds = [c.seed, c.seed + 1, c.seed + 2];
  try { if (window.Notification && Notification.permission === "default") Notification.requestPermission(); } catch { /* not offered */ }
  err.classList.add("hidden");
  if (bad.length) { leaveStep2(); setStep(2); return; }
  const b = $("go"); b.disabled = true; b.textContent = "Запускаем…";
  const { status, body } = await post("/api/train", c);
  b.disabled = false; b.textContent = "Запустить обучение";
  if (status === 200 && body && body.ok && body.run) { openRun(body.run); loadRecent(); return; }
  err.replaceChildren();
  const e = (body && body.error) || {};
  if (e.code === "busy") {
    err.append("Уже идёт другой запуск. Дождитесь его окончания или остановите его. ");
    if (e.run) { const isTrain = recent.some((r) => r.id === e.run); err.append(el("a", { href: isTrain ? "#run=" + encodeURIComponent(e.run) : "/runs.html#" + encodeURIComponent(e.run) }, "Открыть идущий запуск")); }
  } else if (status === 400 || e.code === "bad_arguments") err.append("Сервер не принял настройки: " + (e.message || "неверные значения") + ".");
  else if (status === 0) err.append(NO_SERVER);
  else if (status === 404 || status === 405) err.append("На этом сервере обучение пока не включено (нет /api/train). Обновите AuditGym или запустите тренер из терминала: " + terminalCmd(c));
  else err.append("Не удалось запустить: " + (e.message || "ошибка сервера " + status) + ".");
  err.classList.remove("hidden");
});

// =====================================================================================================  dashboard
const tip = $("tip");
function placeTip(x, y) {
  tip.hidden = false;
  const r = tip.getBoundingClientRect();
  let left = x + 16; if (left + r.width > innerWidth - 8) left = x - r.width - 16; left = Math.max(8, left);
  tip.style.left = left + "px"; tip.style.top = Math.max(8, Math.min(innerHeight - r.height - 8, y - r.height / 2)) + "px";
}
const hideTip = () => { tip.hidden = true; };

function niceStep(raw) { const p = 10 ** Math.floor(Math.log10(raw)), f = raw / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p; }
function autoDomain(vals, floor) {  // [0, hi] with 3–5 round ticks; hi never below `floor`
  const mx = Math.max(floor, ...vals.filter(Number.isFinite)); const st = niceStep(mx / 4); const hi = Math.ceil(mx / st - 1e-9) * st;
  const ticks = []; for (let v = 0; v <= hi + 1e-9; v += st) ticks.push(+v.toFixed(6));
  return { lo: 0, hi, ticks };
}
const tickTxt = (v) => (v === 0 ? "0" : (v < 0 ? MINUS : "") + String(+Math.abs(v).toFixed(2)));
function xTicks(n) { const st = n <= 12 ? 1 : niceStep(n / 6); const out = [1]; for (let v = st; v <= n; v += st) if (v > 1) out.push(v); return out; }

// A line chart that keeps its frame and grows its lines as points arrive (no rebuild, no flicker).
class LineChart {
  constructor(host, o) { this.host = host; this.o = o; this.key = ""; this.len = {}; this.count = 0; this.hover = null; this.fresh = true; }
  update(points, n) {
    const o = this.o, pts = (o.dev ? points.filter((p) => p.dev) : points).filter((p) => o.series.some((s) => Number.isFinite(s.get(p))));
    this.pts = pts;
    const W = Math.max(240, Math.round(this.host.clientWidth || 600));
    const dom = o.domain(pts);
    const key = [W, n, dom.lo, dom.hi, base.reconcile, base.random].join("|");
    const rebuilt = key !== this.key;
    if (rebuilt) { this.build(W, Math.max(2, n), dom); this.key = key; }
    this.draw(pts, !RM && (!rebuilt || this.fresh));
    this.fresh = false;
    this.svg.setAttribute("aria-label", o.aria(pts, n));
    if (this.hover != null && document.activeElement === this.svg) this.show(Math.min(this.hover, pts.length - 1));
  }
  build(W, n, dom) {
    const o = this.o, H = Math.round(Math.min(o.h, Math.max(150, W * 0.72))), m = { l: 38, r: o.endLabels ? 44 : 14, t: 10, b: 24 };
    this.m = m; this.W = W; this.H = H; this.n = n;
    this.X = (i) => m.l + (i / (n - 1)) * (W - m.l - m.r);
    this.Y = (v) => m.t + ((dom.hi - v) / (dom.hi - dom.lo)) * (H - m.t - m.b);
    this.host.replaceChildren();
    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", height: H, class: "ch tr-ch", role: "img", tabindex: "0", "aria-roledescription": "график" }, this.host);
    this.svg = s;
    for (const t of dom.ticks) {
      svg("line", { x1: m.l, x2: W - m.r, y1: this.Y(t), y2: this.Y(t), class: t === 0 && dom.lo < 0 ? "zero" : "grid" }, s);
      svg("text", { x: m.l - 8, y: this.Y(t) + 3.5, "text-anchor": "end", class: "tick" }, s).textContent = tickTxt(t);
    }
    for (const t of xTicks(n)) svg("text", { x: this.X(t - 1), y: H - 6, "text-anchor": "middle", class: "tick" }, s).textContent = t;
    this.refLabels = [];
    for (const r of o.refs ? o.refs() : []) {
      if (!Number.isFinite(r.v)) continue;
      const y = this.Y(Math.max(dom.lo, Math.min(dom.hi, r.v)));
      svg("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, class: "ref" }, s);
      const t = svg("text", { x: m.l + 8, y: y + (y - m.t < 16 ? 14 : -6), class: "ref-l" }, s); t.textContent = `${r.label} ${f2(r.v)}`;
      this.refLabels.push([t, r.v]);
    }
    this.gLines = svg("g", {}, s); this.gMarks = svg("g", {}, s); this.gEnds = svg("g", {}, s);
    this.paths = o.series.map((se) => svg("path", { class: "tl " + se.cls }, this.gLines));
    this.len = {}; this.count = 0;
    this.gHover = svg("g", { class: "hov", visibility: "hidden" }, s);
    this.xh = svg("line", { y1: m.t, y2: H - m.b, class: "xh" }, this.gHover);
    this.hdots = o.series.map((se) => svg("circle", { r: 4.5, class: "mk " + se.cls }, this.gHover));
    svg("rect", { x: m.l, y: 0, width: Math.max(1, W - m.l - m.r + 6), height: H - m.b, class: "hit" }, s);
    s.addEventListener("pointermove", (ev) => this.onMove(ev));
    s.addEventListener("pointerleave", () => { if (document.activeElement !== s) this.hide(); });
    s.addEventListener("focus", () => { if (this.pts.length) this.show(this.hover ?? this.pts.length - 1); });
    s.addEventListener("blur", () => this.hide());
    s.addEventListener("keydown", (ev) => {
      if (!this.pts.length) return;
      const k = this.hover ?? this.pts.length - 1, last = this.pts.length - 1;
      const next = { ArrowLeft: k - 1, ArrowRight: k + 1, Home: 0, End: last }[ev.key];
      if (ev.key === "Escape") { this.hide(); return; }
      if (next == null) return;
      ev.preventDefault(); this.show(Math.max(0, Math.min(last, next)));
    });
  }
  draw(pts, animate) {
    const o = this.o, dense = o.endDot || pts.length > 20, grew = animate && pts.length > this.count;
    o.series.forEach((se, k) => {
      const xy = pts.map((p) => [this.X(p.i), this.Y(se.get(p))]).filter((q) => Number.isFinite(q[1]));
      const path = this.paths[k], prev = this.len[k] || 0;
      path.setAttribute("d", xy.map((q, j) => (j ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1)).join(""));
      const L = xy.length > 1 ? path.getTotalLength() : 0; this.len[k] = L;
      if (animate && L > prev + 0.5) {  // reveal only the new stretch of the line
        path.style.transition = "none"; path.style.strokeDasharray = `${L} ${L}`; path.style.strokeDashoffset = String(L - prev);
        path.getBoundingClientRect();
        path.style.transition = `stroke-dashoffset ${prev ? 0.5 : 0.9}s cubic-bezier(.3,.7,.2,1)`; path.style.strokeDashoffset = "0";
        const done = () => { path.style.strokeDasharray = ""; path.style.strokeDashoffset = ""; path.style.transition = ""; path.removeEventListener("transitionend", done); };
        path.addEventListener("transitionend", done);
      }
    });
    // markers: every point while sparse, the end dot only once dense; a new marker appears as its line reaches it
    this.gMarks.replaceChildren();
    o.series.forEach((se) => pts.forEach((p, j) => {
      const v = se.get(p); if (!Number.isFinite(v) || (dense && j !== pts.length - 1)) return;
      const c = svg("circle", { cx: this.X(p.i), cy: this.Y(v), r: 4, class: "mk " + se.cls + (animate && j >= this.count ? " in" : "") }, this.gMarks);
      if (animate && j >= this.count && this.count === 0) c.style.animationDelay = (0.9 * j / Math.max(1, pts.length - 1)).toFixed(2) + "s";
    }));
    // direct end labels (values in text colour), pushed apart when they would collide
    this.gEnds.replaceChildren();
    if (o.endLabels && pts.length) {
      const last = pts[pts.length - 1];
      const labs = o.series.map((se) => ({ v: se.get(last), y: this.Y(se.get(last)) })).filter((q) => Number.isFinite(q.v)).sort((a, b) => a.y - b.y);
      for (let j = 1; j < labs.length; j++) if (labs[j].y - labs[j - 1].y < 12) labs[j].y = labs[j - 1].y + 12;
      const over = labs.length ? labs[labs.length - 1].y - (this.H - this.m.b) : 0; if (over > 0) labs.forEach((q) => (q.y -= over));
      for (const q of labs) svg("text", { x: this.X(last.i) + 8, y: q.y + 3.5, class: "end" + (grew ? " in" : "") }, this.gEnds).textContent = o.fmt(q.v);
    }
    // a reference label sits at the end of the plot (left or right) where the data line is farther from it
    const se0 = o.series[0], vals = pts.map((p) => se0.get(p)).filter(Number.isFinite);
    for (const [t, v] of this.refLabels) {
      const left = vals.length ? Math.abs(vals[0] - v) : 9, right = vals.length ? Math.abs(vals[vals.length - 1] - v) : 0;
      const atRight = right > left && vals.length > 1;
      t.setAttribute("x", atRight ? this.X(this.n - 1) - 8 : this.m.l + 8); t.setAttribute("text-anchor", atRight ? "end" : "start");
    }
    this.count = pts.length;
  }
  onMove(ev) {
    if (!this.pts.length) return;
    const r = this.svg.getBoundingClientRect(), x = (ev.clientX - r.left) * (this.W / r.width);
    let best = 0; this.pts.forEach((p, j) => { if (Math.abs(this.X(p.i) - x) < Math.abs(this.X(this.pts[best].i) - x)) best = j; });
    this.show(best, ev.clientX, ev.clientY);
  }
  show(j, cx, cy) {
    const p = this.pts[j]; if (!p) return;
    if (LineChart.active && LineChart.active !== this) LineChart.active.hide();
    LineChart.active = this; this.hover = j;
    const x = this.X(p.i); this.xh.setAttribute("x1", x); this.xh.setAttribute("x2", x);
    this.o.series.forEach((se, k) => { const v = se.get(p), d = this.hdots[k]; d.setAttribute("visibility", Number.isFinite(v) ? "visible" : "hidden"); if (Number.isFinite(v)) { d.setAttribute("cx", x); d.setAttribute("cy", this.Y(v)); } });
    this.gHover.setAttribute("visibility", "visible");
    tip.replaceChildren(el("span", { class: "tt" }, `Итерация ${p.i + 1}`),
      ...this.o.series.map((se) => el("span", { class: "tip-r" }, el("i", { class: "lk " + se.cls, "aria-hidden": "true" }), el("b", {}, this.o.fmt(se.get(p))), el("span", {}, se.name))),
      ...(this.o.extra ? this.o.extra(p) : []).map((l) => el("span", { class: "tip-x" }, l)));
    if (cx == null) { const r = this.svg.getBoundingClientRect(), sc = r.width / this.W; cx = r.left + x * sc; cy = r.top + this.Y(this.o.series[0].get(p)) * sc; }
    placeTip(cx, cy);
  }
  hide() { this.hover = null; if (this.gHover) this.gHover.setAttribute("visibility", "hidden"); hideTip(); }
}

const dv = (k) => (p) => (p.dev ? p.dev[k] : NaN);
const tv = (k) => (p) => p[k];
const R11 = () => ({ lo: -1, hi: 1, ticks: [-1, -0.5, 0, 0.5, 1] });
const ariaLine = (title, get, fmt) => (pts, n) => {
  if (!pts.length) return `${title}: данных пока нет.`;
  const vals = pts.map((p) => [p.i, get(p)]).filter((q) => Number.isFinite(q[1]));
  const first = vals[0], last = vals[vals.length - 1], mx = vals.reduce((a, b) => (b[1] > a[1] ? b : a)), mn = vals.reduce((a, b) => (b[1] < a[1] ? b : a));
  return `${title}, ${plural(vals.length, "точка", "точки", "точек")} из ${n} итераций: в начале ${fmt(first[1])}, сейчас ${fmt(last[1])} (итерация ${last[0] + 1}), наибольшее ${fmt(mx[1])}, наименьшее ${fmt(mn[1])}. Стрелки влево и вправо — по точкам.`;
};
const charts = {
  dev: new LineChart($("ch-dev"), { h: 318, dev: true, endLabels: true, domain: R11, fmt: f2, series: [{ name: "награда на dev", cls: "s1", get: dv("reward") }],
    refs: () => [{ v: base.reconcile, label: "Сверщик" }, { v: base.random, label: "Стажёр" }],
    extra: (p) => [`F1 ${f2(p.dev.f1)} · ложных ${num(p.dev.fp, 1)} · шагов ${num(p.dev.steps, 1)}`, `до Сверщика ${sgn(p.dev.reward - base.reconcile)}`],
    aria: ariaLine("Награда на отложенных эпизодах dev", dv("reward"), f2) }),
  train: new LineChart($("ch-train"), { h: 210, endLabels: true, endDot: true, domain: R11, fmt: f2,
    series: [{ name: "лучший кандидат", cls: "s3", get: tv("train_best") }, { name: "элита", cls: "s2", get: tv("train_elite") }, { name: "среднее популяции", cls: "s1", get: tv("train_mean") }],
    extra: (p) => [`${plural(p.episodes, "эпизод", "эпизода", "эпизодов")} · ${num(p.seconds, 1)} с`], aria: ariaLine("Средняя награда популяции на обучении", tv("train_mean"), f2) }),
  q: new LineChart($("ch-q"), { h: 210, dev: true, endLabels: true, domain: () => ({ lo: 0, hi: 1, ticks: [0, 0.25, 0.5, 0.75, 1] }), fmt: f2,
    series: [{ name: "F1", cls: "s1", get: dv("f1") }, { name: "точность", cls: "s2", get: dv("precision") }, { name: "полнота", cls: "s3", get: dv("recall") }],
    aria: ariaLine("F1 находок на dev", dv("f1"), f2) }),
  fp: new LineChart($("ch-fp"), { h: 170, dev: true, endLabels: true, domain: (pts) => autoDomain(pts.map(dv("fp")), 1), fmt: (v) => num(v, 1),
    series: [{ name: "ложных на эпизод", cls: "s1", get: dv("fp") }], aria: ariaLine("Ложные находки на эпизод dev", dv("fp"), (v) => num(v, 1)) }),
  steps: new LineChart($("ch-steps"), { h: 170, dev: true, endLabels: true, domain: (pts) => autoDomain(pts.map(dv("steps")), 10), fmt: (v) => num(v, 1),
    series: [{ name: "шагов на эпизод", cls: "s1", get: dv("steps") }], aria: ariaLine("Шаги на эпизод dev", dv("steps"), (v) => num(v, 1)) }),
  sigma: new LineChart($("ch-sigma"), { h: 170, endLabels: true, endDot: true, domain: (pts) => autoDomain(pts.map(tv("sigma")), 0.1), fmt: (v) => num(v, 2),
    series: [{ name: "σ", cls: "s1", get: tv("sigma") }], aria: ariaLine("Разброс поиска σ", tv("sigma"), (v) => num(v, 2)) }),
};

function msg(text, kind = "", link = null) {
  const m = $("d-msg"); delete m.dataset.kind; m.replaceChildren(text); if (link) m.append(" ", el("a", { href: link[0] }, link[1]));
  m.className = "d-msg" + (kind ? " " + kind : ""); m.classList.toggle("hidden", !text);
}
const setKpi = (id, v, d) => { $(id).textContent = v; if (d != null) $(id + "-d").textContent = d; };

function renderDash() {
  const r = run, pts = r.points || [], c = r.config || {}, s = r.summary || {}, n = r.iterations || c.iterations || pts.length || 1;
  const last = pts[pts.length - 1], devs = pts.filter((p) => p.dev);
  const [st, cls] = STATUS[r.status] || [r.status, "dim"];
  $("d-title").textContent = `Аудитор · ${METHODS[r.method || c.method] || r.model || "—"}`;
  $("d-status").className = "badge " + cls; if (r.status === "running") { const sp = document.createElement("span"); sp.className = "ascii-spin"; sp.setAttribute("aria-hidden", "true"); $("d-status").replaceChildren(sp, " " + st); } else $("d-status").textContent = st;
  $("d-cfg").textContent = `${PRESETS[(c.dataset || {}).preset] || "смешанные"} эпизоды · популяция ${c.population ?? "—"} × ${c.episodes_per_candidate ?? "—"} · сид ${c.seed ?? "—"}`;
  $("d-id").textContent = r.id;
  $("d-stop").classList.toggle("hidden", r.status !== "running");
  $("d-save").disabled = !devs.length;
  // KPI row: one hero (best held-out reward and its gaps), the rest small
  const best = s.dev_best ?? (r.best && r.best.dev ? r.best.dev.reward : null), start = s.dev_start ?? (devs[0] ? devs[0].dev.reward : null);
  setKpi("k-best", f2(best), best == null ? "ждём первую проверку на dev" :
    window.AG_LANG === "en"
      ? `${Math.abs(best - base.reconcile).toFixed(2)} ${best - base.reconcile >= 0 ? "above" : "below"} Reconciler (${f2(base.reconcile)})\n${start == null ? "" : sgn(best - start) + " from start (" + f2(start) + ")"}`
      : `${best - base.reconcile >= 0 ? "на " + Math.abs(best - base.reconcile).toFixed(2) + " выше" : "на " + Math.abs(best - base.reconcile).toFixed(2) + " ниже"} Сверщика (${f2(base.reconcile)})\n${start == null ? "" : sgn(best - start) + " от старта (" + f2(start) + ")"}`);
  const at = last ? last.i : -1;  // index of the last finished iteration (run.at counts finished iterations)
  setKpi("k-it", at >= 0 ? `${at + 1} / ${n}` : `0 / ${n}`, `проверок на dev: ${devs.length}`);
  setKpi("k-mean", last ? f2(last.train_mean) : "—", last ? `лучший кандидат ${f2(last.train_best)}` : "открытый режим");
  const eps = s.episodes ?? pts.reduce((a, p) => a + (p.episodes || 0), 0);
  setKpi("k-eps", eps ? thin(eps) : "—", c.population ? `${c.population * (c.episodes_per_candidate || 1)} за итерацию` : "");
  setKpi("k-rate", last && Number.isFinite(last.eps_per_sec) ? num(last.eps_per_sec, 0) : "—", null);
  const secs = s.seconds ?? pts.reduce((a, p) => a + (p.seconds || 0), 0);
  const avg = pts.length ? secs / pts.length : null;
  setKpi("k-time", pts.length ? dur(secs) : "—", r.status === "running" ? (avg ? `осталось ≈ ${dur(avg * Math.max(0, n - at - 1))}` : "считаем…") : r.finished ? `закончено ${when(r.finished)}` : when(r.started));
  // progress: one segment per iteration (a plain bar once there are too many)
  const segs = $("d-segs"), cur = r.status === "running" ? at + 1 : -1;
  if (n <= 60) { if (segs.children.length !== n || segs.dataset.bar) { segs.replaceChildren(...Array.from({ length: n }, () => el("i"))); delete segs.dataset.bar; }
    [...segs.children].forEach((x, i) => { x.className = i <= at ? "on" : i === cur ? "now" : ""; }); }
  else { segs.dataset.bar = "1"; segs.replaceChildren(el("i", { class: "on", style: `flex:none;width:${Math.round(100 * (at + 1) / n)}%` }), el("i")); }
  const every = c.eval_every || 2, nextDev = Math.min(n - 1, (Math.floor(at / every) + 1) * every);
  $("k-prog").textContent = r.status === "running" ? `итерация ${at + 2 > n ? n : at + 2} из ${n} · следующая проверка на dev — итерация ${nextDev + 1}`
    : r.status === "done" ? `завершено · ${plural(n, "итерация", "итерации", "итераций")} · ${plural(devs.length, "проверка", "проверки", "проверок")} на dev`
    : r.status === "stopped" ? `остановлено на итерации ${at + 1} из ${n}` : `ошибка на итерации ${at + 1} из ${n}`;
  for (const ch of Object.values(charts)) ch.update(pts, n);
  renderPolicy();
  renderTable(pts);
  renderTest();
  renderGroup();
  const finished = r.status !== "running" && r.best && r.best.theta;
  $("d-eval").classList.toggle("hidden", !finished);
  $("d-export").classList.toggle("hidden", !finished);
}

// ---- the final number on the fresh test split (measured once when training ends) and its failure analysis
const TYPES = { duplicate_invoice: "дубль счёта", payment_allocation: "разнесение платежа", date_or_fx: "дата или курс", period_classification: "отчётный период", invalid: "некорректная" };
const KINDS = { clean: "чистые", interacting: "взаимодействие", errors: "с ошибками" };
function zbar(v) {  // reward in [-1, 1] as a bar from the zero line
  const x = Math.max(-1, Math.min(1, v ?? 0)), w = Math.abs(x) * 50;
  return el("span", { class: "zb", "aria-hidden": "true" }, el("i", { class: "zb-0" }), el("i", { class: "zb-f " + (x >= 0 ? "pos" : "neg"), style: `left:${x >= 0 ? 50 : 50 - w}%;width:${w}%` }));
}
function meter(found, total) {
  return el("span", { class: "mt", "aria-hidden": "true" }, el("i", { style: `width:${total ? (100 * found / total).toFixed(1) : 0}%` }));
}
function renderTest() {
  const box = $("test-body"), t = run.test, r = run;
  if (r.status_note === "testing") { const sp = el("span", { class: "ascii-spin", "aria-hidden": "true" }); box.replaceChildren(el("p", { class: "test-wait" }, sp, " Измеряем лучшую модель на 20 свежих эпизодах…")); return; }
  if (!t || t.error) { box.replaceChildren(el("p", { class: "test-wait muted" }, t && t.error ? "Не удалось измерить на тестовом наборе: " + t.error : r.status === "running" ? "Появится после обучения: лучшая на dev модель будет один раз проверена на 20 свежих эпизодах рядом со Сверщиком и Стажёром." : "Для этого обучения тестовый замер не сохранён (оно сделано до появления тестового набора).")); return; }
  const rows = [["Обученный аудитор", t.auditor, true], ["Сверщик · ручные правила", t.reconcile, false], ["Стажёр · случайный", t.random, false]];
  const left = el("div", { class: "tb" }, el("h4", {}, "Награда на test"), ...rows.map(([name, m, me]) => el("div", { class: "tb-r" + (me ? " me" : "") },
    el("span", { class: "tb-n" }, name), zbar(m && m.reward), el("span", { class: "tb-v mono " + ((m && m.reward) > 0 ? "pos" : "neg") }, f2(m && m.reward)))),
    el("p", { class: "tb-note" }, `F1 ${f2(t.auditor.f1)} · точность ${f2(t.auditor.precision)} · полнота ${f2(t.auditor.recall)} · ложных ${num(t.auditor.fp, 1)} на эпизод · ${num(t.auditor.steps, 1)} шагов`));
  const an = t.analysis || {}, bt = an.by_type || {};
  const right = el("div", { class: "tb" }, el("h4", {}, "Что нашёл и что пропустил"),
    ...Object.keys(TYPES).filter((k) => bt[k]).map((k) => el("div", { class: "tb-r" }, el("span", { class: "tb-n" }, TYPES[k]), meter(bt[k].found, bt[k].issues),
      el("span", { class: "tb-v mono" }, `${bt[k].found}/${bt[k].issues}`))),
    el("p", { class: "tb-note" }, "Ложные находки: " + (Object.entries(an.false_by_type || {}).map(([k, n]) => `${TYPES[k] || k} ${n}`).join(", ") || "нет")),
    el("p", { class: "tb-note" }, "По видам эпизодов: " + Object.entries(an.by_kind || {}).map(([k, v]) => `${KINDS[k] || k} ${f2(v.reward)}`).join(" · ")));
  box.replaceChildren(left, right);
}

// ---- seeds of a group: one curve per seed on dev, their best and their test number
let grpKey = "", grpRunning = false;
async function renderGroup() {
  const card = $("grp-card"), g = run.group;
  card.classList.toggle("hidden", !g);
  if (!g) return;
  const { status, body } = await api("/api/runs");
  if (status !== 200 || !body || !body.ok) return;
  const members = (body.runs || []).filter((x) => x.group === g).sort((a, b) => (a.seed ?? 0) - (b.seed ?? 0));
  grpRunning = members.some((x) => x.status === "running") || members.length < ((run.group_seeds || []).length || members.length);
  const key = members.map((m) => `${m.id}:${m.status}:${m.at}:${m.test_reward}`).join("|");
  if (key === grpKey && $("grp-chart").childNodes.length) return;
  grpKey = key;
  const full = await Promise.all(members.map(async (m) => { const r = await api("/api/runs/" + encodeURIComponent(m.id)); return (r.body && r.body.run) || m; }));
  const host = $("grp-chart"), W = Math.max(260, host.clientWidth || 520), H = 200, m = { l: 34, r: 10, t: 10, b: 22 };
  const n = Math.max(...full.map((r) => r.iterations || (r.config || {}).iterations || 1));
  const X = (i) => m.l + (n <= 1 ? 0 : (i / (n - 1)) * (W - m.l - m.r)), Y = (v) => m.t + ((1 - v) / 2) * (H - m.t - m.b);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "ch", role: "img", "aria-label": "Награда на dev по сидам" });
  for (const v of [1, 0, -1]) { svg("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: v === 0 ? "zero" : "grid" }, s); const tx = svg("text", { x: m.l - 6, y: Y(v) + 4, class: "tick", "text-anchor": "end" }, s); tx.textContent = tickTxt(v); }
  if (base.reconcile != null) svg("line", { x1: m.l, x2: W - m.r, y1: Y(base.reconcile), y2: Y(base.reconcile), class: "ref" }, s);
  full.forEach((r, k) => {
    const pts = (r.points || []).filter((p) => p.dev);
    if (!pts.length) return;
    svg("polyline", { points: pts.map((p) => `${X(p.i).toFixed(1)},${Y(p.dev.reward).toFixed(1)}`).join(" "), class: `gl s${(k % 3) + 1}` }, s);
  });
  host.replaceChildren(s);
  $("grp-lgd").replaceChildren(...full.map((r, k) => el("li", {}, el("i", { class: `lk s${(k % 3) + 1}` }), `сид ${(r.config || {}).seed ?? r.seed}`)), ...(base.reconcile != null ? [el("li", {}, el("i", { class: "sw ref" }), "Сверщик")] : []));
  $("grp-t").replaceChildren(...full.map((r) => { const ss = r.summary || {}, [st] = STATUS[r.status] || [r.status];
    return el("tr", { class: r.id === run.id ? "on" : "" }, el("td", {}, el("a", { href: "#run=" + encodeURIComponent(r.id) }, `сид ${(r.config || {}).seed ?? r.seed}`)),
      el("td", { class: "num mono" }, f2(ss.dev_start)), el("td", { class: "num mono" }, f2(ss.dev_best)), el("td", { class: "num mono strong" }, f2(((r.test || {}).auditor || {}).reward)), el("td", {}, st)); }));
  const done = full.filter((r) => r.test && r.test.auditor);
  if (done.length > 1) { const v = done.map((r) => r.test.auditor.reward), mean = v.reduce((a, b) => a + b, 0) / v.length;
    $("grp-sub").textContent = `та же конфигурация на ${full.length} сидах · на test: среднее ${f2(mean)}, от ${f2(Math.min(...v))} до ${f2(Math.max(...v))}`; }
}

function renderPolicy() {
  const b = run.best || {}, list = b.describe || [];
  $("pol-sub").textContent = b.dev ? `лучшая на итерации ${b.i + 1} · награда на dev ${f2(b.dev.reward)} · ${plural(list.length, "правило", "правила", "правил")}` : "появится после первой проверки на dev";
  $("pol").replaceChildren(...(list.length ? list.map((d) => el("li", { class: d.on === false ? "off" : "" },
    d.on === false ? el("span", { class: "pol-off", "aria-hidden": "true" }, "—") : (() => { const s = svg("svg", { class: "tm sm", "aria-hidden": "true" }); svg("use", { href: "#tm-agree" }, s); return s; })(),
    el("span", { class: "pol-l" }, d.label || d.key), el("span", { class: "pol-v" }, (d.on === false ? "выкл" + (d.value && d.value !== "выкл" ? " · " + d.value : "") : d.value) ?? ""),
    el("span", { class: "sr-only" }, d.on === false ? "выключено" : "включено")))
    : [el("li", { class: "pol-empty" }, "Пока проверок не было: здесь будут правила, которые выучил аудитор — какие таблицы он читает и какие проверки включает.")]));
}

function renderTable(pts) {
  const devs = pts.filter((p) => p.dev).length;
  $("tbl-n").textContent = pts.length ? `${plural(pts.length, "итерация", "итерации", "итераций")} · ${plural(devs, "проверка", "проверки", "проверок")} на dev` : "";
  const body = $("tbl");
  if (body.dataset.run !== run.id || body.children.length > pts.length) { body.replaceChildren(); body.dataset.run = run.id; }
  for (const p of pts.slice(body.children.length)) {
    const d = p.dev, td = (v, cls = "") => el("td", { class: "num mono" + cls }, v);
    body.append(el("tr", { class: d ? "" : "q" }, td(p.i + 1), td(f2(p.train_mean)), td(f2(p.train_elite)), td(f2(p.train_best)), td(num(p.sigma, 3)),
      td(d ? f2(d.reward) : "—", d ? " strong" : ""), td(d ? f2(d.f1) : "—"), td(d ? f2(d.precision) : "—"), td(d ? f2(d.recall) : "—"),
      td(d ? num(d.fp, 1) : "—"), td(d ? num(d.steps, 1) : "—"), td(p.episodes ?? "—"), td(num(p.seconds, 1) + " с")));
  }
}

function loaded(ok) {  // the run's numbers are shown only once they are read: never a stale or half-empty frame
  for (const e of [$("dash-body"), $("d-status").parentNode, $("d-save")]) e.classList.toggle("hidden", !ok);
  if (!ok) for (const id of ["d-stop", "d-eval", "d-export", "grp-card"]) $(id).classList.add("hidden");
}
async function poll() {
  clearTimeout(timer);
  const id = runId; if (!id) return;
  const { status, body } = await api("/api/runs/" + encodeURIComponent(id));
  if (id !== runId) return;  // the user opened another run meanwhile
  if (status === 200 && body && body.ok && body.run) {
    if (body.run.kind && body.run.kind !== "training") { msg("Это запуск оценки, а не обучение.", "bad", ["/runs.html#" + encodeURIComponent(id), "Открыть на странице «Запуски»"]); return; }
    run = body.run;
    loaded(true);
    if ($("d-msg").dataset.kind === "net") msg("");
    renderDash();
    const running = run.status === "running";
    if (wasRunning && !running && !run.status_note) notifyEnd();
    if (wasRunning && !running) { loadRecent(); msg(run.status === "done" ? "Обучение завершено. Сохраните кривую, чтобы она появилась на странице «Запуски»." : run.status === "stopped" ? "Обучение остановлено; лучшая найденная политика сохранена." : "Обучение прервалось с ошибкой.", run.status === "error" ? "bad" : ""); }
    wasRunning = running || !!run.status_note;
    if (running || run.status_note) timer = setTimeout(poll, 700);
    else if (run.group && grpRunning) timer = setTimeout(poll, 1500);  // the other seeds of the group are still training
    return;
  }
  if (status === 404) { run = null; loaded(false); $("d-title").textContent = "Обучение не найдено"; msg(`Обучение «${id}» не найдено: папка запуска удалена или ещё не создана.`, "bad", ["/train.html", "Новое обучение"]); return; }
  msg(status === 0 ? "Сервер не отвечает — пробуем снова…" : `Сервер ответил ошибкой ${status} — пробуем снова…`, "bad"); $("d-msg").dataset.kind = "net";
  timer = setTimeout(poll, 2000);
}

$("d-stop").addEventListener("click", async () => {
  const b = $("d-stop"); b.disabled = true;
  const { status, body } = await post(`/api/runs/${encodeURIComponent(runId)}/stop`);
  b.disabled = false;
  if (status === 200 && body && body.ok) msg("Останавливаем после текущей итерации…");
  else if (status === 409) msg("Это обучение уже не идёт.", "bad");
  else msg(status === 0 ? NO_SERVER : "Не удалось остановить: " + (((body || {}).error || {}).message || "ошибка " + status), "bad");
  poll();
});
$("d-save").addEventListener("click", async () => {
  const { status, body } = await post(`/api/train/${encodeURIComponent(runId)}/curve`);
  if (status === 200 && body && body.ok) msg("Кривая сохранена в train/curve.json — она показана на странице «Запуски».", "ok", ["/runs.html", "Открыть «Запуски»"]);
  else if (status === 404 && body && body.error && body.error.code === "not_found") msg("Сохранить нельзя: это обучение не найдено на сервере.", "bad");
  else if (status === 404 || status === 405) msg("На этом сервере сохранение кривой пока не включено.", "bad");
  else msg(status === 0 ? NO_SERVER : "Не удалось сохранить кривую: " + (((body || {}).error || {}).message || "ошибка " + status), "bad");
});
function notifyEnd() {  // a desktop notification when the window is in the background (if the user allowed it)
  const text = run.status === "done" ? `лучшая на dev ${f2((run.summary || {}).dev_best)}` + (run.test && run.test.auditor ? ` · на test ${f2(run.test.auditor.reward)}` : "") : run.status === "stopped" ? "остановлено" : "ошибка";
  try { if (document.hidden && window.Notification && Notification.permission === "granted") new Notification("AuditGym: обучение завершено", { body: text }); } catch { /* not offered here */ }
  if (document.hidden) { const t0 = document.title; document.title = "✓ " + t0; addEventListener("focus", () => { document.title = t0; }, { once: true }); }
}
$("d-eval").addEventListener("click", async () => {
  const b = $("d-eval"); b.disabled = true;
  const { status, body } = await post("/api/runs", { model: runId, split: "test" });
  b.disabled = false;
  if (status === 200 && body && body.ok) { location.href = "/runs.html#" + encodeURIComponent(body.run); return; }
  const e = (body && body.error) || {};
  msg(e.code === "busy" ? "Уже идёт другой запуск: дождитесь его окончания." : status === 0 ? NO_SERVER : "Не удалось запустить оценку: " + (e.message || "ошибка " + status), "bad");
});
$("d-export").addEventListener("click", async () => {
  const { status, body } = await post(`/api/runs/${encodeURIComponent(runId)}/export`, { lang: window.AG_LANG === "en" ? "en" : "ru" });
  if (status === 200 && body && body.ok) {
    try { const a = el("a", { href: URL.createObjectURL(new Blob([body.markdown], { type: "text/markdown" })), download: `auditgym-${runId}.md` }); document.body.append(a); a.click(); a.remove(); } catch { /* the file is saved on disk anyway */ }
    msg("Отчёт сохранён: " + body.path, "ok");
  } else msg(status === 0 ? NO_SERVER : "Не удалось сохранить отчёт: " + (((body || {}).error || {}).message || "ошибка " + status), "bad");
});
$("d-new").addEventListener("click", () => { history.pushState(null, "", location.pathname); route(); });

// =====================================================================================================  routing
function openRun(id) { location.hash = "run=" + encodeURIComponent(id); }
function route() {
  const m = /^#run=(.+)$/.exec(location.hash);
  const id = m ? decodeURIComponent(m[1]) : null;
  hideTip();
  if (id) {
    $("wiz").classList.add("hidden"); $("dash").classList.remove("hidden");
    if (id !== runId) { runId = id; run = null; wasRunning = false; msg(""); loaded(false); $("d-title").textContent = "Обучение"; $("tbl").replaceChildren(); for (const ch of Object.values(charts)) { ch.key = ""; ch.fresh = true; } }
    document.title = "AuditGym — обучение " + id;
    poll();
  } else {
    clearTimeout(timer); runId = null; run = null;
    $("dash").classList.add("hidden"); $("wiz").classList.remove("hidden");
    document.title = "AuditGym — обучение аудитора";
    loadRecent();
  }
}
addEventListener("hashchange", route);
let rz = 0;
addEventListener("resize", () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(() => { if (run && !$("dash").classList.contains("hidden")) { for (const ch of Object.values(charts)) ch.fresh = false; renderDash(); } }); });
addEventListener("scroll", hideTip, { passive: true });

setStep(1);
syncSummary();
renderScout();
route();
loadBaselines().then(() => { if (run) renderDash(); });
loadScout().then(renderScout);
