"""Google Sheets Exporter: polls the database and appends results to a Google Sheet."""
import logging
import time
from collections import deque
from typing import Deque, List, Optional

from app.database import Database
from app.models import SpeedTestResult

logger = logging.getLogger(__name__)

RETRY_INTERVAL = 300  # 5 minutes


class GoogleSheetsExporter:
    """Exports speed test results to a Google Sheets spreadsheet.

    On API failure the result is queued and retried every RETRY_INTERVAL seconds.
    Data is only appended — never deleted (Requirement 10.5).
    """

    def __init__(
        self,
        credentials_json: str,
        spreadsheet_id: str,
        db: Database,
    ) -> None:
        self.credentials_json = credentials_json
        self.spreadsheet_id = spreadsheet_id
        self.db = db
        self._retry_queue: Deque[SpeedTestResult] = deque()
        self._client = None
        self._worksheet = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Authenticate with the Google Sheets API via service account JSON."""
        try:
            import gspread
            import json
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            info = json.loads(self.credentials_json)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
            self._client = gspread.Client(auth=creds)
            sheet = self._client.open_by_key(self.spreadsheet_id)
            self._worksheet = sheet.sheet1

            # Ensure header row exists
            if self._worksheet.row_count == 0 or not self._worksheet.row_values(1):
                self._worksheet.append_row(
                    ["Timestamp", "Download (Mbps)", "Upload (Mbps)", "Ping (ms)"]
                )

            logger.info("Authenticated with Google Sheets API")
            return True
        except Exception as exc:
            logger.error("Google Sheets authentication failed: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_result(self, result: SpeedTestResult) -> bool:
        """Append *result* to the spreadsheet; queue for retry on failure."""
        try:
            if self._worksheet is None:
                raise RuntimeError("Not authenticated — call authenticate() first")

            row = [
                result.timestamp.isoformat(sep=" "),
                round(result.download_mbps, 2),
                round(result.upload_mbps, 2),
                round(result.ping_ms, 1),
            ]
            self._worksheet.append_row(row)
            logger.info("Exported result to Google Sheets (timestamp=%s)", result.timestamp)
            return True
        except Exception as exc:
            logger.error("Export failed for result %s: %s — queuing for retry", result.timestamp, exc)
            self._retry_queue.append(result)
            return False

    def retry_failed_exports(self) -> int:
        """Process the retry queue; return the number of successfully exported results."""
        exported = 0
        pending = list(self._retry_queue)
        self._retry_queue.clear()

        for result in pending:
            try:
                if self._worksheet is None:
                    raise RuntimeError("Not authenticated")
                row = [
                    result.timestamp.isoformat(sep=" "),
                    round(result.download_mbps, 2),
                    round(result.upload_mbps, 2),
                    round(result.ping_ms, 1),
                ]
                self._worksheet.append_row(row)
                logger.info("Retry successful for result %s", result.timestamp)
                exported += 1
            except Exception as exc:
                logger.warning("Retry failed for result %s: %s", result.timestamp, exc)
                self._retry_queue.append(result)

        return exported

    # ------------------------------------------------------------------
    # Database polling
    # ------------------------------------------------------------------

    def poll_database(self, last_id: int) -> List[SpeedTestResult]:
        """Return all results with id > *last_id*."""
        return self.db.get_results_after(last_id)

    @property
    def retry_queue_size(self) -> int:
        return len(self._retry_queue)
