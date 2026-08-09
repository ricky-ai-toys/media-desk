"""Schema v2 tests: migration guards, labelled_score, upsert round-trip."""
import sqlite3

import pytest

from backend.app import db


def test_labeled_score_mapping():
    assert db.labelled_score("critical", "accelerating") == 94
    assert db.labelled_score("high", "rising") == 81
    assert db.labelled_score("medium", "stable") == 68
    assert db.labelled_score("low", "fading") == 55
    assert db.labelled_score("nonsense", "") == 68
    assert db.labelled_score("critical", "fading") == 85
    assert all(55 <= db.labelled_score(p, m) <= 95
               for p in ("critical", "high", "medium", "low")
               for m in ("accelerating", "rising", "stable", "fading"))


_OLD_SCHEMA = """
CREATE TABLE agenda_topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT,
  rank INTEGER, title_en TEXT, title_zh TEXT, summary_en TEXT, summary_zh TEXT,
  direction TEXT, score INTEGER
);
CREATE TABLE narratives (
  id INTEGER PRIMARY KEY AUTOINCREMENT, edition_id TEXT,
  idx INTEGER, title_en TEXT, title_zh TEXT, from_en TEXT, to_en TEXT,
  from_zh TEXT, to_zh TEXT, analysis_en TEXT, analysis_zh TEXT
);
"""


def test_migrate_adds_columns_idempotently(tmp_path):
    c = sqlite3.connect(tmp_path / "mig.db")
    c.row_factory = sqlite3.Row
    c.executescript(_OLD_SCHEMA)
    db._migrate(c)
    gift = {r["name"] for r in c.execute("PRAGMA table_info(agenda_topics)")}
    nf = {r["name"] for r in c.execute("PRAGMA table_info(narratives)")}
    assert {"priority", "momentum", "evidence", "coverage"} <= gift
    assert {"driver_en", "driver_zh", "why_en", "why_zh",
            "next_test_en", "next_test_zh"} <= nf
    db._migrate(c)
    assert {r["name"] for r in c.execute("PRAGMA table_info(agenda_topics)")} == gift
    c.close()


def test_upsert_roundtrip_new_fields(tmp_path, monkeypatch):
    from backend.app import config as cfg
    monkeypatch.setattr(cfg, "DB_PATH", tmp_path / "t.db")
    db.init_db()
    eid = db.upsert_edition({
        "start_date": "2026-08-10", "end_date": "2026-08-14",
        "agenda_topics": [{
            "rank": 1, "title_en": "Yen test", "title_zh": "日元测试",
            "summary_en": "s", "summary_zh": "s",
            "priority": "high", "momentum": "rising", "evidence": "moderate",
            "coverage": 3,
        }],
        "narratives": [{
            "title_en": "N1", "title_zh": "N1",
            "from_en": "a", "to_en": "b", "analysis_en": "an",
            "driver_en": "d", "driver_zh": "d",
            "why_en": "w", "why_zh": "w", "next_test_en": "nt", "next_test_zh": "nt",
        }],
    }, None, None)
    ed = db.edition_full(eid)
    a = ed["agenda"][0]
    assert a["priority"] == "high"
    assert a["momentum"] == "rising"
    assert a["evidence"] == "moderate"
    assert a["coverage"] == 3
    assert a["direction"] == "rising"
    assert a["score"] == db.labelled_score("high", "rising")
    n = ed["narratives"][0]
    assert n["driver_en"] == "d" and n["next_test_zh"] == "nt"