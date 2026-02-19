"""Unit tests for GoogleSheetsExporter."""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call

from app.database import Database
from app.exporter import GoogleSheetsExporter
from app.models import SpeedTestResult


@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def exporter(db):
    exp = GoogleSheetsExporter(
        credentials_json="",
        spreadsheet_id="fake-sheet-id",
        db=db,
    )
    # Pre-wire a mock worksheet so tests don't need to call authenticate()
    exp._worksheet = MagicMock()
    return exp


def make_result(ts=None):
    return SpeedTestResult(
        timestamp=ts or datetime(2024, 6, 15, 10, 0, 0),
        download_mbps=95.0,
        upload_mbps=12.0,
        ping_ms=15.0,
        success=True,
        id=1,
    )


# ---------------------------------------------------------------------------
# export_result
# ---------------------------------------------------------------------------

def test_export_result_appends_row(exporter):
    result = make_result()
    success = exporter.export_result(result)
    assert success is True
    exporter._worksheet.append_row.assert_called_once()
    row = exporter._worksheet.append_row.call_args[0][0]
    assert row[0] == "2024-06-15 10:00:00"
    assert row[1] == 95.0
    assert row[2] == 12.0
    assert row[3] == 15.0


def test_export_result_queues_on_failure(exporter):
    exporter._worksheet.append_row.side_effect = Exception("API error")
    result = make_result()
    success = exporter.export_result(result)
    assert success is False
    assert exporter.retry_queue_size == 1


def test_export_result_never_deletes(exporter):
    """Property 24: The exporter never calls any delete-type method."""
    result = make_result()
    exporter.export_result(result)
    # method_calls entries are call objects; call.name is the attribute/method called
    for c in exporter._worksheet.method_calls:
        assert "delete" not in c[0].lower(), f"Unexpected delete call: {c[0]}"


# ---------------------------------------------------------------------------
# retry_failed_exports
# ---------------------------------------------------------------------------

def test_retry_clears_queue_on_success(exporter):
    # Queue two results
    exporter._retry_queue.append(make_result(datetime(2024, 1, 1)))
    exporter._retry_queue.append(make_result(datetime(2024, 1, 2)))

    exported = exporter.retry_failed_exports()
    assert exported == 2
    assert exporter.retry_queue_size == 0


def test_retry_keeps_failed_items_in_queue(exporter):
    exporter._worksheet.append_row.side_effect = Exception("still failing")
    exporter._retry_queue.append(make_result())

    exported = exporter.retry_failed_exports()
    assert exported == 0
    assert exporter.retry_queue_size == 1  # re-queued


def test_retry_partial_success(exporter):
    """Items that succeed are removed; items that fail remain queued."""
    call_count = {"n": 0}

    def flaky(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise Exception("fail second")

    exporter._worksheet.append_row.side_effect = flaky

    exporter._retry_queue.append(make_result(datetime(2024, 1, 1)))
    exporter._retry_queue.append(make_result(datetime(2024, 1, 2)))
    exporter._retry_queue.append(make_result(datetime(2024, 1, 3)))

    exported = exporter.retry_failed_exports()
    assert exported == 2
    assert exporter.retry_queue_size == 1  # the failed one was re-queued


# ---------------------------------------------------------------------------
# poll_database
# ---------------------------------------------------------------------------

def test_poll_database_returns_new_results(db, exporter):
    from app.database import Database as DB
    ts1 = datetime(2024, 1, 1, 10, 0)
    ts2 = datetime(2024, 1, 1, 11, 0)
    ts3 = datetime(2024, 1, 1, 12, 0)

    r1 = SpeedTestResult(timestamp=ts1, download_mbps=50.0, upload_mbps=10.0, ping_ms=20.0)
    r2 = SpeedTestResult(timestamp=ts2, download_mbps=60.0, upload_mbps=11.0, ping_ms=18.0)
    r3 = SpeedTestResult(timestamp=ts3, download_mbps=70.0, upload_mbps=12.0, ping_ms=16.0)

    id1 = db.insert_result(r1)
    id2 = db.insert_result(r2)
    id3 = db.insert_result(r3)

    # Poll from after id1
    results = exporter.poll_database(last_id=id1)
    assert len(results) == 2
    assert results[0].id == id2
    assert results[1].id == id3


def test_poll_database_empty_when_no_new(db, exporter):
    ts = datetime(2024, 1, 1)
    r = SpeedTestResult(timestamp=ts, download_mbps=50.0, upload_mbps=10.0, ping_ms=20.0)
    row_id = db.insert_result(r)
    results = exporter.poll_database(last_id=row_id)
    assert results == []


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def test_export_success_is_logged(exporter, caplog):
    import logging
    with caplog.at_level(logging.INFO):
        exporter.export_result(make_result())
    assert any("Exported" in r.message for r in caplog.records)


def test_export_failure_is_logged(exporter, caplog):
    import logging
    exporter._worksheet.append_row.side_effect = Exception("boom")
    with caplog.at_level(logging.ERROR):
        exporter.export_result(make_result())
    assert any("Export failed" in r.message for r in caplog.records)
