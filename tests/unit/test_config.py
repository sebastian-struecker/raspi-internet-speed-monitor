"""Unit tests for configuration management."""
import os
import pytest
import tempfile
import yaml

from app.models import Config, ScheduleConfig, DatabaseConfig, DashboardConfig


# ---------------------------------------------------------------------------
# Config.load()
# ---------------------------------------------------------------------------

def _write_yaml(data: dict) -> str:
    """Write a dict to a temp YAML file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, f)
    f.close()
    return f.name


def test_load_full_config():
    path = _write_yaml({
        "schedule": {"cron": "*/15 * * * *"},
        "database": {"path": "/tmp/test.db", "retention_days": 30},
        "dashboard": {"port": 9090, "auto_refresh_seconds": 30},
        "logging": {"level": "DEBUG"},
    })
    try:
        config = Config.load(path)
        assert config.schedule.cron == "*/15 * * * *"
        assert config.database.path == "/tmp/test.db"
        assert config.database.retention_days == 30
        assert config.dashboard.port == 9090
        assert config.logging.level == "DEBUG"
    finally:
        os.unlink(path)


def test_load_applies_defaults_for_missing_sections():
    path = _write_yaml({})
    try:
        config = Config.load(path)
        assert config.schedule.cron == "0 * * * *"
        assert config.database.retention_days == 90
        assert config.dashboard.port == 8080
    finally:
        os.unlink(path)


def test_load_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        Config.load("/nonexistent/config.yaml")


# ---------------------------------------------------------------------------
# Config.validate()
# ---------------------------------------------------------------------------

def test_validate_passes_for_valid_config():
    config = Config.default()
    errors = config.validate()
    assert errors == []


def test_validate_rejects_invalid_cron():
    config = Config.default()
    config.schedule.cron = "not-a-cron"
    errors = config.validate()
    assert any("CRON" in e for e in errors)


def test_validate_rejects_four_field_cron():
    config = Config.default()
    config.schedule.cron = "* * * *"
    errors = config.validate()
    assert any("CRON" in e for e in errors)


def test_validate_rejects_negative_retention_days():
    config = Config.default()
    config.database.retention_days = -1
    errors = config.validate()
    assert any("retention_days" in e for e in errors)


def test_validate_rejects_port_zero():
    config = Config.default()
    config.dashboard.port = 0
    errors = config.validate()
    assert any("port" in e for e in errors)


def test_validate_rejects_port_above_65535():
    config = Config.default()
    config.dashboard.port = 65536
    errors = config.validate()
    assert any("port" in e for e in errors)


def test_validate_accepts_boundary_ports():
    for port in (1, 65535):
        config = Config.default()
        config.dashboard.port = port
        errors = config.validate()
        assert not any("port" in e for e in errors), f"Port {port} should be valid"


# ---------------------------------------------------------------------------
# Valid CRON expressions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr", [
    "0 * * * *",
    "*/15 * * * *",
    "0 9 * * 1",
    "0 0 1 * *",
    "30 6 * * 1-5",
])
def test_valid_cron_expressions(expr):
    config = Config.default()
    config.schedule.cron = expr
    errors = config.validate()
    assert not any("CRON" in e for e in errors), f"Expected {expr!r} to be valid"


@pytest.mark.parametrize("expr", [
    "invalid",
    "* * * *",
    "60 * * * *",
    "* 25 * * *",
    "",
])
def test_invalid_cron_expressions(expr):
    config = Config.default()
    config.schedule.cron = expr
    errors = config.validate()
    assert any("CRON" in e for e in errors), f"Expected {expr!r} to be invalid"


# ---------------------------------------------------------------------------
# Config.from_env()
# ---------------------------------------------------------------------------

def test_from_env_defaults(monkeypatch):
    """from_env() returns sensible defaults when no env vars are set."""
    for var in (
        "SPEEDTEST_CRON", "DB_PATH", "DB_RETENTION_DAYS",
        "DASHBOARD_PORT", "DASHBOARD_REFRESH_SECONDS", "LOG_LEVEL",
    ):
        monkeypatch.delenv(var, raising=False)

    config = Config.from_env()
    assert config.schedule.cron == "0 * * * *"
    assert config.database.path == "/data/speedtest.db"
    assert config.database.retention_days == 90
    assert config.dashboard.port == 8080
    assert config.dashboard.auto_refresh_seconds == 60
    assert config.logging.level == "INFO"


def test_from_env_reads_all_vars(monkeypatch):
    """from_env() picks up every environment variable."""
    monkeypatch.setenv("SPEEDTEST_CRON", "*/30 * * * *")
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")
    monkeypatch.setenv("DB_RETENTION_DAYS", "30")
    monkeypatch.setenv("DASHBOARD_PORT", "9090")
    monkeypatch.setenv("DASHBOARD_REFRESH_SECONDS", "30")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    config = Config.from_env()
    assert config.schedule.cron == "*/30 * * * *"
    assert config.database.path == "/tmp/test.db"
    assert config.database.retention_days == 30
    assert config.dashboard.port == 9090
    assert config.dashboard.auto_refresh_seconds == 30
    assert config.logging.level == "DEBUG"
