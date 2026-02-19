"""Entry point for the dashboard service."""
import logging
import sys

from app.models import Config
from app.database import Database
from app.dashboard import create_app


def setup_logging(level: str) -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )


def main() -> None:
    config = Config.from_env()

    setup_logging(config.logging.level)

    db = Database(config.database.path)
    app = create_app(db)
    app.run(host="0.0.0.0", port=config.dashboard.port)


if __name__ == "__main__":
    main()
