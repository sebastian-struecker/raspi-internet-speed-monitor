"""Unit tests for the Database component."""
import pytest
from datetime import datetime, timedelta, timezone

from app.database import Database
from app.models import SpeedTestResult


@pytest.fixture
def db():
    """In-memory SQLite database, fresh per test."""
    return Database(":memory:")


def make_result(
    timestamp: datetime,
    download: float = 100.0,
    upload: float = 20.0,
    ping: float = 10.0,
    server: str = "test.server",
) -> SpeedTestResult:
    return SpeedTestResult(
        timestamp=timestamp,
        download_mbps=download,
        upload_mbps=upload,
        ping_ms=ping,
        test_server=server,
    )


# ---------------------------------------------------------------------------
# insert_result
# ---------------------------------------------------------------------------

def test_insert_returns_row_id(db):
    result = make_result(datetime(2024, 1, 1, 12, 0))
    row_id = db.insert_result(result)
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_insert_increments_count(db):
    assert db.count() == 0
    db.insert_result(make_result(datetime(2024, 1, 1)))
    assert db.count() == 1
    db.insert_result(make_result(datetime(2024, 1, 2)))
    assert db.count() == 2


# ---------------------------------------------------------------------------
# get_latest
# ---------------------------------------------------------------------------

def test_get_latest_empty_database(db):
    assert db.get_latest() == []


def test_get_latest_returns_most_recent(db):
    older = make_result(datetime(2024, 1, 1))
    newer = make_result(datetime(2024, 1, 2), download=200.0)
    db.insert_result(older)
    db.insert_result(newer)
    results = db.get_latest(1)
    assert len(results) == 1
    assert results[0].download_mbps == 200.0


def test_get_latest_respects_limit(db):
    for i in range(5):
        db.insert_result(make_result(datetime(2024, 1, i + 1)))
    assert len(db.get_latest(3)) == 3
    assert len(db.get_latest(10)) == 5  # fewer rows than limit


# ---------------------------------------------------------------------------
# query_range
# ---------------------------------------------------------------------------

def test_query_range_empty_database(db):
    results = db.query_range(datetime(2024, 1, 1), datetime(2024, 12, 31))
    assert results == []


def test_query_range_returns_only_matching_rows(db):
    base = datetime(2024, 6, 1)
    db.insert_result(make_result(base - timedelta(days=1)))   # before range
    db.insert_result(make_result(base))                         # inclusive start
    db.insert_result(make_result(base + timedelta(hours=12)))  # inside
    db.insert_result(make_result(base + timedelta(days=1)))     # inclusive end
    db.insert_result(make_result(base + timedelta(days=2)))     # after range

    results = db.query_range(base, base + timedelta(days=1))
    assert len(results) == 3


def test_query_range_inclusive_boundaries(db):
    ts = datetime(2024, 6, 15, 0, 0, 0)
    db.insert_result(make_result(ts))
    results = db.query_range(ts, ts)
    assert len(results) == 1


def test_query_range_results_ordered_by_timestamp(db):
    base = datetime(2024, 1, 1)
    for hours in [5, 1, 3, 2, 4]:
        db.insert_result(make_result(base + timedelta(hours=hours)))
    results = db.query_range(base, base + timedelta(days=1))
    timestamps = [r.timestamp for r in results]
    assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# cleanup_old_data
# ---------------------------------------------------------------------------

def test_cleanup_zero_retention_keeps_all_data(db):
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=365)
    db.insert_result(make_result(old))
    deleted = db.cleanup_old_data(retention_days=0)
    assert deleted == 0
    assert db.count() == 1


def test_cleanup_deletes_old_rows(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.insert_result(make_result(now - timedelta(days=100)))  # old
    db.insert_result(make_result(now - timedelta(days=10)))   # recent
    db.insert_result(make_result(now))                         # now

    deleted = db.cleanup_old_data(retention_days=30)
    assert deleted == 1
    assert db.count() == 2


def test_cleanup_keeps_recent_data(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.insert_result(make_result(now - timedelta(days=5)))
    deleted = db.cleanup_old_data(retention_days=30)
    assert deleted == 0
    assert db.count() == 1


def test_cleanup_returns_deleted_count(db):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(3):
        db.insert_result(make_result(now - timedelta(days=100 + i)))
    deleted = db.cleanup_old_data(retention_days=30)
    assert deleted == 3


# ---------------------------------------------------------------------------
# Round-trip field preservation
# ---------------------------------------------------------------------------

def test_roundtrip_preserves_all_fields(db):
    original = SpeedTestResult(
        timestamp=datetime(2024, 6, 15, 10, 30, 45),
        download_mbps=95.123,
        upload_mbps=12.456,
        ping_ms=14.789,
        test_server="speedtest.example.com",
    )
    db.insert_result(original)
    retrieved = db.get_latest(1)[0]

    assert retrieved.timestamp == original.timestamp
    assert abs(retrieved.download_mbps - original.download_mbps) < 1e-6
    assert abs(retrieved.upload_mbps - original.upload_mbps) < 1e-6
    assert abs(retrieved.ping_ms - original.ping_ms) < 1e-6
    assert retrieved.test_server == original.test_server


# ---------------------------------------------------------------------------
# Persistence across reconnect
# ---------------------------------------------------------------------------

def test_persistence_survives_reconnect(tmp_path):
    db_file = str(tmp_path / "test.db")
    db1 = Database(db_file)
    ts = datetime(2024, 6, 15, 10, 0, 0)
    db1.insert_result(make_result(ts, download=55.0))

    db2 = Database(db_file)
    results = db2.get_latest(1)
    assert len(results) == 1
    assert abs(results[0].download_mbps - 55.0) < 1e-6
