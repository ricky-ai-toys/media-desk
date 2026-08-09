"""Wire-feed (RSS) ingestion: Reuters / FT / Bloomberg headlines with summaries.

Stores articles (headline coverage only — framing and lead-lag, never quotes).
"""
import datetime

import feedparser

from .. import db


def _pub_iso(entry: dict) -> str:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if not parsed:
            continue
        try:
            return datetime.datetime(*parsed[:6], tzinfo=datetime.timezone.utc).isoformat()
        except (TypeError, ValueError):
            continue
    return ""


def fetch_feed(source: dict) -> dict:
    feed = feedparser.parse(source["feed_url"])
    if feed.get("bozo"):
        db.log_source_run(source["id"], "rss", False, 0,
                          f"feed parse error: {feed.get('bozo_exception', '')}")
        return {"source": source["id"], "ok": False, "found": 0,
                "error": str(feed.get("bozo_exception"))[:200]}
    added = 0
    for e in feed.entries:
        if db.upsert_article({
            "source_id": source["id"], "title": e.get("title", ""),
            "link": e.get("link", ""), "summary": e.get("summary", "")[:600],
            "pub_date": _pub_iso(e), "author": e.get("author", ""),
        }):
            added += 1
    db.log_source_run(source["id"], "rss", True, added, f"{added} new items")
    return {"source": source["id"], "ok": True, "added": added}


def sync_all() -> list[dict]:
    from .. import config
    return [fetch_feed(s) for s in config.sources_by_kind("rss")]