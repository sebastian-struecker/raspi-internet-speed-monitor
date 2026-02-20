# Raspi Internet Speed Monitor

> Warning: This project was vibe-coded. Please help in making this even better.

A self-hosted internet speed monitor designed to run on a **Raspberry Pi 3**. It periodically measures download/upload
speeds and ping, stores results in a local SQLite database, exports them to Google Sheets, and serves a live dashboard
in your browser.

## How it works

Three Docker containers run as a stack and communicate through a shared SQLite volume:

| Container         | Role                                                                 |
|-------------------|----------------------------------------------------------------------|
| **speedtest**     | Runs speed tests on a CRON schedule; also handles daily data cleanup |
| **exporter**      | Polls the database and appends new results to a Google Sheet         |
| **dashboard**     | Flask REST API + Chart.js web UI, accessible on port 8080            |
| *(shared volume)* | SQLite database file (`/data/speedtest.db`)                          |

All settings are controlled by environment variables — no config files to mount or edit.

---

## Requirements

- Raspberry Pi 3 (or any ARM/x86 host running Linux)
- Docker ≥ 20.10
- Docker Compose ≥ 1.29
- Internet connection

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-username/raspi-internet-speed-monitor.git
cd raspi-internet-speed-monitor
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Open `.env` and fill in your values. The minimum required changes are:

```bash
# How often to run a speed test (standard 5-field CRON)
SPEEDTEST_CRON=0 * * * *

# Set to false if you don't need Google Sheets export
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEETS_SPREADSHEET_ID=      # paste your Sheet ID here
GOOGLE_SERVICE_ACCOUNT_JSON=       # paste your service account JSON here (see below)
```

All other variables have sensible defaults. See the [Configuration reference](#configuration-reference) below.

### 3. Build and start the containers

```bash
docker compose up -d --build
```

The first build takes a few minutes while Python dependencies are installed. Subsequent starts are fast.

Verify all three containers are running:

```bash
docker compose ps
```

### 4. Open the dashboard

Navigate to `http://<raspberry-pi-ip>:8080` in your browser. The dashboard auto-refreshes every 60 seconds and displays
a time-series chart of recent results.

---

## Auto-start on boot

To start the stack automatically whenever the Raspberry Pi powers on, install the included systemd service.

**1. Copy the project to its permanent location:**

```bash
sudo cp -r . /opt/raspi-internet-speed-monitor
```

**2. Install and enable the service:**

```bash
sudo cp internet-speedtest.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable internet-speedtest.service
sudo systemctl start internet-speedtest.service
```

**3. Verify it is running:**

```bash
sudo systemctl status internet-speedtest.service
```

---

## Day-to-day usage

| Task                       | Command                            |
|----------------------------|------------------------------------|
| Start the stack            | `docker compose up -d`             |
| Stop the stack             | `docker compose down`              |
| View all logs              | `docker compose logs -f`           |
| View logs for one service  | `docker compose logs -f speedtest` |
| Restart a single service   | `docker compose restart dashboard` |
| Update after a code change | `docker compose up -d --build`     |

---

## Configuration reference

All settings are read from environment variables (defined in `.env`).

| Variable                       | Default              | Description                                                                         |
|--------------------------------|----------------------|-------------------------------------------------------------------------------------|
| `SPEEDTEST_CRON`               | `0 * * * *`          | 5-field CRON expression for test timing. Falls back to hourly if invalid.           |
| `DB_PATH`                      | `/data/speedtest.db` | Path inside the container (mapped to the `data` Docker volume).                     |
| `DB_RETENTION_DAYS`            | `90`                 | Days to keep results. Set to `0` to keep data indefinitely.                         |
| `GOOGLE_SHEETS_ENABLED`        | `true`               | Set to `false` to disable Google Sheets export entirely.                            |
| `GOOGLE_SHEETS_SPREADSHEET_ID` | *(empty)*            | Required when `GOOGLE_SHEETS_ENABLED=true`.                                         |
| `GOOGLE_SERVICE_ACCOUNT_JSON`  | *(empty)*            | Full contents of the service account JSON key (single line). Required when enabled. |
| `DASHBOARD_PORT`               | `8080`               | Host port the web UI is exposed on.                                                 |
| `DASHBOARD_REFRESH_SECONDS`    | `60`                 | How often the browser auto-refreshes metrics.                                       |
| `LOG_LEVEL`                    | `INFO`               | Log verbosity: `DEBUG`, `INFO`, `WARNING`, or `ERROR`.                              |

---

## Project structure

```
.
├── app/
│   ├── models.py            # SpeedTestResult and Config dataclasses
│   ├── database.py          # SQLite wrapper
│   ├── speedtest_runner.py  # Speed test execution and retry logic
│   ├── scheduler.py         # CRON scheduling via APScheduler
│   ├── exporter.py          # Google Sheets exporter
│   ├── dashboard.py         # Flask REST API (/api/current, /api/history, /api/stats)
│   ├── static/index.html    # Chart.js web dashboard
│   └── *_service.py         # Container entry points
├── tests/
│   ├── unit/                # pytest unit tests
│   └── property/            # Hypothesis property-based tests (24 correctness properties)
├── .env.example             # Environment variable template — copy to .env and fill in
├── docker-compose.yml
├── Dockerfile.speedtest
├── Dockerfile.exporter
├── Dockerfile.dashboard
└── internet-speedtest.service  # systemd unit for auto-start
```

---

## Running tests

Install the development dependencies and run the test suite:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Property-based tests with Hypothesis statistics
pytest tests/property/ -v --hypothesis-show-statistics

# Single test file
pytest tests/unit/test_database.py -v
```
