"""Flask dashboard: REST API + static frontend for speed test visualisation."""
import logging
import os
from datetime import datetime
from typing import Any, Dict

from flask import Blueprint, Flask, abort, jsonify, render_template, request

from app.database import Database
from app.models import Statistics

logger = logging.getLogger(__name__)


def create_app(db: Database, url_prefix: str = "") -> Flask:
    """Create and configure the Flask application.

    Args:
        db: Database instance
        url_prefix: URL prefix for reverse proxy routing (e.g., '/internet-speed-dashboard')
    """
    # Configure Flask with template folder
    template_folder = os.path.join(os.path.dirname(__file__), "templates")
    app = Flask(__name__, template_folder=template_folder)
    app.config["DB"] = db

    # Set APPLICATION_ROOT for proper url_for() generation behind reverse proxy
    if url_prefix:
        app.config["APPLICATION_ROOT"] = url_prefix

    # Create Blueprint with url_prefix
    bp = Blueprint("dashboard", __name__, url_prefix=url_prefix)

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

    @bp.route("/api/history")
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

    @bp.route("/api/stats")
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

    @bp.route("/")
    def index():
        """Serve the frontend."""
        return render_template("index.html", url_prefix=url_prefix)

    # Register Blueprint
    app.register_blueprint(bp)

    return app
