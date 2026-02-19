"""Property-based tests for configuration management.

Properties covered:
  Property 15 – Configuration file round-trip preserves structure
  Property 16 – Configuration validation detects missing required fields
  Property 17 – Missing configuration fields trigger default values
"""
import os
import tempfile
import pytest
import yaml

from hypothesis import given, settings, strategies as st

from app.models import Config, ScheduleConfig, DatabaseConfig, DashboardConfig, LoggingConfig


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

VALID_CRONS = st.sampled_from([
    "0 * * * *",
    "*/15 * * * *",
    "0 9 * * 1",
    "0 0 1 * *",
    "30 6 * * 1-5",
    "0 12 * * 0",
])

INVALID_CRONS = st.sampled_from([
    "invalid",
    "* * * *",
    "60 * * * *",
    "* 25 * * *",
    "",
    "not a cron at all",
])

valid_port = st.integers(min_value=1, max_value=65535)
invalid_port = st.one_of(
    st.integers(max_value=0),
    st.integers(min_value=65536),
)

valid_config_strategy = st.builds(
    Config,
    schedule=st.builds(ScheduleConfig, cron=VALID_CRONS),
    database=st.builds(
        DatabaseConfig,
        path=st.just("/data/speedtest.db"),
        retention_days=st.integers(min_value=0, max_value=3650),
    ),
    dashboard=st.builds(DashboardConfig, port=valid_port, auto_refresh_seconds=st.integers(min_value=5, max_value=3600)),
    logging=st.builds(LoggingConfig, level=st.sampled_from(["DEBUG", "INFO", "WARNING", "ERROR"])),
)


# ---------------------------------------------------------------------------
# Property 16: Configuration validation detects missing required fields
# ---------------------------------------------------------------------------

@given(cron=INVALID_CRONS)
@settings(max_examples=100)
@pytest.mark.property_test
def test_invalid_cron_always_reported(cron):
    """Property 16 (partial): Invalid CRON expressions are always flagged."""
    config = Config.default()
    config.schedule.cron = cron
    errors = config.validate()
    assert any("CRON" in e for e in errors), f"Expected error for CRON {cron!r}"


@given(retention=st.integers(max_value=-1))
@settings(max_examples=100)
@pytest.mark.property_test
def test_negative_retention_always_reported(retention):
    """Property 16 (partial): Negative retention_days is always flagged."""
    config = Config.default()
    config.database.retention_days = retention
    errors = config.validate()
    assert any("retention_days" in e for e in errors)


@given(port=invalid_port)
@settings(max_examples=100)
@pytest.mark.property_test
def test_invalid_port_always_reported(port):
    """Property 16 (partial): Out-of-range port numbers are always flagged."""
    config = Config.default()
    config.dashboard.port = port
    errors = config.validate()
    assert any("port" in e for e in errors)


@given(cron=VALID_CRONS, port=valid_port, retention=st.integers(min_value=0))
@settings(max_examples=100)
@pytest.mark.property_test
def test_valid_config_has_no_errors(cron, port, retention):
    """Property 16 (partial): Valid config produces no errors."""
    config = Config.default()
    config.schedule.cron = cron
    config.dashboard.port = port
    config.database.retention_days = retention
    errors = config.validate()
    assert errors == []


# ---------------------------------------------------------------------------
# Property 15: Configuration file round-trip preserves structure
# ---------------------------------------------------------------------------

@given(config=valid_config_strategy)
@settings(max_examples=100)
@pytest.mark.property_test
def test_config_roundtrip_preserves_structure(config):
    """Property 15: Serialise to YAML and parse back produces equivalent config."""
    data = config.to_dict()
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, f)
    f.close()
    try:
        loaded = Config.load(f.name)
        assert loaded.schedule.cron == config.schedule.cron
        assert loaded.database.path == config.database.path
        assert loaded.database.retention_days == config.database.retention_days
        assert loaded.dashboard.port == config.dashboard.port
        assert loaded.dashboard.auto_refresh_seconds == config.dashboard.auto_refresh_seconds
        assert loaded.logging.level == config.logging.level
    finally:
        os.unlink(f.name)


# ---------------------------------------------------------------------------
# Property 17: Missing configuration fields trigger default values
# ---------------------------------------------------------------------------

@pytest.mark.property_test
def test_empty_config_file_uses_all_defaults():
    """Property 17: An empty config file produces a fully-defaulted Config."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump({}, f)
    f.close()
    try:
        config = Config.load(f.name)
        defaults = Config.default()
        assert config.schedule.cron == defaults.schedule.cron
        assert config.database.path == defaults.database.path
        assert config.database.retention_days == defaults.database.retention_days
        assert config.dashboard.port == defaults.dashboard.port
        assert config.dashboard.auto_refresh_seconds == defaults.dashboard.auto_refresh_seconds
        assert config.logging.level == defaults.logging.level
    finally:
        os.unlink(f.name)


@given(
    cron=VALID_CRONS,
    retention=st.integers(min_value=0, max_value=3650),
)
@settings(max_examples=100)
@pytest.mark.property_test
def test_partial_config_merges_with_defaults(cron, retention):
    """Property 17: Partial config merges provided values with defaults for missing sections."""
    data = {"schedule": {"cron": cron}, "database": {"retention_days": retention}}
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(data, f)
    f.close()
    try:
        config = Config.load(f.name)
        assert config.schedule.cron == cron
        assert config.database.retention_days == retention
        # Default for unspecified sections
        assert config.dashboard.port == 8080
        assert config.logging.level == "INFO"
    finally:
        os.unlink(f.name)
