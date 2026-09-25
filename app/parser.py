"""
Email parser and deterministic subject matching engine for Belvo Attendance Tracker.
"""

from datetime import datetime
from email.utils import parseaddr
import re
from typing import Optional, Tuple
from app.config import WORK_REPORT_SUBJECT_REGEX, DATE_FORMAT
from app.models import EmailMessage, ParsedReport, LogCategory


def extract_clean_email(raw_sender: Optional[str]) -> str:
    """
    Extracts and normalizes an email address from a header value.
    Handles 'Name <user@domain.com>', '<user@domain.com>', 'user@domain.com'.
    Returns trimmed, lowercase email address or empty string.
    """
    _, email = extract_sender_name_and_email(raw_sender)
    return email


def extract_sender_name_and_email(raw_sender: Optional[str]) -> Tuple[str, str]:
    """
    Extracts display name and normalized email address from a header value.
    If name is missing, formats the email username into a human-friendly display name.
    """
    if not raw_sender:
        return ("", "")
    name, email_address = parseaddr(raw_sender)
    if not email_address and "@" in raw_sender:
        email_address = raw_sender.strip("<> ")
    clean_email = email_address.strip().lower()
    clean_name = name.strip()
    if not clean_name and clean_email:
        username = clean_email.split("@")[0]
        clean_name = username.replace(".", " ").replace("_", " ").title()
    return (clean_name, clean_email)


def normalize_and_validate_date(date_str: str) -> Optional[str]:
    """
    Validates and normalizes date strings into standard YYYY-MM-DD.
    Supports YYYY-MM-DD, YYYY/MM/DD, DD-MM-YYYY, DD/MM/YYYY.
    Returns normalized YYYY-MM-DD or None if invalid.
    """
    if not date_str:
        return None
    cleaned = date_str.strip().replace("/", "-")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.strftime(DATE_FORMAT)
        except ValueError:
            continue
    return None


def validate_date_string(date_str: str) -> bool:
    """Validates that a string is a valid YYYY-MM-DD calendar date."""
    if not date_str:
        return False
    try:
        datetime.strptime(date_str, DATE_FORMAT)
        return True
    except (ValueError, TypeError):
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


# Additional regexes for flexible / live work report parsing
FUZZY_WORK_REPORT_KEYWORD_REGEX = re.compile(
    r"\b(?:daily\s+)?work\s+(?:report|submission|update|status|task|summary|done|completed)\b|"
    r"\b(?:daily|today|my|today's)\s+(?:daily\s+)?(?:work\s+)?(?:report|task|tasks|update|submission|status|summary)\b|"
    r"\b(?:task|tasks|work)\s+(?:was\s+|is\s+|are\s+)?(?:completed|done|finished|submitted)\b|"
    r"\bwork\s+report\b|\bdaily\s+report\b|\bwork\s+submission\b|\bstatus\s+report\b|\bprogress\s+report\b|"
    r"\bdaily\s+update\b|\bwork\s+update\b|\bstatus\s+update\b|\btask\s+update\b",
    re.IGNORECASE,
)
ABSENT_SUBJECT_REGEX = re.compile(
    r"\babsent\b|\bmarking\s+absent\b|\babsent\s+today\b|\babsence\b|\bnot\s+attending\b",
    re.IGNORECASE,
)
LEAVE_SUBJECT_REGEX = re.compile(
    r"\b(?:on\s+|taking\s+|applying\s+for\s+)?leave\b|"
    r"\bleave\s+(?:application|request|notice|for\s+today|today|day)\b|"
    r"\b(?:sick|casual|emergency|annual|planned)\s+leave\b|"
    r"\b(?:day\s+off|out\s+of\s+office|\booo\b)\b|"
    r"\b(?:unable\s+to|cannot|can't)\s+attend\b|"
    r"\bpermission(?:\s+for\s+today)?\b|"
    r"\bnot\s+(?:available|coming|well)\b",
    re.IGNORECASE,
)
DATE_IN_TEXT_REGEX = re.compile(
    r"\b(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}[-/]\d{2}[-/]\d{4})\b"
)


def parse_work_report(
    message: EmailMessage,
    target_date: str,
    allow_fuzzy: bool = False,
) -> ParsedReport:
    """
    Deterministically evaluates an email message against work report rules.
    - Normalizes sender
    - Checks for missing subject
    - Evaluates subject with regex
    - Validates embedded work date
    - Flags late reports without rejecting valid work date
    - In allow_fuzzy mode, tolerates natural subject variations, recognizes leave notices, and infers date
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
    if match:
        extracted_date = match.group(1)
        if validate_date_string(extracted_date):
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
        else:
            return ParsedReport(
                raw_message=message,
                is_valid=False,
                normalized_sender_email=normalized_sender,
                extracted_date=extracted_date,
                category=LogCategory.MALFORMED_SUBJECT,
                notes=f"Extracted date '{extracted_date}' is not a valid calendar date."
            )

    # Case 3: Explicit Absent notice parsing (used in live Gmail mode)
    if allow_fuzzy and ABSENT_SUBJECT_REGEX.search(subject):
        extracted_date = None
        date_match = DATE_IN_TEXT_REGEX.search(subject)
        if date_match:
            extracted_date = normalize_and_validate_date(date_match.group(1))

        if not extracted_date and message.received_at:
            try:
                clean_iso = message.received_at.replace("Z", "+00:00")
                recv_dt = datetime.fromisoformat(clean_iso)
                try:
                    target_dt = datetime.strptime(target_date, DATE_FORMAT)
                    if abs((recv_dt.date() - target_dt.date()).days) <= 1:
                        extracted_date = target_date
                    else:
                        extracted_date = recv_dt.strftime(DATE_FORMAT)
                except Exception:
                    extracted_date = recv_dt.strftime(DATE_FORMAT)
            except Exception:
                extracted_date = None

        if not extracted_date:
            extracted_date = target_date

        if validate_date_string(extracted_date):
            return ParsedReport(
                raw_message=message,
                is_valid=True,
                normalized_sender_email=normalized_sender,
                extracted_date=extracted_date,
                category=LogCategory.VALID_REPORT,
                notes=f"Absent notice received via email for {extracted_date}.",
                is_absent=True,
            )

    # Case 4: Leave notice parsing (used in live Gmail mode)
    if allow_fuzzy and LEAVE_SUBJECT_REGEX.search(subject):
        extracted_date = None
        date_match = DATE_IN_TEXT_REGEX.search(subject)
        if date_match:
            extracted_date = normalize_and_validate_date(date_match.group(1))

        if not extracted_date and message.received_at:
            try:
                clean_iso = message.received_at.replace("Z", "+00:00")
                recv_dt = datetime.fromisoformat(clean_iso)
                try:
                    target_dt = datetime.strptime(target_date, DATE_FORMAT)
                    if abs((recv_dt.date() - target_dt.date()).days) <= 1:
                        extracted_date = target_date
                    else:
                        extracted_date = recv_dt.strftime(DATE_FORMAT)
                except Exception:
                    extracted_date = recv_dt.strftime(DATE_FORMAT)
            except Exception:
                extracted_date = None

        if not extracted_date:
            extracted_date = target_date

        if validate_date_string(extracted_date):
            return ParsedReport(
                raw_message=message,
                is_valid=True,
                normalized_sender_email=normalized_sender,
                extracted_date=extracted_date,
                category=LogCategory.VALID_REPORT,
                notes=f"Leave notice received via email for {extracted_date}.",
                is_leave=True,
            )

    # Case 4: Flexible work report parsing (used in live Gmail mode)
    if allow_fuzzy and FUZZY_WORK_REPORT_KEYWORD_REGEX.search(subject):
        extracted_date = None
        date_match = DATE_IN_TEXT_REGEX.search(subject)
        if date_match:
            extracted_date = normalize_and_validate_date(date_match.group(1))

        # If no date in subject, infer from message.received_at or target_date
        if not extracted_date and message.received_at:
            try:
                clean_iso = message.received_at.replace("Z", "+00:00")
                recv_dt = datetime.fromisoformat(clean_iso)
                try:
                    target_dt = datetime.strptime(target_date, DATE_FORMAT)
                    if abs((recv_dt.date() - target_dt.date()).days) <= 1:
                        extracted_date = target_date
                    else:
                        extracted_date = recv_dt.strftime(DATE_FORMAT)
                except Exception:
                    extracted_date = recv_dt.strftime(DATE_FORMAT)
            except Exception:
                extracted_date = None

        if not extracted_date:
            extracted_date = target_date

        if validate_date_string(extracted_date):
            is_late = is_late_submission(message.received_at, extracted_date)
            category = LogCategory.LATE_REPORT if is_late else LogCategory.VALID_REPORT
            notes = f"Accepted work report (date: {extracted_date})."
            return ParsedReport(
                raw_message=message,
                is_valid=True,
                normalized_sender_email=normalized_sender,
                extracted_date=extracted_date,
                category=category,
                notes=notes
            )

    return ParsedReport(
        raw_message=message,
        is_valid=False,
        normalized_sender_email=normalized_sender,
        extracted_date=None,
        category=LogCategory.MALFORMED_SUBJECT,
        notes=f"Subject '{subject}' does not match pattern 'Daily Work Report - YYYY-MM-DD'."
    )
