import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.environ.get("MEDIA_DESK_CONFIG", ROOT / "config" / "sources.yaml"))

with open(CONFIG_PATH, encoding="utf-8") as f:
    _cfg = yaml.safe_load(f)

DB_PATH = Path(os.environ.get("MEDIA_DESK_DB", _cfg["db"]["path"]))
TRANSCRIPT_DIR = Path(os.environ.get("MEDIA_DESK_TRANSCRIPTS", _cfg["fetch"]["transcript_dir"]))
FETCH = _cfg["fetch"]
V5 = _cfg["v5"]
ANALYSIS = _cfg["analysis"]
WEB = _cfg["web"]

SOURCES = {s["id"]: s for s in _cfg["sources"] if s.get("enabled", True)}


def sources_by_kind(kind: str):
    return [s for s in SOURCES.values() if s["kind"] == kind]


def source_by_id(sid: str):
    return SOURCES.get(sid)


def admin_token() -> str | None:
    return os.environ.get(WEB["admin_token_env"]) or None
