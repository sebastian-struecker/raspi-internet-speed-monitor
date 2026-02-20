"""Speedtest component: executes internet speed tests and stores results."""
import logging
import time
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)

from app.database import Database
from app.models import SpeedTestResult

logger = logging.getLogger(__name__)

# Module-level import so tests can patch `app.speedtest_runner._st_module`
try:
    import speedtest as _st_module  # type: ignore[import]
except ImportError:  # pragma: no cover
    _st_module = None  # type: ignore[assignment]


class SpeedtestRunner:
    """Executes speed tests and persists results with retry logic."""

    MAX_RETRIES = 3

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Test execution
    # ------------------------------------------------------------------

    def execute_test(self) -> SpeedTestResult:
        """Run a speed test and return the result (success or failure record)."""
        try:
            if _st_module is None:
                raise ImportError("speedtest-cli is not installed")

            logger.info("Starting speed test…")
            st = _st_module.Speedtest(secure=True)

            logger.info("  → Finding best server…")
            st.get_best_server()
            server_info = st.results.server
            logger.info("  → Using server: %s (%s, %s)",
                       server_info.get('host', 'unknown'),
                       server_info.get('sponsor', 'unknown'),
                       server_info.get('country', 'unknown'))

            logger.info("  → Testing download speed…")
            st.download()

            logger.info("  → Testing upload speed…")
            st.upload()

            results = st.results.dict()

            result = SpeedTestResult(
                timestamp=_utcnow(),
                download_mbps=results["download"] / 1_000_000,
                upload_mbps=results["upload"] / 1_000_000,
                ping_ms=results["ping"],
                test_server=results.get("server", {}).get("host"),
                success=True,
            )
            logger.info(
                "Speed test complete: ↓%.1f Mbps  ↑%.1f Mbps  ping=%.0f ms",
                result.download_mbps,
                result.upload_mbps,
                result.ping_ms,
            )
            return result

        except Exception as exc:
            logger.error("Speed test failed: %s", exc)
            return SpeedTestResult(
                timestamp=_utcnow(),
                download_mbps=0.0,
                upload_mbps=0.0,
                ping_ms=0.0,
                success=False,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # Persistence with retry
    # ------------------------------------------------------------------

    def store_result(self, result: SpeedTestResult, retries: int = MAX_RETRIES) -> bool:
        """Store *result* in the database with exponential-backoff retry."""
        for attempt in range(retries):
            try:
                row_id = self.db.insert_result(result)
                result.id = row_id
                logger.info("Result stored with id=%d", row_id)
                return True
            except Exception as exc:
                is_last = attempt == retries - 1
                if is_last:
                    logger.warning(
                        "Database error (attempt %d/%d): %s",
                        attempt + 1,
                        retries,
                        exc,
                    )
                else:
                    wait = 2 ** attempt  # 1 s, 2 s, …
                    logger.warning(
                        "Database error (attempt %d/%d): %s — retrying in %ds",
                        attempt + 1,
                        retries,
                        exc,
                        wait,
                    )
                    time.sleep(wait)

        logger.error("Failed to store result after %d attempts", retries)
        return False

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def run_and_store(self) -> Optional[SpeedTestResult]:
        """Execute a test and store the result; returns the result or None on store failure."""
        result = self.execute_test()
        stored = self.store_result(result)
        return result if stored else None
