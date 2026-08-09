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
             "momentum": "accelerating", "evidence": "strong"} for _ in range(4)],
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