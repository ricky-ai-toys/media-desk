import type { AgendaItem, Desk, DeskData, EditionMeta, InterviewGroup, LeadLag, LifecycleTrack, Narrative, PrCounsel, QcCheck, SourceHealth, TickerItem } from "../lib/api";
import { asList, esc } from "../lib/dom";
import { clip, ellipsis, shortDate } from "../lib/format";
import { DIR_ZH, EVID_ZH, dirLabel, getLang, L, pick, QCAT } from "../lib/i18n";
import { MOM_ARROW } from "../lib/svg";

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
  const thesis = pick(dd.thesis_en, dd.thesis_zh) || pick(dd.week_summary_en, dd.week_summary_zh) || "—";
  // Headline = first sentence (or first em-dash clause for run-on leads),
  // body = the remainder — the full thesis must stay on the page.
  // EN punctuation must be followed by whitespace (avoids splitting "U.S.");
  // CJK sentence marks stand alone.
  const sent = thesis.match(/^([\s\S]{0,240}?(?:[.!?](?:\s+|$)|[。！？；]))/);
  const dash = !sent ? thesis.match(/^([\s\S]{0,180}?)\s*[—–]\s*([\s\S]+)$/) : null;
  const headline = (sent ? sent[1] ?? thesis : dash ? dash[1] ?? thesis : "").trim() || ellipsis(thesis, 150);
  const rest = (sent ? thesis.slice((sent[0] ?? "").length) : dash ? dash[2] ?? "" : "").trim();
  const body = rest ? clip(rest, 90) : "";
  return `
    <article class="lead">
      <p class="kicker">${esc(L("International Financial Media · Weekly Brief", "国际财经媒体 · 每周简报"))}</p>
      <h1 class="lead-h">${esc(headline)}</h1>
      ${body ? `<p class="lead-body">${esc(body)}</p>` : ""}
      <p class="lead-meta">
        <span>${L(d.status === "done" ? "Published" : "Draft", d.status === "done" ? "已发布" : "草稿")}</span>
        ${d.qc && d.qc.status === "PASS" ? `<span class="ok">QC PASS</span>` : ""}
        ${heroDelta(d, lifecycle, prevEdition)}
        <span>${L("Week", "周期")} <b>${shortDate(d.start)} → ${shortDate(d.end)}</b></span>
        ${dd.episode_count != null ? `<span>${L("Episodes", "节目")} <b>${dd.episode_count}</b></span>` : ""}
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
    nw ? `${nw} ${L("topics new", "个新议题")}` : "",
    carried ? `${carried} ${L("carried over", "个延续")}` : "",
    dropped ? `${dropped} ${L("dropped", "个淡出")}` : "",
  ].filter(Boolean);
  const tip = L("Topic lifecycle vs the previous edition", "与上一期相比的议题轨迹");
  return parts.length ? `<span title="${esc(tip)}">${parts.join(" · ")}</span>` : "";
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
  // Full title — truncation hid the actual story; let it wrap instead.
  const title = pick(a.title_en, a.title_zh) || "—";
  const sub = ellipsis(pick(a.summary_en, a.summary_zh), 160);
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
  ].filter((f): f is [string, string] => !!f);  return `
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
        ${facts.length ? `<div class="facts-grid">${facts.map(([k, v]) => `<div class="fact"><div class="fact-k">${esc(k)}</div><div class="fact-v">${esc(clip(v, 18))}</div></div>`).join("")}</div>` : !sub ? `<p class="g-sub s">${esc(L("Detail cells not generated for this item.", "该条目未生成详情格。"))}</p>` : ""}
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
  if (!events.length) {
    return sec(
      L("Week ahead", "下周展望"),
      L("dates to watch", "关键日期"),
      `<div class="empty">${L("Week-ahead calendar was not generated for this edition.", "本期未生成下周前瞻日历。")}</div>`,
    );
  }
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

/* ---------------------------------- qc notice ---------------------------------- */

const QC_HINT: Record<string, { en: string; zh: string }> = {
  topic_facts_present: {
    en: "agenda-topic fact cells (driver / next test / exposure) are missing",
    zh: "议题事实格（驱动 / 下一步检验 / 谁受影响）缺失",
  },
  week_ahead_present: { en: "the week-ahead calendar section is missing", zh: "下周前瞻板块缺失" },
};

function qcSummaryText(blocks: number, total: number): string {
  if (!blocks) return L(`Editorial QC flagged ${total} note(s) — click to expand`, `编辑质检备注 ${total} 条——点击展开`);
  return L(`QC blocked ${blocks} item(s), ${total - blocks} note(s) — click to expand`, `质检阻断 ${blocks} 项、备注 ${total - blocks} 条——点击展开`);
}

function qcDetails(d: Desk): string {
  const qc = d.qc;
  if (!qc || qc.status === "PASS") return "";
  const blocks = asList(qc.blocks).map(String);
  const failing = asList<QcCheck>(qc.checks).filter((c) => c && c.pass === false && c.check);
  if (!blocks.length && !failing.length) return "";
  const items = blocks
    .map((b) => {
      const h = QC_HINT[b];
      const text = h ? L(h.en, h.zh) : b.replace(/_/g, " ");
      return `<li>${esc(text)}</li>`;
    })
    .join("");
  const details = failing.length
    ? `<div class="ts-sub">${esc(L("All flagged checks", "全部标记项"))}</div>
       <ul class="feed muted">${failing.map((c) => `<li><b>${esc(String(c.check).replace(/_/g, " "))}</b>${c.detail ? ` — ${esc(c.detail)}` : ""}</li>`).join("")}</ul>`
    : "";
  return `
    <details class="qc-details">
      <summary>
        <span class="qc fail">QC FAIL</span>
        <b>${esc(qcSummaryText(blocks.length, blocks.length + failing.length))}</b>
        <i class="qc-caret" aria-hidden="true">▸</i>
      </summary>
      <ul>${items}</ul>
      ${details}
    </details>`;
}

/* ---------------------------------- narratives ---------------------------------- */

function narrativeCard(n: Narrative): string {
  const from = pick(n.from_en, n.from_zh);
  const to = pick(n.to_en, n.to_zh);
  // Textual WAS → NOW flow instead of the old two-box diagram: the frames
  // themselves are the content, boxes just got in the way.
  const shift = from || to ? `
    <div class="shift-flow">
      ${from ? `<div class="sf-row past"><span class="sf-tag">${esc(L("WAS", "原来"))}</span><p>${esc(clip(from, 12))}</p></div>` : ""}
      ${to ? `<div class="sf-arrow" aria-hidden="true">↓</div>
      <div class="sf-row now"><span class="sf-tag">${esc(L("NOW", "现在"))}</span><p>${esc(clip(to, 12))}</p></div>` : ""}
    </div>` : "";
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
  if (!boxes.length) return "";
  const zh = getLang() === "zh";
  const cards = boxes
    .map((b, i) => {
      const impl = pick(b.implication_en, b.implication_zh);
      const Q = asList(zh && b.questions_likely_zh?.length ? b.questions_likely_zh : b.questions_likely_en);
      const E = asList(zh && b.evidence_to_prepare_zh?.length ? b.evidence_to_prepare_zh : b.evidence_to_prepare_en);
      // CJK prose has no spaces — judge length by characters in zh mode.
      const longImpl = zh ? impl.length > 42 : impl.split(/\s+/).length > 9;
      return `
      <details class="comms c${(i % 3) + 1}">
        <summary class="comms-head">
          <b class="comms-title">${esc(pick(b.title_en, b.title_zh) || "—")}</b>
          <span class="comms-teaser">${esc(zh ? ellipsis(impl, 42) : clip(impl, 9))}</span>
        </summary>
        ${longImpl ? `<p class="implication">${esc(zh ? ellipsis(impl, 160) : clip(impl, 14))}</p>` : ""}
        ${Q.length ? `<span class="chunk-label" aria-hidden="true"></span><div class="chunk">${Q.map((q) => `<span class="chip">${esc(clip(q, 10))}</span>`).join("")}</div>` : ""}
        ${E.length ? `<span class="chunk-label ev" aria-hidden="true"></span><div class="chunk ev">${E.map((e) => `<span class="chip">${esc(clip(e, 10))}</span>`).join("")}</div>` : ""}
        ${(b.risky_en || b.risky_zh) ? `<div class="risky">${esc(L("Watch your tone", "注意表述"))} — ${esc(clip(pick(b.risky_en, b.risky_zh), 40))}</div>` : ""}
      </details>`;
    })
    .join("");
  return sec(L("Communications implications", "沟通启示"), L("general lessons for comms teams", "供沟通团队参考"), `<div class="comms-grid">${cards}</div>`);
}

/* ---------------------------------- interview prep & pr counsel ---------------------------------- */

function interviewsBody(groups: InterviewGroup[]): string {
  return groups
    .map((g) => {
      const qs = asList(getLang() === "zh" && g.questions_zh?.length ? g.questions_zh : g.questions_en);
      const role = pick(g.role_en, g.role_zh);
      return `
      <div class="qgroup">
        <h3>${esc(pick(g.title_en, g.title_zh) || "—")}</h3>
        ${role ? `<div class="ts-sub">${esc(role)}</div>` : ""}
        <ul class="feed">${qs.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>
      </div>`;
    })
    .join("");
}

function prCounselBody(pr: PrCounsel): string {
  const rows = [
    [L("Risk", "风险"), pick(pr.risk_en, pr.risk_zh)],
    [L("Opportunity", "机遇"), pick(pr.opportunity_en, pr.opportunity_zh)],
    [L("Prepare", "准备"), pick(pr.prepare_en, pr.prepare_zh)],
    [L("Avoid", "避免"), pick(pr.avoid_en, pr.avoid_zh)],
  ] as const;
  return rows
    .filter(([, v]) => v)
    .map(([k, v]) => `<div class="dotline"><b class="dot" aria-hidden="true"></b><span class="tag">${esc(k)}</span><p>${esc(clip(v, 40))}</p></div>`)
    .join("");
}

/** One collapsed reference group near the foot of the page: everything a
 *  comms team needs before facing cameras, without pushing analysis up. */
function prepGroup(dd: DeskData, groups: InterviewGroup[] | undefined): string {
  const gs = asList(groups);
  const pr = dd.pr_counsel;
  const hasPr = !!(pr && (pick(pr.risk_en, pr.risk_zh) || pick(pr.opportunity_en, pr.opportunity_zh) || pick(pr.prepare_en, pr.prepare_zh) || pick(pr.avoid_en, pr.avoid_zh)));
  if (!gs.length && !hasPr) return "";
  const parts: string[] = [];
  if (gs.length) parts.push(`<div class="prep-sub"><div class="ts-sub">${esc(L("Interview prep — expected guests & lines of questioning", "采访准备——预期嘉宾与提问方向"))}</div>${interviewsBody(gs)}</div>`);
  if (hasPr) parts.push(`<div class="prep-sub"><div class="ts-sub">${esc(L("PR counsel — standing counsel for comms teams", "公关建议——沟通团队常备提示"))}</div>${prCounselBody(pr as PrCounsel)}</div>`);
  const count = gs.length ? `${gs.length} ${L(gs.length === 1 ? "guest group" : "guest groups", "组嘉宾")}${hasPr ? ` · ${esc(L("counsel", "建议"))}` : ""}` : esc(L("standing counsel", "常备提示"));
  return `
    <details class="prep-group">
      <summary>
        <b>${esc(L("Interview prep & PR counsel", "采访准备与公关建议"))}</b>
        <span class="s">${count}</span>
        <i class="qc-caret" aria-hidden="true">▸</i>
      </summary>
      <div class="prep-body">${parts.join("")}</div>
    </details>`;
}

/* ---------------------------------- questions ---------------------------------- */

function questionsPanel(dd: DeskData): string {
  const groups = asList(dd.question_groups);
  if (groups.length) {
    const zh = getLang() === "zh";
    const body = groups
      .map((g) => {
        const qc = QCAT[g.category || ""];
        const label = qc ? pick(qc.en, qc.zh) : g.category || "—";
        const qs = asList(zh && g.questions_zh?.length ? g.questions_zh : g.questions_en);
        return `
        <div class="qgroup">
          <h3>${esc(label)}</h3>
          <ul class="feed">${qs.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>
        </div>`;
      })
      .join("");
    const top = asList(zh && dd.top_questions_next_week_zh?.length ? dd.top_questions_next_week_zh : dd.top_questions_next_week_en);
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

function watchBody(dd: DeskData): string {
  const ws = asList(dd.watchpoints);
  return ws
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
}

/** Rail placement: signals that could rewrite the story live beside the tape ticker. */
function watchRailBlock(dd: DeskData): string {
  if (!asList(dd.watchpoints).length) return "";
  return `<div class="rail-sec"><header class="sec-head"><h2 class="sec-lab">${esc(L("Watch next", "下周观察"))}</h2></header><div>${watchBody(dd)}</div></div>`;
}

/* ---------------------------------- evidence ---------------------------------- */

function evidencePanel(dd: DeskData): string {
  const es = asList(dd.evidence_statuses);
  const warns = asList(dd.warnings);
  if (!es.length && !warns.length) return "";
  const body = es
    .map((e) => `<div class="list-row"><b>${esc(e.section || "—")}</b> <span class="tag ev-${esc(String(e.status || "emerging").toLowerCase())}">${esc(e.status || "—")}</span>${e.note ? ` <span class="s">· ${esc(e.note)}</span>` : ""}</div>`)
    .join("");
  const notes = warns.length
    ? `<div class="ts-sub amber">${esc(L("Editorial notes", "编者注"))}</div><ul class="feed muted">${warns.map((w) => `<li>${esc(typeof w === "string" ? w : JSON.stringify(w))}</li>`).join("")}</ul>`
    : "";
  return sec(L("Evidence", "证据核查"), L("confidence behind the analysis", "分析背后的置信度"), body + notes);
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
      // Attribution over provenance: who was on the hot seat matters more
      // than which programme carried it.
      const who = [x.guest, x.org].filter(Boolean).map(String);
      return `
      <div class="tick">
        <span class="s">${d ? esc(d) : ""} <i class="tone-dot ${tone}" title="${esc(x.tone)}"></i>${paraphrase}</span>
        <p>${esc(clip(x.question, 14))}</p>
        ${who.length ? `<span class="who">— ${esc(who.join(", "))}</span>` : ""}
      </div>`;
    })
    .join("");
  return `<div class="rail-sec"><header class="sec-head"><h2 class="sec-lab">${esc(L("On the tape", "采访动态"))}</h2></header><div>${body}</div></div>`;
}

/** Full-width comparison in the main column: last week's airwaves (muted)
 *  beside this week's (ink, red risers). Each pane degrades independently;
 *  the section falls back to a note only if both images fail. */
function wordCloudSection(edition: string): string {
  if (!edition) return "";
  const pane = (which: "prev" | "this", label: string) => `
    <figure class="wc-pane wc-pending ${which}">
      <figcaption class="wc-lab">${esc(label)}</figcaption>
      <img src="/api/wordcloud/${encodeURIComponent(edition)}?week=${which}" alt="${esc(L(`Word cloud of ${which === "prev" ? "last" : "this"} week's most-used transcript terms`, `周转写高频词云（${which === "prev" ? "上周" : "本周"}）`))}"
           onload="this.closest('.wc-pane').classList.remove('wc-pending')"
           onerror="var p=this.closest('.wc-pane');p.classList.add('wc-dead');var s=p.closest('.sec');if(s&&!s.querySelector('.wc-pane:not(.wc-dead)'))s.classList.add('wc-none')">
    </figure>`;
  return sec(
    L("This week vs last", "本周对照词云"),
    L("what dominated the airwaves — red marks this week's risers", "电波中的高频词——红色为本周上升词汇"),
    `<div class="wc-grid">${pane("prev", L("Last week", "上周"))}${pane("this", L("This week", "本周"))}</div>
     <div class="wc-fallback s">${esc(L("Word clouds unavailable for this edition.", "本期词云暂不可用。"))}</div>`,
  );
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

function watchlistBlock(dd: DeskData): string {
  const zh = getLang() === "zh";
  const items = asList(zh && dd.watchlist_zh?.length ? dd.watchlist_zh : dd.watchlist_en);
  if (!items.length) return "";
  const rows = items
    .slice(0, 7)
    .map((w) => `<div class="tick"><p>${esc(clip(typeof w === "string" ? w : JSON.stringify(w), 14))}</p></div>`)
    .join("");
  return `<div class="rail-sec"><header class="sec-head"><h2 class="sec-lab">${esc(L("Carry-over watchlist", "延续观察清单"))}</h2></header><div>${rows}</div></div>`;
}

function pipelineBlock(sources: SourceHealth[]): string {
  if (!sources.length) return "";
  const rows = sources
    .map((s) => {
      const isTv = s.kind === "yt_playlist";
      const state = s.stale ? "stale" : s.last_ok === 1 ? "ok" : s.last_ok === 0 ? "down" : s.last_run ? "ok" : "pending";
      const when = s.last_run ? s.last_run.slice(0, 10) : L("never", "从未运行");
      const count = isTv ? s.episodes : s.articles;
      const unit = isTv ? L("ep", "期") : L("art", "篇");
      const tip = s.stale
        ? s.last_episode
          ? L(`starving — last episode ${s.last_episode}`, `断粮 — 最近入库节目 ${s.last_episode}`)
          : L("starving — no episode ever ingested", "断粮 — 从未有节目入库")
        : "";
      return `
      <li>
        <span class="dot ${state}" aria-hidden="true" ${tip ? `title="${esc(tip)}"` : ""}></span>
        <span class="dots"><b class="num">${count}</b><i class="unit">${esc(unit)}</i> · ${esc(when)}</span>
      </li>`;
    })
    .join("");
  return `<div class="rail-sec"><header class="sec-head"><h2 class="sec-lab">${esc(L("Source pipeline", "信源管线"))}</h2></header><ul class="dot-list">${rows}</ul></div>`;
}

/* ---------------------------------- assemble ---------------------------------- */

export function renderBrief(desk: Desk, sources: SourceHealth[] = [], lifecycle: LifecycleTrack[] = [], prevEdition: string | null = null, gapWeeks: EditionMeta[] = []): string {
  const dd = desk.data || ({} as DeskData);
  const lc = lifecycleIndex(lifecycle);
  const withheld = desk.status === "blocked_no_evidence" || desk.status === "synth_failed";
  if (withheld) {
    const warns = asList(dd.warnings).map((w) => `<p>${esc(String(w))}</p>`).join("");
    const rail = pipelineBlock(sources);
    return `<div class="grid"><div class="col-main">
      <div class="sec"><div class="empty">${esc(L(
        "This week was withheld from publication — no episode evidence was captured in the reporting window.",
        "本期因采集窗口内无节目证据而暂缓发布。"))}</div>${warns}</div>
    </div>${rail ? `<aside class="rail">${rail}</aside>` : ""}</div>`;
  }
  const gapBand = gapWeeks.length
    ? `<div class="gap-band" role="status">${esc(L(
        `Data gap: ${gapWeeks.map((g) => `${shortDate(g.start_date)} → ${shortDate(g.end_date)}`).join(", ")} withheld (no episode evidence). Showing the latest evidenced brief.`,
        `数据缺口：${gapWeeks.map((g) => `${shortDate(g.start_date)} → ${shortDate(g.end_date)}`).join("、")} 因无节目证据暂缓发布，当前展示最近一期有证据的简报。`))}</div>`
    : "";
  // Reading order, user-first: what happened (lead, tape), what it sounded
  // like (clouds), what's coming (week ahead), how the story moved
  // (narratives, comms), what people are asking (questions/exchanges),
  // then reference material (prep/counsel collapsed, evidence, QC).
  const main =
    gapBand +
    lead(desk, dd, lifecycle, prevEdition) +
    tapeSection(desk.agenda || [], dd.episode_count ?? 0, lc) +
    wordCloudSection(desk.edition) +
    weekAheadPanel(dd) +
    sec(L("Narrative shifts", "叙事转向"), L("what changed", "叙事如何转向"), `<div class="narr-grid">${(desk.narratives || []).map(narrativeCard).join("")}</div>`) +
    commsCards(dd) +
    `<div class="pair">
      ${questionsPanel(dd)}
      ${exchangesPanel(dd)}
    </div>` +
    prepGroup(dd, desk.interview_groups) +
    evidencePanel(dd) +
    qcDetails(desk);
  const rail =
    tickerBlock(asList(desk.ticker)) +
    watchRailBlock(dd) +
    leadLagBlock(asList<LeadLag>(desk.framing?.lead_lag)) +
    watchlistBlock(dd) +
    pipelineBlock(sources);
  return `
    <div class="grid">
      <div class="col-main">${main}</div>
      ${rail ? `<aside class="rail">${rail}</aside>` : ""}
    </div>`;
}