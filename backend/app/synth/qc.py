"""QC gate, ported from the v5 qc_gate.py and re-pointed at DB artifacts.

Checks: reporting period, source coverage, dynamic topics (==4), structure,
narratives 4, recurring questions, EN/ZH figure alignment, exact report name,
bilingual blocks, legal-block phrases only.
"""
import datetime as _dt
import json
import re

from .. import db
from . import report_spec as spec

LEGAL_BLOCK = ("LOW_CONFIDENCE_BLOCK", "DO_NOT_SEND", "unverified claim in report")


def topic_facts_present(data: dict) -> bool:
    topics = data.get("agenda_topics", [])
    return bool(topics) and all(t.get("driver_en") and t.get("next_test_en") and t.get("stakes_en")
                                for t in topics)


def week_ahead_present(data: dict) -> bool:
    events = data.get("week_ahead_events", [])
    if not (spec.WEEK_AHEAD_RANGE[0] <= len(events) <= spec.WEEK_AHEAD_RANGE[1]):
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
        # prompt contract: strictly next Monday-Friday — weekends rejected
        if not (lo <= d <= hi) or d.weekday() >= 5 or not e.get("event_en"):
            return False
    return True


def pr_counsel_complete(data: dict) -> bool:
    """All eight PR-counsel cells non-empty (no stitched fallbacks allowed)."""
    pr = data.get("pr_counsel") or {}
    return all(pr.get(k) for k in
               ("risk_en", "risk_zh", "opportunity_en", "opportunity_zh",
                "prepare_en", "prepare_zh", "avoid_en", "avoid_zh"))


def interview_groups_parallel(data: dict) -> bool:
    """EN and ZH interview-group arrays must be the same length."""
    en, zh = data.get("interview_groups_en"), data.get("interview_groups_zh")
    if en is None and zh is None:
        return True
    return len(en or []) == len(zh or [])


def question_group_items_parallel(data: dict) -> bool:
    """Each question group must have the same number of EN and ZH questions."""
    for g in data.get("question_groups") or []:
        if len(g.get("questions_en") or []) != len(g.get("questions_zh") or []):
            return False
    return True


def terse_lengths(data: dict) -> bool:
    topics = data.get("agenda_topics", [])
    if not topics:
        return True
    over = [t for t in topics if len((t.get("summary_en") or "").split()) > spec.TERSE_QC_WORDS]
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
                "topic_facts_present", "week_ahead_present",
                "pr_counsel_complete", "interview_groups_parallel",
                "question_group_items_parallel")

    def add_v2(name, ok, detail):
        add(name, ok if not legacy else True,
            detail if not legacy else f"{detail} (legacy schema, will gate after resynthesis)",
            blockable=not legacy)

    add("correct_reporting_period",
        data.get("start_date") == ed["start_date"] and data.get("end_date") == ed["end_date"],
        f"{ed['start_date']}..{ed['end_date']}")
    add("minimum_source_coverage", len(days) >= 4, f"{len(days)} weekdays")
    add("source_manifest_saved", bool(episodes), f"{len(episodes)} episodes")
    add("topics_selected_dynamically",
        spec.TOPIC_RANGE[0] <= len(data.get("agenda_topics", [])) <= spec.TOPIC_RANGE[1],
        f"{len(data.get('agenda_topics', []))} topics")
    add("agenda_structure_complete",
        all(t.get("title_en") and t.get("summary_en") for t in data.get("agenda_topics", [])),
        "all topics have title+summary")
    add("narratives_3_to_4",
        spec.NARRATIVE_RANGE[0] <= len(data.get("narratives", [])) <= spec.NARRATIVE_RANGE[1],
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
    add_v2("comms_boxes_present", len(data.get("comms_boxes", [])) >= spec.COMMS_BOXES_MIN,
        f"{len(data.get('comms_boxes', []))} comms boxes")
    add_v2("question_group_categories_vocab",
        all(g.get("category") in spec.QUESTION_CATEGORIES
            for g in data.get("question_groups", [])),
        "categories within vocab")
    add_v2("watchpoint_triggers_present",
        all(bool(w.get("trigger_en")) for w in data.get("watchpoints", []))
        and spec.WATCHPOINT_RANGE[0] <= len(data.get("watchpoints", [])) <= spec.WATCHPOINT_RANGE[1],
        f"{len(data.get('watchpoints', []))} watchpoints with triggers")
    add_v2("media_exchanges_complete",
        len(data.get("media_exchanges", [])) >= spec.MEDIA_EXCHANGES_MIN
        and all(ex.get("pattern_en") and ex.get("premise_en") for ex in data.get("media_exchanges", [])),
        f"{len(data.get('media_exchanges', []))} exchanges")
    add_v2("evidence_status_vocab",
        all(es.get("status") in spec.EVIDENCE_STATUSES
            for es in data.get("evidence_statuses", [])),
        f"{len(data.get('evidence_statuses', []))} statuses in vocab")
    add_v2("agenda_labeled",
        all(t.get("priority") in spec.PRIORITIES
            and t.get("momentum") in spec.MOMENTA
            and t.get("evidence") in spec.EVIDENCE_LEVELS
            for t in data.get("agenda_topics", [])),
        "priority/momentum/evidence labels on all topics")
    add_v2("topic_facts_present", topic_facts_present(data),
        f"{len(data.get('agenda_topics', []))} topics with driver/next_test/stakes")
    add_v2("week_ahead_present", week_ahead_present(data),
        f"{len(data.get('week_ahead_events', []))} events in next-week window")
    add_v2("pr_counsel_complete", pr_counsel_complete(data),
        "all 8 PR-counsel cells present")
    add_v2("interview_groups_parallel", interview_groups_parallel(data),
        f"EN {len(data.get('interview_groups_en') or [])} / "
        f"ZH {len(data.get('interview_groups_zh') or [])} groups")
    add_v2("question_group_items_parallel", question_group_items_parallel(data),
        "EN/ZH question counts equal per group")
    add("terse_lengths", terse_lengths(data),
        "topic summaries within soft length budget", blockable=False)
    fig_diffs = _figure_diffs(data)
    add("en_zh_figures_align", not fig_diffs,
        "; ".join(fig_diffs[:3]) if fig_diffs else "number sets match",
        blockable=legacy)
    add("exact_report_name",
        data.get("report_title", "") == spec.REPORT_TITLE,
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

    legacy_ok = legacy and all(q["pass"] for q in checks)
    v2_ok = (not legacy) and all(q["pass"] or not q.get("blockable", True) for q in checks)
    passed_publish = not blocks and (legacy_ok or v2_ok)
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
    return not _figure_diffs(data)


def _figure_diffs(data: dict) -> list[str]:
    """Per-field EN/ZH number-set comparison (recursive over _en/_zh pairs).

    Replaces the old global set comparison: a figure legitimately present in
    only one language of one field no longer masks — or fakes — alignment
    elsewhere. Returns human-readable diffs for QC detail.
    """
    excluded = _dynamic_excludes(data)
    diffs = []
    for path, en_text, zh_text in _paired_texts(data):
        en = _numbers(en_text, excluded)
        zh = _numbers(zh_text, excluded)
        if en != zh:
            diffs.append(f"{path or '(top)'}: EN {sorted(en)} vs ZH {sorted(zh)}")
    return diffs


def _paired_texts(obj, path=""):
    """Yield (path, en_text, zh_text) for every sibling *_en/*_zh pair."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_en") and isinstance(v, str):
                zk = k[:-3] + "_zh"
                zh = obj.get(zk)
                if isinstance(zh, str):
                    yield (f"{path}.{k[:-3]}" if path else k[:-3], v, zh)
            else:
                yield from _paired_texts(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _paired_texts(item, f"{path}[{i}]")


def _dynamic_excludes(data: dict) -> set[str]:
    """Numbers guaranteed to appear regardless of content (report dates and
    structural constants) — derived from the edition itself, not hardcoded,
    so the check keeps working when the calendar year rolls over."""
    ex = {"7"}  # days per week, appears in boilerplate
    for key in ("start_date", "end_date"):
        try:
            d = _dt.date.fromisoformat(str(data.get(key, "")))
        except ValueError:
            continue
        ex.update({str(d.year), str(d.month), str(d.day),
                   f"{d.month:02d}", f"{d.day:02d}"})
    return ex


def _numbers(s: str, excluded: set[str] | None = None) -> set[str]:
    excluded = excluded or set()
    return {t for t in re.findall(r"\d+", s) if t not in excluded}