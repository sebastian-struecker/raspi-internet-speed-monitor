"""Unit tests for the Scheduler component."""
import pytest

from app.scheduler import Scheduler, DEFAULT_CRON


# ---------------------------------------------------------------------------
# validate_cron
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expr", [
    "0 * * * *",
    "*/15 * * * *",
    "0 9 * * 1",
    "30 6 * * 1-5",
])
def test_valid_cron_expressions(expr):
    assert Scheduler.validate_cron(expr) is True


@pytest.mark.parametrize("expr", [
    "invalid",
    "* * * *",       # 4 fields
    "60 * * * *",    # minute out of range
    "* 25 * * *",    # hour out of range
    "",
])
def test_invalid_cron_expressions(expr):
    assert Scheduler.validate_cron(expr) is False


# ---------------------------------------------------------------------------
# CRON resolution (replaces load_schedule)
# ---------------------------------------------------------------------------

def test_valid_cron_is_accepted():
    s = Scheduler("*/30 * * * *", lambda: None)
    assert s._cron == "*/30 * * * *"


def test_invalid_cron_falls_back_to_default():
    s = Scheduler("not-valid", lambda: None)
    assert s._cron == DEFAULT_CRON


def test_missing_cron_falls_back_to_default():
    s = Scheduler("", lambda: None)
    assert s._cron == DEFAULT_CRON


# ---------------------------------------------------------------------------
# Trigger execution
# ---------------------------------------------------------------------------

def test_trigger_callable_is_invoked():
    """Scheduler stores on_trigger and it can be called directly."""
    triggered = []
    s = Scheduler("0 * * * *", lambda: triggered.append(1))
    s.on_trigger()
    assert len(triggered) == 1
