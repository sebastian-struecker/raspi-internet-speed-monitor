"""Scheduler component: CRON-based scheduling."""
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_CRON = "0 * * * *"


class Scheduler:
    """Schedules a callable based on a CRON expression."""

    def __init__(self, cron: str, on_trigger: Callable[[], None]) -> None:
        self.on_trigger = on_trigger
        self._cron = self._resolve_cron(cron)
        self._scheduler = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # CRON helpers
    # ------------------------------------------------------------------

    @staticmethod
    def validate_cron(expression: str) -> bool:
        """Return True if *expression* is a valid 5-field CRON string."""
        try:
            from croniter import croniter
            return croniter.is_valid(expression)
        except Exception:
            return False

    def _resolve_cron(self, expression: str) -> str:
        """Return *expression* if valid, otherwise fall back to the default."""
        if self.validate_cron(expression):
            return expression
        logger.error(
            "Invalid CRON expression %r — using default %r",
            expression,
            DEFAULT_CRON,
        )
        return DEFAULT_CRON

    # ------------------------------------------------------------------
    # Simple croniter-based scheduling (runs in main thread)
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the scheduler and block until stopped."""
        from datetime import datetime
        from croniter import croniter

        logger.info("Starting scheduler with CRON %r", self._cron)
        logger.info("Using main-thread execution (no APScheduler threading)")

        cron = croniter(self._cron, datetime.now())
        next_run = cron.get_next(datetime)
        logger.info("Next run scheduled at: %s", next_run)

        try:
            while not self._stop_event.is_set():
                now = datetime.now()

                if now >= next_run:
                    logger.info("Triggering scheduled job at %s", now)
                    try:
                        self.on_trigger()
                    except Exception as e:
                        logger.exception("Job execution failed: %s", e)

                    # Calculate next run time
                    next_run = cron.get_next(datetime)
                    logger.info("Next run scheduled at: %s", next_run)

                # Sleep for a short interval
                time.sleep(1)

        finally:
            self._stop_event.set()

    def stop(self) -> None:
        self._stop_event.set()
