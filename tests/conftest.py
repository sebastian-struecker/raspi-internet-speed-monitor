"""Shared pytest fixtures."""
import pytest
from datetime import datetime
from app.models import SpeedTestResult, Config


@pytest.fixture
def sample_result():
    return SpeedTestResult(
        timestamp=datetime(2024, 1, 15, 10, 0, 0),
        download_mbps=95.3,
        upload_mbps=12.4,
        ping_ms=15.0,
        test_server="speedtest.example.com",
        success=True,
    )


@pytest.fixture
def default_config():
    return Config.default()
