"""Framing analytics — the desk's novel layer.

Built on the seeded editions, episodes, analyses and interview entries:
- lifecycle tracks: agenda topics chained across editions with phase transitions
- framing collisions: same topic, opposite sentiment frames, with evidence quotes
- lead-lag: per-topic ordering of first coverage across shows and wire feeds
- coverage asymmetry: which shows ignored a top topic; wire-vs-TV gaps
"""
import datetime
import json
import re
from collections import defaultdict

from .. import db
from ..tokens import kw, overlap


def _tracks(topics: list[dict]) -> list[dict]:
    """Group agenda_topics rows across editions into lifecycle tracks."""
    tracks: list[dict] = []
    for row in topics:
        k = kw(row["title_en"])
        best_i, best = None, 0.0
        for i, tr in enumerate(tracks):
            s = overlap(tr["_kw"], k)
            if s > best:
                best_i, best = i, s
        if best_i is not None and best >= 0.4:
            tracks[best_i]["points"].append(row)
            tracks[best_i]["_kw"] |= k
        else:
            tracks.append({"_kw": set(k), "points": [row]})
    out = []
    for tr in tracks:
        pts = sorted(tr["points"], key=lambda p: (p["end_date"], p["rank"]))
        top = max(pts, key=lambda p: p["score"])
        out.append({
            "label": top["title_en"], "title_zh": top.get("title_zh") or "",
            "first_seen": pts[0]["edition_id"], "last_seen": pts[-1]["edition_id"],
            "week_count": len({p["edition_id"] for p in pts}),
            "points": [{"edition": p["edition_id"], "rank": p["rank"], "score": norm10(p["score"]),
                        "direction": p["direction"], "end_date": p["end_date"]} for p in pts],
        })
    out.sort(key=lambda t: (len(t["points"]), t["last_seen"]), reverse=True)
    for t in out:
        t["phase"] = _phase(t["points"])
        if len(t["points"]) >= 2:
            f, l = t["points"][0], t["points"][-1]
            t["rank_delta"] = l["rank"] - f["rank"]
            t["score_delta"] = round((l.get("score") or 0) - (f.get("score") or 0), 1)
        else:
            t["rank_delta"] = t["score_delta"] = 0
    return out


def norm10(score: float) -> float:
    """Legacy editions mixed 0-10 and 0-100 scores; expose everything as /10."""
    if score is None:
        return 0.0
    if score > 10:
        return round(score / 10, 1)
    return round(float(score), 1)


def _phase(pts: list[dict]) -> str:
    if len(pts) == 1:
        return "new"
    last = pts[-1].get("direction", "")
    if last in ("fading", "shifting"):
        return "fading"
    if last in ("rising", "accelerating"):
        return "rising"
    if len(pts) >= 3 and pts[-2].get("direction") in ("rising", "accelerating"):
        return "peaked"
    return "stable"


def lifecycle() -> dict:
    return {"tracks": _tracks(db.agenda_series())}


def _tone_score(md: str) -> int | None:
    m = re.search(r"(?:Tone|Sentiment)[:\*]*\s*[^(【（]*\(?([+-]?\d{1,2})\)", md or "")
    return int(m.group(1)) if m else None


def _analyses_for_week(start: str, end: str) -> list[dict]:
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT a.markdown, e.title, e.show_name, e.pub_date FROM analyses a "
            "JOIN episodes e ON e.id=a.episode_id WHERE e.pub_date>=? AND e.pub_date<=?",
            (start, end))]


def collisions(edition_id: str) -> list[dict]:
    """Same-topic framing fights inside one edition, with show-level evidence."""
    ed = db.edition_full(edition_id)
    if not ed:
        return []
    topics = ed["data"].get("agenda_topics", [])
    analyses = _analyses_for_week(ed["start_date"], ed["end_date"])
    by_topic: dict[str, list] = defaultdict(list)
    for t in topics:
        k = kw(t.get("title_en", ""))
        if not k:
            continue
        for a in analyses:
            if overlap(k, kw(a["title"])) >= 0.5:
                by_topic[t["title_en"]].append({
                    "source": a["show_name"], "date": a["pub_date"],
                    "score": _tone_score(a["markdown"] or ""), "episode_title": a["title"]})
    out = []
    for title, ev in by_topic.items():
        scored = [e for e in ev if e["score"] is not None]
        if len(scored) < 2:
            continue
        spread = max(e["score"] for e in scored) - min(e["score"] for e in scored)
        if spread >= 3:
            out.append({"topic": title, "spread": spread,
                        "extreme_bull": max(scored, key=lambda e: e["score"]),
                        "extreme_bear": min(scored, key=lambda e: e["score"]),
                        "n": len(scored)})
    return sorted(out, key=lambda c: c["spread"], reverse=True)


def _week_episode_topics(start: str, end: str) -> list[dict]:
    """Episode + its analysed hot topics (titles may be filenames for legacy weeks)."""
    with db.conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT e.id, e.pub_date, e.show_name, a.hot_topics_json FROM episodes e "
            "LEFT JOIN analyses a ON a.episode_id = e.id "
            "WHERE e.pub_date>=? AND e.pub_date<=?", (start, end))]


def lead_lag(edition_id: str) -> list[dict]:
    """Per agenda topic: first TV mention, first wire mention, wire lead in days."""
    ed = db.edition_full(edition_id)
    if not ed:
        return []
    with db.conn() as c:
        wire = [dict(r) for r in c.execute(
            "SELECT title, pub_date FROM articles WHERE pub_date>=? AND pub_date<=?",
            (ed["start_date"], ed["end_date"]))]
    eps = _week_episode_topics(ed["start_date"], ed["end_date"])
    out = []
    for t in ed["agenda"]:
        k = kw(t.get("title_en", ""))
        hits = []
        for e in eps:
            topics = " ".join(x.get("title", "") for x in
                              json.loads(e["hot_topics_json"] or "[]"))
            if overlap(k, kw(topics)) >= 0.4:
                hits.append(e)
        wires = [w for w in wire if overlap(k, kw(w["title"])) >= 0.4]
        first_show = min(hits, key=lambda s: s["pub_date"])["pub_date"] if hits else None
        first_wire = min(wires, key=lambda w: w["pub_date"])["pub_date"] if wires else None
        gap_days = None
        if first_show and first_wire:
            try:
                gap_days = (datetime.date.fromisoformat(first_show) -
                            datetime.date.fromisoformat(first_wire)).days
            except ValueError:
                gap_days = None
        out.append({
            "topic": t["title_en"], "tv_first": first_show, "wire_first": first_wire,
            "wire_lead_days": gap_days, "tv_count": len(hits), "wire_count": len(wires),
        })
    return out


def asymmetry(edition_id: str) -> list[dict]:
    """Blind spots: top topics absent from shows that carried other agenda items."""
    ed = db.edition_full(edition_id)
    if not ed:
        return []
    eps = _week_episode_topics(ed["start_date"], ed["end_date"])
    shows = sorted({e["show_name"] for e in eps})
    out = []
    for t in ed["agenda"]:
        k = kw(t.get("title_en", ""))
        absent = []
        for sh in shows:
            carried = any(
                e["show_name"] == sh and
                overlap(k, kw(" ".join(x.get("title", "") for x in
                                      json.loads(e["hot_topics_json"] or "[]")))) >= 0.4
                for e in eps)
            if not carried:
                absent.append(sh)
        if absent:
            out.append({"topic": t["title_en"], "absent_shows": absent})
    return out