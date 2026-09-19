# Media Desk — International Financial Media Command Deck

Web-first, bilingual (EN/中文) media-intelligence dashboard built on the v5 weekly
pipeline: agenda lifecycle, framing collisions, anchor-pressure & interview
mining, multi-source wire coverage (Bloomberg / CNBC / FT / wire), with the
weekly email + PDF demoted to exports.

## Stack

- Backend: Python 3.13, FastAPI, SQLite + FTS5 (no ORM)
- Frontend: TypeScript components (Header / EditionSwitcher / ReadingContainer /
  Footer) bundled with esbuild into `web/static/dist/` — newsprint editorial
  layout, self-hosted fonts (Newsreader / IBM Plex, no CDN), zero-CLS
- LLM: DeepSeek `deepseek-v4-flash` (official API) for daily episode analysis
  and weekly synthesis
- Ingestion: RSS feeds (feedparser) + YouTube playlists (yt-dlp)
- Serving: systemd `media-desk.service` → uvicorn on 127.0.0.1:8517 →
  Caddy vhost `media.ricky.study:8443` (Tailscale HTTPS)

## Frontend build

```bash
cd web
npm install                 # once; build/typecheck/watch scripts
npm run build               # bundle -> web/static/dist (fonts included)
npm run watch               # rebuild on change
npm run typecheck           # tsc --noEmit
```

## Quick start

```bash
cd ~/workspace/media-desk
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
MEDIA_DESK_ADMIN_TOKEN=dev-secret DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY \
  .venv/bin/python -m uvicorn backend.wsgi:app --port 8517
# open http://localhost:8517
```

Seeding (imports the three historical v5 weeks from `~/workspace/yt-weekly/burson-weekly/`):

```bash
.venv/bin/python backend/app/seed.py     # idempotent, merges editions
```

## API layout

| Endpoint | Purpose |
|---|---|
| `GET /api/meta` | latest edition, edition list, source health, pipeline state |
| `GET /api/desk?edition=` | one-edition briefing (agenda, narratives, framing, guests, ticker) |
| `GET /api/lifecycle` | multi-week agenda tracks (label, phase, rank/score deltas) |
| `GET /api/framing?edition=` | collisions (clash/era pairs), lead-lag, asymmetry |
| `GET /api/interviews` | guest log (tone-tagged, filterable) |
| `GET /api/radar` | source health, episode coverage, wire feed |
| `GET /api/search?q=` | FTS5 across transcripts + wire articles |
| `GET /api/stream` | SSE pipeline events |
| `GET /export/{edition}/{csv\|email\|pdf}` | exports |
| `POST /api/admin/{ingest,analyze,synthesize}` /`api/admin/qc/{edition}` | token-gated (`X-Admin-Token`) |

## Scheduler (systemd timers)
- `media-desk-daily.timer` — every 01:00 HKT: wire ingest + LLM analysis of new episodes
- `media-desk-weekly.timer` — Sat 00:00 HKT: synthesize current week + run QC gate

Scripts: `/usr/local/bin/media-desk-{daily,weekly}.sh`; admin token in
`/etc/media-desk-admin-token` (root-only, `MEDIA_DESK_ADMIN_TOKEN=…` +
`DEEPSEEK_API_KEY=…`).

## QC gate
Follows the v5 12-point checklist (reporting period, coverage, source manifest,
agenda selection, narratives, recurring interview questions, EN/ZH alignment,
name accuracy, bilingual completeness, legal-block words), extended with
schema-v2 gates: thesis, narrative arc, comms boxes, question-group vocab,
watchpoint triggers, media exchanges, evidence-status vocabulary and
priority/momentum/evidence labels on agenda topics. On v2 editions the
EN/ZH figure-parity check is informational (ZH side is editorial, not a
mechanical translation).

## Re-synthesis (schema v2)
Seeded v1 editions are re-synthesized to the v2 weekly brief (see
`docs/superpowers/plans/2026-08-09-weekly-brief-iteration.md` for the schema
diff). Requires `DEEPSEEK_API_KEY`:

```bash
.venv/bin/python scripts/resynth_weeks.py            # all editions
.venv/bin/python scripts/resynth_weeks.py --edition <edition-id>  # one
```

Each edition is re-synthesized then immediately run through the QC gate;
any blocked edition prints its blocks and stays non-published.

## Tests
```bash
.venv/bin/python -m pytest tests/ -q
```
The suite is self-contained: `tests/conftest.py` auto-builds a synthetic fixture
DB via `scripts/make_fixture_db.py` on first run (no production data needed).
It covers meta/desk/lifecycle/framing/radar/search/edition/export endpoints,
search FTS, auth guards, the QC gate, synthesis integrity (server-side evidence
overrides, LLM retry/failure markers) and lifecycle chaining rules.

## Source verification
`scripts/verify_sources.py` checks a playlist's resolution, title matching,
date obtainability (title date, flat-playlist upload_date, or the batched
probe) and caption download before GO:
```bash
.venv/bin/python scripts/verify_sources.py                     # disabled candidates
.venv/bin/python scripts/verify_sources.py cnbc_squawk_box_us  # re-check a live source
```
Status (2026-09-19):
- `bloomberg_asia_trade` / `bloomberg_china_show` / `bloomberg_insight` —
  clip-mode: dated full-episode uploads stopped 2026-09-08/09; daily undated
  clips are ingested via the date-probe path and surface as "(segment clips)".
- `cnbc_squawk_box_asia` / `cnbc_squawk_box_us` — enabled clip-mode sources.
- `cnbc_china_connection` / `cnbc_street_signs_asia` — retired 2026-09: CNBC
  closed its Hong Kong bureau and cancelled these shows; removed from the catalog.
- CNBC "Watch In Full" full-episode playlists are country-locked against this
  egress — set a `proxy_url` and re-run verify_sources before enabling.

## Report spec
Section counts, vocabularies and word budgets live in
`backend/app/synth/report_spec.py` — the single source of truth consumed by
both the synthesis prompt and the QC gate. Change numbers there, nowhere else.

## Notes
- `tls internal` is used at the Caddy vhost until a public DNS record for
  `media.ricky.study` exists; browsers will warn on the CA. Point the record at
  this host and remove `tls internal` for a Let's Encrypt cert.
- /etc/hosts line `127.0.0.1 media.ricky.study` is used for local CLI/dev
  access; delete it if you move to public DNS.
- PDF export renders via headless Chrome with `--no-sandbox` (required when the
  service runs as root); it only ever prints server-generated HTML, never
  remote input.
- CNBC Asia TV full episodes are re-run unless the playlist becomes available.