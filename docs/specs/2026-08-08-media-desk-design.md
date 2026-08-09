# Media Desk — Design Spec (2026-08-08)

## 1. Purpose
Turn the v5 weekly newsletter pipeline into a self-serve, web-first, bilingual
intelligence desk. Email/PDF are demoted to exports; the web dashboard is the
primary surface.

## 2. Principles
- **Web-first**: every insight available as JSON + rendered in the deck; exports
  are one-click, not a separate product.
- **Daily, not live**: one ingest+analyze pulse per day; synthesis once per
  week (Sat). Deterministic refreshes, not streaming commentary.
- **Command-deck UX**: terminal-style concern for media watchers — fast
  scannable panels, hot signals, EN/中文 toggle.
- **Novel primitives over more content**: cameras on *how* the story is told
  across programs and weeks (framing), not just what was said.

## 3. Dataset model (SQLite + FTS5)
- `sources` (rss / yt_playlist) → `episodes` → `transcript_chunks` + FTS5 mirror
- `articles` + FTS5 (wire)
- `analyses` (LLM daily digests per episode)
- `editions` (weekly bundles) → `agenda_topics`, `narratives`,
  `interview_groups`, `interview_entries`
- `frames` (lifecycle snapshots), `pressure` (anchor-pressure index),
  `source_runs`, `pipeline_state`

## 3. Analytics primitives (the "six novel bits")
1. **Agenda lifecycle** — multi-week tracks: first/last seen, phase, weekly
   rank & score deltas (`framing/engine.lifecycle`).
2. **Framing collisions** — same event told differently by different shows
   (`clash` groups with paired Q&A evidence).
3. **Lead/lag** — TV-first vs wire-first per topic, days-gap.
4. **Coverage asymmetry** — hot topic present in some shows, absent in others.
5. **Anchor-pressure index** — per-guest tone score aggregated per program
   (`analyze/evidence.pressure_index`).
6. **Interview mining** — auto question clustering → recurring-question
   detection (`cluster_questions`).

## 4. Pipeline (systemd timers)
- Daily 01:00 HKT: `ingest` (RSS + playlists) then `analyze` (LLM on new episodes).
- Sat 00:00 HKT: `synthesize` (week bundle + narratives + interviews) then `qc`.
- QC = v5 12-point gate; blocks publish on failure.

## 5. Deployment
- systemd `media-desk.service` (uvicorn, 127.0.0.1:8517), Restart=always.
- Caddy vhost `media.ricky.study:8443` (Tailscale plane; `tls internal` until
  public DNS exists).
- Admin APIs token-gated (`X-Admin-Token`, root-only env file).

## 6. Decisions deferred (explicit non-goals)
- No user accounts; single public deck + one admin key.
- No live TV streaming; daily pull only.
- CNBC Asia TV: kept off air until a reliable full-episode playlist exists.
- LLM cost kept small: chunk summaries reduced; weekly synthesis uses digest
  context (~2k words).

## 7. Verification
- `pytest tests/` — read-only API + QC gate suite (17 passing).
- Headless-Chromium render checks for the web deck.