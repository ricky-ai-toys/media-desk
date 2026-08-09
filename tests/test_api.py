"""Read-only QA suite against the seeded database (see README for seeding)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("MEDIA_DESK_ADMIN_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402
from backend.app import db as dbmod  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_meta_latest_edition(client):
    r = client.get("/api/meta")
    assert r.status_code == 200
    d = r.json()
    assert d["latest"] and d["editions"], "seed data missing (run seed.py)"
    assert d["latest"] in {e["id"] for e in d["editions"]}


def test_desk_shape(client):
    r = client.get("/api/desk")
    assert r.status_code == 200
    d = r.json()
    assert d["edition"].startswith(d["start"])
    assert isinstance(d["agenda"], list) and len(d["agenda"]) >= 4
    assert len(d["narratives"]) >= 3
    assert isinstance(d["interviews"], list)
    assert "framing" in d and {"collisions", "lead_lag", "asymmetry"} <= set(d["framing"])


def test_desk_agenda_fields(client):
    r = client.get("/api/desk")
    a = r.json()["agenda"][0]
    for key in ("rank", "score", "title_en", "title_zh", "direction"):
        assert key in a, f"missing agenda field {key}"


def test_desk_scores_normalized_10(client):
    r = client.get("/api/desk")
    for a in r.json()["agenda"]:
        assert 0 <= a["score"] <= 10, f"score {a['score']} not on /10 scale"


def test_desk_attribution(client):
    r = client.get("/api/desk")
    attr = r.json().get("attribution") or []
    assert len(attr) == len(r.json()["agenda"])
    for t in attr:
        assert "rank" in t and "shows" in t
        assert t["total_episodes"] > 0
    top = max(attr, key=lambda t: t["covered"])
    assert top["shows"], "expected at least one show carrying a topic"


def test_desk_guests_sanitized(client):
    r = client.get("/api/desk")
    for i in r.json()["interviews"]:
        g = i.get("guest") or ""
        assert "[unverified" not in g and "⚠️" not in g and "[" not in g, g
        org = i.get("org")
        if org:
            assert not org.startswith("[") and "unverified" not in org.lower()


def test_lifecycle_tracks(client):
    r = client.get("/api/lifecycle")
    assert r.status_code == 200
    tracks = r.json().get("tracks") or []
    for t in tracks:
        assert t["label"] and t["first_seen"] and t["points"]


def test_interviews_filter(client):
    r = client.get("/api/interviews?limit=10")
    assert r.status_code == 200
    assert len(r.json()) <= 10
    r2 = client.get("/api/interviews?q=yen")
    assert r2.status_code == 200


def test_framing_view(client):
    latest = client.get("/api/meta").json()["latest"]
    r = client.get(f"/api/framing?edition={latest}")
    assert r.status_code == 200
    f = r.json()
    assert {"collisions", "lead_lag", "asymmetry"} <= set(f)


def test_radar(client):
    r = client.get("/api/radar")
    assert r.status_code == 200
    d = r.json()
    assert d["sources"] and d["wire_totals"]
    assert len(d["wire_feed"]) > 0


def test_search_fts(client):
    r = client.get("/api/search?q=yen")
    assert r.status_code == 200
    d = r.json()
    assert len(d["results"]) > 0
    assert any(x["kind"] == "transcript" for x in d["results"])


def test_search_requires_query(client):
    assert client.get("/api/search").status_code == 422


def test_edition_detail(client):
    latest = client.get("/api/meta").json()["latest"]
    r = client.get(f"/api/edition/{latest}")
    assert r.status_code == 200
    ed = r.json()
    assert ed["id"] == latest and ed["data"]


def test_edition_404(client):
    assert client.get("/api/edition/nope").status_code == 404


def test_export_csv(client):
    latest = client.get("/api/meta").json()["latest"]
    r = client.get(f"/export/{latest}/csv")
    assert r.status_code == 200
    assert "rank" in r.text.lower() or "," in r.text


def test_export_email(client):
    latest = client.get("/api/meta").json()["latest"]
    r = client.get(f"/export/{latest}/email")
    assert r.status_code == 200
    assert "html" in r.headers["content-type"]
    assert "MEDIA" in r.text.upper() or "media" in r.text


def test_admin_guard(client):
    r = client.post("/api/admin/qc/whatever", headers={"X-Admin-Token": "bad"})
    assert r.status_code in (401, 403)


def test_admin_qc(client):
    latest = client.get("/api/meta").json()["latest"]
    r = client.post(f"/api/admin/qc/{latest}", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 200
    assert r.json()["status"] == "PASS"


def test_db_counts():
    with dbmod.conn() as c:
        eps = c.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        arts = c.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    assert eps >= 40
    assert arts >= 50


def test_edition_weekday_span():
    latest = dbmod.latest_edition()
    assert latest["start_date"] < latest["end_date"]
