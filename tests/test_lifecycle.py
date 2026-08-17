"""Lifecycle chaining rules: threshold + intersection floor, single-point phase."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from backend.app.framing import engine  # noqa: E402


def _row(title, edition, direction="rising", rank=1, score=80):
    return {"title_en": title, "title_zh": "", "edition_id": edition,
            "end_date": edition.split("_to_")[1], "rank": rank,
            "direction": direction, "score": score}


def test_single_point_fading_is_not_new():
    pts = [{"direction": "fading"}]
    assert engine._phase(pts) == "fading"
    assert engine._phase([{"direction": "rising"}]) == "new"
    assert engine._phase([{"direction": ""}]) == "new"


def test_tracks_chain_on_strong_overlap():
    rows = [
        _row("Hormuz shipping risk lifts oil prices", "2026-08-03_to_2026-08-07"),
        _row("Hormuz shipping risk lifts oil further", "2026-08-10_to_2026-08-14"),
    ]
    tracks = engine._tracks(rows)
    assert len(tracks) == 1 and tracks[0]["week_count"] == 2


def test_tracks_reject_two_keyword_accidents():
    """Only 2 shared keywords on short titles must NOT chain (the live bug:
    the Hormuz story split into two tracks / unrelated stories merged)."""
    rows = [
        _row("Korea chip rally leverage", "2026-08-03_to_2026-08-07"),
        _row("Korea retail leverage fears", "2026-08-10_to_2026-08-14"),
    ]
    tracks = engine._tracks(rows)
    # 'korea', 'leverage' shared = 2 words, overlap high but intersection < 3
    assert len(tracks) == 2
