"""Verify candidate yt_playlist sources before enabling them.

For each disabled source with a playlist_url, checks (via yt-dlp):
  1. the URL resolves and yields flat-playlist rows
  2. title_regex matches recent uploads
  3. a publish date is obtainable — from the title, from flat-playlist
     upload_date, or from the batched date probe (flat upload_date can
     regress to 'NA', which silently starves clip-mode sources)
  4. captions (manual or auto-subs, en) are downloadable for a matched item

Prints a go/no-go report. Run on the server (needs YouTube access):

    .venv/bin/python scripts/verify_sources.py            # all disabled yt sources
    .venv/bin/python scripts/verify_sources.py cnbc_squawk_box_us
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import yaml  # noqa: E402

from app.ingest import youtube as yt  # noqa: E402

CFG = ROOT / "config" / "sources.yaml"


def verify(source: dict) -> dict:
    r = {"id": source["id"], "checks": {}, "go": False}
    url = source.get("playlist_url")
    if not url:
        r["checks"]["url_present"] = False
        return r
    r["checks"]["url_present"] = True
    try:
        rows = yt._playlist_rows(source, limit=10)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        r["checks"]["playlist_resolves"] = False
        r["error"] = str(e)[:300]
        return r
    r["checks"]["playlist_resolves"] = True
    pattern = re.compile(source.get("title_regex", ".*"), re.IGNORECASE)
    matched = [row for row in rows if pattern.search(row["title"])]
    r["checks"]["title_matches"] = len(matched)
    if not matched:
        return r
    # Date availability: title regex/inline date, flat upload_date, or probe.
    dated = [row for row in matched if yt._pubdate(row["title"], row["upload_date"])]
    if len(dated) == len(matched):
        r["checks"]["date_source"] = "title" if any(
            yt._pubdate(row["title"], "NA") for row in dated) else "upload_date"
    else:
        undated = [row["id"] for row in matched if row["id"] not in
                   {d["id"] for d in dated}]
        probed = yt._probe_dates(undated[:3], source)
        r["checks"]["date_source"] = "probe" if probed else "NONE"
    if r["checks"]["date_source"] == "NONE":
        r["error"] = ("no date obtainable (title, upload_date and probe all "
                      "failed) — enabling this source would ingest nothing")
        return r
    vid = matched[0]["id"]
    with tempfile.TemporaryDirectory() as td:
        text = yt.fetch_transcript(source, vid, Path(td))
    r["checks"]["captions_probe"] = bool(text)
    if text:
        r["checks"]["transcript_words"] = len(text.split())
    r["sample"] = {"id": vid, "title": matched[0]["title"][:80]}
    r["go"] = (r["checks"]["captions_probe"]
               and r["checks"]["transcript_words"] >= int(
                   source.get("min_transcript_words")
                   or yt.config.FETCH.get("min_transcript_words", 500)))
    return r


def main():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    yt_sources = [s for s in cfg["sources"] if s.get("kind") == "yt_playlist"]
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        # Explicit id: verify it regardless of enabled state — re-checking a
        # live source after an outage or playlist change is the main use.
        candidates = [s for s in yt_sources if s["id"] == only]
        if not candidates:
            print(f"no yt_playlist source with id '{only}' in {CFG}")
            return
    else:
        candidates = [s for s in yt_sources if not s.get("enabled", True)]
        if not candidates:
            print("no disabled yt_playlist candidates to verify "
                  "(pass an explicit id to re-check a live source)")
            return
    for s in candidates:
        r = verify(s)
        verdict = "GO  -> safe to set enabled: true" if r["go"] else "NO-GO"
        print(f"\n== {r['id']}: {verdict}")
        for k, v in r["checks"].items():
            print(f"   {k}: {v}")
        if r.get("sample"):
            print(f"   sample: {r['sample']['title']} ({r['sample']['id']})")
        if r.get("error"):
            print(f"   error: {r['error']}")


if __name__ == "__main__":
    main()
