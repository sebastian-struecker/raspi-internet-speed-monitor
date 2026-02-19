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
    # APScheduler integration
    # ------------------------------------------------------------------

    def _build_scheduler(self, cron: str):
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        sched = BackgroundScheduler()
        minute, hour, day, month, day_of_week = cron.split()
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
        sched.add_job(self.on_trigger, trigger, id="speedtest")
        return sched

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Start the scheduler and block until stopped."""
        logger.info("Starting scheduler with CRON %r", self._cron)
        self._scheduler = self._build_scheduler(self._cron)
        self._scheduler.start()

        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        finally:
            self._stop_event.set()
            if self._scheduler and self._scheduler.running:
                self._scheduler.shutdown()

    def stop(self) -> None:
        self._stop_event.set()
