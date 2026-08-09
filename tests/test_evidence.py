"""Coverage digest tests against the seeded week (read-only)."""
from backend.app.analyze.evidence import agenda_evidence


def test_agenda_evidence_coverage_seeded():
    ev = agenda_evidence("2026-08-03", "2026-08-07")
    assert ev["source_files"] > 0
    assert ev["days"] == sorted(ev["days"])
    assert set(ev["coverage"]) == set(ev["topic_counts"])
    assert set(ev["first_seen"]) == set(ev["topic_counts"])
    assert set(ev["last_seen"]) == set(ev["topic_counts"])
    for t, n in ev["topic_counts"].items():
        assert ev["coverage"][t] >= 1
        assert n >= ev["coverage"][t]
        assert ev["first_seen"][t] <= ev["last_seen"][t]
    assert len(ev["topic_counts"]) >= 5