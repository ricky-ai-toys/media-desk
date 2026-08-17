# Deck v2.1 (PR-ready, visual, de-duplicated) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the web deck PR-actionable and visual: C-card tape with real data-ink (coverage bars, lifecycle chips), week-ahead calendar, terse synthesis output, de-duplicated sections, and the measured layout bugs fixed.

**Architecture:** Backend adds additive fields (per-topic driver/next_test/stakes, week_ahead_events) + terse-write rules + 3 new QC gates; frontend re-renders the tape as C-cards, fetches `/api/lifecycle` for chips, adds a Week-ahead section, tightens caps, and fixes closed-`<details>` phantom layout with explicit `display:none`. All editions resynthesized. No export changes, no new deps.

**Tech Stack:** Python 3.13 + FastAPI + SQLite; vanilla TS + esbuild; DeepSeek `deepseek-v4-flash`.

## Global Constraints

- `requirements.txt` unchanged; no new npm deps.
- Email/PDF exports byte-compatible (no legacy-field changes; new fields additive).
- Legacy editions must keep rendering after frontend changes (fields absent → hidden, not broken).
- New topic fields: `driver_en/zh, next_test_en/zh, stakes_en/zh`; new deck field: `week_ahead_events[] {date, event_en, event_zh, why_en, why_zh}`.
- Word caps (prompt rule, frontend clips as net): thesis ≤25, topic summary ≤22, implication ≤14, all cells ≤10.
- QC: new blocking gates `topic_facts_present`, `week_ahead_present`; soft gate `terse_lengths`.
- Resynth requires `DEEPSEEK_API_KEY` (present in env).

---

### Task 1: DB migration + upsert for new topic fact columns

**Files:**
- Modify: `backend/app/db.py`
- Test: `tests/test_db_schema.py`

**Interfaces:**
- Produces: `agenda_topics` columns `driver_en, driver_zh, next_test_en, next_test_zh, stakes_en, stakes_zh` (TEXT); `upsert_edition(data, manifest, qc)` writes them from `t.get("driver_en")` etc., defaulting to "".

- [ ] **Step 1: Write the failing test**

Append to `tests/test_db_schema.py`:

```python
def test_topic_fact_columns_roundtrip(tmp_path, monkeypatch):
    from backend.app import db as dbmod
    d = tmp_path / "t.db"
    monkeypatch.setattr(dbmod, "DB_PATH", str(d))
    dbmod.init_db()
    edition_id = "2026-08-10_to_2026-08-14"
    dbmod.upsert_edition({
        "report_title": "International Financial Media Weekly",
        "start_date": "2026-08-10", "end_date": "2026-08-14",
        "agenda_topics": [{"rank": 1, "title_en": "T", "title_zh": "议题",
                           "summary_en": "s", "summary_zh": "摘要",
                           "driver_en": "d", "driver_zh": "驱动",
                           "next_test_en": "n", "next_test_zh": "检验",
                           "stakes_en": "st", "stakes_zh": "影响"}],
    }, {"episodes": []}, None)
    ed = dbmod.edition_full(edition_id)
    t = ed["agenda"][0]
    assert t["driver_en"] == "d" and t["driver_zh"] == "驱动"
    assert t["next_test_en"] == "n" and t["stakes_zh"] == "影响"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db_schema.py::test_topic_fact_columns_roundtrip -v`
Expected: FAIL (sqlite OperationalError / no such column)

- [ ] **Step 3: Implement migration + upsert**

In `backend/app/db.py`:
- Extend the migration list (next to the existing narrative columns at ~line 121):

```python
    "ALTER TABLE agenda_topics ADD COLUMN driver_en TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN driver_zh TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN next_test_en TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN next_test_zh TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN stakes_en TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN stakes_zh TEXT",
```

- In `upsert_edition`, change the agenda INSERT (~line 269) to include the new columns with `""` defaults:

```python
                "INSERT INTO agenda_topics (edition_id, rank, title_en, title_zh, summary_en, summary_zh, direction, score, priority, momentum, evidence, coverage, driver_en, driver_zh, next_test_en, next_test_zh, stakes_en, stakes_zh) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (edition_id, t.get("rank"), t.get("title_en", ""), t.get("title_zh", ""),
                 t.get("summary_en", ""), t.get("summary_zh", ""), t.get("direction", ""),
                 t.get("score"), t.get("priority", ""), t.get("momentum", ""),
                 t.get("evidence", ""), t.get("coverage"),
                 t.get("driver_en", ""), t.get("driver_zh", ""),
                 t.get("next_test_en", ""), t.get("next_test_zh", ""),
                 t.get("stakes_en", ""), t.get("stakes_zh", "")),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db_schema.py -q`
Expected: PASS (new + existing schema tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/db.py tests/test_db_schema.py
git commit -m "feat(db): agenda topic fact columns (driver/next_test/stakes)"
```

---

### Task 2: Synthesis — terse-write rules, new schema fields, week-ahead

**Files:**
- Modify: `backend/app/synth/weekly.py`
- Test: `tests/test_qc_v2.py` (data fixtures for Task 3's gates)

**Interfaces:**
- Produces: prompt rules; `agenda_topics[]` with `driver_en/zh, next_test_en/zh, stakes_en/zh`; `week_ahead_events[]`; `_derive_legacy` guarantees `data["week_ahead_events"]` exists (list).

- [ ] **Step 1: Extend SYSTEM rules**

In `backend/app/synth/weekly.py`, append to `SYSTEM` (before "EXACTLY 3-5 agenda topics…"):

```python
    "(7) Write terse. Thesis <= 25 words. Each agenda summary is ONE sentence of <= 22 words. "
    "Each comms implication <= 14 words. Every cell field (driver, why, next_test, stakes, shift, "
    "affected, priority_raises, premise, response, lesson) <= 10 words, telegraphic, no lists. "
    "ZH fields obey the same brevity. "
    "(8) week_ahead_events must be 3-5 real, dated events strictly AFTER the reporting week "
    "(next Monday-Friday), each with a one-clause why-it-matters; never invent dates or events "
    "not supported by the corpus or universally known calendar items (policy meetings, data "
    "releases, earnings, deadlines). "
```

- [ ] **Step 2: Extend SCHEMA**

In `SCHEMA`, change the agenda_topics fragment to:

```python
    'agenda_topics[] {rank, title_en, title_zh, summary_en, summary_zh, priority(critical|high|medium), '
    'momentum(accelerating|rising|stable|fading), evidence(strong|moderate|emerging), coverage(int), '
    'driver_en, driver_zh, next_test_en, next_test_zh, stakes_en, stakes_zh}, '
```

and after the watchpoints fragment add:

```python
    'week_ahead_events[] {date(YYYY-MM-DD), event_en, event_zh, why_en, why_zh}, '
```

- [ ] **Step 3: Guarantee the field in `_derive_legacy`**

In `_derive_legacy`, after `data.setdefault("evidence_statuses", [])` add:

```python
    data.setdefault("week_ahead_events", [])
```

- [ ] **Step 4: Verify no syntax errors + resynth smoke (one edition)**

Run: `.venv/bin/python -c "from backend.app.synth import weekly; print('ok')"`
Expected: ok

- [ ] **Step 5: Commit**

```bash
git add backend/app/synth/weekly.py
git commit -m "feat(synth): terse-write rules, topic facts, week-ahead events"
```

---

### Task 3: QC gates — topic_facts_present, week_ahead_present, terse_lengths

**Files:**
- Modify: `backend/app/synth/qc.py`
- Test: `tests/test_qc_v2.py`

**Interfaces:**
- Consumes: `data["agenda_topics"]` with the Task 2 fields; `data["week_ahead_events"]`; `data["end_date"]`.
- Produces: checks `topic_facts_present` (blocking), `week_ahead_present` (blocking), `terse_lengths` (non-blocking).

- [ ] **Step 1: Write failing tests**

Append to `tests/test_qc_v2.py`:

```python
import datetime as _dt

def _base_v2_data():
    return {
        "report_title": "International Financial Media Weekly",
        "start_date": "2026-08-10", "end_date": "2026-08-14",
        "thesis_en": "x", "thesis_zh": "x",
        "week_summary_en": "x", "week_summary_zh": "x",
        "agenda_topics": [{"rank": 1, "title_en": "T", "summary_en": "s",
                           "driver_en": "d", "next_test_en": "n", "stakes_en": "st"}],
        "narratives": [{"driver_en": "d", "why_en": "w", "next_test_en": "n"}] * 3,
        "comms_boxes": [{"title_en": "t", "implication_en": "i"}] * 3,
        "question_groups": [{"category": "policy_credibility", "questions_en": ["q"] * 3}],
        "watchpoints": [{"trigger_en": "t"}] * 3,
        "media_exchanges": [{"pattern_en": "p", "premise_en": "p"}] * 3,
        "evidence_statuses": [{"status": "confirmed"}],
        "recurring_questions_en": ["q", "q2", "q3"],
        "week_ahead_events": [],
    }


> NOTE: `run_qc` reads an edition from the DB. The gates are implemented as module-level
> helper functions (Step 3) and tested directly, then wired into `run_qc`:

```python
def test_qc_topic_facts_present():
    from backend.app.synth import qc
    assert qc.topic_facts_present({"agenda_topics": [{"driver_en": "d", "next_test_en": "n", "stakes_en": "s"}]})
    assert not qc.topic_facts_present({"agenda_topics": [{"driver_en": "d", "next_test_en": "n"}]})

def test_qc_week_ahead_window():
    from backend.app.synth import qc
    good = {"end_date": "2026-08-14", "week_ahead_events": [
        {"date": "2026-08-17", "event_en": "BOJ"}, {"date": "2026-08-19", "event_en": "CPI"}]}
    assert qc.week_ahead_present(good)
    bad = {"end_date": "2026-08-14", "week_ahead_events": [
        {"date": "2026-08-13", "event_en": "past"}, {"date": "2026-09-01", "event_en": "far"}]}
    assert not qc.week_ahead_present(bad)
    assert not qc.week_ahead_present({"end_date": "2026-08-14", "week_ahead_events": []})

def test_qc_terse_lengths_soft():
    from backend.app.synth import qc
    assert qc.terse_lengths({"agenda_topics": [{"summary_en": "short"}]})
    long = {"agenda_topics": [{"summary_en": "word " * 30}]}
    assert not qc.terse_lengths(long)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_qc_v2.py -k "topic_facts or week_ahead or terse" -v`
Expected: FAIL (ImportError: cannot import name)

- [ ] **Step 3: Implement helpers + wire into run_qc**

In `backend/app/synth/qc.py`, add module helpers and a `datetime` import:

```python
def topic_facts_present(data: dict) -> bool:
    topics = data.get("agenda_topics", [])
    return bool(topics) and all(t.get("driver_en") and t.get("next_test_en") and t.get("stakes_en")
                                for t in topics)


def week_ahead_present(data: dict) -> bool:
    events = data.get("week_ahead_events", [])
    if not (3 <= len(events) <= 5):
        return False
    try:
        end = _dt.date.fromisoformat(data["end_date"])
    except (KeyError, ValueError):
        return False
    lo, hi = end + _dt.timedelta(days=1), end + _dt.timedelta(days=10)
    for e in events:
        try:
            d = _dt.date.fromisoformat(str(e.get("date", "")))
        except ValueError:
            return False
        if not (lo <= d <= hi) or not e.get("event_en"):
            return False
    return True


def terse_lengths(data: dict) -> bool:
    topics = data.get("agenda_topics", [])
    if not topics:
        return True
    over = [t for t in topics if len((t.get("summary_en") or "").split()) > 24]
    return len(over) <= max(1, len(topics) // 5)
```

In `run_qc`, add to the `blocking` tuple and to the check list (after `agenda_labeled`):

```python
    blocking = (..., "topic_facts_present", "week_ahead_present")
```

```python
    add_v2("topic_facts_present", topic_facts_present(data),
        f"{len(data.get('agenda_topics', []))} topics with driver/next_test/stakes")
    add_v2("week_ahead_present", week_ahead_present(data),
        f"{len(data.get('week_ahead_events', []))} events in next-week window")
    add("terse_lengths", terse_lengths(data),
        "topic summaries within soft length budget", blockable=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_qc_v2.py -k "topic_facts or week_ahead or terse" -v`
Expected: PASS. Then full suite: `.venv/bin/python -m pytest tests/ -q` — must stay green.

- [ ] **Step 5: Commit**

```bash
git add backend/app/synth/qc.py tests/test_qc_v2.py
git commit -m "feat(qc): topic-facts and week-ahead gates, terse-length soft check"
```

---

### Task 4: Frontend libs — ellipsis, lang/title, aria-pressed

**Files:**
- Modify: `web/src/lib/format.ts`, `web/src/lib/i18n.ts`, `web/src/components/EditionSwitcher.ts`

**Interfaces:**
- Produces: `ellipsis(s: string, n: number): string`; `setLang(l)` sets `document.documentElement.lang`; EN/中文 buttons get `aria-pressed`.

- [ ] **Step 1: format.ts — add ellipsis**

Append to `web/src/lib/format.ts`:

```ts
/** Hard cut with an ellipsis; respects existing ending punctuation. */
export function ellipsis(s: string | null | undefined, n: number): string {
  const t = String(s ?? "").trim();
  if (!t) return "";
  if (t.length <= n) return t;
  return t.slice(0, n).replace(/[,;:!?—–]+$/, "").trim() + "…";
}
```

- [ ] **Step 2: i18n.ts — lang on <html>**

Change `setLang` to:

```ts
export function setLang(l: Lang): void {
  lang = l;
  document.documentElement.lang = l;
}
```

- [ ] **Step 3: EditionSwitcher — aria-pressed**

In `applyLang`, after the class toggles add:

```ts
    this.enBtn.setAttribute("aria-pressed", String(l === "en"));
    this.zhBtn.setAttribute("aria-pressed", String(l === "zh"));
```

and set both in the constructor's initial render: `aria-pressed="true"` on EN, `aria-pressed="false"` on 中文.

- [ ] **Step 4: Typecheck**

Run: `cd web && npm run typecheck`
Expected: PASS (no errors)

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/format.ts web/src/lib/i18n.ts web/src/components/EditionSwitcher.ts
git commit -m "feat(web): ellipsis helper, html lang sync, aria-pressed toggle"
```

---

### Task 5: CSS — phantom-layout fix, flex rows, C-card + chip + calendar styles

**Files:**
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: new class names from Task 6 (`g-card`, `cov-bar`, `chip lc-*`, `facts-grid`, `wk-cal`, `.narr-body-hide` etc. — names below are the contract).
- Produces: closed-details bodies truly hidden; `.list-row` flex; rail clearance; card/chip/calendar visuals.

- [ ] **Step 1: Kill phantom closed-details layout**

Replace the `.glance { border-bottom… }` block area and add, after the existing `.g-body` rule:

```css
.glance:not([open]) .g-body,
.narr:not([open]) .narr-body,
.comms .chunk, .comms .implication, .comms .risky,
.wp:not([open]) .wp-grid { display: none; }
```

> The `.comms`/`.wp` rows are cards whose open-body children are the only content; closing
> them must free their space. `.narr:not([open]) .narr-body` frees narrative bodies.

- [ ] **Step 2: Evidence rows to flex**

Replace the `.list-row` rule with:

```css
.list-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; padding: 7px 0; border-bottom: 1px dashed var(--hair); font-size: 13px; }
```

- [ ] **Step 3: Rail clearance**

Change `.rail` sticky line from `top: 84px` to `top: 92px`.

- [ ] **Step 4: C-card tape styles**

Replace `.glance`/`.g-row`/`.g-body` visual rules with card semantics (keep the grid column classes for the head). Add:

```css
.glance { border: 1px solid var(--hair); background: var(--card); margin-bottom: 10px; animation: tapeIn .32s ease both; animation-delay: calc(var(--i) * 26ms); }
.glance.critical { border-top: 3px solid var(--signal); }
.glance.high { border-top: 3px solid var(--amber); }
.glance.medium { border-top: 3px solid var(--mist); }
.g-row { display: grid; grid-template-columns: 32px minmax(0, 1fr) 26px auto auto 46px; column-gap: 12px; align-items: center; padding: 11px 14px; cursor: pointer; list-style: none; }
.g-row::-webkit-details-marker { display: none; }
summary.g-row::marker { content: ""; }
.g-row:hover { background: var(--glow); }
.g-no { font-family: var(--mono); font-size: 12px; font-weight: 600; color: var(--faint); text-align: right; }
.glance.critical .g-no { color: var(--signal); }
.glance.high .g-no { color: var(--amber); }
.g-title { font-family: var(--disp); font-size: 15.5px; font-weight: 600; line-height: 1.3; color: var(--ink); }
.g-cov { font-family: var(--mono); font-size: 10.5px; color: var(--slate); text-align: right; font-variant-numeric: tabular-nums; }
.g-mom { font-size: 14px; text-align: center; font-family: var(--mono); }
.cov-bar { height: 4px; background: var(--glow); }
.cov-bar i { display: block; height: 100%; background: var(--ink); }
.glance.critical .cov-bar i { background: var(--signal); }
.glance.high .cov-bar i { background: var(--amber); }
.g-body { padding: 10px 14px 13px; display: grid; gap: 9px; }
.g-sub { font-family: var(--disp); font-size: 14px; color: var(--body); line-height: 1.55; max-width: 76ch; }
.facts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; }
.fact-k { font-family: var(--mono); font-size: 8.5px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--faint); margin-bottom: 1px; }
.fact-v { font-size: 12px; color: var(--body); }
.chip { font-family: var(--mono); font-size: 9px; font-weight: 600; letter-spacing: .1em; border: 1px solid; padding: 1px 6px; white-space: nowrap; }
.chip.lc-new { color: var(--up); border-color: #bcd8c7; background: #f0f7f2; }
.chip.lc-up { color: var(--signal); border-color: #d9a49e; background: #fbf1f0; }
.chip.lc-down { color: var(--amber); border-color: #d9b66f; background: #faf4e6; }
.chip.lc-carried { color: var(--faint); border-color: var(--hair); background: var(--card); }
```

Remove now-dead rules: `.g-lead`, `.tape`, `.g-viz`, `.spark`, `.g-sig`, `.g-fold` visual references (leave harmless if referenced in mobile rules — see Step 5). Keep `.lab`, `.prio-*`, `.ev-*` (still used in head + body).

- [ ] **Step 5: Mobile grid sync**

Update the `@media (max-width: 640px)` `.g-row` block to the new 6-column head (hide `.g-cov` chip column, keep rank/title/mom):

```css
  .tape-head { display: none; }
  .g-row { grid-template-columns: 28px minmax(0, 1fr) 24px auto; padding: 10px 12px; }
  .g-no { grid-column: 1; }
  .g-main { grid-column: 2; }
  .g-mom { grid-column: 3; }
  .g-prio { grid-column: 4; grid-row: 1; }
  .g-cov { grid-column: 2; grid-row: 2; justify-self: start; }
```

- [ ] **Step 6: Week-ahead calendar**

Add:

```css
.wk-cal { border: 1px solid var(--hair); background: var(--card); }
.wk-row { display: grid; grid-template-columns: 96px 1fr; gap: 12px; padding: 9px 14px; border-bottom: 1px dashed var(--hair); align-items: baseline; }
.wk-row:last-child { border-bottom: none; }
.wk-d { font-family: var(--mono); font-size: 10px; font-weight: 600; color: var(--amber); letter-spacing: .06em; }
.wk-e { font-size: 12.5px; color: var(--body); }
.wk-e b { color: var(--ink); font-weight: 600; }
```

- [ ] **Step 7: Build + visual check**

Run: `cd web && npm run build && node scripts/snap.mjs`
Expected: builds; snap shows 5 glance rows, no console errors. Then run the DOM check:
`node scripts/overlap2.mjs` — expect no painted overlaps beyond the sparkline fill; and a one-liner closed-row check via `node scripts/details-debug.mjs` must show closed rows' `.g-body` rect height 0.

- [ ] **Step 8: Commit**

```bash
git add web/src/styles.css
git commit -m "feat(web): C-card tape, lifecycle chips, week-ahead calendar CSS; kill phantom details layout"
```

---

### Task 6: BriefView — C-cards, de-dup, chips, caps, week-ahead panel

**Files:**
- Modify: `web/src/views/BriefView.ts`

**Interfaces:**
- Consumes: `ellipsis` (Task 4); `LifecycleTrack` type + `lifecycle`/`prevEditionId` args (Task 7 wires them); new topic fields and `week_ahead_events` in `DeskData` (api.ts, updated here in Step 0).
- Produces: `renderBrief(desk, sources, lifecycle, prevEditionId)`; tape rows as `.glance` C-cards with `.chip lc-*`, `.cov-bar`, `.facts-grid`; `weekAheadPanel` section; hero delta line.

- [ ] **Step 0: Extend `web/src/lib/api.ts`**

Add to `AgendaItem`: `driver_en?, driver_zh?, next_test_en?, next_test_zh?, stakes_en?, stakes_zh?`.
Add to `DeskData`: `week_ahead_events?: { date?: string; event_en?: string; event_zh?: string; why_en?: string; why_zh?: string }[]`.
Add:

```ts
export interface LifecycleTrack {
  label?: string;
  title_zh?: string;
  first_seen?: string;
  last_seen?: string;
  phase?: string;
  rank_delta?: number;
}
```

- [ ] **Step 1: Lifecycle chip resolution**

Add to `BriefView.ts` (imports: `LifecycleTrack`):

```ts
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
  const zh = getLang() === "zh";
  if (track.phase === "new") return `<span class="chip lc-new">${L("NEW", "新增")}</span>`;
  const d = track.rank_delta ?? 0;
  if (d > 0) return `<span class="chip lc-up">↑${d}</span>`;
  if (d < 0) return `<span class="chip lc-down">↓${Math.abs(d)}</span>`;
  return `<span class="chip lc-carried">${L("carried", "延续")}</span>`;
}
```

- [ ] **Step 2: Rewrite tapeRow as C-card**

Replace `tapeRow` body with:

```ts
function tapeRow(a: AgendaItem, i: number, episodeCount: number, lc: Map<string, LifecycleTrack>): string {
  const prio = String(a.priority || "").toLowerCase();
  const momentum = String(a.momentum || "").toLowerCase();
  const evidence = String(a.evidence || "").toLowerCase();
  const arrow = MOM_ARROW[momentum] || "→";
  const title = clip(pick(a.title_en, a.title_zh), 10) || "—";
  const sub = clip(pick(a.summary_en, a.summary_zh), 22);
  const prioLab = prio ? L(PRIO_LAB[prio as keyof typeof PRIO_LAB] || prio.toUpperCase(), DIR_ZH[prio] || prio.toUpperCase()) : "";
  const cls = PRIO_CLS[prio as keyof typeof PRIO_CLS] || "";
  const track = lc.get(normKey(pick(a.title_en, a.title_zh))) || lc.get(normKey(a.title_en || ""));
  const chip = lcChip(track);
  const pct = episodeCount > 0 && a.coverage != null ? Math.max(0, Math.min(100, Math.round((a.coverage / episodeCount) * 100))) : null;
  const facts = [
    [L("Driver", "驱动"), pick(a.driver_en, a.driver_zh)],
    [L("Next test", "下一步检验"), pick(a.next_test_en, a.next_test_zh)],
    [L("Who's exposed", "谁受影响"), pick(a.stakes_en, a.stakes_zh)],
  ].filter(([, v]) => v);
  const dots = "●".repeat(EVID_DOTS[evidence]?.[0] ?? 0) + "○".repeat(3 - (EVID_DOTS[evidence]?.[0] ?? 0));
  return `
    <details class="glance ${cls}" style="--i:${i}"${i === 0 ? " open" : ""}>
      <summary class="g-row">
        <span class="g-no">${String(a.rank ?? i + 1).padStart(2, "0")}</span>
        <span class="g-main"><b class="g-title">${esc(title)}</b></span>
        <span class="g-mom" aria-hidden="true">${arrow}</span>
        ${prioLab ? `<span class="lab g-prio prio-${esc(prio || "n")}">${esc(prioLab)}</span>` : ""}
        ${chip}
        ${a.coverage != null ? `<span class="g-cov">${a.coverage}/${episodeCount}</span>` : ""}
      </summary>
      ${pct != null ? `<div class="cov-bar"><i style="width:${pct}%"></i></div>` : ""}
      <div class="g-body">
        ${sub ? `<p class="g-sub">${esc(sub)}</p>` : ""}
        ${facts.length ? `<div class="facts-grid">${facts.map(([k, v]) => `<div><div class="fact-k">${esc(k)}</div><div class="fact-v">${esc(clip(v, 10))}</div></div>`).join("")}</div>` : ""}
        ${evidence && EVID_DOTS[evidence] ? `<span class="lab ev-${esc(evidence)}">${dots} ${esc(L(evidence, EVID_ZH[evidence] || evidence))}</span>` : ""}
      </div>
    </details>`;
}
```

Update `tapeSection(agenda, episodeCount, lc)` to pass them through; drop the `.g-sub`/`.tape` duplication, the sparkline, and the old `.g-viz` (Task 5 CSS removed them).

- [ ] **Step 3: lead() truncation + caps**

Change the headline/body logic to use `ellipsis`:

```ts
  const headline = (i > 24 && i < 110 ? thesis.slice(0, i + 1) : ellipsis(thesis, 100)).trim();
  const body = (i > 24 && i < 110 ? thesis.slice(i + 2) : "").trim();
```

and `clip(body, 45)` → `clip(body, 25)`. Import `ellipsis` from `../lib/format`.

- [ ] **Step 4: commsCards — drop teaser, cap implication**

Remove the `comms-teaser` span from both the boxes and the pr_counsel branch; change implication clips to `14`, opportunity to `14`, risky to `20`.

- [ ] **Step 5: watch + exchanges caps**

`watchPanel`: cell clips `30` → `10` (shift/affected/why), title clip 14 stays. `exchangesPanel`: cell clips `40` → `10`, and remove the `response`/`lesson` rows only if both empty (already filtered by `v ?` guard).

- [ ] **Step 6: weekAheadPanel + hero delta**

Add:

```ts
const WD = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

function weekAheadPanel(dd: DeskData): string {
  const es = asList(dd.week_ahead_events);
  if (!es.length) return "";
  const rows = es.map((e) => {
    let dlab = esc(e.date || "");
    try {
      const d = new Date((e.date || "").slice(0, 10) + "T00:00:00");
      if (!Number.isNaN(d.getTime())) dlab = `${WD[d.getDay()]} ${String(d.getDate()).padStart(2, "0")}`;
    } catch { /* keep raw */ }
    return `<div class="wk-row"><div class="wk-d">${dlab}</div><div class="wk-e"><b>${esc(pick(e.event_en, e.event_zh))}</b>${pick(e.why_en, e.why_zh) ? ` — ${esc(clip(pick(e.why_en, e.why_zh), 14))}` : ""}</div></div>`;
  }).join("");
  return sec(L("Week ahead", "下周看点"), L("dated events to watch", "下周重要日程"), `<div class="wk-cal">${rows}</div>`);
}

function heroDelta(desk: Desk, tracks: LifecycleTrack[], prevEdition: string | null): string {
  const id = desk.edition;
  const nw = tracks.filter((t) => t.first_seen === id).length;
  const carried = tracks.filter((t) => t.last_seen === id && t.first_seen !== id).length;
  const dropped = prevEdition ? tracks.filter((t) => t.last_seen === prevEdition).length : 0;
  if (!nw && !carried && !dropped) return "";
  const zh = getLang() === "zh";
  const parts = [
    nw ? `${nw} ${L("new", "新增")}` : "",
    carried ? `${carried} ${L("carried", "延续")}` : "",
    dropped ? `${dropped} ${L("dropped", "淡出")}` : "",
  ].filter(Boolean);
  return parts.length ? `<span class="lc-delta">${parts.join(" · ")}</span>` : "";
}
```

Add `heroDelta` output into the `lead-meta` (before the Week span), guarded by `desk`/`tracks`.

- [ ] **Step 7: renderBrief signature + assembly**

```ts
export function renderBrief(desk: Desk, sources: SourceHealth[] = [], lifecycle: LifecycleTrack[] = [], prevEdition: string | null = null): string {
  const dd = desk.data || ({} as DeskData);
  const lc = lifecycleIndex(lifecycle);
  const main =
    lead(desk, dd, lifecycle, prevEdition) +
    tapeSection(desk.agenda || [], dd.episode_count ?? 0, lc) +
    sec(L("Narrative shifts", "叙事转向"), L("what changed", "叙事如何转向"), `<div class="narr-grid">${(desk.narratives || []).map(narrativeCard).join("")}</div>`) +
    commsCards(dd) +
    `<div class="pair">${watchPanel(dd)}${weekAheadPanel(dd)}</div>` +
    `<div class="pair">${questionsPanel(dd)}${exchangesPanel(dd)}</div>` +
    evidencePanel(dd);
  ...
}
```

(evidencePanel stays; narrativeCard/others unchanged.)

- [ ] **Step 8: Typecheck + build + snap**

Run: `cd web && npm run typecheck && npm run build && node scripts/snap.mjs`
Expected: all pass; `.glance` rows render; no errors. Run `node scripts/details-debug.mjs` — closed rows' body height must be 0.

- [ ] **Step 9: Commit**

```bash
git add web/src/views/BriefView.ts web/src/lib/api.ts
git commit -m "feat(web): C-card tape with coverage bars + lifecycle chips, week-ahead panel, de-duped sections"
```

---

### Task 7: main.ts — lifecycle fetch, prev edition, per-lang title

**Files:**
- Modify: `web/src/main.ts`, `web/src/components/ReadingContainer.ts`

**Interfaces:**
- Consumes: `renderBrief(desk, sources, lifecycle, prevEdition)` (Task 6).
- Produces: `showBrief(desk, sources, lifecycle, prevEdition)`; per-language `document.title`.

- [ ] **Step 1: main.ts**

- Import `type LifecycleTrack` from `./lib/api`.
- Add to state: `lifecycle: LifecycleTrack[]` and `prevEdition: string | null`.
- In `boot()`, after meta loads:

```ts
    const eds = meta.editions || [];
    const idx = eds.findIndex((e) => e.id === meta.latest);
    state.prevEdition = idx > 0 ? eds[idx - 1].id : null;
    const lc = await api<{ tracks: LifecycleTrack[] }>("/api/lifecycle");
    state.lifecycle = lc.tracks || [];
```

- Pass into `reading.showBrief(state.desk, state.meta?.sources ?? [], state.lifecycle, state.prevEdition)` in `loadDesk`.
- In `onLang` and after boot, set `document.title`:

```ts
function applyTitle(): void {
  document.title = getLang() === "zh" ? "媒体台 · 国际财经媒体每周简报" : "Media Desk — International Financial Media Weekly Brief";
}
```

call it in `boot()` and in the `onLang` callback.

- [ ] **Step 2: ReadingContainer**

`showBrief(desk, sources, lifecycle, prevEdition)` passes all four through to `renderBrief`. Import `LifecycleTrack` type.

- [ ] **Step 3: Typecheck + build + manual DOM check**

Run: `cd web && npm run typecheck && npm run build && node scripts/snap.mjs`
Then a quick DOM probe (`node scripts/paint-test.mjs` variant or inline evaluate): tape row 1 has `.chip.lc-*`; `.lc-delta` present in lead meta; `document.documentElement.lang` flips to "zh" after clicking 中文 (drive via puppeteer click on `#lang-zh`).

- [ ] **Step 4: Commit**

```bash
git add web/src/main.ts web/src/components/ReadingContainer.ts
git commit -m "feat(web): lifecycle data + prev-edition wiring, per-lang document title"
```

---

### Task 8: Search highlighting

**Files:**
- Modify: `web/src/views/SearchView.ts`

- [ ] **Step 1: Implement mark + count**

Replace `renderSearch` body construction:

```ts
function mark(s: string | null | undefined, q: string): string {
  const text = String(s ?? "");
  if (!text || q.length < 2) return esc(text);
  const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
  return text.split(re).map((part, i) => (i % 2 === 1 ? `<mark>${esc(part)}</mark>` : esc(part))).join("");
}
```

Use `mark(x.title || x.source_name || "—", query)` for the title and `mark(x.snip, query)` for the snippet. Add count to the header: `L("Search", "检索")}: ${esc(query)} <span class="s">· ${hits.length} ${L("hits", "条结果")}</span>`.

- [ ] **Step 2: Typecheck + build**

Run: `cd web && npm run typecheck && npm run build`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add web/src/views/SearchView.ts
git commit -m "feat(web): search hit highlighting and result count"
```

---

### Task 9: Resynthesize all editions + full verification

**Files:**
- Run: `scripts/resynth_weeks.py` (no code change)

- [ ] **Step 1: Resynth all editions**

Run: `.venv/bin/python scripts/resynth_weeks.py`
Expected: each edition synthesized, QC run; report the per-edition status. Any FAIL → re-run that edition once (`--edition <id>`); if still FAIL, leave `needs_review` and report.

- [ ] **Step 2: Backend suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: green (suite ~25+).

- [ ] **Step 3: Frontend suite**

Run: `cd web && npm run typecheck && npm run build && node scripts/snap.mjs`
Expected: no console/page errors, CLS < 0.01, 5 glance rows at all viewports. Run `node scripts/overlap2.mjs` (expect no painted overlaps) and `node scripts/details-debug.mjs` (closed bodies height 0).

- [ ] **Step 4: Content spot-check via API**

Run: `curl -s "http://localhost:8517/api/desk" | python3 -c "import json,sys; d=json.load(sys.stdin); t=d['agenda'][0]; print(t.get('driver_en'), '|', d['data'].get('week_ahead_events'))"`
Expected: topic facts + week-ahead events present on the latest edition.

- [ ] **Step 5: Final report**

Summarize: gates, resynth outcomes, any edition still needs_review, verification numbers.

## Self-review notes (run at plan-write time)

- Spec coverage: layout bugs → Task 5 (phantom layout, list-row flex, rail clearance) + Task 6 Step 3 (lead ellipsis); de-dup → Task 6 Steps 2-4; data-ink → Tasks 5-7; synthesis + QC → Tasks 1-3; search → Task 8; resynth/verification → Task 9. Deferred items intentionally absent.
- Placeholders: none; every step has exact code or command.
- Type consistency: `renderBrief(desk, sources, lifecycle, prevEdition)` signature is defined in Task 6 Step 7 and consumed identically in Task 7; `LifecycleTrack` defined in Task 6 Step 0, used in Tasks 6-7; `topic_facts_present/week_ahead_present/terse_lengths` defined in Task 3 Step 3, tested there and called in `run_qc`.
