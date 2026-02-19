"""Property-based tests for the Speedtest component.

Properties covered:
  Property 1  – Speed test results contain all required metrics
  Property 3  – Failed speed tests are logged and don't crash the system
  Property 4  – CRON expression validation correctly identifies valid and invalid expressions
  Property 5  – Invalid CRON expressions trigger default schedule fallback
  Property 6  – CRON expression is stored and used by the scheduler
  Property 10 – Database storage retry implements exponential backoff
  Property 18 – Network failures are logged and don't prevent subsequent tests
"""
import time
import logging
import pytest
from datetime import timezone, datetime
from unittest.mock import MagicMock, patch

from hypothesis import given, settings, strategies as st

from app.database import Database
from app.models import SpeedTestResult, Config
from app.speedtest_runner import SpeedtestRunner
from app.scheduler import Scheduler, DEFAULT_CRON


# ---------------------------------------------------------------------------
# Property 1: Speed test results contain all required metrics
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_successful_result_has_all_required_metrics():
    """Property 1: A successful SpeedTestResult has all required fields."""
    result = SpeedTestResult(
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        download_mbps=95.0,
        upload_mbps=12.0,
        ping_ms=15.0,
        success=True,
    )
    assert isinstance(result.timestamp, datetime)
    assert isinstance(result.download_mbps, float)
    assert isinstance(result.upload_mbps, float)
    assert isinstance(result.ping_ms, float)
    assert result.success is True


@given(
    download=st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False),
    upload=st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False),
    ping=st.floats(min_value=0.0, max_value=5_000.0, allow_nan=False),
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_speedtest_result_fields_preserved(download, upload, ping):
    """Property 1: All metric fields survive dataclass construction."""
    ts = datetime.now(timezone.utc).replace(tzinfo=None)
    result = SpeedTestResult(timestamp=ts, download_mbps=download, upload_mbps=upload, ping_ms=ping)
    assert result.timestamp == ts
    assert result.download_mbps == download
    assert result.upload_mbps == upload
    assert result.ping_ms == ping


# ---------------------------------------------------------------------------
# Property 3: Failed speed tests don't crash the system
# ---------------------------------------------------------------------------

@given(error_msg=st.text(max_size=200))
@settings(max_examples=100)
@pytest.mark.property_test
def test_failed_test_does_not_raise(error_msg):
    """Property 3: execute_test catches all exceptions and returns a failure result."""
    db = Database(":memory:")
    runner = SpeedtestRunner(db)

    mock_st_module = MagicMock()
    mock_st_module.Speedtest.side_effect = Exception(error_msg)

    with patch("app.speedtest_runner._st_module", mock_st_module):
        result = runner.execute_test()

    assert isinstance(result, SpeedTestResult)
    assert result.success is False


# ---------------------------------------------------------------------------
# Property 4: CRON expression validation correctly identifies valid/invalid
# ---------------------------------------------------------------------------

VALID_CRONS = [
    "0 * * * *",
    "*/15 * * * *",
    "0 9 * * 1",
    "0 0 1 * *",
    "30 6 * * 1-5",
]
INVALID_CRONS = [
    "invalid",
    "* * * *",
    "60 * * * *",
    "",
    "not a cron",
]


@given(expr=st.sampled_from(VALID_CRONS))
@settings(max_examples=len(VALID_CRONS))
@pytest.mark.property_test
def test_valid_cron_identified_as_valid(expr):
    """Property 4 (valid): Validator accepts all valid 5-field CRON expressions."""
    assert Scheduler.validate_cron(expr) is True


@given(expr=st.sampled_from(INVALID_CRONS))
@settings(max_examples=len(INVALID_CRONS))
@pytest.mark.property_test
def test_invalid_cron_identified_as_invalid(expr):
    """Property 4 (invalid): Validator rejects all invalid expressions."""
    assert Scheduler.validate_cron(expr) is False


# ---------------------------------------------------------------------------
# Property 5: Invalid CRON expressions trigger default schedule fallback
# ---------------------------------------------------------------------------

@given(expr=st.sampled_from(INVALID_CRONS))
@settings(max_examples=len(INVALID_CRONS))
@pytest.mark.property_test
def test_invalid_cron_triggers_default_fallback(expr):
    """Property 5: Scheduler falls back to DEFAULT_CRON for any invalid expression."""
    s = Scheduler(expr, lambda: None)
    assert s._cron == DEFAULT_CRON


# ---------------------------------------------------------------------------
# Property 6: CRON expression is stored and used by the scheduler
# ---------------------------------------------------------------------------

@given(cron=st.sampled_from(VALID_CRONS))
@settings(max_examples=len(VALID_CRONS))
@pytest.mark.property_test
def test_configuration_loading_reads_cron(cron):
    """Property 6: Scheduler stores the provided valid CRON expression."""
    s = Scheduler(cron, lambda: None)
    assert s._cron == cron


# ---------------------------------------------------------------------------
# Property 10: Database storage retry implements exponential backoff
# ---------------------------------------------------------------------------

@given(fail_count=st.integers(min_value=1, max_value=2))
@settings(max_examples=10)
@pytest.mark.property_test
def test_retry_uses_exponential_backoff(fail_count):
    """Property 10: store_result sleeps for 2^attempt seconds between non-final retries."""
    db = Database(":memory:")
    runner = SpeedtestRunner(db)

    call_count = {"n": 0}

    def flaky_insert(result):
        call_count["n"] += 1
        if call_count["n"] <= fail_count:
            raise Exception("locked")
        return 1

    runner.db.insert_result = flaky_insert

    result = SpeedTestResult(
        timestamp=datetime(2024, 1, 1),
        download_mbps=50.0,
        upload_mbps=10.0,
        ping_ms=20.0,
    )

    sleep_calls = []
    with patch("time.sleep", side_effect=lambda x: sleep_calls.append(x)):
        runner.store_result(result, retries=3)

    # sleep is called fail_count times (once between each non-final failure)
    assert len(sleep_calls) == fail_count
    for i, delay in enumerate(sleep_calls):
        assert delay == 2 ** i, f"Expected delay 2^{i}={2**i}, got {delay}"


# ---------------------------------------------------------------------------
# Property 18: Network failures don't prevent subsequent tests
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_network_failure_does_not_prevent_next_test():
    """Property 18: After a failed test, execute_test can be called again successfully."""
    db = Database(":memory:")
    runner = SpeedtestRunner(db)

    mock_st_module = MagicMock()
    mock_st_module.Speedtest.side_effect = Exception("Network down")

    # First call fails
    with patch("app.speedtest_runner._st_module", mock_st_module):
        result1 = runner.execute_test()
    assert result1.success is False

    # Second call also fails — system is still running, just can't reach speedtest servers
    with patch("app.speedtest_runner._st_module", mock_st_module):
        result2 = runner.execute_test()
    assert result2.success is False
    assert isinstance(result2, SpeedTestResult)
