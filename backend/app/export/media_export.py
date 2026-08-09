"""CSV + PDF exports. PDF uses headless chromium print-to-pdf of the print layout."""
import csv
import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

CHROME = (shutil.which("google-chrome") or shutil.which("google-chrome-stable")
          or "/snap/bin/chromium")


def agenda_csv(edition: dict) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["rank", "title_en", "title_zh", "summary_en", "summary_zh", "direction", "score"])
    for t in edition["data"].get("agenda_topics", []):
        w.writerow([t.get("rank"), t.get("title_en"), t.get("title_zh"), t.get("summary_en"),
                    t.get("summary_zh"), t.get("direction"), t.get("score")])
    return out.getvalue()


def interviews_csv(edition_id: str) -> str:
    from .. import db
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["date", "show", "guest", "org", "role", "tone", "question", "answer"])
    for e in db.interview_entries(edition_id):
        qs = e.get("questions") or [""]
        answers = e.get("notable_quotes") or [""]
        for i in range(max(len(qs), len(answers))):
            w.writerow([e.get("date"), e.get("show"), e.get("guest"), e.get("org"),
                        e.get("role"), e.get("tone"),
                        (qs[i] if i < len(qs) else "")[:400],
                        (answers[i] if i < len(answers) else "")[:400]])
    return out.getvalue()


def print_html(edition: dict) -> str:
    """Full A4 print layout: cover + EN + ZH + appendix."""
    from .email import render_email
    body = render_email(edition)
    appendix = (
        '<div style="page-break-before:always"></div>'
        '<h2>Appendix — source inventory</h2><ul>'
        + "".join(f"<li>{e.get('date')} · {e.get('program')} · {e.get('file')}</li>"
                  for e in (edition["manifest"] or {}).get("episodes", [])[:40])
        + "</ul>"
        + '<h2>Methodology</h2><p>Bilingual report synthesised from the week\'s TV transcripts '
        'and daily episode analyses; agenda topics are selected dynamically by editorial LLM; '
        'interview log derives from anchor-guest exchanges.</p>'
        '<h2>QC</h2><pre>' + json.dumps(edition.get("qc") or {}, ensure_ascii=False, indent=1)[:2000] + "</pre>"
    )
    return body + appendix


def pdf_from_html(html_str: str, out_path: Path) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html_str)
        tmp = f.name
    try:
        base = [CHROME, "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                "--virtual-time-budget=10000", "--run-all-compositor-stages-before-draw"]
        url = f"file://{tmp}"
        for headless in ("--headless=new", "--headless"):
            r = subprocess.run(
                base + [headless, f"--print-to-pdf={out_path}", url],
                capture_output=True, text=True, timeout=120, check=False)
            if out_path.exists() and out_path.stat().st_size > 1000:
                return True
        return False
    finally:
        Path(tmp).unlink(missing_ok=True)