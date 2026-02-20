from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import yaml


@dataclass
class SpeedTestResult:
    """Represents a single internet speed test result."""

    timestamp: datetime
    download_mbps: float
    upload_mbps: float
    ping_ms: float

    test_server: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None

    # Populated after database insertion
    id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "download_mbps": round(self.download_mbps, 2),
            "upload_mbps": round(self.upload_mbps, 2),
            "ping_ms": round(self.ping_ms, 1),
            "test_server": self.test_server,
            "success": self.success,
            "error_message": self.error_message,
        }

    @classmethod
    def from_db_row(cls, row: tuple) -> "SpeedTestResult":
        return cls(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            download_mbps=row[2],
            upload_mbps=row[3],
            ping_ms=row[4],
            test_server=row[5],
        )


@dataclass
class Statistics:
    """Aggregate statistics for a time period."""

    avg_download_mbps: float
    avg_upload_mbps: float
    avg_ping_ms: float

    min_download_mbps: float
    max_download_mbps: float
    min_upload_mbps: float
    max_upload_mbps: float
    min_ping_ms: float
    max_ping_ms: float

    total_tests: int
    failed_tests: int

    period_start: datetime
    period_end: datetime

    def to_dict(self) -> dict:
        return {
            "averages": {
                "download_mbps": round(self.avg_download_mbps, 2),
                "upload_mbps": round(self.avg_upload_mbps, 2),
                "ping_ms": round(self.avg_ping_ms, 1),
            },
            "download": {
                "min": round(self.min_download_mbps, 2),
                "max": round(self.max_download_mbps, 2),
            },
            "upload": {
                "min": round(self.min_upload_mbps, 2),
                "max": round(self.max_upload_mbps, 2),
            },
            "ping": {
                "min": round(self.min_ping_ms, 1),
                "max": round(self.max_ping_ms, 1),
            },
            "tests": {
                "total": self.total_tests,
                "failed": self.failed_tests,
                "success_rate": (
                    round(
                        (self.total_tests - self.failed_tests)
                        / self.total_tests
                        * 100,
                        1,
                    )
                    if self.total_tests > 0
                    else 0
                ),
            },
            "period": {
                "start": self.period_start.isoformat(),
                "end": self.period_end.isoformat(),
            },
        }


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScheduleConfig:
    cron: str = "0 * * * *"


@dataclass
class DatabaseConfig:
    path: str = "/data/speedtest.db"
    retention_days: int = 90


@dataclass
class DashboardConfig:
    port: int = 8080
    auto_refresh_seconds: int = 60
    url_prefix: str = ""


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class Config:
    """Main configuration model."""

    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def default(cls) -> "Config":
        return cls()

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        import os

        def _bool(val: str) -> bool:
            return val.strip().lower() in ("1", "true", "yes")

        return cls(
            schedule=ScheduleConfig(
                cron=os.environ.get("SPEEDTEST_CRON", "0 * * * *"),
            ),
            database=DatabaseConfig(
                path=os.environ.get("DB_PATH", "/data/speedtest.db"),
                retention_days=int(os.environ.get("DB_RETENTION_DAYS", "90")),
            ),
            dashboard=DashboardConfig(
                port=int(os.environ.get("DASHBOARD_PORT", "8080")),
                auto_refresh_seconds=int(os.environ.get("DASHBOARD_REFRESH_SECONDS", "60")),
                url_prefix=os.environ.get("URL_PREFIX", ""),
            ),
            logging=LoggingConfig(
                level=os.environ.get("LOG_LEVEL", "INFO"),
            ),
        )

    @classmethod
    def load(cls, path: str) -> "Config":
        """Load configuration from YAML file, applying defaults for missing fields."""
        try:
            with open(path, "r") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise

        schedule_data = data.get("schedule", {}) or {}
        database_data = data.get("database", {}) or {}
        dashboard_data = data.get("dashboard", {}) or {}
        logging_data = data.get("logging", {}) or {}

        return cls(
            schedule=ScheduleConfig(**{k: v for k, v in schedule_data.items() if k in ScheduleConfig.__dataclass_fields__}),
            database=DatabaseConfig(**{k: v for k, v in database_data.items() if k in DatabaseConfig.__dataclass_fields__}),
            dashboard=DashboardConfig(**{k: v for k, v in dashboard_data.items() if k in DashboardConfig.__dataclass_fields__}),
            logging=LoggingConfig(**{k: v for k, v in logging_data.items() if k in LoggingConfig.__dataclass_fields__}),
        )

    def validate(self) -> List[str]:
        """Validate configuration, returning a list of error messages."""
        errors: List[str] = []

        if not self._is_valid_cron(self.schedule.cron):
            errors.append(f"Invalid CRON expression: {self.schedule.cron}")

        if self.database.retention_days < 0:
            errors.append("retention_days must be non-negative")

        if not (1 <= self.dashboard.port <= 65535):
            errors.append(f"Invalid port number: {self.dashboard.port}")

        return errors

    @staticmethod
    def _is_valid_cron(expression: str) -> bool:
        """Validate a standard 5-field CRON expression."""
        try:
            from croniter import croniter
            return croniter.is_valid(expression)
        except Exception:
            return False

    def to_dict(self) -> dict:
        """Serialise to a plain dict (YAML-compatible)."""
        return {
            "schedule": {"cron": self.schedule.cron},
            "database": {
                "path": self.database.path,
                "retention_days": self.database.retention_days,
            },
            "dashboard": {
                "port": self.dashboard.port,
                "auto_refresh_seconds": self.dashboard.auto_refresh_seconds,
                "url_prefix": self.dashboard.url_prefix,
            },
            "logging": {"level": self.logging.level},
        }
