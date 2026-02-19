"""Entry point for the Google Sheets Exporter service."""
import logging
import sys
import time

from app.models import Config
from app.database import Database
from app.exporter import GoogleSheetsExporter, RETRY_INTERVAL


def setup_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


POLL_INTERVAL = 30  # seconds between DB polls


def main() -> None:
    config = Config.from_env()

    setup_logging(config.logging.level)
    logger = logging.getLogger(__name__)

    if not config.google_sheets.enabled:
        logger.info("Google Sheets export is disabled — exiting")
        return

    db = Database(config.database.path)
    exporter = GoogleSheetsExporter(
        credentials_json=config.google_sheets.credentials_json,
        spreadsheet_id=config.google_sheets.spreadsheet_id,
        db=db,
    )

    if not exporter.authenticate():
        logger.error("Failed to authenticate with Google Sheets — will retry on next poll")

    last_id = 0
    last_retry_time = 0.0

    while True:
        # Poll for new results
        try:
            new_results = exporter.poll_database(last_id)
            for result in new_results:
                exporter.export_result(result)
                if result.id is not None and result.id > last_id:
                    last_id = result.id
        except Exception as exc:
            logger.error("Error polling database: %s", exc)

        # Retry failed exports every 5 minutes
        now = time.monotonic()
        if now - last_retry_time >= RETRY_INTERVAL:
            if exporter.retry_queue_size > 0:
                logger.info("Processing %d queued exports…", exporter.retry_queue_size)
                exporter.retry_failed_exports()
            last_retry_time = now

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
