"""Flask dashboard: REST API + static frontend for speed test visualisation."""
import logging
from datetime import datetime
from typing import Any, Dict

from flask import Flask, abort, jsonify, request, send_from_directory

from app.database import Database
from app.models import Statistics

logger = logging.getLogger(__name__)


def create_app(db: Database, static_folder: str = None) -> Flask:
    """Create and configure the Flask application."""
    import os
    if static_folder is None:
        static_folder = os.path.join(os.path.dirname(__file__), "static")

    app = Flask(__name__, static_folder=static_folder)
    app.config["DB"] = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _db() -> Database:
        return app.config["DB"]

    def _parse_dt(value: str, param_name: str) -> datetime:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            abort(400, description=f"Invalid ISO datetime for '{param_name}': {value!r}")

    # ------------------------------------------------------------------
    # API endpoints
    # ------------------------------------------------------------------

    @app.route("/api/current")
    def get_current():
        """Return the most recent speed test result."""
        results = _db().get_latest(limit=1)
        if not results:
            return jsonify(None), 200
        return jsonify(results[0].to_dict())

    @app.route("/api/history")
    def get_history():
        """Return results within a date range.

        Query params:
          start – ISO datetime (required)
          end   – ISO datetime (required)
        """
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        if not start_str or not end_str:
            abort(400, description="'start' and 'end' query parameters are required")

        start = _parse_dt(start_str, "start")
        end = _parse_dt(end_str, "end")

        results = _db().query_range(start, end)
        return jsonify([r.to_dict() for r in results])

    @app.route("/api/stats")
    def get_statistics():
        """Return aggregate statistics (avg/min/max) for a date range.

        Query params:
          start – ISO datetime (required)
          end   – ISO datetime (required)
        """
        start_str = request.args.get("start")
        end_str = request.args.get("end")
        if not start_str or not end_str:
            abort(400, description="'start' and 'end' query parameters are required")

        start = _parse_dt(start_str, "start")
        end = _parse_dt(end_str, "end")

        results = _db().query_range(start, end)
        if not results:
            return jsonify(None), 200

        downloads = [r.download_mbps for r in results]
        uploads = [r.upload_mbps for r in results]
        pings = [r.ping_ms for r in results]
        failed = sum(1 for r in results if not r.success)

        stats = Statistics(
            avg_download_mbps=sum(downloads) / len(downloads),
            avg_upload_mbps=sum(uploads) / len(uploads),
            avg_ping_ms=sum(pings) / len(pings),
            min_download_mbps=min(downloads),
            max_download_mbps=max(downloads),
            min_upload_mbps=min(uploads),
            max_upload_mbps=max(uploads),
            min_ping_ms=min(pings),
            max_ping_ms=max(pings),
            total_tests=len(results),
            failed_tests=failed,
            period_start=start,
            period_end=end,
        )
        return jsonify(stats.to_dict())

    # ------------------------------------------------------------------
    # Frontend
    # ------------------------------------------------------------------

    @app.route("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    return app
