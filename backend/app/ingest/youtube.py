"""YouTube playlist ingestion: discover episodes (flat-playlist), fetch captions,
convert VTT -> plain text and store transcript chunks. Used by any yt_playlist
source (Bloomberg legacy + CNBC Asia).
"""
import datetime
import os
import re
import subprocess
from pathlib import Path

from .. import config
from .. import db

YT = os.path.expanduser("~/workspace/yt-tools/.venv/bin")

_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")


def _env():
    env = os.environ.copy()
    env["PATH"] = YT + ":" + env.get("PATH", "")
    return env


def _pubdate(title: str, upload_date: str) -> str | None:
    m = _DATE_RE.search(title)
    if m:
        a, b, y = m.group(1), m.group(2), m.group(3)
        for fmt in ("%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(f"{a}/{b}/{y}", fmt).date().isoformat()
            except ValueError:
                continue
    try:
        return datetime.datetime.strptime(str(upload_date), "%Y%m%d").date().isoformat()
    except (TypeError, ValueError):
        return None


def _playlist_rows(source: dict, limit: int = 30) -> list[dict]:
    url = source.get("playlist_url") or source.get("feed_url")
    if not url:
        return []
    cmd = ["yt-dlp", "--flat-playlist", "--playlist-end", str(limit),
           "--print", "%(id)s|%(upload_date)s|%(title)s", url]
    out = subprocess.check_output(cmd, env=_env(), text=True, stderr=subprocess.STDOUT)
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        rows.append({"id": parts[0].strip(), "upload_date": parts[1].strip(),
                     "title": "|".join(parts[2:]).strip()})
    return rows


def _vtt_to_text(text: str) -> str:
    out, prev = [], ""
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("WEBVTT") or s.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*-->", s):
            continue
        if s.isdigit():
            continue
        s = s.replace("<c>", "").replace("</c>", "")
        if s == prev:
            continue
        out.append(s)
        prev = s
    return " ".join(out)


def fetch_transcript(source: dict, vid: str, out_dir: Path) -> str | None:
    """Download captions as VTT, return plain text or None."""
    out_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://www.youtube.com/watch?v={vid}"
    subprocess.run(
        ["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs",
         "--sub-langs", "en.*", "--convert-subs", "vtt", "--sub-format", "vtt",
         "-o", f"{out_dir}/%(id)s.%(ext)s", url],
        env=_env(), capture_output=True, text=True, timeout=600)
    vtts = sorted(out_dir.glob(f"{vid}.*.vtt")) + sorted(out_dir.glob(f"{vid}.vtt"))
    for v in vtts:
        try:
            text = _vtt_to_text(v.read_text(encoding="utf-8", errors="replace"))
            if len(text.split()) > 100:
                Path(out_dir / f"{vid}.txt").write_text(text, encoding="utf-8")
                return text
        except OSError:
            continue
    return None


def _episode_exists(ep_id: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM episodes WHERE id=?", (ep_id,)).fetchone() is not None


def chunks_of(text: str, size: int = 900) -> list[str]:
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def sync_playlist(source: dict) -> dict:
    try:
        rows = _playlist_rows(source)
    except subprocess.CalledProcessError as e:
        db.log_source_run(source["id"], "yt_playlist", False, 0, str(e)[:200])
        return {"source": source["id"], "ok": False, "found": 0, "error": str(e)[:200]}
    lookback = datetime.timedelta(days=int(config.FETCH.get("lookback_days", 7)))
    cutoff = datetime.date.today() - lookback
    pattern = re.compile(source["title_regex"], re.IGNORECASE)
    matched, fail = 0, 0
    for r in rows:
        if not pattern.search(r["title"]):
            continue
        pub = _pubdate(r["title"], r["upload_date"])
        if not pub or datetime.date.fromisoformat(pub) < cutoff:
            continue
        ep_id = r["id"]
        if _episode_exists(ep_id):
            continue
        text = fetch_transcript(source, ep_id, config.TRANSCRIPT_DIR)
        if not text:
            fail += 1
            continue
        db.upsert_episode({
            "id": ep_id, "source_id": source["id"], "external_id": ep_id,
            "title": r["title"], "show_name": source["name"], "pub_date": pub,
            "url": f"https://www.youtube.com/watch?v={ep_id}", "kind": "yt",
            "words": len(text.split()),
            "transcript_path": str(config.TRANSCRIPT_DIR / f"{ep_id}.txt"),
        })
        db.replace_chunks(ep_id, chunks_of(text))
        matched += 1
    db.log_source_run(source["id"], "yt_playlist", fail == 0, matched,
                      f"{matched} new episodes, {fail} no-caption")
    return {"source": source["id"], "ok": fail == 0, "added": matched, "failed": fail}