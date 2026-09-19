"""Contract tests for the evidence-loyalty changes (PR-1).

Covers: server-side coverage overrides, rule-based evidence statuses,
synth_failed marker, LLM retry/backoff, pr_counsel no-stitch gate,
per-field figure alignment, week-ahead weekday rule, bilingual parity gates,
zero-evidence hard gate, stale-source flags.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from backend.app import config  # noqa: E402
from backend.app import db  # noqa: E402
from backend.app import llm  # noqa: E402
from backend.app.synth import qc as qcmod  # noqa: E402
from backend.app.synth import weekly  # noqa: E402

W_START, W_END = "2026-08-10", "2026-08-14"


@pytest.fixture
def week_db(tmp_path, monkeypatch):
    db_path = tmp_path / "synth.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "ROOT", tmp_path)
    db.init_db()
    for i, day in enumerate(["2026-08-10", "2026-08-11", "2026-08-12"]):
        ep = f"ep{i}"
        db.upsert_episode({"id": ep, "source_id": "bloomberg_asia_trade",
                           "title": f"The Asia Trade {day}", "show_name": "The Asia Trade",
                           "pub_date": day, "kind": "yt"})
        db.upsert_analysis(ep, (
            "## 2. Hot Topics\n"
            "**1. Yen intervention watch as dollar weakens**\n"
            "- *Tone:* Cautious (-1)\n\n"
            "## 5. Anchor–Guest Tension\n"
            "1. **Anchor question:** Will it hold?\n"
            "   **Guest reply:** Maybe. **Tension point:** credibility\n"), None, None)
    yield db_path


def _llm_payload(coverage=5):
    return {
        "report_title": "International Financial Media Weekly",
        "thesis_en": "T", "thesis_zh": "T",
        "agenda_topics": [{
            "rank": 1, "title_en": "Yen intervention watch as dollar weakens",
            "title_zh": "日元", "summary_en": "s", "summary_zh": "摘",
            "priority": "high", "momentum": "rising", "evidence": "moderate",
            "coverage": coverage,  # LLM claims 5 programmes
            "driver_en": "d", "driver_zh": "d", "next_test_en": "n",
            "next_test_zh": "n", "stakes_en": "st", "stakes_zh": "st",
        }],
        "narratives": [], "comms_boxes": [], "question_groups": [],
        "media_exchanges": [], "watchpoints": [], "week_ahead_events": [],
        "evidence_statuses": [
            {"section": "Week ahead events", "status": "confirmed",
             "note": "LLM self-graded"}],
        "interview_groups_en": [], "interview_groups_zh": [],
        "pr_counsel": {"risk_en": "r", "risk_zh": "r", "opportunity_en": "o",
                       "opportunity_zh": "o", "prepare_en": "p",
                       "prepare_zh": "p", "avoid_en": "a", "avoid_zh": "a"},
        "warnings": [],
    }


def test_coverage_overridden_by_server_evidence(week_db, monkeypatch):
    """LLM-claimed coverage=5 must be replaced by the real programme count."""
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: _llm_payload(coverage=5))
    out = weekly.synthesize_week(W_START, W_END)
    ed = db.edition_full(out["edition"])
    topic = ed["data"]["agenda_topics"][0]
    assert topic["coverage"] == 1  # only The Asia Trade carried it
    assert topic["evidence_programmes"] == ["The Asia Trade"]
    assert ed["data"]["episode_count"] == 3


def test_zero_evidence_topic_gets_warning_and_zero_coverage(week_db, monkeypatch):
    payload = _llm_payload()
    payload["agenda_topics"][0]["title_en"] = "Martian bond market rally"
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: payload)
    out = weekly.synthesize_week(W_START, W_END)
    ed = db.edition_full(out["edition"])
    topic = ed["data"]["agenda_topics"][0]
    assert topic["coverage"] == 0
    assert any("no episode evidence" in w for w in ed["data"]["warnings"])


def test_evidence_statuses_rule_based_never_confirmed(week_db, monkeypatch):
    """LLM self-graded 'confirmed' week-ahead must be replaced by rules."""
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: _llm_payload())
    out = weekly.synthesize_week(W_START, W_END)
    statuses = {s["section"]: s["status"]
                for s in db.edition_full(out["edition"])["data"]["evidence_statuses"]}
    assert statuses["Week ahead events"] == "supported"
    assert "confirmed" not in statuses.values()


def test_llm_failure_marks_synth_failed(week_db, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("api down")
    monkeypatch.setattr(weekly.llm, "chat_json", boom)
    with pytest.raises(RuntimeError):
        weekly.synthesize_week(W_START, W_END)
    ed = db.edition_full(f"{W_START}_to_{W_END}")
    assert ed["status"] == "synth_failed"
    raw = week_db.parent / "data" / "llm_raw" / f"{W_START}_to_{W_END}.json"
    assert raw.exists() and "api down" in raw.read_text()


def test_raw_payload_dumped(week_db, monkeypatch):
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: _llm_payload())
    weekly.synthesize_week(W_START, W_END)
    raw = json.loads((week_db.parent / "data" / "llm_raw"
                      / f"{W_START}_to_{W_END}.json").read_text())
    assert raw["payload"]["report_title"] == "International Financial Media Weekly"


def test_chat_retries_transient_errors(monkeypatch):
    calls = {"n": 0}

    class FakeResponse:
        def raise_for_status(self):
            if calls["n"] < 3:
                import httpx
                raise httpx.HTTPError("flaky")

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def post(self, *a, **k):
            calls["n"] += 1
            return FakeResponse()

    monkeypatch.setattr(llm.httpx, "Client", FakeClient)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setenv(config.ANALYSIS["api_key_env"], "test-key")
    assert llm.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert calls["n"] == 3  # failed twice, succeeded on third


def test_chat_gives_up_after_retries(monkeypatch):
    class FakeClient:
        def __init__(self, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def post(self, *a, **k):
            import httpx
            raise httpx.HTTPError("down")

    monkeypatch.setattr(llm.httpx, "Client", FakeClient)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    monkeypatch.setenv(config.ANALYSIS["api_key_env"], "test-key")
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_chat_json_retries_malformed(monkeypatch):
    outs = iter(["not json", "still not", '{"a": 1}'])
    monkeypatch.setattr(llm, "chat", lambda *a, **k: next(outs))
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    assert llm.chat_json("s", "u") == {"a": 1}


def test_ticker_marks_unverified_quotes(tmp_path, monkeypatch):
    """Anchor questions not found in the transcript are flagged verified=False."""
    from backend.app.api import routes
    db_path = tmp_path / "tick.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    db.init_db()
    db.upsert_episode({"id": "epA", "source_id": "bloomberg_asia_trade", "title": "t",
                       "show_name": "The Asia Trade", "pub_date": "2026-08-11",
                       "kind": "yt"})
    db.replace_chunks("epA", ["the anchor asked will the yen defense hold this "
                              "quarter against the dollar"])
    items = routes._ticker([
        {"show": "The Asia Trade", "date": "2026-08-11", "tone": "challenging",
         "questions": ["Will the yen defense hold this quarter?"]},
        {"show": "The Asia Trade", "date": "2026-08-11", "tone": "evasive",
         "questions": ["Is the martian bond rally sustainable?"]},
    ])
    assert items[0]["verified"] is True
    assert items[1]["verified"] is False


def test_sync_sources_disables_stale(tmp_path, monkeypatch):
    """Sources dropped from yaml must disappear from public source_health."""
    db_path = tmp_path / "src.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    db.init_db()
    db.upsert_source({"id": "ghost_feed", "name": "Ghost", "outlet": "G",
                      "kind": "rss", "enabled": False})
    db.sync_sources()  # yaml-driven: ghost_feed is not in yaml -> disabled
    ids = {s["id"] for s in db.source_health()}
    assert "ghost_feed" not in ids
    ids_all = {s["id"] for s in db.source_health(include_disabled=True)}
    assert "ghost_feed" in ids_all


# --- QC-level gates -----------------------------------------------------------

def _v2_payload(**over):
    data = {
        "start_date": W_START, "end_date": W_END,
        "report_title": "International Financial Media Weekly",
        "thesis_en": "T", "thesis_zh": "T",
        "week_summary_en": "S", "week_summary_zh": "Z",
        "agenda_topics": [{"title_en": "t", "summary_en": "s", "priority": "high",
                           "momentum": "rising", "evidence": "strong",
                           "driver_en": "d", "next_test_en": "n", "stakes_en": "st"}
                          for _ in range(3)],
        "narratives": [{"driver_en": "d", "why_en": "w", "next_test_en": "n"}
                       for _ in range(3)],
        "comms_boxes": [{"title_en": "c"} for _ in range(3)],
        "question_groups": [{"category": "policy_credibility",
                             "questions_en": ["a"], "questions_zh": ["甲"]}],
        "watchpoints": [{"trigger_en": "w"}] * 3,
        "media_exchanges": [{"pattern_en": "p", "premise_en": "p"}] * 3,
        "evidence_statuses": [{"status": "supported"}],
        "interview_groups_en": [{"title_en": "g", "questions_en": ["q"]}],
        "interview_groups_zh": [{"title_zh": "组", "questions_zh": ["问"]}],
        "pr_counsel": {"risk_en": "r", "risk_zh": "r", "opportunity_en": "o",
                       "opportunity_zh": "o", "prepare_en": "p", "prepare_zh": "p",
                       "avoid_en": "a", "avoid_zh": "a"},
        "recurring_questions_en": ["a", "b", "c"],
        "week_ahead_events": [
            {"date": "2026-08-17", "event_en": "BOJ"},
            {"date": "2026-08-19", "event_en": "CPI"},
            {"date": "2026-08-21", "event_en": "Earnings"}],
        "warnings": [],
    }
    data.update(over)
    return data


def _run(tmp_path, monkeypatch, data):
    db_path = tmp_path / "q.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    db.init_db()
    eid = db.upsert_edition(data, {"episodes": [
        {"date": d} for d in ("2026-08-10", "2026-08-11",
                              "2026-08-12", "2026-08-13")]}, None)
    return qcmod.run_qc(eid)


def test_pr_counsel_incomplete_blocks(tmp_path, monkeypatch):
    data = _v2_payload(pr_counsel={"risk_en": "r"})
    r = _run(tmp_path, monkeypatch, data)
    assert r["status"] == "FAIL" and "pr_counsel_complete" in r["blocks"]


def test_interview_groups_unbalanced_blocks(tmp_path, monkeypatch):
    data = _v2_payload(interview_groups_zh=[])
    r = _run(tmp_path, monkeypatch, data)
    assert r["status"] == "FAIL" and "interview_groups_parallel" in r["blocks"]


def test_question_group_imbalance_blocks(tmp_path, monkeypatch):
    data = _v2_payload(question_groups=[{
        "category": "policy_credibility", "questions_en": ["a", "b"],
        "questions_zh": ["甲"]}])
    r = _run(tmp_path, monkeypatch, data)
    assert r["status"] == "FAIL" and "question_group_items_parallel" in r["blocks"]


def test_week_ahead_weekend_rejected(tmp_path, monkeypatch):
    # 2026-08-16 is a Sunday
    data = _v2_payload(week_ahead_events=[
        {"date": "2026-08-16", "event_en": "Sunday event"},
        {"date": "2026-08-19", "event_en": "CPI"},
        {"date": "2026-08-21", "event_en": "Earnings"}])
    r = _run(tmp_path, monkeypatch, data)
    assert "week_ahead_present" in r["blocks"]


def test_figure_diffs_are_per_field(tmp_path, monkeypatch):
    data = _v2_payload(thesis_en="Oil at 90 dollars", thesis_zh="油价九十美元")
    r = _run(tmp_path, monkeypatch, data)
    check = next(c for c in r["checks"] if c["check"] == "en_zh_figures_align")
    assert not check["pass"]
    assert "thesis" in check["detail"] and "90" in check["detail"]
    # v2: still informational, not blocking
    assert "en_zh_figures_align" not in r["blocks"]


def test_figure_year_rollover_no_false_positive(tmp_path, monkeypatch):
    # The reporting year in dates must not trip the check in any year.
    data = _v2_payload()
    r = _run(tmp_path, monkeypatch, data)
    check = next(c for c in r["checks"] if c["check"] == "en_zh_figures_align")
    assert check["pass"], check["detail"]


# --- zero-evidence hard gate ---------------------------------------------------

def test_zero_evidence_week_blocked_without_llm(week_db, monkeypatch):
    def never(*a, **k):
        raise AssertionError("LLM must not be called for an unevidenced week")
    monkeypatch.setattr(weekly.llm, "chat_json", never)
    out = weekly.synthesize_week("2026-09-14", "2026-09-18")
    assert out["blocked"] is True
    ed = db.edition_full("2026-09-14_to_2026-09-18")
    assert ed["status"] == "blocked_no_evidence"
    assert any("no episode evidence" in w for w in ed["data"]["warnings"])


def test_latest_edition_skips_blocked_week(week_db, monkeypatch):
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: _llm_payload())
    weekly.synthesize_week(W_START, W_END)  # evidenced August week
    weekly.synthesize_week("2026-09-14", "2026-09-18")  # newer but empty
    assert db.latest_edition()["id"] == f"{W_START}_to_{W_END}"


def test_blocked_week_resynthesizes_after_backfill(week_db, monkeypatch):
    """Critical #1 regression: a withheld week must be re-synthesizable once
    ingest catches up, without the caller having to pass force=True."""
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: _llm_payload())
    assert weekly.synthesize_week("2026-09-14", "2026-09-18")["blocked"] is True
    db.upsert_episode({"id": "bk1", "source_id": "bloomberg_asia_trade",
                       "title": "The Asia Trade 2026-09-15",
                       "show_name": "The Asia Trade (segment clips)",
                       "pub_date": "2026-09-15", "kind": "yt"})
    db.upsert_analysis("bk1", (
        "## 2. Hot Topics\n"
        "**1. Yen intervention watch as dollar weakens**\n"
        "- *Tone:* Cautious (-1)\n\n"
        "## 5. Anchor–Guest Tension\n"
        "1. **Anchor question:** Will it hold?\n"
        "   **Guest reply:** Maybe. **Tension point:** credibility\n"), None, None)
    out = weekly.synthesize_week("2026-09-14", "2026-09-18")
    assert not out.get("blocked") and not out.get("exists")
    ed = db.edition_full("2026-09-14_to_2026-09-18")
    assert ed["status"] not in ("blocked_no_evidence", "synth_failed")
    assert len(ed["agenda"]) == 1


def test_published_week_not_retroactively_blocked(week_db, monkeypatch):
    """Required #2 regression: a later zero-evidence re-run must not strip a
    week whose report was already produced."""
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: _llm_payload())
    weekly.synthesize_week(W_START, W_END)
    with db.conn() as c:
        c.execute("DELETE FROM analyses")
        c.execute("DELETE FROM transcript_chunks")
        c.execute("DELETE FROM episodes")
    out = weekly.synthesize_week(W_START, W_END)
    assert out.get("exists") and not out.get("blocked")
    ed = db.edition_full(f"{W_START}_to_{W_END}")
    assert ed["status"] not in ("blocked_no_evidence", "synth_failed")


def test_admin_synthesize_pipeline_mapping(week_db, monkeypatch):
    """"Exists" no-ops must not be reported as a fresh "done" synthesis."""
    from backend.app.api import admin
    monkeypatch.setattr(weekly.llm, "chat_json", lambda *a, **k: _llm_payload())
    admin.run_synthesize(W_START, W_END)
    assert db.get_pipeline()["status"] == "done"
    admin.run_synthesize(W_START, W_END)  # second call hits the exists path
    p = db.get_pipeline()
    assert p["status"] == "skipped" and "already present" in p["message"]


def test_qc_withheld_week_keeps_blocked_status(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "bw.db")
    db.init_db()
    eid = db.mark_edition_blocked("2026-09-14", "2026-09-18",
                                  "no episode evidence in window")
    r = qcmod.run_qc(eid)
    assert r["status"] == "FAIL" and r["blocked"]
    assert db.edition_full(eid)["status"] == "blocked_no_evidence"


def test_export_of_withheld_week_is_409(tmp_path, monkeypatch):
    """Email/PDF renderers assume editorial payload keys — a withheld week must
    be refused at the route boundary, not crash mid-render (found in live drill)."""
    from fastapi.testclient import TestClient
    from backend.app.main import app
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ex.db")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    db.init_db()
    eid = db.mark_edition_blocked("2026-07-06", "2026-07-10", "drill")
    client = TestClient(app)
    assert client.get(f"/export/{eid}/email").status_code == 409
    assert client.get(f"/export/{eid}/pdf").status_code == 409
    assert client.get(f"/export/{eid}/csv").status_code == 200
    # Required #7/#8: the read paths must not hand withheld weeks an
    # empty-but-green QC payload or a raw edition dump.
    d = client.get(f"/api/desk?edition={eid}").json()
    assert d["status"] == "blocked_no_evidence"
    assert d["qc"] is None and d["agenda"] == [] and d["narratives"] == []
    e = client.get(f"/api/edition/{eid}").json()
    assert e["status"] == "blocked_no_evidence"
    assert e["qc"] is None and e["agenda"] == [] and e["narratives"] == []


def test_empty_manifest_blocks_coverage_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "em.db")
    db.init_db()
    eid = db.upsert_edition(_v2_payload(), {"episodes": []}, None)
    r = qcmod.run_qc(eid)
    assert r["status"] == "FAIL"
    assert "minimum_source_coverage" in r["blocks"]
    assert "source_manifest_saved" in r["blocks"]


# --- stale-source detection ----------------------------------------------------

def test_source_health_stale_flags(tmp_path, monkeypatch):
    import datetime
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "st.db")
    monkeypatch.setattr(config, "FETCH", dict(config.FETCH, stale_days=10))
    db.init_db()
    today = datetime.date.today()
    for sid, kind in [("yt_old", "yt_playlist"), ("yt_fresh", "yt_playlist"),
                      ("yt_starving", "yt_playlist"), ("yt_future", "yt_playlist"),
                      ("yt_boot", "yt_playlist"), ("rss_old", "rss")]:
        db.upsert_source({"id": sid, "name": sid, "outlet": "O", "kind": kind,
                          "enabled": True})
    db.upsert_episode({"id": "e1", "source_id": "yt_old", "title": "t",
                       "show_name": "Old", "kind": "yt",
                       "pub_date": (today - datetime.timedelta(days=30)).isoformat()})
    db.upsert_episode({"id": "e2", "source_id": "yt_fresh", "title": "t",
                       "show_name": "Fresh", "kind": "yt",
                       "pub_date": (today - datetime.timedelta(days=1)).isoformat()})
    db.upsert_episode({"id": "e3", "source_id": "yt_future", "title": "t",
                       "show_name": "Future", "kind": "yt",
                       "pub_date": (today + datetime.timedelta(days=5)).isoformat()})
    db.log_source_run("yt_starving", "yt_playlist", True, 0, "0 new episodes")
    health = {s["id"]: s for s in db.source_health()}
    assert health["yt_old"]["stale"] is True
    assert health["yt_old"]["last_episode"] == \
        (today - datetime.timedelta(days=30)).isoformat()
    assert health["yt_fresh"]["stale"] is False
    assert health["yt_starving"]["stale"] is True   # ran, but never landed an episode
    assert health["yt_boot"]["stale"] is False      # zero episodes before first run
    assert health["yt_future"]["stale"] is True    # future-dated last episode is a fault
    assert health["rss_old"]["stale"] is False     # RSS exempt — wire keeps flowing
