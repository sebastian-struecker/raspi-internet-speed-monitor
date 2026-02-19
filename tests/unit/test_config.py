"""Unit tests for configuration management."""
import os
import pytest
import tempfile
import yaml

from app.models import Config, ScheduleConfig, DatabaseConfig, GoogleSheetsConfig, DashboardConfig


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
        "google_sheets": {
            "enabled": True,
            "spreadsheet_id": "abc123",
        },
        "dashboard": {"port": 9090, "auto_refresh_seconds": 30},
        "logging": {"level": "DEBUG"},
    })
    try:
        config = Config.load(path)
        assert config.schedule.cron == "*/15 * * * *"
        assert config.database.path == "/tmp/test.db"
        assert config.database.retention_days == 30
        assert config.google_sheets.spreadsheet_id == "abc123"
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
    config.google_sheets.enabled = False
    errors = config.validate()
    assert errors == []


def test_validate_rejects_invalid_cron():
    config = Config.default()
    config.schedule.cron = "not-a-cron"
    config.google_sheets.enabled = False
    errors = config.validate()
    assert any("CRON" in e for e in errors)


def test_validate_rejects_four_field_cron():
    config = Config.default()
    config.schedule.cron = "* * * *"
    config.google_sheets.enabled = False
    errors = config.validate()
    assert any("CRON" in e for e in errors)


def test_validate_rejects_negative_retention_days():
    config = Config.default()
    config.database.retention_days = -1
    config.google_sheets.enabled = False
    errors = config.validate()
    assert any("retention_days" in e for e in errors)


def test_validate_rejects_missing_spreadsheet_id_when_enabled():
    config = Config.default()
    config.google_sheets.enabled = True
    config.google_sheets.spreadsheet_id = ""
    errors = config.validate()
    assert any("spreadsheet_id" in e for e in errors)


def test_validate_allows_missing_spreadsheet_id_when_disabled():
    config = Config.default()
    config.google_sheets.enabled = False
    config.google_sheets.spreadsheet_id = ""
    errors = config.validate()
    assert not any("spreadsheet_id" in e for e in errors)


def test_validate_rejects_port_zero():
    config = Config.default()
    config.dashboard.port = 0
    config.google_sheets.enabled = False
    errors = config.validate()
    assert any("port" in e for e in errors)


def test_validate_rejects_port_above_65535():
    config = Config.default()
    config.dashboard.port = 65536
    config.google_sheets.enabled = False
    errors = config.validate()
    assert any("port" in e for e in errors)


def test_validate_accepts_boundary_ports():
    for port in (1, 65535):
        config = Config.default()
        config.dashboard.port = port
        config.google_sheets.enabled = False
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
    config.google_sheets.enabled = False
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
    config.google_sheets.enabled = False
    errors = config.validate()
    assert any("CRON" in e for e in errors), f"Expected {expr!r} to be invalid"


# ---------------------------------------------------------------------------
# Config.from_env()
# ---------------------------------------------------------------------------

def test_from_env_defaults(monkeypatch):
    """from_env() returns sensible defaults when no env vars are set."""
    for var in (
        "SPEEDTEST_CRON", "DB_PATH", "DB_RETENTION_DAYS",
        "GOOGLE_SHEETS_ENABLED", "GOOGLE_SHEETS_SPREADSHEET_ID",
        "GOOGLE_SERVICE_ACCOUNT_JSON", "DASHBOARD_PORT",
        "DASHBOARD_REFRESH_SECONDS", "LOG_LEVEL",
    ):
        monkeypatch.delenv(var, raising=False)

    config = Config.from_env()
    assert config.schedule.cron == "0 * * * *"
    assert config.database.path == "/data/speedtest.db"
    assert config.database.retention_days == 90
    assert config.google_sheets.enabled is True
    assert config.google_sheets.spreadsheet_id == ""
    assert config.google_sheets.credentials_json == ""
    assert config.dashboard.port == 8080
    assert config.dashboard.auto_refresh_seconds == 60
    assert config.logging.level == "INFO"


def test_from_env_reads_all_vars(monkeypatch):
    """from_env() picks up every environment variable."""
    monkeypatch.setenv("SPEEDTEST_CRON", "*/30 * * * *")
    monkeypatch.setenv("DB_PATH", "/tmp/test.db")
    monkeypatch.setenv("DB_RETENTION_DAYS", "30")
    monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "false")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "sheet-abc")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    monkeypatch.setenv("DASHBOARD_PORT", "9090")
    monkeypatch.setenv("DASHBOARD_REFRESH_SECONDS", "30")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    config = Config.from_env()
    assert config.schedule.cron == "*/30 * * * *"
    assert config.database.path == "/tmp/test.db"
    assert config.database.retention_days == 30
    assert config.google_sheets.enabled is False
    assert config.google_sheets.spreadsheet_id == "sheet-abc"
    assert config.google_sheets.credentials_json == '{"type":"service_account"}'
    assert config.dashboard.port == 9090
    assert config.dashboard.auto_refresh_seconds == 30
    assert config.logging.level == "DEBUG"


@pytest.mark.parametrize("value,expected", [
    ("true", True), ("True", True), ("TRUE", True),
    ("1", True), ("yes", True), ("YES", True),
    ("false", False), ("False", False), ("0", False), ("no", False),
])
def test_from_env_bool_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", value)
    config = Config.from_env()
    assert config.google_sheets.enabled is expected


def test_validate_rejects_missing_credentials_json_when_enabled(monkeypatch):
    """validate() reports an error when sheets are enabled but credentials_json is empty."""
    monkeypatch.setenv("GOOGLE_SHEETS_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_SHEETS_SPREADSHEET_ID", "my-sheet")
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)

    config = Config.from_env()
    errors = config.validate()
    assert any("credentials_json" in e for e in errors)
