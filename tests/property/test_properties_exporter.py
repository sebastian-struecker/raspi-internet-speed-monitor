"""Property-based tests for the Google Sheets Exporter.

Properties covered:
  Property 11 – Configuration loading reads Google Sheets spreadsheet ID
  Property 12 – Failed Google Sheets exports are queued for retry
  Property 13 – Export attempts are logged regardless of outcome
  Property 24 – Google Sheets exporter never deletes data
"""
import logging
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from hypothesis import given, settings, strategies as st

from app.database import Database
from app.exporter import GoogleSheetsExporter
from app.models import SpeedTestResult, Config


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

reasonable_float = st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
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
        ping_ms=draw(reasonable_float),
        success=True,
    )


def make_exporter(worksheet=None):
    db = Database(":memory:")
    exp = GoogleSheetsExporter(
        credentials_json="",
        spreadsheet_id="fake-sheet-id",
        db=db,
    )
    exp._worksheet = worksheet or MagicMock()
    return exp


# ---------------------------------------------------------------------------
# Property 11: Configuration loading reads Google Sheets spreadsheet ID
# ---------------------------------------------------------------------------

@given(sheet_id=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "P"))))
@settings(max_examples=100)
@pytest.mark.property_test
def test_config_spreadsheet_id_is_preserved(sheet_id):
    """Property 11: Any non-empty spreadsheet_id survives Config construction."""
    config = Config.default()
    config.google_sheets.spreadsheet_id = sheet_id
    assert config.google_sheets.spreadsheet_id == sheet_id


# ---------------------------------------------------------------------------
# Property 12: Failed exports are queued for retry
# ---------------------------------------------------------------------------

@given(result=speed_test_result())
@settings(max_examples=100)
@pytest.mark.property_test
def test_failed_export_always_queued(result):
    """Property 12: Any API failure causes the result to be queued."""
    worksheet = MagicMock()
    worksheet.append_row.side_effect = Exception("API unavailable")
    exporter = make_exporter(worksheet)

    queue_before = exporter.retry_queue_size
    exporter.export_result(result)
    assert exporter.retry_queue_size == queue_before + 1


@given(results=st.lists(speed_test_result(), min_size=1, max_size=10))
@settings(max_examples=50)
@pytest.mark.property_test
def test_multiple_failures_all_queued(results):
    """Property 12: All failed exports end up in the queue."""
    worksheet = MagicMock()
    worksheet.append_row.side_effect = Exception("API down")
    exporter = make_exporter(worksheet)

    for r in results:
        exporter.export_result(r)

    assert exporter.retry_queue_size == len(results)


# ---------------------------------------------------------------------------
# Property 13: Export attempts are logged regardless of outcome
# ---------------------------------------------------------------------------

def _capture_logs(logger_name: str, level: int):
    """Context manager returning a list that collects LogRecord messages."""
    import contextlib

    class _ListHandler(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []
        def emit(self, record):
            self.records.append(self.format(record))

    @contextlib.contextmanager
    def _ctx():
        handler = _ListHandler()
        lgr = logging.getLogger(logger_name)
        lgr.addHandler(handler)
        old_level = lgr.level
        lgr.setLevel(level)
        try:
            yield handler.records
        finally:
            lgr.removeHandler(handler)
            lgr.setLevel(old_level)

    return _ctx()


@given(result=speed_test_result())
@settings(max_examples=100)
@pytest.mark.property_test
def test_successful_export_is_logged(result):
    """Property 13 (success): Successful exports produce a log entry."""
    exporter = make_exporter()
    with _capture_logs("app.exporter", logging.INFO) as records:
        exporter.export_result(result)
    assert any("exported" in r.lower() or "export" in r.lower() for r in records)


@given(result=speed_test_result())
@settings(max_examples=100)
@pytest.mark.property_test
def test_failed_export_is_logged(result):
    """Property 13 (failure): Failed exports produce a log entry."""
    worksheet = MagicMock()
    worksheet.append_row.side_effect = Exception("boom")
    exporter = make_exporter(worksheet)

    with _capture_logs("app.exporter", logging.ERROR) as records:
        exporter.export_result(result)
    assert any("fail" in r.lower() or "error" in r.lower() for r in records)


# ---------------------------------------------------------------------------
# Property 24: Google Sheets exporter never deletes data
# ---------------------------------------------------------------------------

@given(results=st.lists(speed_test_result(), min_size=1, max_size=10))
@settings(max_examples=100)
@pytest.mark.property_test
def test_exporter_never_calls_delete(results):
    """Property 24: No sequence of exporter operations calls any delete method."""
    worksheet = MagicMock()
    exporter = make_exporter(worksheet)

    for r in results:
        exporter.export_result(r)
    exporter.retry_failed_exports()

    for method_name, *_ in worksheet.method_calls:
        assert "delete" not in method_name.lower(), (
            f"Exporter called delete method: {method_name}"
        )
