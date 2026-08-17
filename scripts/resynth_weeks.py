#!/usr/bin/env python3
"""Re-synthesize all stored editions under the schema-v2 weekly brief,
then run the v2 QC gate on each. Requires DEEPSEEK_API_KEY.

Usage: .venv/bin/python scripts/resynth_weeks.py [--edition <id>]
"""
import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backend.app import config  # noqa: E402
from backend.app import db  # noqa: E402
from backend.app.synth import qc  # noqa: E402
from backend.app.synth import weekly as synth  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", help="resynthesize only this edition id")
    args = ap.parse_args()

    db.init_db()
    with db.conn() as c:
        rows = c.execute("SELECT id, start_date, end_date FROM editions ORDER BY end_date").fetchall()
    if args.edition:
        rows = [r for r in rows if r["id"] == args.edition]
        if not rows:
            print(f"edition {args.edition} not found"); sys.exit(1)

    for r in rows:
        print(f"== resynth {r['id']} ({r['start_date']}..{r['end_date']})")
        try:
            out = synth.synthesize_week(r["start_date"], r["end_date"], force=True)
            res = qc.run_qc(r["id"])
            print(f"   -> {out.get('message', 'ok')} | QC {res['status']} "
                  f"(blocks={res['blocks']})")
        except Exception as e:  # noqa: BLE001
            print(f"   FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()