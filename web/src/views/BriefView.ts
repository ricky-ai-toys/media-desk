import type { AgendaItem, Desk, DeskData, LeadLag, LifecycleTrack, Narrative, SourceHealth, TickerItem } from "../lib/api";
import { asList, esc } from "../lib/dom";
import { clip, ellipsis, shortDate } from "../lib/format";
import { DIR_ZH, EVID_ZH, dirLabel, L, pick, QCAT } from "../lib/i18n";
import { MOM_ARROW, shiftSvg } from "../lib/svg";

/* ---------------------------------- section scaffolding ---------------------------------- */

const sec = (label: string, hint: string, body: string): string => `
  <section class="sec">
    <header class="sec-head">
      <h2 class="sec-lab">${esc(label)}</h2>
      ${hint ? `<span class="sec-hint">${esc(hint)}</span>` : ""}
    </header>
    <div class="sec-body">${body}</div>
  </section>`;

const empty = (): string => `<div class="empty">${L("Empty", "暂无数据")}</div>`;

/* ---------------------------------- lead story ---------------------------------- */

function lead(d: Desk, dd: DeskData, lifecycle: LifecycleTrack[], prevEdition: string | null): string {
  const outlets = asList(dd.monitored_outlets).join(", ");
  const thesis = pick(dd.thesis_en, dd.thesis_zh) || pick(dd.week_summary_en, dd.week_summary_zh) || "—";
  const i = thesis.indexOf(". ");
  const headline = (i > 24 && i < 110 ? thesis.slice(0, i + 1) : ellipsis(thesis, 100)).trim();
  const body = (i > 24 && i < 110 ? thesis.slice(i + 2) : "").trim();
  return `
    <article class="lead">
      <p class="kicker">${L("International Financial Media · Weekly Brief", "国际财经媒体 · 每周简报")}</p>
      <h1 class="lead-h">${esc(headline)}</h1>
      ${body ? `<p class="lead-body">${esc(clip(body, 25))}</p>` : ""}
      <p class="lead-meta">
        <span>${L(d.status === "done" ? "Published" : "Draft", d.status === "done" ? "已发布" : "草稿")}</span>
        ${d.qc && d.qc.status === "PASS" ? `<span class="ok">QC PASS</span>` : ""}
        ${heroDelta(d, lifecycle, prevEdition)}
        <span>${L("Week", "周期")} <b>${shortDate(d.start)} → ${shortDate(d.end)}</b></span>
        ${dd.episode_count != null ? `<span>${L("Episodes", "节目")} <b>${dd.episode_count}</b></span>` : ""}
        ${outlets ? `<span>${L("Monitoring", "监测")} <b>${esc(outlets)}</b></span>` : ""}
      </p>
    </article>`;
}

/* ---------------------------------- lifecycle ---------------------------------- */

const normKey = (s: string): string => (s || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, "");

function lifecycleIndex(tracks: LifecycleTrack[]): Map<string, LifecycleTrack> {
  const m = new Map<string, LifecycleTrack>();
  for (const t of tracks || []) {
    const k = normKey(t.label || "");
    if (k) m.set(k, t);
  }
  return m;
}

function lcChip(track: LifecycleTrack | undefined): string {
  if (!track) return "";
  if (track.phase === "new") return `<span class="chip lc-new">${L("NEW", "新增")}</span>`;
  const d = track.rank_delta ?? 0;
  if (d > 0) return `<span class="chip lc-up">↑${d}</span>`;
  if (d < 0) return `<span class="chip lc-down">↓${Math.abs(d)}</span>`;
  return `<span class="chip lc-carried">${L("carried", "延续")}</span>`;
}

function heroDelta(desk: Desk, tracks: LifecycleTrack[], prevEdition: string | null): string {
  const id = desk.edition;
  const nw = tracks.filter((t) => t.first_seen === id).length;
  const carried = tracks.filter((t) => t.last_seen === id && t.first_seen !== id).length;
  const dropped = prevEdition ? tracks.filter((t) => t.last_seen === prevEdition).length : 0;
  if (!nw && !carried && !dropped) return "";
  const parts = [
    nw ? `${nw} ${L("new", "新增")}` : "",
    carried ? `${carried} ${L("carried", "延续")}` : "",
    dropped ? `${dropped} ${L("dropped", "淡出")}` : "",
  ].filter(Boolean);
  return parts.length ? `<span>${parts.join(" · ")}</span>` : "";
}

/* ---------------------------------- agenda: the tape ---------------------------------- */

const PRIO_CLS = { critical: "critical", high: "high", medium: "medium" } as const;
const PRIO_LAB = { critical: "CRITICAL", high: "HIGH", medium: "MEDIUM", low: "LOW" } as const;
const EVID_DOTS: Record<string, [number, string]> = { strong: [3, "●"], moderate: [2, "●"], emerging: [1, "●"] };

function tapeRow(a: AgendaItem, i: number, episodes: number, lc: Map<string, LifecycleTrack>): string {
  const prio = String(a.priority || "").toLowerCase();
  const momentum = String(a.momentum || "").toLowerCase();
  const evidence = String(a.evidence || "").toLowerCase();
  const arrow = MOM_ARROW[momentum] || "→";
  const dots = EVID_DOTS[evidence]?.[0] ?? 0;
  const dotStr = "●".repeat(dots) + "○".repeat(3 - dots);
  const title = ellipsis(pick(a.title_en, a.title_zh), 10) || "—";
  const sub = ellipsis(pick(a.summary_en, a.summary_zh), 22);
  const prioLab = prio ? L(PRIO_LAB[prio as keyof typeof PRIO_LAB] || prio.toUpperCase(), DIR_ZH[prio] || prio.toUpperCase()) : "";
  const cls = PRIO_CLS[prio as keyof typeof PRIO_CLS] || "";
  const firstOpen = i === 0 ? " open" : "";
  const track = lc.get(normKey(a.title_en || a.title_zh || ""));
  const cov = a.coverage != null && episodes ? `${a.coverage}/${episodes}` : a.coverage != null ? String(a.coverage) : "";
  const pct = a.coverage != null && episodes ? Math.min(100, Math.round((a.coverage / episodes) * 100)) : 0;
  const facts = [
    a.driver_en || a.driver_zh ? [L("Driver", "驱动"), pick(a.driver_en, a.driver_zh)] : null,
    a.next_test_en || a.next_test_zh ? [L("Next test", "下一步检验"), pick(a.next_test_en, a.next_test_zh)] : null,
    a.stakes_en || a.stakes_zh ? [L("Who's exposed", "谁受影响"), pick(a.stakes_en, a.stakes_zh)] : null,
  ].filter((f): f is [string, string] => !!f);
  return `
    <details class="glance ${cls}" style="--i:${i}"${firstOpen}>
      <summary class="g-row">
        <span class="g-no">${String(a.rank ?? i + 1).padStart(2, "0")}</span>
        <span class="g-main"><b class="g-title">${esc(title)}</b></span>
        <span class="g-mom" aria-label="${esc(dirLabel(momentum))}" title="${esc(dirLabel(momentum))}">${arrow}</span>
        ${lcChip(track)}
        ${prioLab ? `<span class="lab g-prio prio-${esc(prio || "n")}">${esc(prioLab)}</span>` : ""}
        <span class="g-cov">${esc(cov)}</span>
      </summary>
      <div class="cov-bar" aria-hidden="true"><i style="width:${pct}%"></i></div>
      <div class="g-body">
        ${sub ? `<p class="g-sub">${esc(sub)}</p>` : ""}
        ${facts.length ? `<div class="facts-grid">${facts.map(([k, v]) => `<div class="fact"><div class="fact-k">${esc(k)}</div><div class="fact-v">${esc(ellipsis(v, 10))}</div></div>`).join("")}</div>` : ""}
        ${evidence ? `<div class="fact-k">${esc(L("Evidence", "证据"))} <span class="g-ev">${dotStr}</span></div>` : ""}
      </div>
    </details>`;
}

function tapeSection(agenda: AgendaItem[], episodeCount: number, lc: Map<string, LifecycleTrack>): string {
  if (!agenda.length) return sec(L("At a glance", "本周聚焦"), L("ranked by editorial significance", "按编辑重要性排序"), empty());
  const rows = agenda
    .slice()
    .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99))
    .map((a, i) => tapeRow(a, i, episodeCount, lc))
    .join("");
  const head = `
    <div class="tape-head" aria-hidden="true">
      <span class="th th-no">#</span>
      <span class="th th-topic">${esc(L("Topic", "议题"))}</span>
      <span class="th th-mom">${esc(L("Mom", "动向"))}</span>
      <span class="th th-lc">${esc(L("Track", "轨迹"))}</span>
      <span class="th th-prio">${esc(L("Pri", "优先级"))}</span>
      <span class="th th-cov">${esc(L("Cov", "覆盖"))}</span>
    </div>`;
  return sec(L("The week's tape", "本周议题"), L("ranked · click a row for the story", "按重要性排序 · 点击查看详情"), `<div class="glist">${head}${rows}</div>`);
}

/* ---------------------------------- week ahead ---------------------------------- */

function weekAheadPanel(dd: DeskData): string {
  const events = asList(dd.week_ahead_events);
  if (!events.length) return "";
  const rows = events
    .map((e) => {
      const d = (e.date || "").slice(5).replace("-", "/");
      const [ev, why] = pick(e.event_en, e.event_zh).split(/\.|\n/, 2);
      const w = e.why_en || e.why_zh;
      return `
      <div class="wk-row">
        <span class="wk-d">${esc(d)}</span>
        <span class="wk-e">${esc(ev)}${w ? ` — <span class="s">${esc(ellipsis(w, 10))}</span>` : ""}</span>
      </div>`;
    })
    .join("");
  return sec(L("Week ahead", "下周展望"), L("dates to watch", "关键日期"), `<div class="wk-cal">${rows}</div>`);
}

/* ---------------------------------- narratives ---------------------------------- */

function narrativeCard(n: Narrative): string {
  const from = pick(n.from_en, n.from_zh);
  const to = pick(n.to_en, n.to_zh);
  const shift = from || to ? `<div class="shift-viz-wrap">${shiftSvg(from || "—", to || "—")}</div>` : "";
  const rows = [
    [L("Driver", "驱动"), pick(n.driver_en, n.driver_zh)],
    [L("Why", "为什么"), pick(n.why_en, n.why_zh)],
  ] as const;
  const body = rows
    .filter(([, v]) => v)
    .map(([k, v]) => `<div class="dotline"><b class="dot" aria-hidden="true"></b><span class="tag">${esc(k)}</span><p>${esc(clip(v, 22))}</p></div>`)
    .join("");
  const next = pick(n.next_test_en, n.next_test_zh);
  return `
    <details class="narr">
      <summary class="narr-head">
        <b class="narr-title">${esc(pick(n.title_en, n.title_zh) || "—")}</b>
        ${from || to ? `<span class="narr-mini">${L("Shift", "转向")}</span>` : ""}
      </summary>
      ${shift}
      <div class="narr-body">
        ${body}
        ${next ? `<div class="dotline next"><b class="dot" aria-hidden="true"></b><span class="tag">${esc(L("Next test", "下一步检验"))}</span><p>${esc(clip(next, 22))}</p></div>` : ""}
      </div>
    </details>`;
}

/* ---------------------------------- comms cards ---------------------------------- */

function commsCards(dd: DeskData): string {
  const boxes = asList(dd.comms_boxes);
  if (boxes.length) {
    const cards = boxes
      .map((b, i) => {
        const Q = asList(b.questions_likely_en);
        const E = asList(b.evidence_to_prepare_en);
        return `
        <details class="comms c${(i % 3) + 1}">
          <summary class="comms-head">
            <b class="comms-title">${esc(pick(b.title_en, b.title_zh) || "—")}</b>
            <span class="comms-teaser">${esc(clip(pick(b.implication_en, b.implication_zh), 9))}</span>
          </summary>
          ${(pick(b.implication_en, b.implication_zh) || "").split(/\s+/).length > 9
            ? `<p class="implication">${esc(clip(pick(b.implication_en, b.implication_zh), 14))}</p>` : ""}
          ${Q.length ? `<span class="chunk-label" aria-hidden="true"></span><div class="chunk">${Q.map((q) => `<span class="chip">${esc(clip(q, 10))}</span>`).join("")}</div>` : ""}
          ${E.length ? `<span class="chunk-label ev" aria-hidden="true"></span><div class="chunk ev">${E.map((e) => `<span class="chip">${esc(clip(e, 10))}</span>`).join("")}</div>` : ""}
          ${b.risky_en ? `<div class="risky">${esc(L("Watch your tone", "注意表述"))} — ${esc(clip(pick(b.risky_en, b.risky_zh), 40))}</div>` : ""}
        </details>`;
      })
      .join("");
    return sec(L("Communications implications", "沟通启示"), L("general lessons for comms teams", "供沟通团队参考"), `<div class="comms-grid">${cards}</div>`);
  }
  const pr = dd.pr_counsel;
  if (!pr || (!pr.risk_en && !pr.avoid_en)) return "";
  return sec(
    L("Communications", "沟通启示"),
    L("general lessons", "公关提示"),
    `<div class="comms-grid"><details class="comms c1">
      <summary class="comms-head">
        <b class="comms-title">${esc(L("Narrative risk", "叙事风险"))}</b>
        <span class="comms-teaser">${esc(clip(pick(pr.risk_en, pr.risk_zh), 9))}</span>
      </summary>
      ${pr.risk_en ? `<p class="implication">${esc(clip(pick(pr.risk_en, pr.risk_zh), 50))}</p>` : ""}
      ${pr.opportunity_en ? `<span class="chunk-label">${esc(L("Opportunity", "机遇"))}</span><p class="implication">${esc(clip(pick(pr.opportunity_en, pr.opportunity_zh), 40))}</p>` : ""}
      ${pr.avoid_en ? `<div class="risky">${esc(clip(pick(pr.avoid_en, pr.avoid_zh), 40))}</div>` : ""}
    </details></div>`,
  );
}

/* ---------------------------------- questions ---------------------------------- */

function questionsPanel(dd: DeskData): string {
  const groups = asList(dd.question_groups);
  if (groups.length) {
    const body = groups
      .map((g) => {
        const qc = QCAT[g.category || ""];
        const label = qc ? pick(qc.en, qc.zh) : g.category || "—";
        const qs = asList(g.questions_en);
        return `
        <div class="qgroup">
          <h3>${esc(label)}</h3>
          <ul class="feed">${qs.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>
        </div>`;
      })
      .join("");
    const top = asList(dd.top_questions_next_week_en);
    const topBlock = top.length
      ? `<div class="ts-sub amber">${esc(L("Most likely to recur next week", "下周最可能继续追问"))}</div><ul class="feed">${top.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>`
      : "";
    return sec(L("Questions gaining traction", "媒体正在追问什么"), L("what anchors are asking", "主播与记者在追问什么"), body + topBlock);
  }
  const rec = asList(dd.recurring_questions_en || []);
  if (!rec.length) return "";
  return sec(
    L("Recurring questions", "高频提问"),
    "",
    `<ul class="feed">${rec.map((q) => `<li>${esc(typeof q === "string" ? q : q.text || q.q || JSON.stringify(q))}</li>`).join("")}</ul>`,
  );
}

/* ---------------------------------- exchanges ---------------------------------- */

function exchangesPanel(dd: DeskData): string {
  const ex = asList(dd.media_exchanges);
  if (!ex.length) return "";
  const body = ex
    .map((x, i) => {
      const recur = x.likely_to_recur === false ? "" : `<span class="tag emerging">${esc(L("likely to recur", "很可能重演"))}</span>`;
      const cells = [
        [L("Media premise", "媒体预设"), pick(x.premise_en, x.premise_zh)],
        [L("Response observed", "受访回应"), pick(x.response_en, x.response_zh)],
        [L("Internal lesson", "内部启示"), pick(x.lesson_en, x.lesson_zh)],
      ] as const;
      return `
        <div class="exch">
          <h3>${esc(L("Questioning pattern", "提问模式"))} ${i + 1} ${recur}</h3>
          ${cells.map(([k, v]) => (v ? `<div><div class="ts-sub">${esc(k)}</div><p class="p">${esc(clip(v, 10))}</p></div>` : "")).join("")}
        </div>`;
    })
    .join("");
  return sec(L("High-signal exchanges", "值得关注的对谈"), L("media questioning patterns", "媒体提问模式"), body);
}

/* ---------------------------------- watchpoints ---------------------------------- */

function watchPanel(dd: DeskData): string {
  const ws = asList(dd.watchpoints);
  if (!ws.length) return "";
  const body = ws
    .map((w, i) => {
      const cells = [
        [L("Shift", "转向"), pick(w.shift_en, w.shift_zh)],
        [L("Affected", "受影响"), pick(w.affected_en, w.affected_zh)],
        [L("Why it matters", "为何重要"), pick(w.priority_raises_en, w.priority_raises_zh)],
      ] as const;
      return `
        <details class="wp">
          <summary class="wp-head">
            <span class="wp-alert">${String(i + 1).padStart(2, "0")}</span>
            <b class="wp-title">${esc(clip(pick(w.trigger_en, w.trigger_zh), 14))}</b>
          </summary>
          <div class="wp-grid">
            ${cells.map(([k, v]) => (v ? `<div class="wp-cell"><b>${esc(k)}</b><p>${esc(clip(v, 14))}</p></div>` : "")).join("")}
          </div>
        </details>`;
    })
    .join("");
  return sec(L("Watch next", "下周观察"), L("what would change the story", "哪些信号将改写叙事"), body);
}

/* ---------------------------------- evidence ---------------------------------- */

function evidencePanel(dd: DeskData): string {
  const es = asList(dd.evidence_statuses);
  if (!es.length) return "";
  const body = es
    .map((e) => `<div class="list-row"><b>${esc(e.section || "—")}</b> <span class="tag ev-${esc(String(e.status || "emerging").toLowerCase())}">${esc(e.status || "—")}</span>${e.note ? ` <span class="s">· ${esc(e.note)}</span>` : ""}</div>`)
    .join("");
  return sec(L("Evidence", "证据核查"), L("confidence behind the analysis", "分析背后的置信度"), body);
}

/* ---------------------------------- rail ---------------------------------- */

const TONE_CLS: Record<string, string> = {
  challenging: "tone-hard",
  evasive: "tone-soft",
  supportive: "tone-ok",
  neutral: "tone-neutral",
};

function tickerBlock(ticker: TickerItem[]): string {
  if (!ticker.length) return "";
  const t = ticker.slice(0, 7);
  const body = t
    .map((x) => {
      const d = (x.date || "").slice(5);
      const tone = x.tone ? TONE_CLS[x.tone.toLowerCase()] || "tone-neutral" : "tone-neutral";
      const paraphrase = x.verified === false
        ? ` <span class="tag emerging">${esc(L("paraphrase", "转述"))}</span>` : "";
      return `
      <div class="tick">
        <span class="s">${d ? esc(d) : ""}${x.show ? ` · ${esc(x.show)}` : ""} <i class="tone-dot ${tone}" title="${esc(x.tone)}"></i>${paraphrase}</span>
        <p>${esc(clip(x.question, 14))}</p>
      </div>`;
    })
    .join("");
  return `<div class="rail-sec"><header class="sec-head"><h2 class="sec-lab">${esc(L("On the tape", "采访动态"))}</h2></header><div>${body}</div></div>`;
}

function leadLagBlock(ll: LeadLag[]): string {
  if (!ll.length) return "";
  const rows = ll
    .slice(0, 6)
    .map((x) => {
      const first = x.tv_first && (!x.wire_first || x.tv_first <= x.wire_first) ? "TV" : x.wire_first ? "Wire" : null;
      return `
      <div class="tick">
        <p>${esc(clip(x.topic, 8))}</p>
        <span class="s">TV ${x.tv_count ?? 0} · wire ${x.wire_count ?? 0}${first ? ` · ${esc(L(first + " first", first === "TV" ? "电视先行" : "快讯先行"))}` : ""}</span>
      </div>`;
    })
    .join("");
  return `<div class="rail-sec"><header class="sec-head"><h2 class="sec-lab">${esc(L("Wire vs TV", "快讯与电视"))}</h2></header><div>${rows}</div></div>`;
}

function pipelineBlock(sources: SourceHealth[]): string {
  if (!sources.length) return "";
  const rows = sources
    .map((s) => {
      const state = s.last_ok === 1 ? "ok" : s.last_ok === 0 ? "down" : s.last_run ? "ok" : "pending";
      const when = s.last_run ? s.last_run.slice(0, 10) : L("never", "从未运行");
      return `
      <li>
        <span class="dot ${state}" aria-hidden="true"></span>
        <span class="dots"><b class="num">${s.articles}</b><i class="unit">${L("art", "篇")}</i> · ${esc(when)}</span>
      </li>`;
    })
    .join("");
  return `<div class="rail-sec"><header class="sec-head"><h2 class="sec-lab">${esc(L("Source pipeline", "信源管线"))}</h2></header><ul class="dot-list">${rows}</ul></div>`;
}

/* ---------------------------------- assemble ---------------------------------- */

export function renderBrief(desk: Desk, sources: SourceHealth[] = [], lifecycle: LifecycleTrack[] = [], prevEdition: string | null = null): string {
  const dd = desk.data || ({} as DeskData);
  const lc = lifecycleIndex(lifecycle);
  const main =
    lead(desk, dd, lifecycle, prevEdition) +
    tapeSection(desk.agenda || [], dd.episode_count ?? 0, lc) +
    weekAheadPanel(dd) +
    sec(L("Narrative shifts", "叙事转向"), L("what changed", "叙事如何转向"), `<div class="narr-grid">${(desk.narratives || []).map(narrativeCard).join("")}</div>`) +
    commsCards(dd) +
    `<div class="pair">
      ${questionsPanel(dd)}
      ${exchangesPanel(dd)}
    </div>` +
    `<div class="pair">
      ${watchPanel(dd)}
      ${evidencePanel(dd)}
    </div>`;
  const rail =
    tickerBlock(asList(desk.ticker)) +
    leadLagBlock(asList<LeadLag>(desk.framing?.lead_lag)) +
    pipelineBlock(sources);
  return `
    <div class="grid">
      <div class="col-main">${main}</div>
      ${rail ? `<aside class="rail">${rail}</aside>` : ""}
    </div>`;
}