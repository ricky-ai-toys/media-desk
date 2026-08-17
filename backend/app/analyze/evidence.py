"""Evidence extractors, ported from the v5 pipeline and re-pointed at the DB.

- extract_hot_topics / agenda_evidence: candidate topics + frequency (LLM ranks later)
- parse_tension / interview_monitor: per-interview records + recurring question clusters
"""
import re
from collections import defaultdict

from .. import db

TOPIC_STOP = {"this", "that", "with", "from", "will", "have", "been", "their", "about",
              "into", "more", "over", "after", "week", "market", "markets", "china",
              "lens", "macro", "tech", "political", "commercial", "tone", "negative",
              "cautious", "positive", "neutral"}

_TENSION_SEC = re.compile(r"##\s*5\..*?Anchor[–-]Guest Tension(.*?)(?=\n##\s|\Z)", re.S)
_QTITLE = re.compile(r"\*\*(\d+)[.)]?\s+(.+?)\*\*$")
_GREPLY = re.compile(r"\*\*(?:Guest reply|Guest reply:)\*\*\s*(.*?)\s*\*\*(?:Tension point|Tension point:)\*\*", re.S)
_TENS = re.compile(r"\*\*(?:Tension point|Tension point:)\*\*\s*(.*?)(?=\n\d+\.|\Z)", re.S)
_ATTR = re.compile(r"—\s*[^—\n]*?(Anchor|Reporter|Bloomberg|CNBC)[^\n]*")


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s*[-–]\s*$", "", s.strip())
    s = _ATTR.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_hot_topics(md: str) -> list[str]:
    m = re.search(r"##\s*2\.\s*Hot Topics.*?(?=\n##\s|\Z)", md, re.S)
    if not m:
        return []
    out = []
    for line in m.group(0).splitlines():
        tm = _QTITLE.match(line.strip())
        if tm:
            t = re.split(r"\s*/\s*", tm.group(2).strip())[0].strip()
            if 8 <= len(t) <= 200:
                out.append(t)
    return out


def agenda_evidence(start: str, end: str) -> dict:
    counts: dict[str, int] = defaultdict(int)
    days: set[str] = set()
    programmes: dict[str, set] = defaultdict(set)
    seen: dict[str, set] = defaultdict(set)
    with db.conn() as c:
        rows = c.execute(
            "SELECT a.markdown, e.pub_date, e.show_name FROM analyses a "
            "JOIN episodes e ON e.id=a.episode_id "
            "WHERE e.pub_date>=? AND e.pub_date<=?", (start, end)).fetchall()
        for r in rows:
            days.add(r["pub_date"])
            for t in extract_hot_topics(r["markdown"] or ""):
                counts[t] += 1
                programmes[t].add(r["show_name"] or "")
                seen[t].add(r["pub_date"])
    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return {
        "topic_counts": dict(ranked),
        "coverage": {t: len(programmes[t]) for t in counts},
        "topic_programmes": {t: sorted(p for p in programmes[t] if p) for t in counts},
        "first_seen": {t: min(seen[t]) for t in counts},
        "last_seen": {t: max(seen[t]) for t in counts},
        "source_files": len(rows),
        "days": sorted(days),
    }


def parse_tension(md: str) -> list[dict]:
    m = _TENSION_SEC.search(md or "")
    if not m:
        return []
    items = []
    for seg in re.split(r"\n\d+\.\s+\*\*Anchor question:\*\*", m.group(1)):
        if not seg.strip():
            continue
        q = re.search(r"(.*?)\s*\*\*(?:Guest reply|Guest reply:)\*\*", seg, re.S)
        r = _GREPLY.search(seg)
        t = _TENS.search(seg)
        question = clean_text(q.group(1)) if q else ""
        reply = clean_text(r.group(1)) if r else ""
        tension = clean_text(t.group(1)) if t else ""
        if not question:
            continue
        items.append({"question": question, "reply": reply[:240], "tension": tension[:240],
                      "tone": classify_tone(question, reply, tension)})
    return items


def classify_tone(q: str, r: str, t: str) -> str:
    low = (q + " " + r + " " + t).lower()
    if any(w in low for w in ["contradict", "challenge", "irresponsible", "deflect", "pushback", "disagree"]):
        return "challenging"
    if any(w in low for w in ["evade", "not allowed", "compliance", "deflection", "avoid"]):
        return "evasive"
    if any(w in low for w in ["bull", "upside", "buy", "growth", "optimistic", "exponential"]):
        return "supportive"
    return "exploratory"


def interview_monitor(start: str, end: str) -> dict:
    log: list[dict] = []
    with db.conn() as c:
        rows = c.execute(
            "SELECT a.markdown, a.episode_id, e.pub_date, e.show_name FROM analyses a "
            "JOIN episodes e ON e.id=a.episode_id WHERE e.pub_date>=? AND e.pub_date<=? "
            "ORDER BY e.pub_date", (start, end)).fetchall()
        for r in rows:
            for it in parse_tension(r["markdown"] or ""):
                log.append({"date": r["pub_date"], "source_file": f"{r['episode_id']}_daily_analysis.md",
                            "show": r["show_name"], **it, "confidence": "medium"})
    recurring = cluster_questions([x["question"] for x in log])
    return {"interview_log": log, "recurring_questions": recurring, "interview_count": len(log)}


KW_STOP = {"the", "a", "an", "is", "are", "will", "how", "what", "why", "do", "you",
           "we", "this", "that", "of", "to", "in", "on", "for", "with", "and", "or"}


def _kw(q: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", q.lower()) if len(w) >= 4 and w not in KW_STOP}


def cluster_questions(questions: list[str], min_share: float = 0.5) -> list[dict]:
    clusters: list[dict] = []
    for q in questions:
        k = _kw(q)
        if not k:
            continue
        placed = False
        for cl in clusters:
            if len(k & cl["kw"]) / max(1, len(k)) >= min_share:
                cl["qs"].append(q)
                cl["kw"] |= k
                placed = True
                break
        if not placed:
            clusters.append({"theme": q, "kw": set(k), "qs": [q]})
    clusters.sort(key=lambda c: len(c["qs"]), reverse=True)
    return [{"theme": cl["qs"][0][:200], "occurrences": len(cl["qs"]),
             "sample_questions": cl["qs"][:4]} for cl in clusters[:6]]


def pressure_index(entries: list[dict]) -> list[dict]:
    """Anchor pressure per (edition, show): challenges vs softballs, evasion rate."""
    by: dict[tuple, dict] = {}
    for e in entries:
        tone = (e.get("tone") or "").lower()
        key = (e.get("date", ""), e.get("show", "?"))
        b = by.setdefault(key, {"challenges": 0, "softballs": 0, "evasions": 0, "n": 0})
        b["n"] += 1
        if tone == "challenging":
            b["challenges"] += 1
        if tone == "evasive":
            b["evasions"] += 1
        if tone == "supportive":
            b["softballs"] += 1
    out = []
    for (date, show), b in sorted(by.items()):
        n = max(1, b["n"])
        pressure = (b["challenges"] + 0.5 * b["evasions"]) / n
        out.append({"date": date, "show": show, "pressure": round(pressure, 2),
                    "challenges": b["challenges"], "softballs": b["softballs"],
                    "evasions": b["evasions"], "sampled": b["n"]})
    return out