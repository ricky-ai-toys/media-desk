"""Public read-only API routers (admin gated separately)."""
import datetime
import json
import re
from collections import Counter

from fastapi import APIRouter, HTTPException, Query

from .. import db
from ..analyze.evidence import pressure_index
from ..framing import engine as framing
from ..ingest import rss as rss_ingest
from ..ingest import youtube as yt_ingest
from ..synth import weekly as synth
from ..synth import qc

router = APIRouter()

EDITION_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})$")


def _public_pipeline(p: dict | None) -> dict | None:
    """Public pipeline view: stage/status only — internal messages stay admin-side."""
    if not p:
        return None
    return {"stage": p.get("stage"), "status": p.get("status"),
            "updated_at": p.get("updated_at")}


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
            "pipeline": _public_pipeline(db.get_pipeline())}


@router.get("/desk")
def desk(edition: str | None = None):
    latest = db.latest_edition()
    ed = db.edition_full(edition) if edition else (
        db.edition_full(latest["id"]) if latest else None)
    if not ed:
        raise HTTPException(404, "no edition found")
    if ed["status"] in ("blocked_no_evidence", "synth_failed"):
        # Withheld weeks render as a visible gap, not a half-empty report.
        return {
            "edition": ed["id"], "start": ed["start_date"], "end": ed["end_date"],
            "status": ed["status"], "qc": None,
            "data": ed["data"], "agenda": [], "narratives": [],
            "interview_groups": [],
            "framing": {"collisions": [], "lead_lag": [], "asymmetry": []},
            "attribution": [], "interviews": [], "pressure": [], "ticker": [],
        }
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
            "collisions": framing.collisions(ed),
            "lead_lag": framing.lead_lag(ed),
            "asymmetry": framing.asymmetry(ed),
        },
        "attribution": _topic_attribution(ed["id"], agenda),
        "interviews": db.interview_entries(ed["id"], limit=120),
        "pressure": pressure_index(db.interview_entries(ed["id"], limit=500)),
        "ticker": _ticker(db.interview_entries(ed["id"], limit=120)),
    }


_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "its", "are",
         "was", "has", "had", "but", "not", "new", "after", "over", "than", "will",
         "per", "vs", "one", "two", "say", "says", "said", "also", "now", "get",
         "come", "week", "amid", "eyes", "watch", "deal", "fade", "test"}


def _topic_attribution(edition_id: str, agenda: list[dict]) -> list[dict]:
    """Which shows carried each agenda topic (keyword match over chunk text).

    All keywords for a topic go into one OR-combined scan; DISTINCT keeps the
    count at one hit per episode regardless of how many keywords matched.
    """
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
            words = re.findall(r"[a-z]{4,}", text)
            kws = [w for w, _ in Counter(w for w in words if w not in _STOP).most_common(8)]
            counts: Counter = Counter()
            if kws:
                cond = " OR ".join("tc.text LIKE ?" for _ in kws)
                rows = c.execute(
                    "SELECT DISTINCT tc.episode_id FROM transcript_chunks tc "
                    "JOIN episodes e ON e.id=tc.episode_id JOIN editions ed ON ed.id=? "
                    "WHERE e.pub_date BETWEEN ed.start_date AND ed.end_date "
                    f"AND ({cond})",
                    (edition_id, *[f"%{w}%" for w in kws])).fetchall()
                for (eid,) in rows:
                    sn = show_of.get(eid)
                    if sn:
                        counts[sn] += 1
            per_show = [{"show": sn, "chunks": n} for sn, n in
                        counts.most_common(4)]
            out.append({"rank": a.get("rank"), "shows": per_show,
                        "total_episodes": len(eps),
                        "covered": sum(counts.values())})
    return out


def _normalized(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _ticker(interviews: list[dict]) -> list[dict]:
    """Flagged anchor questions, each verified against the day's transcript.

    Items whose wording cannot be found in the transcript are marked
    verified=False so the UI can label them as paraphrase instead of
    presenting editorial inference as a verbatim quote.
    """
    flagged = [i for i in interviews if (i.get("tone") or "").lower() in ("challenging", "evasive")]
    corpus: dict[tuple, str] = {}
    out = []
    with db.conn() as c:
        for i in flagged[:8]:
            key = (i.get("show") or "", i.get("date") or "")
            if key not in corpus:
                rows = c.execute(
                    "SELECT tc.text FROM transcript_chunks tc "
                    "JOIN episodes e ON e.id=tc.episode_id "
                    "WHERE e.show_name=? AND e.pub_date=?", key).fetchall()
                corpus[key] = _normalized("\n".join(r["text"] for r in rows))
            q = (i.get("questions") or [""])[0]
            snippet = " ".join(_normalized(q).split()[:8])
            verified = bool(snippet) and snippet in corpus[key]
            out.append({"date": i["date"], "show": i["show"],
                        "guest": i.get("guest"), "org": i.get("org"),
                        "tone": i["tone"], "question": q[:160],
                        "verified": verified})
    return out


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
    if ed["status"] in ("blocked_no_evidence", "synth_failed"):
        # Same honesty as /desk: withheld weeks expose metadata + warnings only.
        return {"id": ed["id"], "start_date": ed["start_date"],
                "end_date": ed["end_date"], "status": ed["status"],
                "data": ed["data"], "manifest": {}, "qc": None,
                "agenda": [], "narratives": [], "interview_groups": []}
    return ed


@router.get("/wordcloud/{eid}")
def wordcloud(eid: str, week: str = "this"):
    """Term-cloud PNG for the edition — `week=this` (ink + red risers) or
    `week=prev` (muted last-week cloud); 404 when it cannot be produced."""
    from fastapi import Response
    from .. import wordcloud as wcgen
    if week not in ("this", "prev"):
        raise HTTPException(status_code=400, detail="week must be 'this' or 'prev'")
    if not EDITION_ID_RE.fullmatch(eid):
        raise HTTPException(status_code=404, detail="edition not found")
    try:
        png = wcgen.build_png(eid, week=week)
    except Exception:
        png = None
    if not png:
        raise HTTPException(status_code=404, detail="word cloud unavailable")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/lifecycle")
def lifecycle():
    return framing.lifecycle()


@router.get("/interviews")
def interviews(edition: str | None = None, q: str | None = None,
               guest_type: str | None = None, limit: int = Query(200, le=1000)):
    return db.interview_entries(edition, q, guest_type, limit=limit)


@router.get("/framing")
def framing_view(edition: str):
    ed = db.edition_full(edition)
    return {"collisions": framing.collisions(ed),
            "lead_lag": framing.lead_lag(ed),
            "asymmetry": framing.asymmetry(ed)}


@router.get("/radar")
def radar(edition: str | None = None):
    health = db.source_health()
    latest = db.latest_edition()
    eid = edition or (latest["id"] if latest else None)
    m = EDITION_ID_RE.fullmatch(eid or "")
    if not m:
        raise HTTPException(404, "edition not found")
    try:
        start = datetime.date.fromisoformat(m.group(1)).isoformat()
        end = datetime.date.fromisoformat(m.group(2)).isoformat()
    except ValueError:
        raise HTTPException(404, "edition not found")
    with db.conn() as c:
        coverage = [dict(r) for r in c.execute(
            "SELECT e.show_name, e.pub_date, COUNT(*) n FROM episodes e "
            "WHERE e.pub_date>=? AND e.pub_date<=? GROUP BY e.show_name, e.pub_date",
            (start, end))]
    with db.conn() as c:
        wire = [dict(r) for r in c.execute(
            "SELECT s.outlet, COUNT(*) n FROM articles a JOIN sources s ON s.id=a.source_id "
            "GROUP BY s.outlet ORDER BY n DESC")]
    return {"sources": health, "coverage": coverage, "wire_totals": wire,
            "coverage_matrix": db.coverage_radar(eid)["matrix"],
            "wire_feed": _recent_articles()}


def _recent_articles(limit: int = 40) -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT a.title, a.link, a.pub_date, s.name AS source_name "
            "FROM articles a JOIN sources s ON s.id=a.source_id "
            "ORDER BY a.pub_date DESC LIMIT ?", (limit,))]


@router.get("/search")
def search(q: str = Query(min_length=2), limit: int = Query(30, le=100)):
    return {"query": q, "results": db.query_fts(q, limit)}


@router.get("/stream")
async def stream():
    from .sse import event_stream
    return await event_stream()