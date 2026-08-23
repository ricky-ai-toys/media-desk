# Media Desk — Code Review Handoff (Aug 2026)

> Purpose: give a fresh AI agent the fastest possible path to review & iterate on
> the Media Desk codebase. This maps the architecture, the data flow, the
> key algorithms/logic, known friction points, and where the real code lives.
> Read this first, then open only the files you need to change.

---

## 1. What this system is

**Media Desk** = a web-first, bilingual (EN/中文) financial-media intelligence
dashboard. It ingests Bloomberg/CNBC Asia TV transcripts (YouTube) + wire RSS
(FT/Bloomberg/investing), runs LLM analysis per episode, synthesizes a weekly
bilingual editorial brief, gates it through a QC checklist, and exposes it via
a read-only API + TypeScript web shell. The weekly email + PDF are *exports*.

It is the web "command deck" evolution of an older v5 pipeline whose outputs
(weekly JSON/manifest/QC) are imported at seed time.

## 2. Stack

- **Backend:** Python 3.13, FastAPI, SQLite + FTS5, no ORM (raw SQL).
- **Frontend:** TypeScript, esbuild bundle → `web/static/dist/`, no framework,
  self-hosted fonts, zero-CLS newsprint layout.
- **LLM:** DeepSeek `deepseek-v4-flash` via OpenAI-compatible API
  (`config.ANALYSIS`, base `https://api.deepseek.com/v1`, key from
  `DEEPSEEK_API_KEY` env).
- **Ingestion:** `feedparser` (RSS wire) + `yt-dlp` (YouTube transcripts, VTT→text).
- **Serve:** systemd `media-desk.service` → uvicorn `127.0.0.1:8517` → Caddy
  vhost `media.ricky.study:8443` (Tailscale).

## 3. Directory map (read-only SKIM for orientation)

```
backend/app/
  main.py            FastAPI app factory, /export/{edition}/{csv|email|pdf}
  config.py          loads config/sources.yaml; env overrides (DB, transcripts, admin token)
  db.py              515 lines — the whole SQLite store. RAW-SQL heavy. Schema + migrations + queries.
  tokens.py          kw()/overlap() — keyword-set overlap used everywhere for topic matching.
  llm.py             DeepSeek client; chat() and chat_json() (json_object mode, strips ``` fences).
  seed.py            imports legacy v5 artifacts (raw transcripts, analyses, editions) into the DB.
  analyze/
    daily.py         per-episode LLM analysis → markdown + structured hot_topics/tension.
    evidence.py      extract_hot_topics, agenda_evidence, parse_tension, context/tonality, clustering, pressure_index.
  framing/
    engine.py        lifecycle tracks, framing collisions, lead-lag, coverage asymmetry (full heuristics).
  synth/
    weekly.py        THE weekly editorial synthesis — one big LLM JSON call (system prompt + schema v2).
    qc.py            QC gate (12+ v1 checks + v2 schema gates) → PASS/FAIL, blocks, status write.
  api/
    routes.py        public read-only endpoints (meta/desk/lifecycle/framing/interviews/radar/search/stream/editions/edition).
    admin.py         token-gated ingest/analyze/synthesize/qc triggers + _last_week() (Fri-to-Fri window).
    sse.py           Server-Sent Events pipeline stream.
  ingest/
    rss.py           feedparser → articles (headline/summary only; used for framing/lead-lag, never quotes).
    youtube.py       yt-dlp flat-playlist → title regex filter → caption fetch → VTT→text → chunks.
  export/
    media_export.py  agenda CSV + A4 print HTML + headless-chromium print-to-pdf.
    email.py         v5-layout-compatible bilingual HTML email template + subject.
scripts/
  resynth_weeks.py   force re-synthesize all editions to schema v2, run QC, print blocks.
config/sources.yaml  source catalog (kind: yt_playlist | rss), fetch/analysis/db/v5/web settings.
web/src/             TS: main.ts, api.ts(lib), views/BriefView(412)/SearchView, components, lib/*.
tests/               pytest suite (read-only, needs seeded data/media.db).
```

## 4. The pipeline (data flow — THE key mental model)

```
[yt-dlp playlist] ──synced──▶ episodes (+transcript chunks into transcript_fts)
[RSS feeds] ────────synced──▶ articles (+articles_fts)
        │
        ▼  POST /api/admin/analyze  (or daily timer)
[episodes without analyses] → daily.analyze_episode() → 1 LLM call per episode
        │                        → markdown + hot_topics[] + tension[] stored
        ▼  POST /api/admin/synthesize  (or weekly timer)
[agenda_evidence + interview_monitor + _episode_digest] → ONE LLM chat_json call
        │                        → schema-v2 edition data dict (see §6)
        ▼  POST /api/admin/qc/{edition}
[qc.run_qc()] → PASS → status="published" ;  FAIL → "needs_review" + blocks[]
        ▼
API (desk/lifecycle/framing/radar/search)  +  exports (email / PDF / CSV)
```

**Admin triggers are token-gated** (`X-Admin-Token`, `secrets.compare_digest`,
env `MEDIA_DESK_ADMIN_TOKEN`). Systemd timers: `media-desk-daily.timer` 01:00 HKT
(ingest+analyze), `media-desk-weekly.timer` Sat 00:00 HKT (synthesize+QC).

## 5. Key algorithms & logic (the meat — read these carefully)

### 5a. Keyword overlap matcher — `tokens.py` + `db.coverage_radar`
The system matches topics↔episodes **by keyword-set overlap**, not embeddings:
- `kw(text)` → set of lowercase `[a-z0-9]{3,}` words minus a stoplist (`china`,
  `market(s)`, `week`, pronouns…).
- `overlap(a,b)` = `|a∩b| / min(|a|,|b|)`. Thresholds: framing ≥0.4–0.5,
  coverage radar ≥0.4. **This is the single most reused heuristic** and a likely
  precision-vs-recall tuning point (short fuzzy topics → false matches).
- Lifecycle `_tracks` greedily chains topics across editions whenever overlap ≥0.4,
  merging keyword sets forward (union). This determines "is this the same story
  as last week" — sensitive to threshold.

### 5b. Framing analytics — `framing/engine.py`
- **norm10(score):** legacy data mixed 0–10 and 0–100 scores → normalize /10.
- **collisions():** per topic, gather analyses whose title overlaps ≥0.5; parse
  a `Tone|Sentiment: ±N` score out of each markdown (`_tone_score` regex);
  if spread between max/min ≥3 across ≥2 scored episodes → flag clash w/ extreme bull & bear.
- **lead_lag():** per agenda topic, first TV mention vs first wire mention, wire lead in days.
- **asymmetry():** which shows carried every topic → mark shows that *didn't* carry a top topic (blind spots).

### 5c. Evidence extractors — `analyze/evidence.py`
- `extract_hot_topics(md)`: regex `## 2. Hot Topics`, pulls `**N. Title**`, splits ` / `, keeps 8–200 char titles.
- `parse_tension(md)`: regexes for the `## 5. Anchor–Guest Tension` block model (Anchor question / Guest reply / Tension point).
- `classify_tone`: keyword battery → `challenging | evasive | supportive | exploratory`.
- `cluster_questions`: greedy clustering of interview questions by keyword overlap (min_share 0.5), sample top-6 clusters.
- `pressure_index(entries)`: per (date, show) → `pressure = (challenges + 0.5*evasions) / n`.
- **These regex parsers assume the exact LLM markdown outline in `daily.DAILY_OUTLINE`.** If the outline format changes, these break — a tightly-coupled fragile spot.

### 5d. The weekly LLM synthesis — `synth/weekly.py` ★
The editorial brain. `SYSTEM` prompt encodes editorial rules:
- ONE thesis naming the week's tension (≤25 words).
- Rank topics by editorial significance (prominence/momentum/reach/persistence), NOT mention count; each topic gets `priority(critical|high|medium)`, `momentum(accelerating|rising|stable|fading)`, `evidence(strong|moderate|emerging)`, `coverage(int)`.
- Narratives carry: `from→to` frame, `driver` (what changed), `why it matters`, `next_test`.
- Watchpoints must name trigger/shift/affected/priority_raises.
- ZH must read as idiomatic mainland financial-desk Chinese, not word-for-word translation.
- Hard counts: **EXACTLY 3–5 agenda topics, EXACTLY 3–4 narratives, 3 media_exchanges, 3–5 watchpoints**, recurring groups 3–5 qs each.
- `SCHEMA` string is the JSON contract (v2 superset). `synthesize_week()` builds a lean context (evidence counts + episode digests truncated) and makes **ONE** `chat_json` call (`max_tokens=24000`), then `_derive_legacy()` back-fills v1-compatible fields (`week_summary`, `recurring_questions_*`, `pr_counsel`, `watchlist_*`) so legacy email/PDF/QC keep working.
- NOTE: the synthesis prompt is huge context for one call; cost/latency/failure handling is a real constraint (no retry, no chunking across a week).

### 5e. QC gate — `synth/qc.py`
Runs after synthesis. Distinguishes **legacy** (seeded v1: no `thesis_en`/`comms_boxes`) vs **v2**.
- v1 blocking set (`blocking` tuple): dynamic topics, exact report name, EN/ZH figures align, bilingual blocks, thesis, narratives, etc.
- v2 extra gates via `add_v2` (skipped if legacy): thesis, narrative arc, comms boxes, question-group vocab, watchpoint triggers, media exchanges, evidence-status vocab, agenda labels, topic facts, week-ahead window.
- `_figures_align` compares the **set** of numbers in ALL `_en` fields vs `_zh` fields (excludes `{13,17,7,2026}`). This is a blunt EN/ZH parity check — numeric-only.
- Publish gate: no blocks AND (all blockable checks pass). Status written back to DB.

### 5f. Daily per-episode analysis — `analyze/daily.py`
`DAILY_OUTLINE` is the 7-section markdown contract (header / hot topics / reporting frame incl. verbatim quotes + sentiment scores / corporate voices table / anchor-guest tension / forecasting push / agenda signal). `_hot_topics`/`_tension` re-parse that markdown back into structured rows.

### 5g. Ingestion — `ingest/youtube.py` + `ingest/rss.py`
- **YouTube:** `yt-dlp --flat-playlist` (30 rows) → match `title_regex` (e.g. `The Asia Trade \d{1,2}/\d{1,2}/\d{4}`) → parse date from title (tries `%m/%d` then `%d/%m`) or `upload_date` → enforce 7-day lookback → if new, `fetch_transcript` (yt-dlp auto-subs → VTT → plain text, min 500 words) → store chunks.
- **RSS:** feedparser → title/summary (summary capped 600 chars) → `INSERT OR IGNORE` by unique `link`.

### 5h. DB layer — `backend/app/db.py`
- Raw SQL, FTS5 virtual tables fed by **triggers** (`chunks_ai`/`articles_ai` on INSERT), WAL mode, foreign_keys on.
- `edition` id = `"{start_date}_to_{end_date}"` (YYYY-MM-DD). `upsert_edition` rewrites agenda/narratives/interview_groups wholesale (DELETE + INSERT) each save.
- Data is stored JSON (`data_json`, `qc_json`, `manifest_json`) plus denormalized relational rows for agenda/narratives/groups — dual representation; keep in sync.
- `_migrate()` runs guarded column adds (schema v2 evolution) + fixes the historical analyses-dedupe bug (unique index on episode_id).
- `_fts_query()` sanitizes free-text → quoted-AND terms so FTS5 can't throw on user input.

## 6. Schema-v2 edition payload (what `weekly.synthesize_week` produces)

Top-level keys — **know this contract before editing exports/QC**:
`report_title, start_date, end_date, monitored_outlets[], source_file_count,
episode_count, thesis_en/zh, agenda_topics[] {rank,title_en/zh,summary_en/zh,
priority,momentum,evidence,coverage,driver_en/zh,next_test_en/zh,stakes_en/zh},
narratives[] {title_*, from_*, to_*, driver_*, why_*, next_test_*},
comms_boxes[] {title, implication, questions_likely[], evidence_to_prepare[], risky, +zh},
question_groups[] {category(policy_credibility|market_consequences|corporate_exposure|narrative_durability), questions_en[], questions_zh[]},
top_questions_next_week_en/zh[], media_exchanges[] {pattern,premise,response,lesson,likely_to_recur,+zh},
watchpoints[] {trigger,shift,affected,priority_raises,+zh}, week_ahead_events[]
{date(YYYY-MM-DD, strictly next Mon–Fri),event_en/zh,why_en/zh}, evidence_statuses[]
{section,status(confirmed|supported|emerging|interpretive),note},
interview_groups_en[] {title_en,role_en,questions_en[3]}, interview_groups_zh[],
pr_counsel {risk/opportunity/prepare/avoid x en/zh}, watchlist_en/zh[],
recurring_questions_en/zh[], warnings[]`.

## 7. Exports (deliverable surfaces — email/PDF get handed to external PR clients)

- **email.py `render_email`**: gradient hero + meta strip (programs/strands/days/outlets),
   agenda cards (rank, EN title, momentum badge, 22-word summary), narrative shift table,
   interview question groups, PR counsel 2×2 (risk/opportunity/prepare/avoid), then a ZH
   mirror panel (blue banner declares it's an editorial adaptation, not literal translation).
   `first_sentence()` truncates to n words. `email_subject()` = standard title + dates.
- **media_export.py**: `agenda_csv`, `interviews_csv`, `print_html` (full A4: email body +
   source-inventory appendix + methodology + QC dump), `pdf_from_html` via headless chromium
   (`google-chrome`/`chromium`, tries `--headless=new` then `--headless`, ≥1000-byte = ok).
   `main.py _pdf_fresh` reuses a rendered PDF unless the edition was updated after it.

## 8. Known friction points / probable iteration targets (from reading the code)

1. **Keyword-overlap matching** (§5a) is binary and fuzzy — no embeddings, no weighted
   terms, thresholds hand-tuned. Collisions/lead-lag/attribution/lifecycle all inherit its
   precision/recall tradeoffs. High-value upgrade area.
2. **Regex ↔ LLM-markdown coupling** (§5c/5f): every structured field is carved out of the
   LLM's prose with brittle regexes on an assumed exact outline. If model output drifts, the
   pipeline silently yields empty topics/tension. No schema enforcement on the daily pass
   (the weekly pass does use `json_object` mode). Could add a machine-parseable JSON layer
   to the daily analysis too.
3. **Single monolithic weekly LLM call** (§5d): everything synthesized in one 24k-token
   call. No retry/backoff, no per-section delegation, failure = entire week lost. The docstring
   says "chunked delegations" but the code makes **one** call — worth aligning code to intent.
4. **`_figures_align` EN/ZH parity** (§5e) compares number *sets* across all `_en` vs `_zh`
   fields — can false-block when a figure legitimately appears in only one language.
5. **Dual data representation** (§5h): edition JSON + redundant relational rows. Any new
   field must be added to both `upsert_edition` and the `edition_full` read path.
6. **No auth/rate-limit on analytics cost**: admin analyze runs up to 20 LLM calls per hit;
   synth is one 24k-token call. Only a static admin token protects it.
7. **`raw root /editions_root` hardcoded paths** in config point to an older
   `~/workspace/yt-weekly/` tree — seed is a one-time migration path, not a live source.

## 9. How to run / verify

```bash
cd ~/workspace/media-desk
.venv/bin/python -m pytest tests/ -q            # needs seeded data/media.db (present)
MEDIA_DESK_ADMIN_TOKEN=dev DEEPSEEK_API_KEY=$KEY \
  .venv/bin/python -m uvicorn backend.wsgi:app --port 8517   # then curl /api/*, admin triggers
.venv/bin/python -m backend.app.seed --all       # idempotent import
.venv/bin/python scripts/resynth_weeks.py        # re-synth all + QC each
# exports: GET /export/{edition}/{csv|email|pdf}
```

Current DB state (seeded): `editions=4, episodes=58, analyses=58, articles=613,
agenda_topics=20, interview_entries=102, narratives=16`. Git: single commit
`f0dbd8c feat: media desk v5 web command deck`, working tree has uncommitted
iterations (README, admin, routes, db, exports, ingests all modified since last commit).

## 10. Where the "v5" legacy prompts/layouts live

- Old pipeline roots (raw/analysis/editions) under `config.V5`: `~/workspace/yt-weekly/*`.
- The standing skill that *generates* the old weekly: skill
  `burson-international-financial-media-weekly` (`config.V5.skill_root`). Media Desk
  supersedes it for the web; the email/PDF layouts are kept byte-compatible with its output.
