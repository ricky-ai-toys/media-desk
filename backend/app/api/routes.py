"""Public read-only API routers (admin gated separately)."""
import json

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..analyze.evidence import pressure_index
from ..framing import engine as framing
from ..ingest import rss as rss_ingest
from ..ingest import youtube as yt_ingest
from ..synth import weekly as synth
from ..synth import qc

router = APIRouter()


@router.get("/meta")
def meta():
    latest = db.latest_edition()
    with db.conn() as c:
        editions = [dict(r) for r in c.execute(
            "SELECT id, start_date, end_date, status FROM editions ORDER BY end_date DESC")]
    health = db.source_health()
    return {"latest": latest["id"] if latest else None,
            "editions": editions,
            "sources": health,
            "pipeline": db.get_pipeline()}


@router.get("/desk")
def desk(edition: str | None = None):
    ed = db.edition_full(edition) if edition else (
        db.edition_full(db.latest_edition()["id"]) if db.latest_edition() else None)
    if not ed:
        raise HTTPException(404, "no edition found")
    press = pressure_index(db.interview_entries(ed["id"], limit=500))
    interviews = db.interview_entries(ed["id"], limit=120)
    agenda = list(ed["agenda"])
    for a in agenda:
        if isinstance(a.get("score"), (int, float)):
            a["score"] = framing.norm10(a["score"])
    return {
        "edition": ed["id"], "start": ed["start_date"], "end": ed["end_date"],
        "status": ed["status"], "qc": ed["qc"],
        "data": ed["data"], "agenda": agenda, "narratives": ed["narratives"],
        "interview_groups": ed["interview_groups"],
        "framing": {
            "collisions": framing.collisions(ed["id"]),
            "lead_lag": framing.lead_lag(ed["id"]),
            "asymmetry": framing.asymmetry(ed["id"]),
        },
        "attribution": _topic_attribution(ed["id"], agenda),
        "interviews": interviews,
        "ticker": _ticker(interviews),
    }


_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "its", "are",
         "was", "has", "had", "but", "not", "new", "after", "over", "than", "will",
         "per", "vs", "one", "two", "say", "says", "said", "also", "now", "get",
         "come", "week", "amid", "eyes", "watch", "deal", "fade", "test"}


def _topic_attribution(edition_id: str, agenda: list[dict]) -> list[dict]:
    """Which shows carried each agenda topic (FTS keyword match over chunk text)."""
    import re as _re
    from collections import Counter
    out = []
    with db.conn() as c:
        eps = [dict(r) for r in c.execute(
            "SELECT e.id, e.show_name FROM episodes e JOIN editions ed "
            "ON ed.id=? WHERE e.pub_date BETWEEN ed.start_date AND ed.end_date",
            (edition_id,))]
        show_of = {e["id"]: e["show_name"] for e in eps}
        if not eps:
            return []
        for a in agenda:
            text = f"{a.get('title_en') or ''} {a.get('summary_en') or ''}".lower()
            words = _re.findall(r"[a-z]{4,}", text)
            kws = [w for w in Counter(w for w in words if w not in _STOP).most_common(8)]
            counts: Counter = Counter()
            seen: set[str] = set()
            for w, _ in kws:
                rows = c.execute(
                    "SELECT tc.episode_id FROM transcript_chunks tc "
                    "JOIN episodes e ON e.id=tc.episode_id WHERE e.pub_date "
                    "BETWEEN (SELECT start_date FROM editions WHERE id=?) "
                    "AND (SELECT end_date FROM editions WHERE id=?) AND tc.text LIKE ?",
                    (edition_id, edition_id, f"%{w}%")).fetchall()
                for (eid,) in rows:
                    sn = show_of.get(eid)
                    if sn and eid not in seen:
                        seen.add(eid)
                        counts[sn] += 1
            per_show = [{"show": sn, "chunks": n} for sn, n in
                        counts.most_common(4)]
            out.append({"rank": a.get("rank"), "shows": per_show,
                        "total_episodes": len(eps),
                        "covered": sum(n for _, n in counts.items())})
    return out


def _ticker(interviews: list[dict]) -> list[dict]:
    flagged = [i for i in interviews if (i.get("tone") or "").lower() in ("challenging", "evasive")]
    return [{"date": i["date"], "show": i["show"], "tone": i["tone"],
             "question": (i.get("questions") or [""])[0][:160]} for i in flagged[:8]]


@router.get("/editions")
def editions():
    with db.conn() as c:
        rows = c.execute(
            "SELECT id, start_date, end_date, status, json_extract(data_json, '$.week_summary_en') AS summary "
            "FROM editions ORDER BY end_date DESC").fetchall()
    return [dict(r) for r in rows]


@router.get("/edition/{eid}")
def edition(eid: str):
    ed = db.edition_full(eid)
    if not ed:
        raise HTTPException(404, "edition not found")
    return ed


@router.get("/lifecycle")
def lifecycle():
    return framing.lifecycle()


@router.get("/interviews")
def interviews(edition: str | None = None, q: str | None = None,
               guest_type: str | None = None, limit: int = Query(200, le=1000)):
    return db.interview_entries(edition, q, guest_type, limit=limit)


@router.get("/framing")
def framing_view(edition: str):
    return {"collisions": framing.collisions(edition),
            "lead_lag": framing.lead_lag(edition),
            "asymmetry": framing.asymmetry(edition)}


@router.get("/radar")
def radar(edition: str | None = None):
    health = db.source_health()
    latest = db.latest_edition()
    eid = edition or (latest["id"] if latest else None)
    coverage = []
    if eid:
        with db.conn() as c:
            rows = c.execute(
                "SELECT e.show_name, e.pub_date, COUNT(*) n FROM episodes e "
                "WHERE e.pub_date>=? AND e.pub_date<=? GROUP BY e.show_name, e.pub_date",
                (eid.split("_to_")[0], eid.split("_to_")[1])).fetchall()
        coverage = [dict(r) for r in rows]
    with db.conn() as c:
        wire = [dict(r) for r in c.execute(
            "SELECT s.outlet, COUNT(*) n FROM articles a JOIN sources s ON s.id=a.source_id "
            "GROUP BY s.outlet ORDER BY n DESC")]
    return {"sources": health, "coverage": coverage, "wire_totals": wire,
            "wire_feed": _recent_articles()}


def _recent_articles(limit: int = 40) -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT a.title, a.link, a.pub_date, s.name AS source_name "
            "FROM articles a JOIN sources s ON s.id=a.source_id "
            "ORDER BY a.pub_date DESC LIMIT ?", (limit,))]


@router.get("/search")
def search(q: str = Query(min_length=2), limit: int = 30):
    return {"query": q, "results": db.query_fts(q, limit)}


@router.get("/stream")
async def stream():
    from .sse import event_stream
    return await event_stream()