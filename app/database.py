"""SQLite database component for storing speed test results."""
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.models import SpeedTestResult

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS speed_tests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     DATETIME NOT NULL,
    download_mbps REAL NOT NULL,
    upload_mbps   REAL NOT NULL,
    ping_ms       REAL NOT NULL,
    test_server   TEXT,
    success       INTEGER NOT NULL DEFAULT 1,
    error_message TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_timestamp ON speed_tests(timestamp);
"""


def _utcnow() -> datetime:
    """Return the current UTC time as a naive datetime."""
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


class Database:
    """Wrapper around a SQLite database for speed test results.

    For `:memory:` databases a single persistent connection is kept so that
    the schema and data survive across method calls.  For file-based
    databases, a new connection is opened per operation and closed
    immediately after to avoid file-descriptor leaks.
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        # Keep a persistent connection for in-memory databases
        self._persistent_conn: Optional[sqlite3.Connection] = None
        if db_path == ":memory:":
            self._persistent_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._persistent_conn.row_factory = sqlite3.Row
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, sql: str, params: tuple = (), *, write: bool = False):
        """Execute *sql* and return (rows, lastrowid, rowcount).

        For persistent connections the connection is reused; for file-based
        connections the connection is explicitly closed after use.
        """
        conn = self._connect()
        is_temp = self._persistent_conn is None
        try:
            if write:
                with conn:  # transaction: commits on success, rolls back on exception
                    cursor = conn.execute(sql, params)
                    return cursor.fetchall(), cursor.lastrowid, cursor.rowcount
            else:
                cursor = conn.execute(sql, params)
                return cursor.fetchall(), None, None
        finally:
            if is_temp:
                conn.close()

    def _init_schema(self) -> None:
        conn = self._connect()
        is_temp = self._persistent_conn is None
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            if is_temp:
                conn.close()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def insert_result(self, result: SpeedTestResult) -> int:
        """Insert a SpeedTestResult and return the new row ID."""
        sql = """
            INSERT INTO speed_tests
                (timestamp, download_mbps, upload_mbps, ping_ms, test_server, success, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        _, row_id, _ = self._execute(
            sql,
            (
                result.timestamp.isoformat(),
                result.download_mbps,
                result.upload_mbps,
                result.ping_ms,
                result.test_server,
                1 if result.success else 0,
                result.error_message,
            ),
            write=True,
        )
        logger.debug("Inserted speed test result with id=%d", row_id)
        return row_id  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query_range(self, start: datetime, end: datetime) -> List[SpeedTestResult]:
        """Return all results whose timestamp is within [start, end]."""
        sql = """
            SELECT id, timestamp, download_mbps, upload_mbps, ping_ms, test_server, success, error_message
            FROM speed_tests
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """
        rows, _, _ = self._execute(sql, (start.isoformat(), end.isoformat()))
        return [self._row_to_result(row) for row in rows]

    def get_latest(self, limit: int = 1) -> List[SpeedTestResult]:
        """Return the most recent *limit* results."""
        sql = """
            SELECT id, timestamp, download_mbps, upload_mbps, ping_ms, test_server, success, error_message
            FROM speed_tests
            ORDER BY timestamp DESC
            LIMIT ?
        """
        rows, _, _ = self._execute(sql, (limit,))
        return [self._row_to_result(row) for row in rows]

    def get_results_after(self, last_id: int) -> List[SpeedTestResult]:
        """Return all results with id > *last_id*, ordered by id ascending."""
        sql = """
            SELECT id, timestamp, download_mbps, upload_mbps, ping_ms, test_server, success, error_message
            FROM speed_tests
            WHERE id > ?
            ORDER BY id ASC
        """
        rows, _, _ = self._execute(sql, (last_id,))
        return [self._row_to_result(row) for row in rows]

    def count(self) -> int:
        """Return total number of rows (useful in tests)."""
        rows, _, _ = self._execute("SELECT COUNT(*) FROM speed_tests")
        return rows[0][0]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def cleanup_old_data(self, retention_days: int) -> int:
        """Delete rows older than *retention_days*. 0 means keep everything."""
        if retention_days <= 0:
            logger.debug("Retention days is %d — skipping cleanup", retention_days)
            return 0

        cutoff = _utcnow() - timedelta(days=retention_days)
        _, _, deleted = self._execute(
            "DELETE FROM speed_tests WHERE timestamp < ?",
            (cutoff.isoformat(),),
            write=True,
        )
        logger.info("Cleanup deleted %d rows older than %s", deleted, cutoff.isoformat())
        return deleted  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_result(row) -> SpeedTestResult:
        return SpeedTestResult(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            download_mbps=row["download_mbps"],
            upload_mbps=row["upload_mbps"],
            ping_ms=row["ping_ms"],
            test_server=row["test_server"],
            success=bool(row["success"]),
            error_message=row["error_message"],
        )
