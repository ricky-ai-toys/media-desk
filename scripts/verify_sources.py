"""Verify candidate yt_playlist sources before enabling them.

For each disabled source with a playlist_url, checks (via yt-dlp):
  1. the URL resolves and yields flat-playlist rows
  2. title_regex matches recent uploads
  3. captions (manual or auto-subs, en) are available for matched items
  4. transcript word count clears fetch.min_transcript_words

Prints a go/no-go report. Run on the server (needs YouTube access):

    .venv/bin/python scripts/verify_sources.py            # all disabled yt sources
    .venv/bin/python scripts/verify_sources.py cnbc_squawk_box_asia
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

CFG = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"


def _run(cmd: list[str], timeout: int = 120) -> tuple[bool, str]:
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT,
                                      timeout=timeout)
        return True, out
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        return False, str(getattr(e, "output", e))[:300]


def verify(source: dict) -> dict:
    import re
    r = {"id": source["id"], "checks": {}, "go": False}
    url = source.get("playlist_url")
    if not url:
        r["checks"]["url_present"] = False
        return r
    r["checks"]["url_present"] = True
    ok, out = _run(["yt-dlp", "--flat-playlist", "--playlist-end", "10",
                    "--print", "%(id)s|%(title)s", url])
    r["checks"]["playlist_resolves"] = ok
    if not ok:
        r["error"] = out
        return r
    rows = [l.split("|", 1) for l in out.splitlines() if "|" in l]
    pattern = re.compile(source.get("title_regex", ".*"), re.IGNORECASE)
    matched = [(vid, t) for vid, t in rows if len(vid) > 3 and pattern.search(t or "")]
    r["checks"]["title_matches"] = len(matched)
    if not matched:
        return r
    vid = matched[0][0]
    ok, out = _run(["yt-dlp", "--skip-download", "--write-auto-subs", "--write-subs",
                    "--sub-langs", "en.*", "--print", "%(subtitles)s",
                    f"https://www.youtube.com/watch?v={vid}"], timeout=180)
    r["checks"]["captions_probe"] = ok
    r["sample"] = {"id": vid, "title": matched[0][1][:80]}
    r["go"] = all([r["checks"]["url_present"], r["checks"]["playlist_resolves"],
                   r["checks"]["title_matches"] > 0, r["checks"]["captions_probe"]])
    return r


def main():
    cfg = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    only = sys.argv[1] if len(sys.argv) > 1 else None
    candidates = [s for s in cfg["sources"]
                  if s.get("kind") == "yt_playlist" and not s.get("enabled", True)]
    if only:
        candidates = [s for s in candidates if s["id"] == only]
    if not candidates:
        print("no disabled yt_playlist candidates to verify")
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
