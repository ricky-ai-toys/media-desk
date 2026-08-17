"""Shared pytest setup.

Points the app at a repo-local fixture DB (built on first run by
scripts/make_fixture_db.py) so the suite runs without production data.
Tests that need an empty DB monkeypatch config.DB_PATH themselves.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

_FIXTURE_DB = ROOT / "data" / "media.db"
os.environ.setdefault("MEDIA_DESK_ADMIN_TOKEN", "test-token")
os.environ.setdefault("MEDIA_DESK_DB", str(_FIXTURE_DB))
os.environ.setdefault("MEDIA_DESK_TRANSCRIPTS", str(ROOT / "data" / "transcripts"))

if not _FIXTURE_DB.exists():
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_fixture_db.py"),
                    str(_FIXTURE_DB)], check=True)
