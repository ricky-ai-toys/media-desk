"""One-time importer of existing v5 pipeline artifacts into the Media Desk store.

Usage: python -m backend.app.seed [--all | --edition 2026-08-03_to_2026-08-07]
"""
import argparse
import json
import re
from pathlib import Path

from . import config
from . import db

SHOW_LABEL = {
    "The Asia Trade": "The Asia Trade",
    "The China Show": "The China Show",
    "Insight": "Insight with Haslinda Amin",
}
SOURCE_BY_SHOW = {
    "The Asia Trade": "bloomberg_asia_trade",
    "The China Show": "bloomberg_china_show",
    "Insight with Haslinda Amin": "bloomberg_insight",
    "Insight": "bloomberg_insight",
}


def _chunk(text: str, size: int = 900) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def import_transcript(episode: dict) -> str | None:
    """Import raw transcript + daily analysis for one manifest episode."""
    date, fname = episode.get("date"), episode.get("file")
    if not date or not fname:
        return None
    raw_dir = Path(config.V5["raw_root"]) / date
    ep_id = Path(fname).stem
    if not Path(raw_dir / fname).exists():
        return None
    text = (raw_dir / fname).read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    words = len(text.split())
    show = episode.get("program", "The Asia Trade")
    source_id = SOURCE_BY_SHOW.get(show, "bloomberg_asia_trade")
    db.upsert_episode({
        "id": ep_id, "source_id": source_id, "external_id": ep_id,
        "title": fname, "show_name": show, "pub_date": date,
        "url": "", "kind": "yt", "words": words,
        "transcript_path": str(raw_dir / fname),
    })
    db.replace_chunks(ep_id, _chunk(text))
    analysis_dir = Path(config.V5["analysis_root"]) / date
    md = analysis_dir / f"{ep_id}_daily_analysis.md"
    if md.exists():
        text = md.read_text(encoding="utf-8", errors="replace")
        db.upsert_analysis(ep_id, text,
                           _parse_hot_topics(text), _parse_tension(text))
    return ep_id


def _parse_hot_topics(md: str) -> list[dict]:
    items = []
    for m in re.finditer(r"\*\*(\d+)\.\s+(.+?)\*\*(?:\s*\n|$)", md):
        items.append({"rank": int(m.group(1)), "title": m.group(2).strip()})
    return items


def _parse_tension(md: str) -> list[dict]:
    blocks = re.split(r"\n\s*\d+\.?\s*\*\*Anchor question[:\*]*", md)
    return [{"block": b[:200]} for b in blocks[1:]]


_ATTR = re.compile(r"—\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,]+?)(?:,|\s|$)", re.S)
# legacy v4 format: "Role, Org, July 13: *\"quote\"" — no em-dash, name unverified
_ATTR2 = re.compile(r"^\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}\s*:\s*\*?\s*\"", re.S)


def _map_attributions(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        ans = str(e.get("key_answer") or e.get("answer") or "")
        m = _ATTR.search(ans)
        if m:
            guest, role, org = (m.group(1).strip(), m.group(2).strip(), m.group(3).strip())
        else:
            m2 = _ATTR2.match(ans)
            if m2:
                role, org = m2.group(1).strip(), m2.group(2).strip()
                guest = ""
            else:
                guest, role, org = "", "", ""
        out.append({
            "guest": guest,
            "org": org,
            "role": role,
            "show": (e.get("source_file") or "").replace("_daily_analysis.md", ""),
            "date": e.get("date", ""),
            "tone": e.get("tension") or e.get("tone") or "",
            "questions": [str(e.get("question") or "")],
            "notable_quotes": [ans],
            "confidence": _to_float(e.get("confidence")),
        })
    return out


def _to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return {"high": 1.0, "medium": 0.6, "low": 0.3}.get(str(v).lower(), 0.0)


def import_edition(eid: str) -> str | None:
    root = Path(config.V5["editions_root"]) / eid
    data_path = root / "report_data.json"
    if not data_path.exists():
        return None
    data = json.loads(data_path.read_text(encoding="utf-8"))
    manifest = {}
    mfile = root / "source_manifest.json"
    if mfile.exists():
        manifest = json.loads(mfile.read_text(encoding="utf-8"))
    qc = {}
    qfile = root / "quality_control.json"
    if qfile.exists():
        qc = json.loads(qfile.read_text(encoding="utf-8"))
    db.upsert_edition(data, manifest, qc)
    ilog = root / "interview_log.json"
    if ilog.exists():
        payload = json.loads(ilog.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            entries = payload.get("interview_log") or payload.get("interviews") or []
        else:
            entries = payload
        entries = _map_attributions(entries) if isinstance(entries, list) else []
        db.replace_interview_entries(eid, entries)
    imported = 0
    for ep in manifest.get("episodes", []):
        if import_transcript(ep):
            imported += 1
    print(f"seeded {eid}: episodes={imported} topics={len(data.get('agenda_topics', []))} "
          f"qc={qc.get('status')}")
    return eid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--edition")
    args = ap.parse_args()
    db.init_db()
    root = Path(config.V5["editions_root"])
    if args.edition:
        import_edition(args.edition)
    elif args.all:
        for d in sorted(root.iterdir()):
            if d.name.startswith("20") and (d / "report_data.json").exists():
                import_edition(d.name)
    else:
        import_edition("2026-08-03_to_2026-08-07")


if __name__ == "__main__":
    main()