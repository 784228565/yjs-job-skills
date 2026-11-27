"""Initialize and append to delivery_log.csv in the status directory."""

import csv
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

LOG_DIR = config.STATUS_DIR
LOG_FILE = config.DELIVERY_LOG_CSV

HEADERS = [
    "timestamp", "seq_no", "company", "job_title", "url",
    "result", "method", "confirmation", "issues", "notes"
]


def _now_iso():
    """Local-time ISO8601 timestamp with timezone (consistent with submitted_at)."""
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def init_log():
    """Create delivery_log.csv (with header) if it does not exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(HEADERS)
        return True
    return False


def append_row(seq_no, company, job_title, url, result, method,
               confirmation="", issues="", notes=""):
    """Append a delivery record to the CSV.

    Args:
        seq_no: Queue sequence number
        company: Company name
        job_title: Job title
        url: Job posting URL
        result: Final status ONLY -> Submitted | Skipped | Blocked | NeedsUser.
                Intermediate scan states (HasApplyButton, Clicked,
                NeedsInvestigation, ...) belong in `notes`, never in `result`.
        method: Direct | Alternate | None
        confirmation: Confirmation evidence (submission success message, etc.)
        issues: Brief description of any issues encountered
        notes: Additional notes (including intermediate scan states)
    """
    init_log()
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow([
            _now_iso(),
            seq_no, company, job_title, url,
            result, method, confirmation, issues, notes
        ])


if __name__ == "__main__":
    print(("Created: " if init_log() else "Already exists: ") + str(LOG_FILE))
