# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A multi-container Docker application for monitoring internet speed on Raspberry Pi 3. It periodically measures
download/upload speeds and ping, stores results in SQLite, and serves a web dashboard.

## Commands

```bash
# Run all tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v --cov

# Property-based tests with Hypothesis statistics
pytest tests/property/ -v --hypothesis-show-statistics

# Single test file
pytest tests/unit/test_database.py -v

# Start all containers
docker compose up -d --build

# View logs for a specific service
docker compose logs -f speedtest

# Stop all containers
docker compose down
```

Tests need a venv with `requirements-dev.txt` installed. There is no pre-existing venv committed; create one with
`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`.

## Architecture

Three Docker containers sharing a named `data` volume that holds the SQLite file:

- **speedtest** (`app/speedtest_runner.py` + `app/scheduler.py`, entry point `app/speedtest_service.py`): executes speed
  tests via `speedtest-cli`, writes results to SQLite with exponential-backoff retry, and runs a CRON scheduler via
  APScheduler. Also schedules the daily DB cleanup job via a second `BackgroundScheduler`.
- **dashboard** (`app/dashboard.py`, entry point `app/dashboard_service.py`): Flask app with three endpoints (
  `/api/current`, `/api/history`, `/api/stats`) and a Chart.js single-page frontend (`app/static/index.html`). Reads the
  SQLite volume read-only. Exposed on port 8080.
- **SQLite** (`/data/speedtest.db`): a file on the shared `data` volume — no separate DB container. Written by
  speedtest, read by dashboard.

All configuration comes from environment variables read via `Config.from_env()`. There are no config files mounted into
containers.

## Key Implementation Details

**`app/models.py`** — central data model. `SpeedTestResult` is the struct shared by all layers: database and API responses.
`Config.from_env()` reads all settings from environment variables (see table below).
`Config.load(path)` also exists for YAML loading but is not used by any service entry point. `Config.validate()` returns
a list of error strings.

**`app/database.py`** — `Database` class wraps SQLite. Uses a persistent connection for `:memory:` databases (required
for tests) and opens/closes per-operation connections for file-based paths to avoid file-descriptor leaks. All SQL goes
through a single `_execute()` helper. The schema stores `success` and `error_message` so failed tests are persisted
correctly. Never expose `_connect()` to callers outside the class.

**`app/speedtest_runner.py`** — imports `speedtest` at module level as `_st_module` so tests can patch
`app.speedtest_runner._st_module` cleanly. Retry: 3 attempts, sleeps `2**attempt` seconds between non-final failures (no
sleep after the last attempt).

**`app/scheduler.py`** — takes `cron` and `on_trigger` in its constructor. Uses `APScheduler.BackgroundScheduler` +
`CronTrigger`. Invalid CRON expressions fall back to `"0 * * * *"` with an error log. No file-watching or hot-reload.

## Key Design Decisions

- **ARM images**: all containers use `arm32v7/python:3.9-slim`.
- **Resource limits**: speedtest ≤ 200 MB RAM, dashboard ≤ 150 MB.
- **CRON fallback**: invalid expressions fall back to `"0 * * * *"` (hourly) with an error log.
- **Retention**: `DB_RETENTION_DAYS=0` keeps data indefinitely; cleanup runs at midnight daily.
- **`datetime.utcnow()` is deprecated** in Python 3.12+. Use `datetime.now(timezone.utc).replace(tzinfo=None)`
  throughout, or the `_utcnow()` helper defined in `database.py` and `speedtest_runner.py`.
- **Hypothesis + pytest fixtures**: `tmp_path` and `caplog` do not reset between Hypothesis examples. Use `tempfile` and
  a custom `MemoryHandler`-style approach instead (see `tests/property/`).

## Configuration

All settings are read from environment variables via `Config.from_env()`:

| Env var                        | Default              | Description                           |
|--------------------------------|----------------------|---------------------------------------|
| `SPEEDTEST_CRON`               | `0 * * * *`          | 5-field CRON expression               |
| `DB_PATH`                      | `/data/speedtest.db` | SQLite file path inside container     |
| `DB_RETENTION_DAYS`            | `90`                 | Days to keep results (0 = forever)    |
| `DASHBOARD_PORT`               | `8080`               | Exposed port                          |
| `DASHBOARD_REFRESH_SECONDS`    | `60`                 | Browser auto-refresh interval         |
| `LOG_LEVEL`                    | `INFO`               | `DEBUG`/`INFO`/`WARNING`/`ERROR`      |

Copy `.env.example` to `.env` and fill in values before running `docker compose up`.

## Testing

Tests across two suites, all passing:

| Suite             | Files                                                                                               | What it covers                                                  |
|-------------------|-----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| `tests/unit/`     | `test_config`, `test_database`, `test_dashboard`, `test_scheduler`, `test_speedtest_runner`        | Specific examples, edge cases, error conditions                 |
| `tests/property/` | `test_properties_config`, `test_properties_database`, `test_properties_speedtest`                   | Correctness properties, 100 Hypothesis examples each            |

`tests/conftest.py` provides shared `sample_result` and `default_config` fixtures. The `Database(":memory:")` fixture in
each test file creates a fresh in-memory DB per test function.
