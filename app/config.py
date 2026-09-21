"""
Configuration settings and constants for Belvo Attendance Tracker.
"""

from pathlib import Path
import re

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR = BASE_DIR / "sample_data"
OUTPUT_DIR = BASE_DIR / "output"

# Default data file paths
DEFAULT_EMPLOYEES_PATH = SAMPLE_DATA_DIR / "employees.csv"
DEFAULT_LEAVE_PATH = SAMPLE_DATA_DIR / "leave.csv"
DEFAULT_MOCK_EMAILS_PATH = SAMPLE_DATA_DIR / "mock_emails.json"
DEFAULT_OUTPUT_PATH = OUTPUT_DIR / "attendance.xlsx"

# Google OAuth & Gmail API settings
def get_credentials_path() -> Path:
    candidates = [
        BASE_DIR / "credentials" / "credentials.json",
        BASE_DIR / "credentials.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]

GMAIL_CREDENTIALS_PATH = get_credentials_path()
GMAIL_TOKEN_PATH = BASE_DIR / "token.json"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Matching rules
DATE_FORMAT = "%Y-%m-%d"

# Regex for Daily Work Report subject:
# Accepts e.g.:
# - "Daily Work Report - 2026-09-17"
# - "daily work report - 2026-09-17"
# - "Daily Work Report: 2026-09-17"
# - "  Daily Work Report - 2026-09-17  "
WORK_REPORT_SUBJECT_REGEX = re.compile(
    r"^\s*daily\s+work\s+report\s*[-:]\s*(\d{4}-\d{2}-\d{2})\s*$",
    re.IGNORECASE
)
