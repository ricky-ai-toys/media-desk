# Weekly Brief Editorial Iteration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Restructure the weekly synthesis + desk into the 7-section editorial brief (thesis, at a glance, narrative shifts, communications implications, questions gaining traction, high-signal exchanges, watch next) with labeled priority/momentum/evidence instead of false-precision scores.

**Architecture:** LLM emits new weekly JSON (`data_json` superset) with editorial sections; code derives legacy fields from the new ones so `email.py`/PDF exports stay byte-compatible. SQLite gains columns on `agenda_topics`/`narratives` via PRAGMA-guarded migration. QC is extended with new gates and flexible counts. Frontend renders the 7 editorial sections only — supporting-intelligence panels (sources, wire, coverage radar, lifecycle, anchor pressure, guest log) are removed from the desk (data still served via API). All 3 seeded editions resynthesized.

**Tech stack:** Python 3.13, FastAPI, SQLite, DeepSeek `deepseek-v4-flash`, vanilla JS.

## Global Constraints

- No new dependencies; `requirements.txt` unchanged.
- Email/PDF exports unchanged byte-for-byte; they read `pr_counsel`, `watchlist_en/zh`, `recurring_questions_en/zh`, `interview_groups_en/zh`, `narratives[].from/to/analysis`.
- Legacy seeded editions keep working before resynthesis: frontend falls back when new fields absent.
- Score remains 0-10 internally for lifecycle deltas; UI shows labels, no meter.
- All new text fields bilingual (EN + ZH); thesis one sentence; narratives 3-4; at-a-glance 3-5.
- New vocab: priority {critical|high|medium|low}, momentum {accelerating|rising|stable|fading}, evidence {strong|moderate|emerging}, evidence status {confirmed|supported|emerging|interpretive}.

---

### Task 1: DB migration + upsert (P0)

**Files:**
- Modify: `backend/app/db.py`
- Test: `tests/test_db_schema.py` (new)

- [x] Add `_migrate(c)` — `PRAGMA table_info` guard → `ALTER TABLE agenda_topics ADD COLUMN priority/momentum/evidence TEXT, coverage INTEGER`; `ALTER TABLE narratives ADD COLUMN driver_en/driver_zh/why_en/why_zh/next_test_en/next_test_zh TEXT`. Call from `init_db()`.
- [x] Add `labelled_score(priority, momentum) -> int` mapping: critical 88, high 78, medium 68 + accelerating +6, rising +3, stable 0, fading -3, clamp 55..95.
- [x] `upsert_edition`: set `direction` = agenda item momentum when direction missing; `score` = labelled_score when missing; write new narrative columns.
- [x] Tests: migration idempotency on fresh DB (run init twice); round-trip persists priority/momentum/evidence/coverage + driver/why/next_test; labelled_score mapping table.

### Task 2: Evidence coverage digest (P1)

**Files:**
- Modify: `backend/app/analyze/evidence.py`, `backend/app/synth/weekly.py`
- Test: `tests/test_evidence.py` (new) — seeded week returns deterministic coverage dicts.

- [x] Extend `agenda_evidence()` to also return `topic_programmes` (topic -> sorted distinct show_names) and first/last seen dates per topic.
- [x] `_episode_digest`/prompt: append `## Coverage evidence` block, truncated.

### Task 3: Synthesis schema v2 + derivation (P0)

**Files:**
- Modify: `backend/app/synth/weekly.py`

- [x] SYSTEM text: editorial framing rules, no false precision, theory of narration, no repeating same development across sections, watchpoints include triggers.
- [x] SCHEMA text adds: `thesis_en/thesis_zh`; agenda topics get `priority/momentum/evidence/coverage` (keep `direction` + `score` legacy-compat); narratives get `driver_en/zh, why_en/zh, next_test_en/zh`; `comms_boxes[] {title_en/zh, implication_en/zh, questions_likely_en[], evidence_to_prepare_en[], risky_en} (+zh mirror)`; `question_groups[]` with category from {policy_credibility, market_consequences, corporate_exposure, narrative_durability}; `media_exchanges[]` (questioning pattern, media premise, response observed, internal lesson, likely to recur); `watchpoints[]` {trigger, possible_shift, affected, priority_raises_if}; `evidence_statuses[]` {section, status, note}.
- [x] `_derive_legacy(data)`: `recurring_questions_en/zh` = join of question groups (+ legacy lists preserved when provided); `watchlist_en/zh` = list of watchpoint triggers; `pr_counsel` 2x2 = aggregate from identity + comms boxes (risk = most severe risky, opportunity = comms gaps etc.); keep existing `interview_groups`.
- [x] `synthesize_week` calls `llm.chat_json(..., max_tokens=24000)` for weekly; apply `_derive_legacy` before `upsert_edition`; agenda score fallback to `db.labelled_score` in upsert.

### Task 4: QC v2 (P1)

**Files:**
- Modify: `backend/app/synth/qc.py`
- Test: `tests/test_qc_v2.py` + adjust `tests/test_api.py`

- [x] `topics_selected_dynamically`: 3 <= len <= 5 (done).
- [x] New checks (blocking when false): `thesis_present`, `narrative_arc_complete` (>=3 narratives with driver/why/next_test), `comms_boxes_present` (each agenda topic has a box), `category_vocab_ok`, `watchpoint_triggers_present`, `media_exchanges_complete`, `evidence_status_vocab`, `score_range`.
- [x] Keep legacy gates; `recurring_questions_present` count >= 3 (was >=6, since watch/questions now split).

### Task 5: Desk API (P1)

- `backend/app/api/routes.py` — desk returns new fields in `data`; no new blocking behavior. Legacy tolerance retained.

### Task 6: Frontend 7-section desk (P1)

**Files:**
- Modify: `web/static/app.js`, `web/static/styles.css`

- [x] `renderBrief`: remove radar/lifecycle/source/wire/anchor/tone panels. New order: hero (thesis), at a glance (labels), narrative shifts (arc + driver/why/next test), comms implications, questions group, media exchanges, watch next, compact evidence footer line.
- [x] Legacy fallback: if `thesis` no, fall back to `week_summary_en`; if comms missing, render `pr_counsel` as replacement.
- [x] CSS badge variants for priority/momentum/evidence; remove meter style usage.

### Task 7: resynth script (P2)

**Files:**
- Create: `scripts/resynth_weeks.py`

- [x] For each edition in DB: `synth.synthesize_week(start,end,force=True)`, then `qc.run_qc(eid)`; print results. Requires `DEEPSEEK_API_KEY`.

### Task 8: Tests, docs, verification (P2)

- [x] `pytest tests/ -q` green (suite ~25).
- [x] Resynthesize 3 seeded weeks; all QC PASS.
- [x] Manual: uvicorn desk renders 7 sections EN+中文; exports render.
- [x] README note for `scripts/resynth_weeks.py`.

## Review pass (code-review-and-quality)

- [x] Independent review: found + fixed `watchPanel` ReferenceError (7th section now defined), QC badge truthiness (`qc.status === "PASS"` in badge + hero), dead `a.lead_lag` render branch in `briefCard`.
- [x] QC status math covered by `tests/test_qc_v2.py` (7 synthetic cases: legacy/v2 clean, figure-mismatch blocking vs non-blocking, missing gates, topic-count gate).