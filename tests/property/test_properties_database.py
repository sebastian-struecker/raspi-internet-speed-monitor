"""Property-based tests for the Database component.

Properties covered:
  Property 7  – Database storage and retrieval round-trip preserves all fields
  Property 8  – Database persistence survives connection close and reopen
  Property 9  – Date range queries return only results within the specified range
  Property 22 – Database cleanup deletes only results older than retention period
  Property 23 – Undefined retention period prevents data deletion
"""
import pytest
from datetime import timezone, datetime, timedelta
from hypothesis import given, settings, strategies as st, assume

from app.database import Database
from app.models import SpeedTestResult


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

reasonable_float = st.floats(min_value=0.1, max_value=10_000.0, allow_nan=False, allow_infinity=False)
reasonable_ping = st.floats(min_value=0.1, max_value=5_000.0, allow_nan=False, allow_infinity=False)

# Datetimes that SQLite can round-trip via isoformat without sub-second precision issues
safe_datetime = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
).map(lambda dt: dt.replace(microsecond=0))


@st.composite
def speed_test_result(draw):
    return SpeedTestResult(
        timestamp=draw(safe_datetime),
        download_mbps=draw(reasonable_float),
        upload_mbps=draw(reasonable_float),
        ping_ms=draw(reasonable_ping),
        test_server=draw(st.one_of(st.none(), st.text(min_size=1, max_size=50))),
    )


# ---------------------------------------------------------------------------
# Property 7: Round-trip preserves all fields
# ---------------------------------------------------------------------------

@given(result=speed_test_result())
@settings(max_examples=100)
@pytest.mark.property_test
def test_roundtrip_preserves_fields(result):
    """Property 7: Store then retrieve yields identical core fields."""
    db = Database(":memory:")
    db.insert_result(result)
    retrieved = db.get_latest(1)[0]

    assert retrieved.timestamp == result.timestamp
    assert abs(retrieved.download_mbps - result.download_mbps) < 1e-6
    assert abs(retrieved.upload_mbps - result.upload_mbps) < 1e-6
    assert abs(retrieved.ping_ms - result.ping_ms) < 1e-6
    assert retrieved.test_server == result.test_server


# ---------------------------------------------------------------------------
# Property 8: Persistence survives connection close and reopen
# ---------------------------------------------------------------------------

@given(result=speed_test_result())
@settings(max_examples=100)
@pytest.mark.property_test
def test_persistence_across_reconnect(result):
    """Property 8: Data is retrievable after closing and reopening the DB."""
    import tempfile
    import os

    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db1 = Database(db_path)
        db1.insert_result(result)
        del db1  # force close

        db2 = Database(db_path)
        retrieved = db2.get_latest(1)[0]

        assert retrieved.timestamp == result.timestamp
        assert abs(retrieved.download_mbps - result.download_mbps) < 1e-6
        assert abs(retrieved.upload_mbps - result.upload_mbps) < 1e-6
        assert abs(retrieved.ping_ms - result.ping_ms) < 1e-6
    finally:
        os.unlink(db_path)


# ---------------------------------------------------------------------------
# Property 9: Date range queries return only results within the range
# ---------------------------------------------------------------------------

@given(
    results=st.lists(speed_test_result(), min_size=0, max_size=20),
    start=safe_datetime,
    duration_hours=st.integers(min_value=1, max_value=24 * 30),
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_query_range_only_returns_results_in_range(results, start, duration_hours):
    """Property 9: Every returned result has timestamp within [start, end]."""
    end = start + timedelta(hours=duration_hours)

    db = Database(":memory:")
    for r in results:
        db.insert_result(r)

    returned = db.query_range(start, end)
    for r in returned:
        assert start <= r.timestamp <= end, (
            f"Returned result {r.timestamp} is outside [{start}, {end}]"
        )


@given(
    results=st.lists(speed_test_result(), min_size=1, max_size=20),
    start=safe_datetime,
    duration_hours=st.integers(min_value=1, max_value=24 * 30),
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_query_range_includes_all_in_range_results(results, start, duration_hours):
    """Property 9 (completeness): Results inside the range are not omitted."""
    end = start + timedelta(hours=duration_hours)

    db = Database(":memory:")
    for r in results:
        db.insert_result(r)

    expected = [r for r in results if start <= r.timestamp <= end]
    returned = db.query_range(start, end)

    assert len(returned) == len(expected)


# ---------------------------------------------------------------------------
# Property 22: Cleanup deletes only rows older than retention period
# ---------------------------------------------------------------------------

@given(
    results=st.lists(speed_test_result(), min_size=1, max_size=20),
    retention_days=st.integers(min_value=1, max_value=3650),
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_cleanup_deletes_only_old_results(results, retention_days):
    """Property 22: cleanup_old_data removes only rows older than retention_days."""
    db = Database(":memory:")
    for r in results:
        db.insert_result(r)

    count_before = db.count()
    db.cleanup_old_data(retention_days)

    # Verify remaining rows are all recent enough
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retention_days)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    remaining = db.query_range(datetime(2000, 1, 1), now)
    for r in remaining:
        assert r.timestamp >= cutoff, (
            f"Row with timestamp {r.timestamp} should have been deleted (cutoff={cutoff})"
        )


# ---------------------------------------------------------------------------
# Property 23: Undefined (0) retention period prevents data deletion
# ---------------------------------------------------------------------------

@given(results=st.lists(speed_test_result(), min_size=1, max_size=20))
@settings(max_examples=100)
@pytest.mark.property_test
def test_zero_retention_keeps_all_data(results):
    """Property 23: retention_days=0 never deletes any rows."""
    db = Database(":memory:")
    for r in results:
        db.insert_result(r)

    count_before = db.count()
    deleted = db.cleanup_old_data(retention_days=0)

    assert deleted == 0
    assert db.count() == count_before
