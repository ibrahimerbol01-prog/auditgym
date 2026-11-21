"use strict";
// Red team: every attack on the same 20 test episodes, judged against silence (the floor) and the honest Reconciler
// (the ceiling), then an RL attacker trained to win reward without finding errors. Data: GET /api/runs, the arena's
// run.json; started with POST /api/arena. Text only via textContent.
const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k === "class") e.className = v; else e.setAttribute(k, v); } for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k))); return e; };
const svg = (tag, attrs = {}, parent) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.append(e); return e; };
const MINUS = "−";
const f2 = (v) => (v == null || !Number.isFinite(v) ? "—" : Math.abs(v) < 0.005 ? "0.00" : (v < 0 ? MINUS : "+") + Math.abs(v).toFixed(2));
const when = (t) => (t ? new Date(t * 1000).toLocaleString((window.AG_LANG === "en" ? "en-GB" : "ru-RU"), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");

const LANES = {
  silence: ["Молчание", "ничего не заявляет: столько получает агент, который ничего не знает"],
  reconcile: ["Честный Сверщик", "ручные правила сверки: читает все таблицы и доказывает каждую находку"],
  flag_all: ["Пометить всё", "атака жюри из брифа: каждый счёт виноват во всём"],
  duplicate_spam: ["Спам повторами", "одна правдоподобная претензия 30 раз: засчитывается ли повтор?"],
  type_shotgun: ["Дробовик типов", "каждый счёт под всеми четырьмя типами ошибок сразу"],
  evidence_padding: ["Набивка доказательств", "по 10 ID доказательств на претензию в надежде покрыть нужный набор"],
  amount_hedging: ["Разброс сумм", "одна пара счетов с десятью разными суммами: дыра в допуске?"],
  no_proof: ["Без доказательств", "честные находки, но без подтверждающих записей: срезать угол"],
  blind_guess: ["Угадывание вслепую", "ответ на первом шаге, ничего не читая: дешевле ли гадать?"],
  invalid_structure: ["Сломанный ответ", "находки в неверном формате: оценщик не должен упасть или засчитать"],
  rl_attacker: ["RL-атакующий", "обучен тем же CEM максимизировать награду, не ища ошибок"],
};
let arenas = [], current = null, arena = null, timer = 0;

async function api(url, opts) { try { const r = await fetch(url, Object.assign({ cache: "no-store" }, opts || {})); return { status: r.status, body: await r.json().catch(() => null) }; } catch { return { status: 0, body: null }; } }

async function load() {
  const { status, body } = await api("/api/runs");
  if (status !== 200 || !body || !body.ok) { $("ar-big-l").textContent = "Сервер недоступен: откройте приложение AuditGym или python -m auditgym.cli ui."; return; }
  arenas = (body.runs || []).filter((r) => r.kind === "arena");
  const want = decodeURIComponent(location.hash.slice(1));
  if (!current) current = arenas.some((a) => a.id === want) ? want : (arenas[0] && arenas[0].id) || null;
  if (current) { const r = await api("/api/runs/" + encodeURIComponent(current)); arena = r.body && r.body.run; }
  render();
  clearTimeout(timer);
  if (arena && arena.status === "running") timer = setTimeout(load, 700);
}

function xpos(v) { return ((Math.max(-1, Math.min(1, v)) + 1) / 2) * 100; }

function render() {
  const a = arena, s = (a && a.summary) || {}, running = a && a.status === "running";
  $("ar-go").disabled = !!running;
  const lanes = (a && a.lanes) || Object.keys(LANES).map((key) => ({ key, status: "idle" }));
  const lane = (k) => lanes.find((x) => x.key === k) || {};
  const floor = lane("silence").reward, ceil = lane("reconcile").reward;
  // hero
  const now = lanes.find((x) => x.status === "running" || x.status === "training");
  if (!a) { $("ar-big").textContent = "—"; $("ar-big-l").textContent = "запустите атаку, чтобы проверить награду"; }
  else if (running) { $("ar-big").textContent = `${lanes.filter((x) => x.status === "done").length} / ${lanes.length}`; $("ar-big-l").textContent = now ? `идёт: ${(LANES[now.key] || [now.key])[0]}${now.status === "training" ? " учится атаковать" : ""}` : "идёт атака"; }
  else if (a.status === "done") { $("ar-big").textContent = `${s.exploits} / ${s.attacks}`; $("ar-big-l").textContent = s.exploits ? "атак нашли лазейку в награде" : "атак обошли защиту: награду не взломать, не найдя ошибок"; }
  else { $("ar-big").textContent = "—"; $("ar-big-l").textContent = a.status === "stopped" ? "атака остановлена" : "атака прервалась: " + (a.error || "ошибка"); }
  $("ar-hero").classList.toggle("bad", !!(a && a.status === "done" && s.exploits));
  $("ar-hero").classList.toggle("ok", !!(a && a.status === "done" && !s.exploits));
  $("ar-floor").textContent = f2(floor); $("ar-ceil").textContent = f2(ceil);
  $("ar-best").textContent = s.best_attack ? `${(LANES[s.best_attack] || [s.best_attack])[0]} ${f2(s.best_attack_reward)}` : "—";
  // lanes
  $("ar-lanes").replaceChildren(...lanes.map((ln) => {
    const [name, desc] = LANES[ln.key] || [ln.key, ""];
    const v = ln.reward, ref = ln.key === "silence" || ln.key === "reconcile";
    const track = el("span", { class: "ar-track", "aria-hidden": "true" }, el("i", { class: "ar-zero" }));
    if (floor != null) track.append(el("i", { class: "ar-floor", style: `left:${xpos(floor)}%` }));
    if (ceil != null) track.append(el("i", { class: "ar-ceil", style: `left:${xpos(ceil)}%` }));
    if (v != null) { const w = Math.abs(xpos(v) - 50); track.append(el("i", { class: "ar-bar " + (ln.verdict === "exploit" ? "x" : v >= 0 ? "pos" : "neg"), style: `left:${v >= 0 ? 50 : 50 - w}%;width:${w}%` })); }
    let badge;
    if (ln.status === "running" || ln.status === "training") { badge = el("span", { class: "badge lime" }, el("span", { class: "ascii-spin", "aria-hidden": "true" }), ln.status === "training" ? " учится" : " идёт"); }
    else if (ref) badge = el("span", { class: "badge dim" }, ln.key === "silence" ? "пол" : "потолок");
    else if (ln.verdict === "exploit") badge = el("span", { class: "badge pink" }, "ЛАЗЕЙКА");
    else if (ln.verdict === "held") badge = el("span", { class: "badge ok" }, "защищено");
    else badge = el("span", { class: "badge dim" }, ln.status === "queued" ? "в очереди" : "—");
    const replay = ln.run && ln.status === "done" ? el("a", { class: "ar-replay", href: "/runs.html#" + encodeURIComponent(ln.run) }, "повтор") : el("span", { class: "ar-replay" });
    return el("li", { class: "ar-lane" + (ref ? " ref" : "") + (ln.verdict === "exploit" ? " x" : "") },
      el("span", { class: "ar-n" }, el("b", {}, name), el("small", {}, desc)), track,
      el("span", { class: "ar-v mono " + (v > 0 ? "pos" : v < 0 ? "neg" : "") }, f2(v)), badge, replay);
  }));
  renderRL(lane("rl_attacker"), floor);
  $("ar-past").replaceChildren(...(arenas.length > 1 ? ["Прошлые атаки: ", ...arenas.slice(0, 6).flatMap((x, i) => [i ? " · " : "",
    el("a", { href: "#" + encodeURIComponent(x.id) }, when(x.started))])] : []));
}

function renderRL(ln, floor) {
  const host = $("ar-rl-chart"), pts = ln.curve || [];
  const W = Math.max(280, host.clientWidth || 520), H = 190, m = { l: 34, r: 10, t: 10, b: 22 };
  const n = Math.max(2, pts.length, 10);
  const X = (i) => m.l + (i / (n - 1)) * (W - m.l - m.r), Y = (v) => m.t + ((1 - v) / 2) * (H - m.t - m.b);
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, class: "ch", role: "img", "aria-label": "Награда RL-атакующего по итерациям" });
  for (const v of [1, 0, -1]) { svg("line", { x1: m.l, x2: W - m.r, y1: Y(v), y2: Y(v), class: v === 0 ? "zero" : "grid" }, s); svg("text", { x: m.l - 6, y: Y(v) + 4, class: "tick", "text-anchor": "end" }, s).textContent = v === 0 ? "0" : (v < 0 ? MINUS : "") + "1"; }
  if (floor != null) svg("line", { x1: m.l, x2: W - m.r, y1: Y(floor), y2: Y(floor), class: "floor" }, s);
  for (const [k, cls] of [["mean", "s2"], ["best", "s1"]]) if (pts.length) svg("polyline", { points: pts.map((p) => `${X(p.i).toFixed(1)},${Y(p[k]).toFixed(1)}`).join(" "), class: "gl " + cls }, s);
  host.replaceChildren(s);
  const st = ln.strategy, box = $("ar-rl-txt");
  if (!st) { box.replaceChildren(el("p", { class: "muted" }, ln.status === "training" ? "Атакующий учится: каждая итерация — 12 стратегий по 4 эпизода; лучшие продолжают." : "Появится после запуска: атакующий ищет стратегию, которая приносит награду без поиска ошибок.")); return; }
  const claims = st.pages.invoices ? st.claims : 0;
  const lines = [
    ["читает", `счета ${st.pages.invoices} стр. · платежи ${st.pages.payments} · книга ${st.pages.ledger}`],
    ["претензий", st.pages.invoices ? `${st.claims} × повтор ${st.repeat}${st.shotgun > 0.5 ? " · под всеми типами" : ""}` : "0 — не читает счета, заявлять нечего"],
    ["доказательств сверху", String(st.evidence_padding)],
    ["лучшее на обучении", f2(ln.train_best)], ["на тесте", f2(ln.reward)]];
  const verdict = ln.reward == null ? "" : claims === 0 || (floor != null && Math.abs(ln.reward - floor) < 0.02)
    ? "Вывод атакующего: лучший способ «взломать» награду — промолчать. Любая претензия без настоящей проверки стоит дороже." : ln.verdict === "exploit" ? "Атакующий нашёл стратегию выше пола — это лазейка, её нужно закрыть." : "Атакующий не смог подняться выше молчания.";
  box.replaceChildren(el("dl", { class: "ar-kv" }, ...lines.flatMap(([k, v]) => [el("dt", {}, k), el("dd", { class: "mono" }, v)])), el("p", { class: "ar-concl" }, verdict));
}

$("ar-go").addEventListener("click", async () => {
  const err = $("ar-err"); err.classList.add("hidden");
  $("ar-go").disabled = true;
  const { status, body } = await api("/api/arena", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  if (status === 200 && body && body.ok) { current = body.run; location.hash = body.run; load(); return; }
  $("ar-go").disabled = false;
  err.textContent = body && body.error && body.error.code === "busy" ? "Уже идёт другой запуск: дождитесь его окончания." : status === 0 ? "Сервер недоступен." : "Не удалось запустить: " + ((body && body.error && body.error.message) || status);
  err.classList.remove("hidden");
});
addEventListener("hashchange", () => { const id = decodeURIComponent(location.hash.slice(1)); if (id && id !== current) { current = id; load(); } });
let rz = 0;
addEventListener("resize", () => { cancelAnimationFrame(rz); rz = requestAnimationFrame(render); });
load();
