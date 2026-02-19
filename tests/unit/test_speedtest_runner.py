"""Unit tests for SpeedtestRunner."""
import pytest
from datetime import timezone, datetime
from unittest.mock import MagicMock, patch, call

from app.database import Database
from app.models import SpeedTestResult
from app.speedtest_runner import SpeedtestRunner


@pytest.fixture
def db():
    return Database(":memory:")


@pytest.fixture
def runner(db):
    return SpeedtestRunner(db)


# ---------------------------------------------------------------------------
# execute_test
# ---------------------------------------------------------------------------

def test_execute_test_returns_success_result(runner):
    fake_results = {
        "download": 95_000_000.0,
        "upload": 12_000_000.0,
        "ping": 15.0,
        "server": {"host": "speedtest.example.com"},
    }
    mock_st_instance = MagicMock()
    mock_st_instance.results.dict.return_value = fake_results
    mock_st_module = MagicMock()
    mock_st_module.Speedtest.return_value = mock_st_instance

    with patch("app.speedtest_runner._st_module", mock_st_module):
        result = runner.execute_test()

    assert result.success is True
    assert abs(result.download_mbps - 95.0) < 0.1
    assert abs(result.upload_mbps - 12.0) < 0.1
    assert result.ping_ms == 15.0
    assert result.test_server == "speedtest.example.com"


def test_execute_test_handles_network_failure(runner):
    """Failed speed tests return a result with success=False and error_message set."""
    mock_st_module = MagicMock()
    mock_st_module.Speedtest.side_effect = Exception("Network unavailable")

    with patch("app.speedtest_runner._st_module", mock_st_module):
        result = runner.execute_test()

    assert result.success is False
    assert result.error_message is not None
    assert result.download_mbps == 0.0
    assert result.upload_mbps == 0.0
    assert result.ping_ms == 0.0


def test_execute_test_always_returns_speedtest_result(runner):
    """execute_test never raises — it always returns a SpeedTestResult."""
    mock_st_module = MagicMock()
    mock_st_module.Speedtest.side_effect = RuntimeError("anything")

    with patch("app.speedtest_runner._st_module", mock_st_module):
        result = runner.execute_test()
    assert isinstance(result, SpeedTestResult)


# ---------------------------------------------------------------------------
# store_result — retry logic
# ---------------------------------------------------------------------------

def test_store_result_succeeds_on_first_attempt(runner, db):
    result = SpeedTestResult(
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        download_mbps=50.0,
        upload_mbps=10.0,
        ping_ms=20.0,
    )
    success = runner.store_result(result)
    assert success is True
    assert db.count() == 1


def test_store_result_retries_on_failure(runner):
    call_count = {"n": 0}

    def flaky_insert(result):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise Exception("DB locked")
        return 1

    runner.db.insert_result = flaky_insert

    result = SpeedTestResult(
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        download_mbps=50.0,
        upload_mbps=10.0,
        ping_ms=20.0,
    )

    with patch("time.sleep"):  # don't actually sleep
        success = runner.store_result(result, retries=3)

    assert success is True
    assert call_count["n"] == 3


def test_store_result_returns_false_after_exhausting_retries(runner):
    runner.db.insert_result = MagicMock(side_effect=Exception("always fails"))

    result = SpeedTestResult(
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        download_mbps=50.0,
        upload_mbps=10.0,
        ping_ms=20.0,
    )

    with patch("time.sleep"):
        success = runner.store_result(result, retries=3)

    assert success is False
    assert runner.db.insert_result.call_count == 3


def test_store_result_exponential_backoff_delays(runner):
    """Sleep is called with 1, 2 seconds (backoff) between non-final attempts."""
    runner.db.insert_result = MagicMock(side_effect=Exception("always fails"))

    result = SpeedTestResult(
        timestamp=datetime(2024, 1, 1),
        download_mbps=50.0,
        upload_mbps=10.0,
        ping_ms=20.0,
    )

    with patch("time.sleep") as mock_sleep:
        runner.store_result(result, retries=3)

    # For 3 attempts: sleep after attempt 0 (1s) and attempt 1 (2s); no sleep after last
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(1)  # 2**0
    mock_sleep.assert_any_call(2)  # 2**1
