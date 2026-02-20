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
    # Enable APScheduler logging for cleanup job
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


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

    logger.info("=" * 60)
    logger.info("Speedtest Service Starting")
    logger.info("=" * 60)
    logger.info("Configuration:")
    logger.info("  CRON Schedule:    %s", config.schedule.cron)
    logger.info("  Database Path:    %s", config.database.path)
    logger.info("  Retention Days:   %s", config.database.retention_days)
    logger.info("  Log Level:        %s", config.logging.level)
    logger.info("=" * 60)

    errors = config.validate()
    for err in errors:
        logger.error("Config validation error: %s", err)

    db = Database(config.database.path)
    runner = SpeedtestRunner(db)

    cleanup_scheduler = run_cleanup(db, config)

    # Wrap the runner to add job-level logging
    def run_speedtest_job():
        logger.info("⏱️  Speedtest job triggered")
        try:
            result = runner.run_and_store()
            if result:
                if result.success:
                    logger.info("✓ Speedtest job completed successfully")
                else:
                    logger.warning("⚠️  Speedtest job completed with failure: %s", result.error_message)
            else:
                logger.error("✗ Speedtest job failed to store result")
        except Exception as exc:
            logger.exception("✗ Speedtest job crashed: %s", exc)

    scheduler = Scheduler(cron=config.schedule.cron, on_trigger=run_speedtest_job)
    try:
        scheduler.run()
    finally:
        cleanup_scheduler.shutdown()


if __name__ == "__main__":
    main()
