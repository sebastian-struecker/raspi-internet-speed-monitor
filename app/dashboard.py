"""Flask dashboard: REST API + static frontend for speed test visualisation."""
import logging
import os
from datetime import datetime
from typing import Any, Dict

from flask import Flask, abort, jsonify, request, send_from_directory

from app.database import Database
from app.models import Statistics

logger = logging.getLogger(__name__)


def create_app(db: Database) -> Flask:
    """Create and configure the Flask application.

    Args:
        db: Database instance
    """
    static_folder = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="/static")
    app.config["DB"] = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _db() -> Database:
        return app.config["DB"]

    def _parse_dt(value: str, param_name: str) -> datetime:
        try:
            # Replace 'Z' suffix with '+00:00' for compatibility with Python 3.9
            if value.endswith('Z'):
                value = value[:-1] + '+00:00'
            dt = datetime.fromisoformat(value)
            # Convert to naive datetime (remove timezone info)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            return dt
        except (ValueError, TypeError):
            abort(400, description=f"Invalid ISO datetime for '{param_name}': {value!r}")

    # ------------------------------------------------------------------
    # API endpoints
    # ------------------------------------------------------------------

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

        successful = [r for r in results if r.success]
        if not successful:
            return jsonify(None), 200

        downloads = [r.download_mbps for r in successful]
        uploads = [r.upload_mbps for r in successful]
        pings = [r.ping_ms for r in successful]
        failed = len(results) - len(successful)

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
            total_tests=len(results),  # all tests including failures
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
        """Serve the frontend."""
        return send_from_directory(static_folder, "index.html")

    return app
