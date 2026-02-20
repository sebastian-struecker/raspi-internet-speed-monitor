"""Unit tests for the Dashboard Flask API."""
import json
import pytest
from datetime import datetime, timedelta

from app.database import Database
from app.dashboard import create_app
from app.models import SpeedTestResult


@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def client(db):
    """Client for standalone mode (no URL prefix)."""
    app = create_app(db, url_prefix="")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture
def client_with_prefix(db):
    """Client for reverse proxy mode (with URL prefix)."""
    app = create_app(db, url_prefix="/internet-speed-dashboard")
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def insert(db, ts, download=100.0, upload=20.0, ping=10.0, success=True):
    r = SpeedTestResult(
        timestamp=ts,
        download_mbps=download,
        upload_mbps=upload,
        ping_ms=ping,
        success=success,
    )
    db.insert_result(r)
    return r


# ---------------------------------------------------------------------------
# /api/history
# ---------------------------------------------------------------------------

def test_history_requires_start_and_end(client):
    assert client.get("/api/history").status_code == 400
    assert client.get("/api/history?start=2024-01-01T00:00").status_code == 400


def test_history_returns_results_in_range(client, db):
    base = datetime(2024, 6, 1)
    insert(db, base - timedelta(days=1))            # before
    insert(db, base, download=80.0)                  # in range
    insert(db, base + timedelta(hours=12), download=90.0)  # in range
    insert(db, base + timedelta(days=2))            # after

    start = base.isoformat()
    end   = (base + timedelta(days=1)).isoformat()
    resp  = client.get(f"/api/history?start={start}&end={end}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2


def test_history_returns_empty_list_when_no_match(client, db):
    insert(db, datetime(2024, 1, 1))
    start = "2025-01-01T00:00:00"
    end   = "2025-12-31T23:59:59"
    resp  = client.get(f"/api/history?start={start}&end={end}")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_history_rejects_invalid_datetime(client):
    resp = client.get("/api/history?start=notadate&end=alsonotadate")
    assert resp.status_code == 400


def test_history_accepts_utc_z_suffix(client, db):
    """Verify that ISO datetime strings with 'Z' suffix are handled correctly."""
    base = datetime(2024, 6, 1)
    insert(db, base, download=100.0)
    insert(db, base + timedelta(hours=1), download=200.0)

    # Use ISO format with 'Z' suffix (as sent by JavaScript .toISOString())
    start = base.isoformat() + 'Z'
    end = (base + timedelta(hours=2)).isoformat() + 'Z'
    resp = client.get(f"/api/history?start={start}&end={end}")

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 2


# ---------------------------------------------------------------------------
# /api/stats
# ---------------------------------------------------------------------------

def test_stats_returns_null_when_no_results(client):
    start = "2024-01-01T00:00:00"
    end   = "2024-12-31T23:59:59"
    resp  = client.get(f"/api/stats?start={start}&end={end}")
    assert resp.status_code == 200
    assert resp.get_json() is None


def test_stats_returns_correct_averages(client, db):
    base = datetime(2024, 6, 1)
    insert(db, base,                      download=100.0, upload=20.0, ping=10.0)
    insert(db, base + timedelta(hours=1), download=200.0, upload=40.0, ping=20.0)

    start = base.isoformat()
    end   = (base + timedelta(hours=2)).isoformat()
    data  = client.get(f"/api/stats?start={start}&end={end}").get_json()

    assert data["averages"]["download_mbps"] == 150.0
    assert data["averages"]["upload_mbps"] == 30.0
    assert data["averages"]["ping_ms"] == 15.0


def test_stats_contains_all_fields(client, db):
    base = datetime(2024, 6, 1)
    insert(db, base)
    start = base.isoformat()
    end   = (base + timedelta(hours=1)).isoformat()
    data  = client.get(f"/api/stats?start={start}&end={end}").get_json()

    for key in ("averages", "download", "upload", "ping", "tests", "period"):
        assert key in data, f"Missing key: {key}"

    assert "total" in data["tests"]
    assert "failed" in data["tests"]
    assert "success_rate" in data["tests"]


def test_stats_requires_start_and_end(client):
    assert client.get("/api/stats").status_code == 400


# ---------------------------------------------------------------------------
# URL Prefix Support (Reverse Proxy Mode)
# ---------------------------------------------------------------------------

def test_index_with_url_prefix(client_with_prefix):
    """Verify that the index page works with URL prefix."""
    resp = client_with_prefix.get("/internet-speed-dashboard/")
    assert resp.status_code == 200
    # Check that the base tag is rendered with the prefix
    assert b'<base href="/internet-speed-dashboard/"' in resp.data


def test_api_with_url_prefix(client_with_prefix, db):
    """Verify that API endpoints work with URL prefix."""
    base = datetime(2024, 6, 1)
    insert(db, base)

    start = base.isoformat()
    end = (base + timedelta(hours=1)).isoformat()

    # API endpoints should be accessible under the prefix
    resp = client_with_prefix.get(f"/internet-speed-dashboard/api/history?start={start}&end={end}")
    assert resp.status_code == 200

    resp = client_with_prefix.get(f"/internet-speed-dashboard/api/stats?start={start}&end={end}")
    assert resp.status_code == 200


def test_index_without_prefix_in_standalone_mode(client):
    """Verify that index page works without prefix in standalone mode."""
    resp = client.get("/")
    assert resp.status_code == 200
    # Should NOT have a base tag in standalone mode
    assert b'<base href=' not in resp.data
