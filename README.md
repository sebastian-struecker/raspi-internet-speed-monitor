# Raspi Internet Speed Monitor

A self-hosted internet speed monitor designed to run on a **Raspberry Pi**. It periodically measures download/upload
speeds and ping, stores results in a local SQLite database, and serves a live dashboard in your browser.

## Features

- 📊 **Real-time Dashboard** - Chart.js visualization with historical data
- ⏰ **Scheduled Tests** - Configurable CRON-based speed test execution
- 💾 **SQLite Storage** - Local database with configurable retention
- 🐳 **Docker Compose** - Easy deployment with Docker
- 🔄 **Auto-refresh** - Live updates without manual refresh
- 🌐 **Multi-app Support** - Can run behind nginx reverse proxy with other applications

## Deployment Modes

### Standalone Mode (Default)

Dashboard accessible directly at `http://<raspberry-pi-ip>:8080/`

### Reverse Proxy Mode

Dashboard accessible at `http://<raspberry-pi-ip>:8080/internet-speed-dashboard/` alongside other web applications.

---

## How it works

Two Docker containers run as a stack and communicate through a shared SQLite volume:

| Container         | Role                                                                 |
|-------------------|----------------------------------------------------------------------|
| **speedtest**     | Runs speed tests on a CRON schedule; also handles daily data cleanup |
| **dashboard**     | Flask REST API + Chart.js web UI                                     |
| *(shared volume)* | SQLite database file (`/data/speedtest.db`)                          |

All settings are controlled by environment variables — no config files to mount or edit.

---

## Requirements

- Raspberry Pi (or any ARM/x86 host running Linux)
- Docker ≥ 20.10
- Docker Compose ≥ 1.29
- Internet connection

---

## Installation

### Standalone Deployment

#### 1. Clone the repository

```bash
git clone https://github.com/your-username/raspi-internet-speed-monitor.git
cd raspi-internet-speed-monitor
```

#### 2. Build and start the containers

```bash
docker compose up -d --build
```

The first build takes a few minutes while Python dependencies are installed. Subsequent starts are fast.

Verify containers are running:

```bash
docker compose ps
```

#### 3. Open the dashboard

Navigate to `http://<raspberry-pi-ip>:8080` in your browser. The dashboard auto-refreshes every 60 seconds and displays
a time-series chart of recent results.

### Reverse Proxy Deployment

For multi-application deployment with nginx reverse proxy:

1. **Set up nginx reverse proxy**
2. **Configure this project**:
   ```bash
   # Edit .env
   URL_PREFIX=/internet-speed-dashboard
   ```
3. **Deploy**:
   ```bash
   docker compose up -d --build
   ```
4. **Access**: `http://<raspberry-pi-ip>:8080/internet-speed-dashboard/`

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
| `DASHBOARD_PORT`               | `8080`               | Internal port the Flask app listens on.                                             |
| `DASHBOARD_REFRESH_SECONDS`    | `60`                 | How often the browser auto-refreshes metrics.                                       |
| `URL_PREFIX`                   | _(empty)_            | URL path prefix for reverse proxy (e.g., `/internet-speed-dashboard`). Leave empty for standalone. |
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
│   ├── dashboard.py         # Flask REST API with Blueprint support
│   ├── templates/
│   │   └── index.html       # Chart.js web dashboard (Jinja2 template)
│   ├── static/              # Static assets (currently empty)
│   └── *_service.py         # Container entry points
├── tests/
│   ├── unit/                # pytest unit tests (95 tests)
│   └── property/            # Hypothesis property-based tests
├── .env.example             # Environment variable template
├── .env                     # Your local configuration (not committed)
├── docker-compose.yml       # Service definitions
├── Dockerfile.speedtest
├── Dockerfile.dashboard
├── NGINX_PROXY_SETUP.md     # Guide for setting up reverse proxy
└── internet-speedtest.service  # systemd unit for auto-start
```

---

## Running tests

Install the development dependencies and run the test suite:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# All tests (95 total)
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Property-based tests with Hypothesis statistics
pytest tests/property/ -v --hypothesis-show-statistics

# Single test file
pytest tests/unit/test_database.py -v
```

---

## Architecture

### Standalone Mode

```
Internet → Port 8080 → Dashboard (Flask) → SQLite DB ← Speedtest Runner
```

### Reverse Proxy Mode

```
Internet → Port 8080 → nginx → /internet-speed-dashboard/ → Dashboard (Flask)
                              → /other-app/ → Other Application

All apps communicate via Docker network: webapps_network
```

---

## Development

See [CLAUDE.md](./CLAUDE.md) for development documentation including:
- Architecture details
- Testing strategy
- Configuration management
- Multi-application deployment

---

## License

MIT

---

## Contributing

Contributions welcome! This project was initially "vibe-coded" and can always be improved.

Please:
- Run tests before submitting PRs
- Follow the existing code style
- Update documentation for new features
