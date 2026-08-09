"""SQLite store for Media Desk. Single writer via connection-per-call (WAL)."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY, name TEXT, outlet TEXT, kind TEXT, cfg_json TEXT, enabled INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS episodes (
  id TEXT PRIMARY KEY, source_id TEXT REFERENCES sources(id), external_id TEXT,
  title TEXT, show_name TEXT, pub_date TEXT, url TEXT, kind TEXT DEFAULT 'yt',
  words INTEGER DEFAULT 0, fetched_at TEXT, transcript_path TEXT
);
CREATE TABLE IF NOT EXISTS transcript_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, episode_id TEXT REFERENCES episodes(id),
  seq INTEGER, text TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
  text, content='transcript_chunks', content_rowid='id'
);
CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT REFERENCES sources(id),
  title TEXT, link TEXT UNIQUE, summary TEXT, pub_date TEXT, author TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  title, summary, content='articles', content_rowid='id'
);
CREATE TABLE IF NOT EXISTS analyses (
  id INTEGER PRIMARY KEY AUTOINCREMENT, episode_id TEXT REFERENCES episodes(id),
  markdown TEXT, hot_topics_json TEXT, tension_json TEXT, generated_at TEXT
);
CREATE TABLE IF NOT EXISTS editions (
  id TEXT PRIMARY KEY, start_date TEXT, end_date TEXT, status TEXT DEFAULT 'published',
  data_json TEXT, manifest_json TEXT, qc_json TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS agenda_topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT REFERENCES editions(id),
  rank INTEGER, title_en TEXT, title_zh TEXT, summary_en TEXT, summary_zh TEXT,
  direction TEXT, score INTEGER, priority TEXT, momentum TEXT, evidence TEXT,
  coverage INTEGER
);
CREATE TABLE IF NOT EXISTS narratives (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT REFERENCES editions(id),
  idx INTEGER, title_en TEXT, title_zh TEXT, from_en TEXT, to_en TEXT,
  from_zh TEXT, to_zh TEXT, analysis_en TEXT, analysis_zh TEXT,
  driver_en TEXT, driver_zh TEXT, why_en TEXT, why_zh TEXT,
  next_test_en TEXT, next_test_zh TEXT
);
CREATE TABLE IF NOT EXISTS interview_groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT REFERENCES editions(id),
  idx INTEGER, title_en TEXT, title_zh TEXT, role_en TEXT, role_zh TEXT,
  questions_en_json TEXT, questions_zh_json TEXT
);
CREATE TABLE IF NOT EXISTS interview_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT REFERENCES editions(id),
  guest TEXT, org TEXT, role TEXT, show TEXT, date TEXT, tone TEXT,
  questions_json TEXT, quotes_json TEXT, confidence REAL
);
CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, kind TEXT,
  started_at TEXT, ended_at TEXT, ok INTEGER, found INTEGER, detail TEXT
);
CREATE TABLE IF NOT EXISTS pipeline_state (
  id INTEGER PRIMARY KEY CHECK (id = 1), stage TEXT, status TEXT,
  target_week TEXT, message TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT REFERENCES editions(id),
  topic TEXT, frame_a_json TEXT, frame_b_json TEXT, evidence_json TEXT
);
CREATE TABLE IF NOT EXISTS pressure (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT REFERENCES editions(id),
  guest_type TEXT, show TEXT, pressure REAL, challenges INTEGER,
  softballs INTEGER, evasions INTEGER, sampled INTEGER
);
CREATE INDEX IF NOT EXISTS idx_chunks_ep ON transcript_chunks(episode_id);
CREATE INDEX IF NOT EXISTS idx_agenda_ed ON agenda_topics(edition_id);
CREATE INDEX IF NOT EXISTS idx_entries_ed ON interview_entries(edition_id);
"""

TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON transcript_chunks BEGIN
  INSERT INTO transcript_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON transcript_chunks BEGIN
  INSERT INTO transcript_fts(transcript_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid, title, summary) VALUES (new.id, new.title, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts, rowid, title, summary) VALUES ('delete', old.id, old.title, old.summary);
END;
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def labelled_score(priority: str, momentum: str | None = None) -> int:
    """Deterministic internal 0-10 editorial-weight fallback for lifecycle deltas
    (UI shows priority/momentum labels; the number is kept only for legacy tracks)."""
    base = {"critical": 88, "high": 78, "medium": 68, "low": 58}
    adj = {"accelerating": 6, "rising": 3, "stable": 0, "fading": -3}
    v = base.get((priority or "").lower(), 68) + adj.get((momentum or "").lower(), 0)
    return max(55, min(95, v))


_MIGRATIONS = [
    "ALTER TABLE agenda_topics ADD COLUMN priority TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN momentum TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN evidence TEXT",
    "ALTER TABLE agenda_topics ADD COLUMN coverage INTEGER",
    "ALTER TABLE narratives ADD COLUMN driver_en TEXT",
    "ALTER TABLE narratives ADD COLUMN driver_zh TEXT",
    "ALTER TABLE narratives ADD COLUMN why_en TEXT",
    "ALTER TABLE narratives ADD COLUMN why_zh TEXT",
    "ALTER TABLE narratives ADD COLUMN next_test_en TEXT",
    "ALTER TABLE narratives ADD COLUMN next_test_zh TEXT",
]


def _migrate(c) -> None:
    """PRAGMA-guarded column adds so existing DBs pick up schema v2."""
    for stmt in _MIGRATIONS:
        parts = stmt.split()
        table, col = parts[2], parts[5]
        cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]
        if col not in cols:
            c.execute(stmt)


@contextmanager
def conn():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
        c.executescript(TRIGGERS)
        _migrate(c)
    sync_sources()
    upsert_pipeline("bootstrap", "idle", "database initialised")


def sync_sources():
    for s in config.SOURCES.values():
        upsert_source(s)


def upsert_pipeline(stage, status, message, target_week=None):
    with conn() as c:
        c.execute(
            "INSERT INTO pipeline_state (id, stage, status, target_week, message, updated_at) "
            "VALUES (1, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET stage=excluded.stage, status=excluded.status, "
            "target_week=excluded.target_week, message=excluded.message, updated_at=excluded.updated_at",
            (stage, status, target_week, message, utcnow()),
        )


def get_pipeline():
    with conn() as c:
        row = c.execute("SELECT * FROM pipeline_state WHERE id=1").fetchone()
        return dict(row) if row else None


def upsert_source(source: dict):
    with conn() as c:
        c.execute(
            "INSERT INTO sources (id, name, outlet, kind, cfg_json, enabled) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, outlet=excluded.outlet, "
            "kind=excluded.kind, cfg_json=excluded.cfg_json, enabled=excluded.enabled",
            (source["id"], source["name"], source["outlet"], source["kind"],
             json.dumps(source, ensure_ascii=False), 1),
        )


def upsert_episode(ep: dict) -> str:
    with conn() as c:
        c.execute(
            "INSERT INTO episodes (id, source_id, external_id, title, show_name, pub_date, url, "
            "kind, words, fetched_at, transcript_path) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, words=excluded.words, "
            "fetched_at=excluded.fetched_at, transcript_path=excluded.transcript_path",
            (ep["id"], ep.get("source_id"), ep.get("external_id", ep["id"]), ep.get("title", ""),
             ep.get("show_name", ""), ep.get("pub_date", ""), ep.get("url", ""), ep.get("kind", "yt"),
             ep.get("words", 0), utcnow(), ep.get("transcript_path")),
        )
        return ep["id"]


def replace_chunks(episode_id: str, chunks: list[str]):
    with conn() as c:
        c.execute("DELETE FROM transcript_chunks WHERE episode_id=?", (episode_id,))
        c.executemany(
            "INSERT INTO transcript_chunks (episode_id, seq, text) VALUES (?,?,?)",
            [(episode_id, i, t) for i, t in enumerate(chunks)],
        )


def upsert_article(a: dict) -> bool:
    with conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO articles (source_id, title, link, summary, pub_date, author) "
            "VALUES (?,?,?,?,?,?)", (a["source_id"], a["title"], a["link"], a.get("summary", ""),
                                     a.get("pub_date", ""), a.get("author", "")))
        return cur.rowcount > 0


def upsert_analysis(episode_id: str, markdown: str, hot_topics: list | None, tension: list | None):
    with conn() as c:
        c.execute(
            "INSERT INTO analyses (episode_id, markdown, hot_topics_json, tension_json, generated_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(id) DO NOTHING",
            (episode_id, markdown,
             json.dumps(hot_topics or [], ensure_ascii=False),
             json.dumps(tension or [], ensure_ascii=False), utcnow()),
        )


def upsert_edition(data: dict, manifest: dict | None, qc: dict | None) -> str:
    edition_id = f"{data['start_date']}_to_{data['end_date']}"
    with conn() as c:
        c.execute(
            "INSERT INTO editions (id, start_date, end_date, status, data_json, manifest_json, qc_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET status=excluded.status, data_json=excluded.data_json, "
            "manifest_json=excluded.manifest_json, qc_json=excluded.qc_json, created_at=excluded.created_at",
            (edition_id, data["start_date"], data["end_date"],
             "published" if qc and qc.get("status") == "PASS" else "needs_review",
             json.dumps(data, ensure_ascii=False),
             json.dumps(manifest or {}, ensure_ascii=False),
             json.dumps(qc or {}, ensure_ascii=False), utcnow()))
        c.execute("DELETE FROM agenda_topics WHERE edition_id=?", (edition_id,))
        for t in data.get("agenda_topics", []):
            c.execute(
                "INSERT INTO agenda_topics (edition_id, rank, title_en, title_zh, summary_en, summary_zh, direction, score, priority, momentum, evidence, coverage) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (edition_id, t.get("rank"), t.get("title_en", ""), t.get("title_zh", ""),
                 t.get("summary_en", ""), t.get("summary_zh", ""),
                 t.get("direction") or t.get("momentum", ""),
                 t.get("score") if t.get("score") is not None else labelled_score(
                     t.get("priority", ""), t.get("momentum", "")),
                 t.get("priority", ""), t.get("momentum", ""),
                 t.get("evidence", ""), t.get("coverage")))
        c.execute("DELETE FROM narratives WHERE edition_id=?", (edition_id,))
        for i, n in enumerate(data.get("narratives", [])):
            c.execute(
                "INSERT INTO narratives (edition_id, idx, title_en, title_zh, from_en, to_en, from_zh, to_zh, analysis_en, analysis_zh, driver_en, driver_zh, why_en, why_zh, next_test_en, next_test_zh) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (edition_id, i, n.get("title_en", ""), n.get("title_zh", ""), n.get("from_en", ""),
                 n.get("to_en", ""), n.get("from_zh", ""), n.get("to_zh", ""),
                 n.get("analysis_en", ""), n.get("analysis_zh", ""),
                 n.get("driver_en", ""), n.get("driver_zh", ""),
                 n.get("why_en", ""), n.get("why_zh", ""),
                 n.get("next_test_en", ""), n.get("next_test_zh", "")))
        c.execute("DELETE FROM interview_groups WHERE edition_id=?", (edition_id,))
        for i, g in enumerate(data.get("interview_groups_en", [])):
            z = data.get("interview_groups_zh", [])
            zh = z[i] if i < len(z) else {}
            c.execute(
                "INSERT INTO interview_groups (edition_id, idx, title_en, title_zh, role_en, role_zh, questions_en_json, questions_zh_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (edition_id, i, g.get("title_en", ""), zh.get("title_zh", ""),
                 g.get("role_en", ""), zh.get("role_zh", ""),
                 json.dumps(g.get("questions_en", []), ensure_ascii=False),
                 json.dumps(zh.get("questions_zh", []), ensure_ascii=False)))
    return edition_id


def replace_interview_entries(edition_id: str, entries: list[dict]):
    with conn() as c:
        c.execute("DELETE FROM interview_entries WHERE edition_id=?", (edition_id,))
        c.executemany(
            "INSERT INTO interview_entries (edition_id, guest, org, role, show, date, tone, questions_json, quotes_json, confidence) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(edition_id, e.get("guest", ""), e.get("org", ""), e.get("role", ""),
              e.get("show", ""), e.get("date", ""), e.get("tone", ""),
              json.dumps(e.get("questions", []), ensure_ascii=False),
              json.dumps(e.get("notable_quotes", []), ensure_ascii=False),
              e.get("confidence", 0.0)) for e in entries])


def log_source_run(source_id: str, kind: str, ok: bool, found: int, detail: str):
    with conn() as c:
        c.execute(
            "INSERT INTO source_runs (source_id, kind, started_at, ended_at, ok, found, detail) "
            "VALUES (?,?,?,?,?,?,?)",
            (source_id, kind, utcnow(), utcnow(), int(ok), found, detail))


def query_fts(q: str, limit: int = 30) -> list[dict]:
    out = []
    with conn() as c:
        rows = c.execute(
            "SELECT e.id AS episode_id, e.title, e.pub_date, e.show_name, s.name AS source_name, "
            "snippet(transcript_fts, 0, '[', ']', '…', 12) AS snip "
            "FROM transcript_fts "
            "JOIN transcript_chunks tc ON tc.id = transcript_fts.rowid "
            "JOIN episodes e ON e.id = tc.episode_id JOIN sources s ON s.id = e.source_id "
            "WHERE transcript_fts MATCH ? ORDER BY rank LIMIT ?", (q, limit)).fetchall()
        for r in rows:
            out.append({"kind": "transcript", **dict(r)})
        rows = c.execute(
            "SELECT a.title, a.link, a.pub_date, s.name AS source_name, "
            "snippet(articles_fts, 0, '[', ']', '…', 12) AS snip "
            "FROM articles_fts "
            "JOIN articles a ON a.id = articles_fts.rowid "
            "JOIN sources s ON s.id = a.source_id "
            "WHERE articles_fts MATCH ? ORDER BY rank LIMIT ?", (q, limit)).fetchall()
        for r in rows:
            out.append({"kind": "wire", **dict(r)})
    return out


def latest_edition() -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM editions ORDER BY end_date DESC LIMIT 1").fetchone()
        return dict(row) if row else None


def edition_full(eid: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM editions WHERE id=?", (eid,)).fetchone()
        if not row:
            return None
        out = dict(row)
        out["data"] = json.loads(out.pop("data_json"))
        out["manifest"] = json.loads(out.pop("manifest_json") or "{}")
        out["qc"] = json.loads(out.pop("qc_json") or "{}")
        out["agenda"] = [dict(r) for r in c.execute(
            "SELECT * FROM agenda_topics WHERE edition_id=? ORDER BY rank", (eid,))]
        out["narratives"] = [dict(r) for r in c.execute(
            "SELECT * FROM narratives WHERE edition_id=? ORDER BY idx", (eid,))]
        out["interview_groups"] = []
        for r in c.execute("SELECT * FROM interview_groups WHERE edition_id=? ORDER BY idx", (eid,)):
            g = dict(r)
            g["questions_en"] = json.loads(g.pop("questions_en_json") or "[]")
            g["questions_zh"] = json.loads(g.pop("questions_zh_json") or "[]")
            out["interview_groups"].append(g)
        return out


def agenda_series() -> list[dict]:
    """Cross-edition agenda lifecycle: one row per topic per edition."""
    with conn() as c:
        rows = c.execute(
            "SELECT a.*, e.start_date, e.end_date FROM agenda_topics a "
            "JOIN editions e ON e.id = a.edition_id ORDER BY e.end_date, a.rank").fetchall()
        return [dict(r) for r in rows]


_BRACKET = re.compile(r"\[[^\]]*\]")
_PLACEHOLDER = ("unverified", "tbd", "placeholder", "unknown", "[firm")


def _clean_guest(d: dict) -> None:
    """Strip editorial placeholders/annotations that leaked into guest fields."""
    guest = _BRACKET.sub("", d.get("guest") or "").strip()
    guest = re.sub(r"\s+", " ", guest)
    d["guest"] = guest or None
    for k in ("org", "role"):
        v = (d.get(k) or "").strip()
        if not v.startswith(("[", "?")) and not v.lower().startswith(_PLACEHOLDER) and len(v) >= 2:
            d[k] = v
        else:
            d[k] = None
    for i, q in enumerate(list(d.get("questions") or [])):
        if isinstance(q, dict) and q.get("q"):
            q["q"] = _BRACKET.sub("", str(q["q"])).strip()
            d["questions"][i] = q


def interview_entries(edition_id: str | None = None, q: str | None = None,
                      guest_type: str | None = None, limit: int = 200) -> list[dict]:
    sql = ("SELECT ie.*, e.start_date, e.end_date FROM interview_entries ie "
           "JOIN editions e ON e.id = ie.edition_id WHERE 1=1")
    args = []
    if edition_id:
        sql += " AND ie.edition_id=?"
        args.append(edition_id)
    if guest_type:
        sql += " AND (ie.role LIKE ? OR ie.guest LIKE ?)"
        args += [f"%{guest_type}%", f"%{guest_type}%"]
    if q:
        sql += " AND (ie.guest LIKE ? OR ie.questions_json LIKE ? OR ie.quotes_json LIKE ?)"
        args += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += f" ORDER BY e.end_date DESC LIMIT {int(limit)}"
    with conn() as c:
        rows = c.execute(sql, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["questions"] = json.loads(d.pop("questions_json") or "[]")
            d["notable_quotes"] = json.loads(d.pop("quotes_json") or "[]")
            _clean_guest(d)
            out.append(d)
        return out


def source_health() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT s.id, s.name, s.outlet, s.kind, "
            "(SELECT COUNT(*) FROM episodes e WHERE e.source_id=s.id) AS episodes, "
            "(SELECT COUNT(*) FROM articles a WHERE a.source_id=s.id) AS articles, "
            "(SELECT ended_at FROM source_runs r WHERE r.source_id=s.id ORDER BY id DESC LIMIT 1) AS last_run, "
            "(SELECT ok FROM source_runs r WHERE r.source_id=s.id ORDER BY id DESC LIMIT 1) AS last_ok "
            "FROM sources s ORDER BY s.kind, s.name")]


def coverage_radar(edition_id: str) -> dict:
    """Topic x source coverage matrix for an edition (from manifest + data)."""
    with conn() as c:
        ed = c.execute("SELECT * FROM editions WHERE id=?", (edition_id,)).fetchone()
        if not ed:
            return {"edition": edition_id, "matrix": []}
        manifest = json.loads(ed["manifest_json"] or "{}")
        data = json.loads(ed["data_json"] or "{}")
        by_source: dict[str, set] = {}
        for ep in manifest.get("episodes", []):
            by_source.setdefault(ep.get("program", "?"), set())
        topics = [t["title_en"] for t in data.get("agenda_topics", [])]
        return {"edition": edition_id, "topics": topics,
                "sources": [{"show": k, "episodes": len(v)} for k, v in by_source.items()],
                "matrix": []}


def episodes_by_date(start: str, end: str) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM episodes WHERE pub_date >= ? AND pub_date <= ? ORDER BY pub_date, source_id",
            (start, end)).fetchall()
        return [dict(r) for r in rows]


def transcript_for(episode_id: str) -> str:
    with conn() as c:
        rows = c.execute("SELECT text FROM transcript_chunks WHERE episode_id=? ORDER BY seq", (episode_id,))
        return "\n".join(r["text"] for r in rows)
