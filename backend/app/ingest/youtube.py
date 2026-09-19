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
# "Squawk Box Asia - 17-Sep-26" — CNBC 'Watch In Full' naming.
_MDY_SHORT_RE = re.compile(r"(?<![\d-])(\d{1,2})-([A-Za-z]{3})-(\d{2})\b")


def _env():
    env = os.environ.copy()
    env["PATH"] = YT + ":" + env.get("PATH", "")
    return env


def _proxy_args(source: dict) -> list[str]:
    proxy = source.get("proxy_url") or config.FETCH.get("proxy_url")
    return ["--proxy", proxy] if proxy else []


def _pubdate(title: str, upload_date: str) -> str | None:
    m = _DATE_RE.search(title)
    if m:
        a, b, y = m.group(1), m.group(2), m.group(3)
        for fmt in ("%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.datetime.strptime(f"{a}/{b}/{y}", fmt).date().isoformat()
            except ValueError:
                continue
    m = _MDY_SHORT_RE.search(title)
    if m:
        try:
            return datetime.datetime.strptime(
                f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "%d-%b-%y").date().isoformat()
        except ValueError:
            pass
    try:
        return datetime.datetime.strptime(str(upload_date), "%Y%m%d").date().isoformat()
    except (TypeError, ValueError):
        return None


def _playlist_rows(source: dict, limit: int = 30) -> list[dict]:
    url = source.get("playlist_url") or source.get("feed_url")
    if not url:
        return []
    cmd = ["yt-dlp", "--flat-playlist", "--playlist-end", str(limit),
           *_proxy_args(source),
           "--print", "%(id)s|%(upload_date)s|%(title)s", url]
    out = subprocess.check_output(cmd, env=_env(), text=True,
                                  stderr=subprocess.STDOUT, timeout=120)
    rows = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) < 3:
            continue
        rows.append({"id": parts[0].strip(), "upload_date": parts[1].strip(),
                     "title": "|".join(parts[2:]).strip()})
    return rows


def _probe_dates(ids: list[str], source: dict) -> dict[str, str]:
    """Resolve upload dates for clips whose titles carry none (flat-playlist
    upload_date is NA). Chunked yt-dlp calls; tolerates partial failure."""
    dates: dict[str, str] = {}
    for chunk in (ids[i:i + 12] for i in range(0, len(ids), 12)):
        urls = [f"https://www.youtube.com/watch?v={i}" for i in chunk]
        cmd = ["yt-dlp", "--no-warnings", "--skip-download",
               *_proxy_args(source),
               "--print", "%(id)s|%(upload_date)s"] + urls
        try:
            out = subprocess.run(cmd, env=_env(), capture_output=True, text=True,
                                 timeout=min(300, 30 + 8 * len(chunk))).stdout
        except (subprocess.TimeoutExpired, OSError):
            continue
        for line in out.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 2 and re.fullmatch(r"\d{8}", parts[1]):
                dates[parts[0]] = datetime.datetime.strptime(
                    parts[1], "%Y%m%d").date().isoformat()
    return dates


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
    # Per-source override: clip-mode sources clear a lower bar than full shows.
    min_words = int(source.get("min_transcript_words")
                    or config.FETCH.get("min_transcript_words", 500))
    url = f"https://www.youtube.com/watch?v={vid}"
    subprocess.run(
        ["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs",
         "--sub-langs", "en.*", "--convert-subs", "vtt", "--sub-format", "vtt",
         *_proxy_args(source),
         "-o", f"{out_dir}/%(id)s.%(ext)s", url],
        env=_env(), capture_output=True, text=True, timeout=600)
    vtts = sorted(out_dir.glob(f"{vid}.*.vtt")) + sorted(out_dir.glob(f"{vid}.vtt"))
    for v in vtts:
        try:
            text = _vtt_to_text(v.read_text(encoding="utf-8", errors="replace"))
            if len(text.split()) > min_words:
                Path(out_dir / f"{vid}.txt").write_text(text, encoding="utf-8")
                return text
        except OSError:
            continue
    return None


def _episode_exists(ep_id: str) -> bool:
    with db.conn() as c:
        return c.execute("SELECT 1 FROM episodes WHERE id=?", (ep_id,)).fetchone() is not None


def chunks_of(text: str, size: int | None = None) -> list[str]:
    size = size or int(config.ANALYSIS.get("chunk_words", 900))
    words = text.split()
    return [" ".join(words[i:i + size]) for i in range(0, len(words), size)]


def sync_playlist(source: dict) -> dict:
    try:
        rows = _playlist_rows(source, int(source.get("scan_limit", 30)))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        db.log_source_run(source["id"], "yt_playlist", False, 0, str(e)[:200])
        return {"source": source["id"], "ok": False, "found": 0, "error": str(e)[:200]}
    lookback = datetime.timedelta(days=int(config.FETCH.get("lookback_days", 7)))
    cutoff = datetime.date.today() - lookback
    pattern = re.compile(source["title_regex"], re.IGNORECASE)
    # Pass 1: keep regex hits that are new to the DB. Rows without a title
    # date (flat-playlist upload_date can come back 'NA') queue for one
    # batched date probe.
    cap = int(config.FETCH.get("max_date_probes", 15))
    ready, pending = [], []
    for r in rows:
        if not pattern.search(r["title"]) or _episode_exists(r["id"]):
            continue
        pub = _pubdate(r["title"], r["upload_date"])
        (ready if pub else pending).append((r, pub))
    # Probe the oldest pending clips first (playlist order is newest-first):
    # a capped probe that always takes the newest entries would leave the
    # older tail permanently unprobed while it ages out of the scan window.
    to_probe, deferred = pending[-cap:], max(0, len(pending) - cap)
    probed = _probe_dates([r["id"] for r, _ in to_probe], source) if to_probe else {}
    undated = 0
    for r, _ in pending:
        if probed.get(r["id"]):
            ready.append((r, probed[r["id"]]))
        else:
            undated += 1
    matched, fail = 0, 0
    for r, pub in ready:
        if datetime.date.fromisoformat(pub) < cutoff:
            continue
        ep_id = r["id"]
        text = fetch_transcript(source, ep_id, config.TRANSCRIPT_DIR)
        if not text:
            fail += 1
            continue
        # Clip-mode sources contribute selected segments, not full programmes —
        # qualify the outlet label so every downstream sample-frame disclosure
        # (prompt context, PDF methodology, email) states this honestly.
        label = source["name"]
        if source.get("content") == "clips":
            label += " (segment clips)"
        db.upsert_episode({
            "id": ep_id, "source_id": source["id"], "external_id": ep_id,
            "title": r["title"], "show_name": label, "pub_date": pub,
            "url": f"https://www.youtube.com/watch?v={ep_id}", "kind": "yt",
            "words": len(text.split()),
            "transcript_path": str(config.TRANSCRIPT_DIR / f"{ep_id}.txt"),
        })
        db.replace_chunks(ep_id, chunks_of(text))
        matched += 1
    detail = f"{matched} new episodes, {fail} no-caption"
    no_date = undated - deferred
    if no_date:
        detail += f", {no_date} undated"
    if deferred:
        detail += f", {deferred} probe-deferred"
    ok = fail == 0 or matched > 0
    db.log_source_run(source["id"], "yt_playlist", ok, matched, detail)
    return {"source": source["id"], "ok": ok, "added": matched,
            "failed": fail, "undated": no_date, "deferred": deferred}
