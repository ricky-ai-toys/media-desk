"""QC gate status math over synthetic payloads (both schema families)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from backend.app import config  # noqa: E402
from backend.app import db  # noqa: E402
from backend.app.synth import qc as qcmod  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "qc-test.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    db.init_db()
    yield db_path
    db_path.unlink(missing_ok=True)


def _full(v2: bool) -> dict:
    """A payload that would pass every gate in the family."""
    data = {
        "start_date": "2026-08-03", "end_date": "2026-08-07",
        "report_title": "International Financial Media Weekly",
        "agenda_topics": [
            {"title_en": "t", "summary_en": "s", "priority": "critical",
             "momentum": "accelerating", "evidence": "strong",
             "driver_en": "d", "next_test_en": "x", "stakes_en": "st"}
            for _ in range(4)],
        "narratives": [
            {"title_en": "story", "title_zh": "叙事",
             "driver_en": "d", "why_en": "w", "next_test_en": "x",
             "from_en": "f", "to_en": "t", "analysis_en": "a", "analysis_zh": "z"}
            for _ in range(4)],
        "recurring_questions_en": ["alpha", "bravo", "charlie"],
        "week_summary_en": "S", "week_summary_zh": "Z",
    }
    if v2:
        data.update({
            "thesis_en": "T", "thesis_zh": "T中文",
            "comms_boxes": [{"title_en": "c"} for _ in range(3)],
            "question_groups": [
                {"category": "policy_credibility", "questions_en": []}],
            "watchpoints": [{"trigger_en": "w"}] * 3,
            "media_exchanges": [{"pattern_en": "p", "premise_en": "p"}] * 3,
            "evidence_statuses": [{"status": "supported"}] * 2,
            "week_ahead_events": [
                {"date": "2026-08-10", "event_en": "BOJ"},
                {"date": "2026-08-12", "event_en": "CPI"},
                {"date": "2026-08-14", "event_en": "Tariff"},
            ],
        })
    return {"id": "2026-08-03_to_2026-08-07", "start_date": "2026-08-03",
            "end_date": "2026-08-07", "manifest": {"episodes": [1] * 5}, "data": data}


def _seed(full: dict, qc_json: dict | None = None):
    manifest = {"episodes": [{"date": f"2026-08-0{i}"} for i in range(3, 8)]}
    with db.conn() as c:
        c.execute(
            "INSERT INTO editions (id, start_date, end_date, status, data_json, manifest_json) "
            "VALUES (?,?,?,?,?,?)",
            (full["id"], full["start_date"], full["end_date"], "draft",
             json.dumps(full["data"], ensure_ascii=False),
             json.dumps(manifest)))
        if qc_json is not None:
            c.execute("UPDATE editions SET qc_json=? WHERE id=?",
                      (json.dumps(qc_json), full["id"]))


def _break(full: dict, **kw) -> dict:
    d = json.loads(json.dumps(full))
    for k, v in kw.items():
        d["data"][k] = v
    return d


def test_legacy_clean_passes():
    _seed(full := _full(False))
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "PASS" and not r["blocks"]


def test_legacy_figure_mismatch_blocks():
    # legacy is strict: figure misalignment must block publish
    full = _break(_full(False), week_summary_en="S 158 gold", week_summary_zh="Z")
    _seed(full)
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "FAIL" and "en_zh_figures_align" in r["blocks"]


def test_legacy_missing_narratives_blocks():
    full = _break(_full(False), narratives=[])
    _seed(full)
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "FAIL" and "narratives_3_to_4" in r["blocks"]


def test_v2_clean_passes():
    _seed(full := _full(True))
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "PASS" and not r["blocks"]


def test_v2_missing_v2_gate_blocks():
    full = _break(_full(True), thesis_en="")
    _seed(full)
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "FAIL" and "thesis_present" in r["blocks"]


def test_v2_figure_mismatch_is_nonblocking():
    # ZH side is editorial in v2: figure mismatch must NOT block
    full = _break(_full(True), thesis_en="T with 158 gold", thesis_zh="T中文 无数字")
    _seed(full)
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "PASS" and "en_zh_figures_align" not in r["blocks"]
    assert any(c["check"] == "en_zh_figures_align" and not c["pass"] for c in r["checks"])


def test_v2_too_many_topics_blocks():
    full = _break(_full(True),
                  agenda_topics=[{"title_en": "t", "summary_en": "s"} for _ in range(6)])
    _seed(full)
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "FAIL" and "topics_selected_dynamically" in r["blocks"]


def test_qc_pass_sets_published_status():
    _seed(full := _full(True))
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "PASS"
    with db.conn() as c:
        st = c.execute("SELECT status FROM editions WHERE id=?", (full["id"],)).fetchone()[0]
    assert st == "published"


def test_qc_fail_sets_needs_review_status():
    full = _break(_full(True), thesis_en="")
    _seed(full)
    qcmod.run_qc(full["id"])
    with db.conn() as c:
        st = c.execute("SELECT status FROM editions WHERE id=?", (full["id"],)).fetchone()[0]
    assert st == "needs_review"


def test_qc_topic_facts_present():
    assert qcmod.topic_facts_present({"agenda_topics": [
        {"driver_en": "d", "next_test_en": "n", "stakes_en": "s"}]})
    assert not qcmod.topic_facts_present({"agenda_topics": [
        {"driver_en": "d", "next_test_en": "n"}]})
    assert not qcmod.topic_facts_present({"agenda_topics": []})


def test_qc_topic_facts_blocks():
    full = _break(_full(True))
    full["data"]["agenda_topics"][0].pop("stakes_en")
    _seed(full)
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "FAIL" and "topic_facts_present" in r["blocks"]


def test_qc_week_ahead_window():
    good = {"end_date": "2026-08-14", "week_ahead_events": [
        {"date": "2026-08-17", "event_en": "BOJ"},
        {"date": "2026-08-19", "event_en": "CPI"},
        {"date": "2026-08-21", "event_en": "Earnings"}]}
    assert qcmod.week_ahead_present(good)
    bad_past = {"end_date": "2026-08-14", "week_ahead_events": [
        {"date": "2026-08-13", "event_en": "past"},
        {"date": "2026-08-19", "event_en": "CPI"},
        {"date": "2026-08-21", "event_en": "Earnings"}]}
    assert not qcmod.week_ahead_present(bad_past)
    bad_far = {"end_date": "2026-08-14", "week_ahead_events": [
        {"date": "2026-08-17", "event_en": "BOJ"},
        {"date": "2026-08-19", "event_en": "CPI"},
        {"date": "2026-09-01", "event_en": "far"}]}
    assert not qcmod.week_ahead_present(bad_far)
    assert not qcmod.week_ahead_present({"end_date": "2026-08-14", "week_ahead_events": []})


def test_qc_week_ahead_blocks():
    full = _break(_full(True), week_ahead_events=[])
    _seed(full)
    r = qcmod.run_qc(full["id"])
    assert r["status"] == "FAIL" and "week_ahead_present" in r["blocks"]


def test_qc_terse_lengths_soft():
    assert qcmod.terse_lengths({"agenda_topics": [{"summary_en": "short"}]})
    long = {"agenda_topics": [{"summary_en": "word " * 30},
                              {"summary_en": "word " * 30},
                              {"summary_en": "word " * 30}]}
    assert not qcmod.terse_lengths(long)
    assert qcmod.terse_lengths({"agenda_topics": []})