"""Ingest-hardening tests: NA upload_date recovery via batched probes,
DD-MMM-YY title dates, scan limits, and proxy injection."""
import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from backend.app import config  # noqa: E402
from backend.app import db  # noqa: E402
from backend.app.ingest import youtube as yt  # noqa: E402

TODAY = datetime.date.today()


def _days_ago(n: int) -> str:
    return (TODAY - datetime.timedelta(days=n)).isoformat()


SOURCE = {"id": "test_clips", "name": "Test Show", "outlet": "T", "kind": "yt_playlist",
          "playlist_url": "https://www.youtube.com/playlist?list=X",
          "title_regex": ".+", "content": "clips", "min_transcript_words": 10,
          "enabled": True}


# --- _pubdate -----------------------------------------------------------------

def test_pubdate_title_date():
    assert yt._pubdate("The Asia Trade 9/9/2026", "NA") == "2026-09-09"


def test_pubdate_na_and_undated_title_is_none():
    assert yt._pubdate("Some clip title", "NA") is None
    assert yt._pubdate("Some clip title", "") is None


def test_pubdate_upload_date_only():
    assert yt._pubdate("t", "20260918") == "2026-09-18"


def test_pubdate_cnb_watch_in_full_format():
    assert yt._pubdate("Squawk Box Asia - 17-Sep-26", "NA") == "2026-09-17"
    assert yt._pubdate("The China Connection - 03-Sep-26", "NA") == "2026-09-03"


def test_pubdate_mdy_not_matched_mid_number_sequence():
    assert yt._pubdate("Score 3-17-Sep-26 lines", "NA") is None


# --- _probe_dates -------------------------------------------------------------

def test_probe_dates_parses_only_clean_id_date_lines(monkeypatch):
    noisy = (
        "[youtube] extracting...\n"
        "vid00000001|20260918\n"
        "Title with|pipes and no date\n"
        "vid00000002|NA\n"
        "vid00000003|20260917\n")

    class Done:
        stdout = noisy

    monkeypatch.setattr(yt.subprocess, "run", lambda *a, **k: Done())
    got = yt._probe_dates(["vid00000001", "vid00000002", "vid00000003"], SOURCE)
    assert got == {"vid00000001": "2026-09-18", "vid00000003": "2026-09-17"}


def test_probe_dates_swallows_timeout(monkeypatch):
    def boom(*a, **k):
        raise yt.subprocess.TimeoutExpired(cmd="yt-dlp", timeout=1)
    monkeypatch.setattr(yt.subprocess, "run", boom)
    assert yt._probe_dates(["a"], SOURCE) == {}


def test_probe_dates_empty_ids_no_call(monkeypatch):
    def never(*a, **k):
        raise AssertionError("must not spawn yt-dlp")
    monkeypatch.setattr(yt.subprocess, "run", never)
    assert yt._probe_dates([], SOURCE) == {}


# --- proxy injection ----------------------------------------------------------

def test_proxy_args_source_and_global(monkeypatch):
    monkeypatch.setattr(config, "FETCH", {})
    assert yt._proxy_args({"proxy_url": "http://p:1"}) == ["--proxy", "http://p:1"]
    assert yt._proxy_args({}) == []
    monkeypatch.setattr(config, "FETCH", {"proxy_url": "http://g:2"})
    assert yt._proxy_args({}) == ["--proxy", "http://g:2"]
    assert yt._proxy_args({"proxy_url": "http://p:1"}) == ["--proxy", "http://p:1"]


# --- sync_playlist probe path -------------------------------------------------

@pytest.fixture
def ingest_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "yt.db")
    monkeypatch.setattr(config, "TRANSCRIPT_DIR", tmp_path / "tr")
    db.init_db()
    db.upsert_source(SOURCE)  # episodes.source_id has an FK


ROWS_NA = [
    {"id": "fresh1", "upload_date": "NA", "title": "Fresh clip one"},
    {"id": "fresh2", "upload_date": "NA", "title": "Fresh clip two"},
    {"id": "stale1", "upload_date": "NA", "title": "Old clip (20 days)"},
]


def test_sync_playlist_recovers_dates_via_probe_and_ingests(tmp_path, monkeypatch, ingest_db):
    monkeypatch.setattr(yt, "_playlist_rows", lambda source, limit=30: list(ROWS_NA))
    monkeypatch.setattr(yt, "_probe_dates", lambda ids, source: {
        "fresh1": _days_ago(1), "fresh2": _days_ago(2), "stale1": _days_ago(20)})
    monkeypatch.setattr(yt, "fetch_transcript",
                        lambda source, vid, out_dir: "word " * 30)
    out = yt.sync_playlist(SOURCE)
    assert out["ok"] and out["added"] == 2  # stale1 dropped by 7-day cutoff
    with db.conn() as c:
        rows = {r["id"]: r["pub_date"] for r in c.execute("SELECT id, pub_date FROM episodes")}
    assert rows == {"fresh1": _days_ago(1), "fresh2": _days_ago(2)}


def test_sync_playlist_probe_cap_and_undated_count(monkeypatch, ingest_db):
    monkeypatch.setattr(config, "FETCH", dict(config.FETCH, max_date_probes=2))
    rows = [{"id": f"c{i}", "upload_date": "NA", "title": f"clip {i}"} for i in range(5)]
    seen = {}

    def fake_probe(ids, source):
        seen["ids"] = ids
        return {i: _days_ago(1) for i in ids[:1]}  # only first resolves

    monkeypatch.setattr(yt, "_playlist_rows", lambda source, limit=30: rows)
    monkeypatch.setattr(yt, "_probe_dates", fake_probe)
    monkeypatch.setattr(yt, "fetch_transcript", lambda source, vid, out_dir: "word " * 30)
    out = yt.sync_playlist(SOURCE)
    assert seen["ids"] == ["c3", "c4"]  # oldest-first: playlist is newest-first, tail = oldest
    assert out["added"] == 1 and out["undated"] == 1 and out["deferred"] == 3
    with db.conn() as c:
        detail = c.execute("SELECT detail FROM source_runs ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert "1 new episodes" in detail and "1 undated" in detail and "3 probe-deferred" in detail


def test_sync_playlist_only_probes_unseen_rows(monkeypatch, ingest_db):
    monkeypatch.setattr(yt, "_playlist_rows", lambda source, limit=30: [
        {"id": "known1", "upload_date": "NA", "title": "known clip"}])
    db.upsert_episode({"id": "known1", "source_id": "test_clips", "title": "known clip",
                       "show_name": "Test Show (segment clips)", "pub_date": _days_ago(1),
                       "kind": "yt"})

    def never(ids, source):
        raise AssertionError("probe must not run for already-ingested rows")
    monkeypatch.setattr(yt, "_probe_dates", never)
    out = yt.sync_playlist(SOURCE)
    assert out["added"] == 0 and out["undated"] == 0


def test_sync_playlist_title_dates_skip_probe(monkeypatch, ingest_db):
    monkeypatch.setattr(yt, "_playlist_rows", lambda source, limit=30: [
        {"id": "d1", "upload_date": "NA",
         "title": f"Show {TODAY.month}/{TODAY.day}/{TODAY.year}"}])

    def never(ids, source):
        raise AssertionError("no probe needed when title carries the date")
    monkeypatch.setattr(yt, "_probe_dates", never)
    monkeypatch.setattr(yt, "fetch_transcript", lambda source, vid, out_dir: "word " * 30)
    out = yt.sync_playlist(SOURCE)
    assert out["added"] == 1


def test_sync_playlist_ok_when_partial_caption_failures(monkeypatch, ingest_db):
    dated = f"{TODAY.month}/{TODAY.day}/{TODAY.year}"
    monkeypatch.setattr(yt, "_playlist_rows", lambda source, limit=30: [
        {"id": "ok1", "upload_date": "NA", "title": f"Good {dated}"},
        {"id": "bad1", "upload_date": "NA", "title": f"Broken {dated}"}])
    monkeypatch.setattr(yt, "fetch_transcript",
                        lambda source, vid, out_dir: None if vid == "bad1" else "word " * 30)
    out = yt.sync_playlist(SOURCE)
    assert out["ok"] and out["added"] == 1 and out["failed"] == 1


def test_sync_playlist_not_ok_when_all_ingests_fail(monkeypatch, ingest_db):
    dated = f"{TODAY.month}/{TODAY.day}/{TODAY.year}"
    monkeypatch.setattr(yt, "_playlist_rows", lambda source, limit=30: [
        {"id": "bad1", "upload_date": "NA", "title": f"Broken {dated}"}])
    monkeypatch.setattr(yt, "fetch_transcript", lambda source, vid, out_dir: None)
    out = yt.sync_playlist(SOURCE)
    assert not out["ok"] and out["added"] == 0 and out["failed"] == 1
