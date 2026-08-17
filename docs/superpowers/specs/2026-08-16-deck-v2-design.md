# Deck v2.1 — PR-ready, visual, de-duplicated (Design Spec)

**Date:** 2026-08-16
**Status:** Approved in review (option C composition, data-ink mini-viz, synthesis+frontend verbosity fix)
**Iteration target:** web deck + weekly synthesis + QC, no export changes

## 1. Problem

Review of the web deck found four issue groups:

1. **Repetition** — tape row shows the same summary twice (`.g-sub` clip 14 + `.tape`
   clip 55); momentum appears as arrow + sparkline + label; evidence as dots + dots-and-label;
   comms teaser is a clip-9 duplicate of the clip-50 implication; QC badge in header and hero.
2. **Verbosity** — prose caps of 45–55 words per summary, 30–40 per exchange/watchpoint cell;
   paragraphs where telegraphic cells belong.
3. **No visuals** — the only "charts" are a 34×12px sparkline with the same four-point
   pattern in every row (not real data), a 120×18 arrow, dots and a bare coverage number.
4. **Layout bugs** — closed `<details>` rows reserve 145px of phantom layout each
   (~580px of dead space in the tape; Chrome `content-visibility:hidden` keeps the box);
   evidence `.list-row` inlines interleave (union-rect overlap risk); lead headline can cut
   mid-word without ellipsis; `<html lang>` never changes on EN/中文 toggle.

## 2. Design decisions (approved)

- **Tape row → C-cards** (option C): bordered card per topic, priority-colored accent top
  edge, rank / title / momentum / lifecycle chip / coverage count in the head, full-width
  coverage bar as a rule, open body = one 18-word sentence + three labelled facts
  (Driver / Next test / Who's exposed) + evidence dots.
- **Data-ink mini-viz**: coverage bars (real data), lifecycle chips (`NEW` / `↑n` / `↓n` /
  `carried`, from `/api/lifecycle`), hero one-line delta ("2 new · 3 carried · 1 dropped").
  No chart library; hand-rolled CSS/SVG in the existing newsprint idiom.
- **Verbosity fixed at the source**: synthesis prompt gains terse-write rules and new
  per-topic fact fields; frontend caps act as a safety net. All editions resynthesized.
- **New "Week ahead" section**: dated events for the coming week (BOJ, CPI, tariff
  deadlines…), from a new `week_ahead_events[]` synthesis field.
- Bug fixes per the review (below).

## 3. Backend changes

### 3.1 `backend/app/db.py`
- `_migrate`: add `agenda_topics` columns `driver_en, driver_zh, next_test_en, next_test_zh,
  stakes_en, stakes_zh` (TEXT), PRAGMA-guarded like the v2 migration.
- `upsert_edition`: write the six new columns in the agenda_topics INSERT; set defaults ""
  when absent so legacy rows round-trip.

### 3.2 `backend/app/synth/weekly.py`
- `SYSTEM`: append terse-write rules — thesis ≤ 25 words; every agenda summary ≤ 22 words,
  one sentence; every implication ≤ 14 words; every cell field (driver, why, next_test,
  stakes, shift, affected, priority_raises, premise, response, lesson) ≤ 10 words,
  telegraphic; ZH same brevity; no lists inside cells.
- `SCHEMA`: `agenda_topics[]` gains `driver_en, driver_zh, next_test_en, next_test_zh,
  stakes_en, stakes_zh`; new `week_ahead_events[] {date(YYYY-MM-DD), event_en, event_zh,
  why_en, why_zh}` — 3-5 events, dates strictly after the reporting week's Friday.
- `_derive_legacy`: no new derivation needed (new fields have no legacy counterpart);
  setdefault `week_ahead_events` to [] for QC safety.

### 3.3 `backend/app/synth/qc.py`
- New blocking v2 gates:
  - `topic_facts_present` — every agenda topic has driver_en + next_test_en + stakes_en.
  - `week_ahead_present` — 3-5 events; every date parses and lies within
    `end_date + 1 .. end_date + 10`.
  - `terse_lengths` — non-blocking soft check: ≤20% of topic summaries exceed 24 words
    (warning only; the prompt does the real work).
- Existing gates untouched.

### 3.4 API — no route changes
`/api/desk` already serves `data` (week_ahead_events rides in `data_json`); `/api/lifecycle`
already serves tracks with `phase`, `rank_delta`, `score_delta`, `first_seen`, `last_seen`.

## 4. Frontend changes (`web/src/`)

### 4.1 `lib/i18n.ts`
- `setLang` also sets `document.documentElement.lang` (and `document.title` per language,
  done in `main.ts` via `L`).

### 4.2 `lib/format.ts`
- `clip` unchanged; add `ellipsis(s, n)` for hard cuts with "…" where needed.

### 4.3 `views/BriefView.ts`
- **lead()**: fix truncation — use `ellipsis`; body cap 25 words.
- **tapeRow() → card structure (C)**:
  - head: rank (mono, priority color), title (serif, 1 line), momentum arrow, lifecycle
    chip, coverage count `n/N` (N = `dd.episode_count`).
  - coverage bar: rule under head, `width = coverage / episode_count` (fallback: hidden).
  - open body: summary (cap 22), three-fact grid (Driver / Next test / Who's exposed —
    from new topic fields; hidden when absent), evidence dots + label once.
  - remove `.g-sub` + `.tape` duplication, the fake sparkline, and the redundant
    momentum/evidence labels in the open body.
- **Lifecycle integration**: `renderBrief` accepts `lifecycle` (fetched once in `main.ts`
  from `/api/lifecycle`); chip resolution by normalized-title match (fallback: `NEW` for
  `phase === "new"`, else `carried`). Hero gains the delta line: new = tracks with
  `first_seen === this edition`, carried = `last_seen === this edition && first_seen < this`,
  dropped = tracks whose `last_seen === previous edition id` (previous id from meta).
- **commsCards()**: drop the teaser (title + implication only); implication cap 14.
- **watchPanel()**: cell caps 10 words.
- **exchangesPanel()**: cell caps 10 words.
- **New weekAheadPanel()**: calendar block — date (mono, amber) + event + why; section
  hidden when no data (graceful degradation for legacy editions).
- **evidencePanel()**: keep, rows → flex (see 4.5).
- **questionsPanel()**: unchanged.
- Remove dead `rangeLabel` import.

### 4.4 `views/SearchView.ts`
- `<mark>` around matched query tokens in title + snip (case-insensitive, escaped),
  hit count in the header, cap stays 40.

### 4.5 `styles.css`
- `.glance:not([open]) .g-body`, `.narr:not([open]) .narr-body`, `.comms:not([open])`
  content, `.wp:not([open]) .wp-grid` → `display: none` (kills the 145px phantom layout;
  rows collapse to their real height).
- `.list-row` → `display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap`
  (b / tag / note can no longer interleave).
- New C-card styles: `.glance` becomes card (border, background, padding, accent top edge
  by priority), `.cov-bar`, `.chip.lc-new`, `.chip.lc-up`, `.chip.lc-down`,
  `.chip.lc-carried`, `.facts-grid`, `.wk-cal` calendar rows.
- Rail sticky `top: 84px` → `top: 92px` (tools row measures 78px at desktop).
- `.seg button` gains `aria-pressed` styling hook (attribute toggle in `EditionSwitcher`).

### 4.6 `components/EditionSwitcher.ts`
- Set `aria-pressed` on EN/中文 buttons.

### 4.7 `main.ts`
- Fetch `/api/lifecycle` once at boot (and reuse), pass into `showBrief`;
- `document.title` per language;
- keep search/meta flow unchanged.

## 5. Re-synthesis
- `scripts/resynth_weeks.py` for all seeded editions (key available). Each edition must
  pass QC with the new gates before being considered done. If an edition fails a gate,
  re-run once with the failure noted; if it still fails, keep it `needs_review` and report.

## 6. Verification
- `pytest tests/ -q` green (suite ~25; no existing test may break — new columns and fields
  are additive).
- `npm run typecheck` clean; `npm run build` clean.
- `node scripts/snap.mjs`: desktop/mid/mobile — no console/page errors, CLS < 0.01,
  `.glance` rows render; new assert: closed rows have zero `.g-body` height.
- Manual DOM check (puppeteer): no painted overlap pairs at 1440/900/390 except the
  sparkline fill; `html lang` flips on 中文 toggle; lifecycle chips appear on tape rows;
  week-ahead section renders only when data present.
- Resynth output: all editions QC PASS incl. new gates.

## 7. Deferred (explicit non-goals)
- Telemetry toggle (`?telemetry=1`: pressure/collisions/lifecycle panels) — next iteration.
- Narrative pressure-dots, section TOC, print stylesheet, `?edition=` deep links,
  automated frontend test harness.
- Search result → transcript context navigation.

## 8. Risks
- **Title-matching lifecycle chips**: `/api/lifecycle` labels may not match agenda titles
  exactly → normalized containment match + fallback chips; cosmetic worst case.
- **LLM terseness**: a soft gate only; prose quality depends on the prompt. If an edition
  overruns the caps, the frontend clip cap still bounds display.
- **week_ahead_events hallucination risk**: dates constrained to the window after the
  reporting week; QC rejects out-of-window dates; events themselves are editorial (no
  fabrication of quotes/figures — the terse-write rules already forbid invented numbers).
