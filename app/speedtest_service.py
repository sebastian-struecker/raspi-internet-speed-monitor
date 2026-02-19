"""Entry point for the combined speedtest + scheduler service."""
import logging
import os
import sys

from app.models import Config
from app.database import Database
from app.speedtest_runner import SpeedtestRunner
from app.scheduler import Scheduler


def setup_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def run_cleanup(db: Database, config: Config) -> None:
    """Run daily cleanup via APScheduler."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    sched = BackgroundScheduler()
    sched.add_job(
        lambda: db.cleanup_old_data(config.database.retention_days),
        CronTrigger(hour=0, minute=0),
        id="cleanup",
    )
    sched.start()
    return sched


def main() -> None:
    config = Config.from_env()

    setup_logging(config.logging.level)
    logger = logging.getLogger(__name__)

    errors = config.validate()
    for err in errors:
        logger.error("Config validation error: %s", err)

    db = Database(config.database.path)
    runner = SpeedtestRunner(db)

    cleanup_scheduler = run_cleanup(db, config)

    scheduler = Scheduler(cron=config.schedule.cron, on_trigger=runner.run_and_store)
    try:
        scheduler.run()
    finally:
        cleanup_scheduler.shutdown()


if __name__ == "__main__":
    main()
