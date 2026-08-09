"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const asList = (v) => (Array.isArray(v) ? v : v ? [v] : []);
const clip = (t, n) => {
  const s = String(t ?? "").trim();
  if (!s) return "";
  const w = s.split(/\s+/);
  return w.length > n ? w.slice(0, n).join(" ").replace(/[,;:!?—–]+$/, "") + "…" : s;
};

const MOM_LVL = { accelerating: 4, hot: 4, rising: 3, stable: 2, shifting: 2, emerging: 3, new: 3, fading: 1, cold: 1 };
function sparkSvg(momentum) {
  const v = MOM_LVL[String(momentum || "").toLowerCase()] || 2;
  const pts = [8, v === 4 ? 2 : v === 3 ? 5 : v === 1 ? 14 : 10, v === 4 ? 14 : v === 3 ? 11 : v === 1 ? 5 : 8, v === 4 ? 10 : 9, v === 4 ? 6 : 7];
  return `<svg class="spark" viewBox="0 0 36 12" aria-label="${esc(String(momentum).toLowerCase())}">
    <polyline fill="none" stroke="currentColor" stroke-width="1.6" points="${pts.map((y, i) => i * 9 + "," + y).join(" ")}"/>
    <polygon points="32,${pts[3]} 32,12 0,12" fill="currentColor" fill-opacity=".08"/>
  </svg>`;
}
function shiftSvg(from, to, cls) {
  return `<svg class="shift-viz ${cls || ""}" viewBox="0 0 120 18" aria-hidden="true">
    <rect x="0" y="3" width="16" height="7" rx="2" class="s-from"/>
    <line x1="16" y1="6" x2="104" y2="6" class="s-line" stroke-dasharray="2 2"/>
    <polygon points="104,3 104,9 112,6" class="s-head"/>
    <rect x="104" y="3" width="16" height="7" rx="2" class="s-to"/>
  </svg>`;
}

const _q = new URLSearchParams(location.search);
let LANG = _q.get("lang") === "zh" ? "zh" : "en";
const L = (en, zh) => (LANG === "zh" && zh ? zh : en);
const pick = (en, zh) => (LANG === "zh" && zh ? zh : en);

const DIR_ZH = { rising: "升温", accelerating: "加速", hot: "高热", fading: "消退", shifting: "转向", emerging: "新晋", escalating: "升级", new: "新晋", stable: "持平", high: "高", medium: "中", critical: "关键" };
const EVID_ZH = { strong: "证据强", moderate: "证据中", emerging: "证据弱" };
const dirLabel = (d) => L((d || "flat").toUpperCase(), (DIR_ZH[d || "flat"] || "—"));

const state = { edition: null, desk: null };

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " -> " + r.status);
  return r.json();
}

/* ---------- boot ---------- */
async function boot() {
  setInterval(() => { $("#clock").textContent = new Date().toLocaleTimeString("en-GB"); }, 1000);
  const meta = await api("/api/meta");
  const sel = $("#edition-select");
  sel.innerHTML = "";
  meta.editions.forEach((e) => {
    const o = document.createElement("option");
    o.value = e.id;
    o.textContent = `${shortDate(e.start_date)} → ${shortDate(e.end_date)}`;
    sel.appendChild(o);
  });
  if (meta.latest) sel.value = meta.latest;
  state.edition = sel.value;
  $("#pipe-state").textContent = L(`pipeline: ${meta.pipeline?.stage ?? "?"} | ${meta.pipeline?.status ?? "?"}`,
    `管线: ${meta.pipeline?.stage ?? "?"} | ${meta.pipeline?.status ?? "?"}`);

  const desk = await api("/api/desk?edition=" + encodeURIComponent(state.edition));
  state.desk = desk;
  renderBrief();
  wire();
}

/* ---------- main render ---------- */
function renderBrief() {
  const d = state.desk;
  const dd = d.data || {};

  const qc = $("#qc-badge");
  const ok = d.qc && d.qc.status === "PASS";
  if (ok) { qc.textContent = "QC PASS"; qc.className = "qc pass"; }
  else { qc.textContent = "QC FAIL"; qc.className = "qc fail"; }

  let h = hero(d, dd);
  h += panel(L("At a glance", "本周聚焦"),
    L("ranked by editorial significance", "按编辑重要性排序"),
    (d.agenda || []).map((a, i) => briefCard(a, i)).join("") || empty());
  h += panel(L("Narrative shifts", "叙事转向"),
    L("what changed and why it matters", "本周故事如何转向、为何重要"),
    '<div class="narr-grid">' + (d.narratives || []).map(narrCard).join("") + "</div>");
  h += commsPanel(dd);
  h += questionsPanel(dd);
  h += exchangesPanel(dd);
  h += watchPanel(dd);
  h += evidenceLine(dd);
  $("#view").innerHTML = h;
}

function commsPanel(dd) {
  const boxes = asList(dd.comms_boxes);
  if (boxes.length) {
    const cards = boxes.map((b, i) => {
      const Q = asList(b.questions_likely_en);
      const E = asList(b.evidence_to_prepare_en);
      return `<details class="comms c${(i % 3) + 1}">
      <summary class="comms-head">
        <h3>${esc(pick(b.title_en, b.title_zh))}</h3>
        <span class="teaser">${esc(clip(pick(b.implication_en, b.implication_zh), 9))}</span>
      </summary>
      <p class="p implication">${esc(clip(pick(b.implication_en, b.implication_zh), 50))}</p>
      ${Q.length ? `<div class="chunk">${Q.map((q) => `<span class="chip">${esc(clip(q, 18))}</span>`).join("")}</div>` : ""}
      ${E.length ? `<div class="chunk ev">${E.map((e) => `<span class="chip">${esc(clip(e, 18))}</span>`).join("")}</div>` : ""}
      ${b.risky_en ? `<div class="risky">${esc(L("Watch your tone", "注意表述"))} — ${esc(clip(pick(b.risky_en, b.risky_zh), 40))}</div>` : ""}
    </details>`;
    }).join("");
    const body = `<div class="comms-grid">${cards}</div>`;
    return panel(L("Communications implications", "沟通启示"),
      L("general lessons for comms teams", "对各沟通团队的启示"), body);
  }
  const pr = dd.pr_counsel || {};
  if (!pr.risk_en && !pr.avoid_en) return "";
  const body = `<div class="comms-grid"><details class="comms c1">
    <summary class="comms-head"><h3>${esc(L("Narrative risk", "叙事风险"))}</h3></summary>
    <p class="p implication">${esc(clip(pick(pr.risk_en, pr.risk_zh), 50))}</p>
    <h3>${esc(L("Opportunity", "机遇"))}</h3><p class="p">${esc(clip(pick(pr.opportunity_en, pr.opportunity_zh), 50))}</p>
    <div class="risky">${esc(clip(pick(pr.avoid_en, pr.avoid_zh), 40))}</div>
  </details></div>`;
  return panel("Communications", L("general lessons", "公关提示"), body);
}

function questionsPanel(dd) {
  const groups = asList(dd.question_groups);
  if (groups.length) {
    const body = groups.map((g, i) => `<div class="qgroup">
      <h3>${esc(pick(_QC(g.category)?.en, _QC(g.category)?.zh) || esc(g.category || "—"))}</h3>
      <ul class="feed">${asList(g.questions_en).map((q) => `<li>${esc(q)}</li>`).join("")}</ul>
    </div>`).join("");
    const top = asList(dd.top_questions_next_week_en);
    const topBlock = top.length ? `<div class="ts-sub">${esc(L("Most likely to recur next week", "下周最可能继续追问"))}</div><ul class="feed">${top.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>` : "";
    return panel(L("Questions gaining traction", "媒体正在追问什么"), L("what anchors are asking", "媒体正在追问什么"), "", body + topBlock);
  }
  const rec = asList(dd.recurring_questions_en || []);
  if (!rec.length) return "";
  return panel(L("Recurring questions", "高频提问"), "",
    '<ul class="feed">' + rec.map((q) => `<li>${esc(typeof q === "string" ? q : q.text || q.q || JSON.stringify(q))}</li>`).join("") + "</ul>");
}

function _QC(cat) {
  return { policy_credibility: { en: "Policy credibility", zh: "政策公信力" },
           market_consequences: { en: "Market consequences", zh: "市场影响" },
           corporate_exposure: { en: "Corporate exposure", zh: "企业敞口" },
           narrative_durability: { en: "Narrative durability", zh: "叙事可持续性" } }[cat];
}

function exchangesPanel(dd) {
  const ex = asList(dd.media_exchanges);
  if (!ex.length) return "";
  const body = ex.map((x, i) => `<div class="exch">
    <h3>${esc(L("Questioning pattern", "提问模式") + " " + (i + 1))}${x.likely_to_recur === false ? "" : ` <span class="tag emerging">${esc(L("likely to recur", "很可能重演"))}</span>`}</h3>
    <div class="ts-sub">${esc(L("Media premise", "媒体预设"))}</div><p class="p">${esc(clip(pick(x.premise_en, x.premise_zh), 40))}</p>
    <div class="ts-sub">${esc(L("Response observed", "受访回应"))}</div><p class="p">${esc(clip(pick(x.response_en, x.response_zh), 40))}</p>
    <div class="ts-sub">${esc(L("Internal lesson", "内部启示"))}</div><p class="p">${esc(clip(pick(x.lesson_en, x.lesson_zh), 40))}</p>
  </div>`).join("");
  return panel(L("High-signal exchanges", "高信号对话"), L("media questioning patterns", "媒体提问模式"), body);
}

function watchPanel(dd) {
  const ws = asList(dd.watchpoints);
  if (!ws.length) return "";
  const body = ws.map((w, i) => `<details class="watchpoint w${(i % 4) + 1}">
    <summary class="wp-head">
      <span class="wp-alert">${String(i + 1).padStart(2, "0")}</span>
      <h3 class="wp-title">${esc(clip(pick(w.trigger_en, w.trigger_zh), 14))}</h3>
    </summary>
    <div class="wp-grid">
      ${pick(w.shift_en, w.shift_zh) ? `<div class="wp-cell"><b>${esc(L("Shift", "转向"))}</b><p>${esc(clip(pick(w.shift_en, w.shift_zh), 45))}</p></div>` : ""}
      ${pick(w.affected_en, w.affected_zh) ? `<div class="wp-cell"><b>${esc(L("Affected", "受影响"))}</b><p>${esc(clip(pick(w.affected_en, w.affected_zh), 30))}</p></div>` : ""}
      ${pick(w.priority_raises_en, w.priority_raises_zh) ? `<div class="wp-cell"><b>${esc(L("Why it matters", "为何重要"))}</b><p>${esc(clip(pick(w.priority_raises_en, w.priority_raises_zh), 30))}</p></div>` : ""}
    </div>
  </details>`).join("");
  return panel(L("Watch next", "下周观察"), L("what would change the story", "哪些信号将改写叙事"), body);
}

function evidenceLine(dd) {
  const es = asList(dd.evidence_statuses);
  if (!es.length) return "";
  const body = `<ul class="feed">${es.map((e) => `<li><b>${esc(e.section)}</b> — <span class="tag ${esc(e.status)}">${esc(e.status)}</span> ${e.note ? `<span class="s">· ${esc(e.note)}</span>` : ""}</li>`).join("")}</ul>`;
  return panel(L("Evidence", "证据核查"), L("confidence behind the analysis", "分析背后的置信度"), body);
}

function hero(d, dd) {
  const outlets = asList(dd.monitored_outlets).join(", ");
  const thesis = pick(dd.thesis_en, dd.thesis_zh) || pick(dd.week_summary_en, dd.week_summary_zh) || "—";
  const i = thesis.indexOf(". ");
  const headline = (i > 24 && i < 110 ? thesis.slice(0, i + 1) : thesis.slice(0, 100)).trim();
  const lead = (i > 24 && i < 110 ? thesis.slice(i + 2) : "").trim();
  return `<section class="hero">
    <p class="kicker">${L("INTERNATIONAL FINANCIAL MEDIA", "国际财经媒体")} · ${rangeLabel(d.start, d.end)}</p>
    <h2 class="hero-title">${esc(headline)}</h2>
    ${lead ? `<p class="lead">${esc(clip(lead, 45))}</p>` : ""}
    <div class="meta">
      <span>${L(d.status === "done" ? "published" : "draft", "已发布")}</span>
      ${d.qc && d.qc.status === "PASS" ? `<span>· QC<b> PASS</b></span>` : ""}
      <span>· ${L("week", "周期")} <b>${shortDate(d.start)} → ${shortDate(d.end)}</b></span>
      ${outlets ? `<span>· ${L("monitored", "监测")} <b>${esc(outlets)}</b></span>` : ""}
      ${dd.episode_count != null ? `<span>· ${L("episodes", "节目")} <b>${dd.episode_count}</b></span>` : ""}
    </div>
  </section>`;
}

const PRIO_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };
const MOM_ARROW = { accelerating: "↗", rising: "↑", stable: "→", fading: "↘" };
const EVID_DOTS = { strong: 3, moderate: 2, emerging: 1 };

function briefCard(a, i) {
  const prio = String(a.priority || "").toLowerCase();
  const momentum = String(a.momentum || "").toLowerCase();
  const evidence = String(a.evidence || "").toLowerCase();
  const cov = Number(a.coverage) || 0;
  const arrow = MOM_ARROW[momentum] || "→";
  const dots = "●".repeat(EVID_DOTS[evidence] || 0) + "○".repeat(3 - (EVID_DOTS[evidence] || 0));
  const prioLab = prio ? L(prio.toUpperCase(), DIR_ZH[prio] || prio.toUpperCase()) : "—";
  const off = prio in PRIO_ORDER ? PRIO_ORDER[prio] : 3;
  const sub = clip(pick(a.summary_en, a.summary_zh), 9);
  return `<details class="glance p${off}">
    <summary class="glance-head">
      <span class="no">${String(i + 1).padStart(2, "0")}</span>
      <span class="gt-title">${esc(clip(pick(a.title_en, a.title_zh), 10))}</span>
      <span class="lab prio-${esc(prio || "n")}">${esc(prioLab)}</span>
    </summary>
    <div class="glance-body">
      ${sub ? `<span class="gt-sub">${esc(sub)}</span>` : ""}
      <p class="tape">${esc(clip(pick(a.summary_en, a.summary_zh), 55))}</p>
      <div class="viz-row">
        <span class="lab mom ${momentum ? esc(momentum) : ""}"><s class="arr">${arrow}</s>${esc(dirLabel(momentum))}</span>
        ${evidence ? `<span class="lab ev-${esc(evidence)}">${dots}<i>${esc(L(evidence, EVID_ZH[evidence] || evidence))}</i></span>` : ""}
        ${cov ? `<span class="mini cov">${cov} ${esc(L("shows", "节目"))}</span>` : ""}
      </div>
    </div>
  </details>`;
}

function narrCard(n, i) {
  const why = pick(n.why_en, n.why_zh);
  const driver = pick(n.driver_en, n.driver_zh);
  const next = pick(n.next_test_en, n.next_test_zh);
  const from = pick(n.from_en, n.from_zh);
  const to = pick(n.to_en, n.to_zh);
  const shift = from || to ? `<div class="shift-viz-wrap">${shiftSvg(from || "—", to || "—", "nv")}</div>` : "";
  return `<details class="narr">
    <summary class="narr-head">
      <h3>${esc(pick(n.title_en, n.title_zh))}</h3>
      ${from || to ? `<span class="mini">${esc(L("shift", "转向"))}</span>` : ""}
    </summary>
    ${shift}
    <div class="narr-body">
      ${driver ? `<div class="dotline"><b class="dot" aria-hidden="true"></b><span class="tag">${esc(L("Driver", "驱动"))}</span><p>${esc(clip(driver, 40))}</p></div>` : ""}
      ${why ? `<div class="dotline"><b class="dot" aria-hidden="true"></b><span class="tag">${esc(L("Why", "为什么"))}</span><p>${esc(clip(why, 40))}</p></div>` : ""}
      ${next ? `<div class="dotline next"><b class="dot" aria-hidden="true"></b><span class="tag">${esc(L("Next test", "下步检验"))}</span><p>${esc(clip(next, 40))}</p></div>` : ""}
    </div>
   </details>`;
}

/* ---------- generic panel ---------- */
function panel(title, hint, body) {
  return `<div class="panel"><div class="panel-head"><h2>${esc(title)}</h2>${hint ? `<span class="hint">${esc(hint)}</span>` : ""}</div><div class="panel-body">${body}</div></div>`;
}
function empty() { return `<div class="empty">${L("empty", "暂无")}</div>`; }

/* ---------- date helpers ---------- */
function shortDate(ed) { return (ed || "").split("_to_")[0].slice(5); }
function rangeLabel(start, end) {
  const parse = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const a = parse(start), b = parse(end);
  if (!a || !b) return `${start} → ${end}`;
  if (LANG === "zh") return `${["日", "一", "二", "三", "四", "五", "六"][a.getDay()]} ${a.getMonth() + 1}/${a.getDate()} – ${["日", "一", "二", "三", "四", "五", "六"][b.getDay()]} ${b.getMonth() + 1}/${b.getDate()}`;
  const wd = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
  return `${wd[a.getDay()]} ${a.getDate()} ${MON[a.getMonth()]} – ${wd[b.getDay()]} ${b.getDate()} ${MON[b.getMonth()]} ${b.getFullYear()}`;
}
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/* ---------- search ---------- */
let deb = null;
$("#search").addEventListener("input", (e2) => {
  clearTimeout(deb);
  const q = e2.target.value.trim();
  if (q.length === 0) { renderBrief(); return; }
  if (q.length < 2) return;
  deb = setTimeout(() => doSearch(q), 380);
});
async function doSearch(q) {
  const r = await api("/api/search?q=" + encodeURIComponent(q));
  const body = r.results.slice(0, 40).map((x) =>
    `<div class="hit"><b>${esc(x.title || x.source_name || "")}</b> <span class="s">[${esc(x.kind)}] ${esc(x.source_name ?? "")} ${esc(x.pub_date ?? "")}</span><br>${esc(x.snip ?? "")}</div>`
  ).join("") || `<div class="empty">${L("no results", "无结果")}</div>`;
  $("#view").innerHTML = panel(L("Search", "检索") + ": " + q, L("press Esc to close", "按 Esc 关闭"), `<div class="hits">${body}</div>`);
}

/* ---------- events ---------- */
$("#edition-select").addEventListener("change", async (e2) => {
  state.edition = e2.target.value;
  state.desk = await api("/api/desk?edition=" + encodeURIComponent(state.edition));
  renderBrief();
});
document.querySelectorAll("#lang-en, #lang-zh").forEach((b) => {
  b.addEventListener("click", async () => {
    document.querySelectorAll("#lang-seg .chip").forEach((c) => c.classList.remove("active"));
    b.classList.add("active");
    LANG = b.id === "lang-zh" ? "zh" : "en";
      await boot();
  });
});
$("#export-btn").addEventListener("click", () => {
  window.open(`/export/${encodeURIComponent(state.edition)}/email`, "_blank");
});
document.addEventListener("keydown", (e2) => {
  if (e2.key === "Escape" && $("#search").value) {
    $("#search").value = "";
    renderBrief();
  }
});

/* ---------- SSE ---------- */
function wire() {
  if (location.search.includes("nossedom=1")) return;
  const es = new EventSource("/api/stream");
  es.addEventListener("pipeline", (ev) => {
    try {
      const p = JSON.parse(ev.data);
      $("#pipe-state").textContent = L(`pipeline: ${p.stage} | ${p.status} @ ${String(p.updated_at).slice(11, 19)}`,
        `管线: ${p.stage} | ${p.status} @ ${String(p.updated_at).slice(11, 19)}`);
      if (p.status === "done") boot();
    } catch (_) { /* ignore */ }
  });
}

boot().catch((e) => { $("#view").innerHTML = `<div class="loading">error: ${esc(e.message)}</div>`; });