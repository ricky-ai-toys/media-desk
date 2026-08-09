"""Admin endpoints — token-gated, run ingestion/synthesis/QC on demand."""
import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException

from .. import config
from .. import db
from ..ingest import rss as rss_ingest
from ..ingest import youtube as yt_ingest
from ..synth import weekly as synth
from ..synth import qc


def _guard(x_admin_token: str | None = Header(default=None)):
    expected = config.admin_token()
    if not expected:
        raise HTTPException(403, "admin token not configured")
    if x_admin_token != expected:
        raise HTTPException(401, "bad token")


admin = APIRouter(prefix="/admin", dependencies=[Depends(_guard)])


@admin.post("/ingest")
def run_ingest():
    """Full ingest pass: wire RSS sync + youtube playlist sync (new transcripts)."""
    db.upsert_pipeline("ingest", "running", "RSS + playlist sync started")
    try:
        rss_results = [rss_ingest.fetch_feed(s) for s in config.sources_by_kind("rss")]
        yt_results = [yt_ingest.sync_playlist(s) for s in config.sources_by_kind("yt_playlist")]
    except Exception as e:  # noqa: BLE001
        db.upsert_pipeline("ingest", "failed", str(e)[:300])
        raise HTTPException(500, str(e)[:300])
    db.upsert_pipeline("ingest", "done",
                       f"rss={len(rss_results)} yt={len(yt_results)} sources synced")
    return {"rss": rss_results, "yt": yt_results}


@admin.post("/analyze")
def run_analyze():
    """Daily analysis for transcripts lacking one (LLM, chunked per episode)."""
    from ..analyze import daily
    with db.conn() as c:
        rows = c.execute(
            "SELECT DISTINCT e.id, e.title, e.show_name, e.pub_date FROM episodes e "
            "LEFT JOIN analyses a ON a.episode_id=e.id WHERE a.id IS NULL "
            "ORDER BY e.pub_date DESC LIMIT 20").fetchall()
    done, failed = [], []
    db.upsert_pipeline("analyze", "running", f"episodes queued: {len(rows)}")
    for r in rows:
        try:
            text = db.transcript_for(r["id"])
            daily.analyze_episode(r["id"], text, r["show_name"], r["pub_date"], r["title"])
            done.append(r["id"])
            db.upsert_pipeline("analyze", "running", f"analyzed {len(done)}/{len(rows)}")
        except Exception as e:  # noqa: BLE001
            failed.append({"id": r["id"], "error": str(e)[:200]})
    db.upsert_pipeline("analyze", "done", f"{len(done)} analyzed, {len(failed)} failed")
    return {"analyzed": done, "failed": failed}


@admin.post("/synthesize")
def run_synthesize(start: str | None = None, end: str | None = None, force: bool = False):
    if not start or not end:
        start, end = _last_week()
    try:
        out = synth.synthesize_week(start, end, force=force)
    except Exception as e:  # noqa: BLE001
        db.upsert_pipeline("synth", "failed", str(e)[:300])
        raise HTTPException(500, str(e)[:300])
    db.upsert_pipeline("synth", "done", f"week {start}..{end} synthesized")
    return out


@admin.post("/qc/{edition_id}")
def run_qc(edition_id: str):
    ed = db.edition_full(edition_id)
    if not ed:
        raise HTTPException(404, "edition not found")
    res = qc.run_qc(edition_id)
    return res


def _last_week() -> tuple[str, str]:
    today = datetime.date.today()
    d = today - datetime.timedelta(days=1)
    while d.weekday() != 4:
        d -= datetime.timedelta(days=1)
    end = d
    start = end - datetime.timedelta(days=4)
    return start.isoformat(), end.isoformat()