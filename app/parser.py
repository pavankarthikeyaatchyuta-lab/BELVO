"""
Email parser and deterministic subject matching engine for Belvo Attendance Tracker.
"""

from datetime import datetime
from email.utils import parseaddr
from typing import Optional, Tuple
from app.config import WORK_REPORT_SUBJECT_REGEX, DATE_FORMAT
from app.models import EmailMessage, ParsedReport, LogCategory


def extract_clean_email(raw_sender: Optional[str]) -> str:
    """
    Extracts and normalizes an email address from a header value.
    Handles 'Name <user@domain.com>', '<user@domain.com>', 'user@domain.com'.
    Returns trimmed, lowercase email address or empty string.
    """
    if not raw_sender:
        return ""
    _, email_address = parseaddr(raw_sender)
    if not email_address and "@" in raw_sender:
        # Fallback in case parseaddr didn't catch a raw unformatted string
        email_address = raw_sender.strip("<> ")
    return email_address.strip().lower()


def validate_date_string(date_str: str) -> bool:
    """Validates that a string is a valid YYYY-MM-DD calendar date."""
    try:
        datetime.strptime(date_str, DATE_FORMAT)
        return True
    except ValueError:
        return False


def is_late_submission(received_at_iso: Optional[str], work_date_str: str) -> bool:
    """
    Determines if an email was received after the work date.
    For example, work date is 2026-09-17 and email is received on 2026-09-18 01:15 AM.
    """
    if not received_at_iso:
        return False
    try:
        # Handle ISO strings with Z or timezone offset
        clean_iso = received_at_iso.replace("Z", "+00:00")
        recv_dt = datetime.fromisoformat(clean_iso)
        work_dt = datetime.strptime(work_date_str, DATE_FORMAT).date()
        return recv_dt.date() > work_dt
    except Exception:
        return False


def parse_work_report(message: EmailMessage, target_date: str) -> ParsedReport:
    """
    Deterministically evaluates an email message against work report rules.
    - Normalizes sender
    - Checks for missing subject
    - Evaluates subject with regex
    - Validates embedded work date
    - Flags late reports without rejecting valid work date
    """
    normalized_sender = extract_clean_email(message.sender)
    subject = (message.subject or "").strip()

    # Case 1: Missing subject
    if not subject:
        return ParsedReport(
            raw_message=message,
            is_valid=False,
            normalized_sender_email=normalized_sender,
            extracted_date=None,
            category=LogCategory.MISSING_SUBJECT,
            notes="Email subject is empty or missing."
        )

    # Case 2: Subject regex matching
    match = WORK_REPORT_SUBJECT_REGEX.match(subject)
    if not match:
        return ParsedReport(
            raw_message=message,
            is_valid=False,
            normalized_sender_email=normalized_sender,
            extracted_date=None,
            category=LogCategory.MALFORMED_SUBJECT,
            notes=f"Subject '{subject}' does not match pattern 'Daily Work Report - YYYY-MM-DD'."
        )

    extracted_date = match.group(1)
    if not validate_date_string(extracted_date):
        return ParsedReport(
            raw_message=message,
            is_valid=False,
            normalized_sender_email=normalized_sender,
            extracted_date=extracted_date,
            category=LogCategory.MALFORMED_SUBJECT,
            notes=f"Extracted date '{extracted_date}' is not a valid calendar date."
        )

    # Check if this matches the target attendance date
    is_late = is_late_submission(message.received_at, extracted_date)
    category = LogCategory.LATE_REPORT if is_late else LogCategory.VALID_REPORT
    notes = "Late report submitted after work date." if is_late else "Valid work report."

    return ParsedReport(
        raw_message=message,
        is_valid=True,
        normalized_sender_email=normalized_sender,
        extracted_date=extracted_date,
        category=category,
        notes=notes
    )
