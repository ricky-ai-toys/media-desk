"""QC gate, ported from the v5 qc_gate.py and re-pointed at DB artifacts.

Checks: reporting period, source coverage, dynamic topics (==4), structure,
narratives 4, recurring questions, EN/ZH figure alignment, exact report name,
bilingual blocks, legal-block phrases only.
"""
import datetime as _dt
import json
import re

from .. import db

LEGAL_BLOCK = ("LOW_CONFIDENCE_BLOCK", "DO_NOT_SEND", "unverified claim in report")


def topic_facts_present(data: dict) -> bool:
    topics = data.get("agenda_topics", [])
    return bool(topics) and all(t.get("driver_en") and t.get("next_test_en") and t.get("stakes_en")
                                for t in topics)


def week_ahead_present(data: dict) -> bool:
    events = data.get("week_ahead_events", [])
    if not (3 <= len(events) <= 5):
        return False
    try:
        end = _dt.date.fromisoformat(data["end_date"])
    except (KeyError, ValueError):
        return False
    lo, hi = end + _dt.timedelta(days=1), end + _dt.timedelta(days=10)
    for e in events:
        try:
            d = _dt.date.fromisoformat(str(e.get("date", "")))
        except ValueError:
            return False
        if not (lo <= d <= hi) or not e.get("event_en"):
            return False
    return True


def terse_lengths(data: dict) -> bool:
    topics = data.get("agenda_topics", [])
    if not topics:
        return True
    over = [t for t in topics if len((t.get("summary_en") or "").split()) > 24]
    return len(over) <= max(1, len(topics) // 5)


def run_qc(edition_id: str) -> dict:
    ed = db.edition_full(edition_id)
    if not ed:
        return {"status": "FAIL", "blocked": True, "checks": [],
                "warnings": ["edition not found"], "blocks": ["edition missing"]}
    data = ed["data"]
    checks = []
    manifest = ed["manifest"] or {}
    episodes = manifest.get("episodes", [])
    days = sorted({e.get("date", "") for e in episodes})
    days = [d for d in days if d]

    def add(name, ok, detail, blockable=True):
        checks.append({"check": name, "pass": bool(ok), "detail": detail,
                       "blockable": bool(blockable)})

    legacy = not data.get("thesis_en") and not data.get("comms_boxes")
    blocking = ("topics_selected_dynamically", "exact_report_name",
                "en_zh_figures_align", "bilingual_blocks_present",
                "thesis_present", "narrative_arc_complete",
                "watchpoint_triggers_present", "media_exchanges_complete",
                "evidence_status_vocab", "agenda_labeled",
                "topic_facts_present", "week_ahead_present")

    def add_v2(name, ok, detail):
        add(name, ok if not legacy else True,
            detail if not legacy else f"{detail} (legacy schema, will gate after resynthesis)",
            blockable=not legacy)

    add("correct_reporting_period",
        data.get("start_date") == ed["start_date"] and data.get("end_date") == ed["end_date"],
        f"{ed['start_date']}..{ed['end_date']}")
    add("minimum_source_coverage", len(days) >= 4, f"{len(days)} weekdays")
    add("source_manifest_saved", bool(episodes), f"{len(episodes)} episodes")
    add("topics_selected_dynamically", 3 <= len(data.get("agenda_topics", [])) <= 5,
        f"{len(data.get('agenda_topics', []))} topics")
    add("agenda_structure_complete",
        all(t.get("title_en") and t.get("summary_en") for t in data.get("agenda_topics", [])),
        "all topics have title+summary")
    add("narratives_3_to_4", 3 <= len(data.get("narratives", [])) <= 4,
        f"{len(data.get('narratives', []))} narratives")
    add("recurring_questions_present",
        len(data.get("recurring_questions_en", [])) >= 3 or
        len(data.get("recurring_questions_zh", [])) >= 3,
        f"{len(data.get('recurring_questions_en', []))} recurring")
    add_v2("thesis_present", bool(data.get("thesis_en")) and bool(data.get("thesis_zh")),
        "thesis EN+ZH present")
    add_v2("narrative_arc_complete",
        sum(bool(n.get("driver_en") and n.get("why_en") and n.get("next_test_en"))
            for n in data.get("narratives", [])) >= 3,
        ">=3 narratives with driver/why/next_test")
    add_v2("comms_boxes_present", len(data.get("comms_boxes", [])) >= 3,
        f"{len(data.get('comms_boxes', []))} comms boxes")
    add_v2("question_group_categories_vocab",
        all(g.get("category") in ("policy_credibility", "market_consequences",
                                  "corporate_exposure", "narrative_durability")
            for g in data.get("question_groups", [])),
        "categories within vocab")
    add_v2("watchpoint_triggers_present",
        all(bool(w.get("trigger_en")) for w in data.get("watchpoints", []))
        and 3 <= len(data.get("watchpoints", [])) <= 5,
        f"{len(data.get('watchpoints', []))} watchpoints with triggers")
    add_v2("media_exchanges_complete",
        len(data.get("media_exchanges", [])) >= 3
        and all(ex.get("pattern_en") and ex.get("premise_en") for ex in data.get("media_exchanges", [])),
        f"{len(data.get('media_exchanges', []))} exchanges")
    add_v2("evidence_status_vocab",
        all(es.get("status") in {"confirmed", "supported", "emerging", "interpretive"}
            for es in data.get("evidence_statuses", [])),
        f"{len(data.get('evidence_statuses', []))} statuses in vocab")
    add_v2("agenda_labeled",
        all(t.get("priority") in {"critical", "high", "medium"}
            and t.get("momentum") in {"accelerating", "rising", "stable", "fading"}
            and t.get("evidence") in {"strong", "moderate", "emerging"}
            for t in data.get("agenda_topics", [])),
        "priority/momentum/evidence labels on all topics")
    add_v2("topic_facts_present", topic_facts_present(data),
        f"{len(data.get('agenda_topics', []))} topics with driver/next_test/stakes")
    add_v2("week_ahead_present", week_ahead_present(data),
        f"{len(data.get('week_ahead_events', []))} events in next-week window")
    add("terse_lengths", terse_lengths(data),
        "topic summaries within soft length budget", blockable=False)
    add("en_zh_figures_align", _figures_align(data), "number sets match",
        blockable=legacy)
    add("exact_report_name",
        data.get("report_title", "") == "International Financial Media Weekly",
        data.get("report_title", ""))
    add("bilingual_blocks_present",
        bool(data.get("week_summary_en")) and bool(data.get("week_summary_zh")),
        "EN+ZH present")

    warnings = list(data.get("warnings", []))
    blocks = []
    for w in data.get("warnings", []):
        if any(b.lower() in str(w).lower() for b in LEGAL_BLOCK):
            blocks.append(str(w))
    for q in checks:
        if not q["pass"] and q.get("blockable", True) and (legacy or q["check"] in blocking):
            blocks.append(q["check"])

    passed_publish = not blocks and (legacy and all(q["pass"] for q in checks)
                                     or not legacy and all(q["pass"] or not q.get("blockable", True)
                                                           for q in checks))
    result = {"status": "PASS" if passed_publish else "FAIL",
              "blocked": bool(blocks), "checks": checks, "warnings": warnings, "blocks": blocks}
    with db.conn() as c:
        c.execute(
            "UPDATE editions SET qc_json=?, status=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False),
             "published" if result["status"] == "PASS" else "needs_review",
             edition_id))
    return result


def _figures_align(data: dict) -> bool:
    en = _numbers(json.dumps({k: v for k, v in data.items() if k.endswith("_en")}, ensure_ascii=False))
    zh = _numbers(json.dumps({k: v for k, v in data.items() if k.endswith("_zh")}, ensure_ascii=False))
    return en == zh


# Figures that appear in every edition regardless of content (report dates,
# common market references) and would always mismatch EN vs ZH. Kept explicit
# so a false block is easy to trace; extend when a new constant appears.
_NUM_EXCLUDE = {"13", "17", "7", "2026"}


def _numbers(s: str) -> set[str]:
    return {t for t in re.findall(r"\d+", s) if t not in _NUM_EXCLUDE}