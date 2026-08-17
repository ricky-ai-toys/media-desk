"""Weekly bilingual synthesis — the LLM editorial pass (deepseek-v4-flash).

Follows the v5 golden rules: evidence in, ranking by LLM not script,
EXACTLY 3-5 agenda topics / 3-4 narratives, and no fabrication
(transcript-only). One chat_json call per week; server-computable fields
(coverage, episode counts, evidence statuses) are overwritten from real
evidence after the call — the model writes prose, never numbers we can
compute ourselves. Legacy export fields (pr_counsel, watchlist_en/zh,
recurring_questions_en/zh) are derived here so email/PDF exports stay
byte-compatible.
"""
import datetime
import json

from .. import config
from .. import db
from .. import llm
from ..analyze.evidence import agenda_evidence, interview_monitor
from ..tokens import kw, overlap

SYSTEM = (
    "You are the editor of International Financial Media Weekly (no agency branding). "
    "Analyze ONLY the supplied weekly media corpus and its extracted evidence. "
    "Produce the structured bilingual report JSON. English first, full simplified "
    "Chinese adaptation for every ZH field. Acronyms (AI, ETF, ADR, CPI) stay as-is. "
    "Never invent topics, quotes, names or figures — if evidence is thin, say so in warnings. "
    "Editorial rules: "
    "(1) Open with one concise thesis that names the tension connecting the week's major stories, "
    "not a list of topics. "
    "(2) Rank agenda topics by editorial significance (prominence, momentum, reach, persistence), "
    "not just mention count; give each priority (critical|high|medium), momentum "
    "(accelerating|rising|stable|fading), evidence strength (strong|moderate|emerging) and "
    "coverage (number of programmes). "
    "(3) For each narrative give the previous frame and current frame, what drove the change, "
    "why it matters for companies, and the next test that would reinforce or reverse it. "
    "(4) Do not repeat the same development in different words across sections; each section has "
    "one job. "
    "(5) Watchpoints must name a trigger, the possible narrative change, affected areas, and what "
    "would raise its priority. "
    "(5b) monitored_outlets must list exactly the programmes supplied in the context — "
    "never name an outlet that was not monitored this week; the report's authority rests "
    "on its stated sample frame. "
    "(6) Every ZH field must read as natural, idiomatic simplified Chinese written by a "
    "mainland financial-media desk — restructure sentences and collocations rather than "
    "translating EN word-for-word; no English syntax or awkward calques in ZH text. "
    "(7) Write terse. Thesis <= 25 words. Each agenda summary is ONE sentence of <= 22 words. "
    "Each comms implication <= 14 words. Every cell field (driver, why, next_test, stakes, shift, "
    "affected, priority_raises, premise, response, lesson) <= 10 words, telegraphic, no lists. "
    "ZH fields obey the same brevity. "
    "(8) week_ahead_events must be 3-5 real, dated events strictly AFTER the reporting week "
    "(next Monday-Friday), each with a one-clause why-it-matters; never invent dates or events "
    "not supported by the corpus or universally known calendar items (policy meetings, data "
    "releases, earnings, deadlines). "
    "EXACTLY 3-5 agenda topics, EXACTLY 3-4 narratives, 3 media_exchanges, 3-5 watchpoints, "
    "recurring question groups of 3-5 questions each. No paragraphs."
)

SCHEMA = (
    'Return ONLY JSON with fields: report_title, start_date, end_date, monitored_outlets[], '
    'source_file_count, episode_count, '
    'thesis_en, thesis_zh, '
    'agenda_topics[] {rank, title_en, title_zh, summary_en, summary_zh, priority(critical|high|medium), '
    'momentum(accelerating|rising|stable|fading), evidence(strong|moderate|emerging), coverage(int), '
    'driver_en, driver_zh, next_test_en, next_test_zh, stakes_en, stakes_zh}, '
    'narratives[] {title_en, title_zh, from_en, to_en, from_zh, to_zh, driver_en, driver_zh, '
    'why_en, why_zh, next_test_en, next_test_zh}, '
    'comms_boxes[] {title_en, implication_en, questions_likely_en[], evidence_to_prepare_en[], '
    'risky_en, title_zh, implication_zh, questions_likely_zh[], evidence_to_prepare_zh[], risky_zh}, '
    'question_groups[] {category(policy_credibility|market_consequences|corporate_exposure|'
    'narrative_durability), questions_en[], questions_zh[]}, '
    'top_questions_next_week_en[], top_questions_next_week_zh[], '
    'media_exchanges[] {pattern_en, premise_en, response_en, lesson_en, likely_to_recur, '
    'pattern_zh, premise_zh, response_zh, lesson_zh}, '
    'watchpoints[] {trigger_en, shift_en, affected_en, priority_raises_en, '
    'trigger_zh, shift_zh, affected_zh, priority_raises_zh}, '
    'week_ahead_events[] {date(YYYY-MM-DD), event_en, event_zh, why_en, why_zh}, '
    'evidence_statuses[] {section, status(confirmed|supported|emerging|interpretive), note}, '
    'interview_groups_en[] {title_en, role_en, questions_en[3]}, '
    'interview_groups_zh[] {title_zh, role_zh, questions_zh[3]}, '
    'pr_counsel {risk_en, risk_zh, opportunity_en, opportunity_zh, prepare_en, prepare_zh, avoid_en, avoid_zh}, '
    'watchlist_en[], watchlist_zh[], recurring_questions_en[], recurring_questions_zh[], warnings[]'
)


def synthesize_week(start: str, end: str, force: bool = False) -> dict:
    """Weekly editorial synthesis. Evidence -> compact digest -> one LLM call
    (context kept lean so the delegation stays well under the timeout rule)."""
    edition_id = f"{start}_to_{end}"
    existing = db.edition_full(edition_id)
    if existing and not force:
        return {"edition": edition_id, "exists": True, "message": "already present"}
    evidence = agenda_evidence(start, end)
    monitor = interview_monitor(start, end)
    digest = _episode_digest(start, end)
    cov_lines = "\n".join(
        f"- {t}: mentions={n}, programmes={evidence['coverage'].get(t, 0)}, "
        f"first={evidence['first_seen'].get(t, '?')} last={evidence['last_seen'].get(t, '?')}"
        for t, n in list(evidence["topic_counts"].items())[:25])
    user = (
        f"REPORTING WEEK: {start} to {end}\n"
        f"MONITORED PROGRAMMES THIS WEEK: {', '.join(_week_outlets(start, end))}\n\n"
        f"## Agenda evidence (topic -> episode mentions)\n"
        f"{json.dumps(evidence['topic_counts'], ensure_ascii=False)[:4000]}\n"
        f"## Coverage evidence (programmes carrying each topic)\n{cov_lines[:4000]}\n"
        f"## Recurring question clusters\n"
        f"{json.dumps(monitor['recurring_questions'], ensure_ascii=False)[:2500]}\n\n"
        f"## Daily episode digests\n{digest[:26000]}\n\n{SCHEMA}"
    )
    try:
        data = llm.chat_json(SYSTEM, user, max_tokens=24000)
    except Exception as e:
        db.mark_edition_failed(start, end, str(e)[:300])
        _dump_raw(start, end, {"error": str(e)[:500]})
        raise
    _dump_raw(start, end, data)
    data.setdefault("warnings", [])
    data = _derive_legacy(data)
    data["start_date"], data["end_date"] = start, end
    _apply_evidence_overrides(data, evidence)
    data["evidence_statuses"] = _rule_based_statuses(data)
    edition_id = db.upsert_edition(data, _manifest(start, end), None)
    db.replace_interview_entries(edition_id, _entries(monitor["interview_log"]))
    return {"edition": edition_id, "exists": False, "outlets": data.get("monitored_outlets")}


def _dump_raw(start: str, end: str, payload: dict) -> None:
    """Persist the raw LLM payload for post-hoc audit (PR-facing traceability)."""
    out_dir = config.ROOT / "data" / "llm_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{start}_to_{end}.json").write_text(
        json.dumps({"start_date": start, "end_date": end,
                    "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "payload": payload}, ensure_ascii=False, indent=1),
        encoding="utf-8")


def _apply_evidence_overrides(data: dict, evidence: dict) -> None:
    """Overwrite every server-computable field with real evidence values.

    The LLM estimates `coverage` (programmes per topic); the live site showed
    a topic claiming 5/15 coverage while Wire-vs-TV showed zero evidence.
    Numbers we can compute are never trusted to the model.
    """
    data["episode_count"] = evidence["source_files"]
    data["source_file_count"] = evidence["source_files"]
    progs = evidence.get("topic_programmes", {})
    for t in data.get("agenda_topics") or []:
        k = kw(t.get("title_en", ""))
        matched: set[str] = set()
        for hot_topic, shows in progs.items():
            if k and overlap(k, kw(hot_topic)) >= 0.5:
                matched |= set(shows)
        t["coverage"] = len(matched)
        t["evidence_programmes"] = sorted(matched)
        if not matched:
            data.setdefault("warnings", []).append(
                f"no episode evidence for agenda topic: {(t.get('title_en') or '')[:80]}")


def _rule_based_statuses(data: dict) -> list[dict]:
    """Evidence statuses derived by rules, not self-graded by the LLM.

    Rationale: the model labelled its own unverifiable week-ahead dates
    'confirmed' on the live site. `confirmed` now requires real grounding;
    week-ahead events can never exceed `supported` without external
    verification.
    """
    covs = [t.get("coverage") or 0 for t in data.get("agenda_topics") or []]
    if covs and min(covs) >= 3:
        agenda_status = "supported"
    elif covs and min(covs) >= 1:
        agenda_status = "emerging"
    else:
        agenda_status = "interpretive"
    episodes = data.get("episode_count") or 0
    return [
        {"section": "Thesis",
         "status": "supported" if episodes else "interpretive",
         "note": f"derived from {episodes} episode digests"},
        {"section": "Agenda topics",
         "status": agenda_status,
         "note": "coverage computed server-side from programme evidence"},
        {"section": "Narratives",
         "status": "interpretive",
         "note": "frames inferred from topic sequencing, not full transcripts"},
        {"section": "Week ahead events",
         "status": "supported",
         "note": "calendar items; dates not externally verified"},
    ]


def _derive_legacy(data: dict) -> dict:
    """Schema v2 superset -> v1-compatible fields (email/PDF/QC keep working).
    Also guarantees week_summary (thesis) and repeated-count stability."""
    data["report_title"] = "International Financial Media Weekly"
    if not data.get("thesis_en"):
        data["thesis_en"] = data.get("week_summary_en", "")
    if not data.get("thesis_zh"):
        data["thesis_zh"] = data.get("week_summary_zh", "")
    data.setdefault("week_summary_en", data["thesis_en"])
    data.setdefault("week_summary_zh", data["thesis_zh"])

    groups = data.get("question_groups") or []
    for lang, src, dst in (("en", "questions_en", "recurring_questions_en"),
                           ("zh", "questions_zh", "recurring_questions_zh")):
        flat = [q for g in groups for q in (g.get(src) or []) if q]
        if flat:
            data[dst] = flat
        data.setdefault(dst, [])

    data.setdefault("top_questions_next_week_en", [])
    data.setdefault("top_questions_next_week_zh", [])

    for g in groups:
        g.setdefault("questions_en", [])
        g.setdefault("questions_zh", [])
    for w in data.get("watchpoints") or []:
        for k in ("trigger_en", "shift_en", "narrative_en", "priority_raises_en",
                  "trigger_zh", "shift_zh", "narrative_zh", "priority_raises_zh"):
            w.setdefault(k, "")
    data.setdefault("watchlist_en", [w.get("trigger_en", "") for w in data.get("watchpoints") or []])
    data.setdefault("watchlist_zh", [w.get("trigger_zh", "") for w in data.get("watchpoints") or []])

    for ex in data.get("media_exchanges") or []:
        for k in ("pattern_en", "premise_en", "response_en", "lesson_en",
                  "pattern_zh", "premise_zh", "response_zh", "lesson_zh"):
            ex.setdefault(k, "")
        if "likely_to_recur" not in ex:
            ex["likely_to_recur"] = True
    for es in data.get("evidence_statuses") or []:
        es.setdefault("note", "")
        if es.get("status") not in ("confirmed", "supported", "emerging", "interpretive"):
            es["status"] = "interpretive"
    data.setdefault("evidence_statuses", [])
    data.setdefault("week_ahead_events", [])

    # pr_counsel: never stitched from comms_boxes (mechanically concatenated
    # client-facing copy is worse than an honest gap). Missing fields stay
    # empty, raise a warning, and are gated by QC's pr_counsel_complete check.
    pr = data.get("pr_counsel") or {}
    for k in ("risk_en", "risk_zh", "opportunity_en", "opportunity_zh",
              "prepare_en", "prepare_zh", "avoid_en", "avoid_zh"):
        pr.setdefault(k, "")
    missing = sorted(k for k, v in pr.items() if not v)
    if missing:
        data.setdefault("warnings", []).append(
            "pr_counsel incomplete: " + ", ".join(missing))
    data["pr_counsel"] = pr

    return data


def _episode_digest(start: str, end: str) -> str:
    with db.conn() as c:
        rows = c.execute(
            "SELECT e.show_name, e.pub_date, a.hot_topics_json FROM analyses a "
            "JOIN episodes e ON e.id=a.episode_id WHERE e.pub_date>=? AND e.pub_date<=? "
            "ORDER BY e.pub_date", (start, end)).fetchall()
    lines = []
    for r in rows:
        topics = ", ".join(x.get("title", "") for x in json.loads(r["hot_topics_json"] or "[]"))
        lines.append(f"[{r['pub_date']}] {r['show_name']}: {topics[:500]}")
    return "\n".join(lines) or "(no analyses available this week)"


def _week_outlets(start: str, end: str) -> list[str]:
    """Programmes actually monitored this week — the report's sample frame."""
    with db.conn() as c:
        rows = c.execute(
            "SELECT DISTINCT show_name FROM episodes "
            "WHERE pub_date>=? AND pub_date<=? AND show_name IS NOT NULL "
            "ORDER BY show_name", (start, end)).fetchall()
    return [r["show_name"] for r in rows if r["show_name"]]


def _manifest(start: str, end: str) -> dict:
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, title, show_name, pub_date FROM episodes WHERE pub_date>=? AND pub_date<=?",
            (start, end)).fetchall()
        return {"start_date": start, "end_date": end,
                "episodes": [{"date": r["pub_date"], "file": f"{r['id']}.txt",
                              "program": r["show_name"], "title": r["title"]} for r in rows]}


def _entries(log: list[dict]) -> list[dict]:
    out = []
    for x in log:
        out.append({
            "guest": "", "org": "", "role": "", "show": x.get("show", ""),
            "date": x.get("date", ""), "tone": x.get("tone", ""),
            "questions": [x.get("question", "")],
            "notable_quotes": [x.get("reply", "")],
            "confidence": 0.5,
        })
    return out