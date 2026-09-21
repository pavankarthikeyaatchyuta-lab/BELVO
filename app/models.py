"""
Data models and enumerations for Belvo Attendance Tracker.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AttendanceStatus(str, Enum):
    PRESENT = "P"
    ABSENT = "A"
    LEAVE = "L"


class LogCategory(str, Enum):
    VALID_REPORT = "VALID_REPORT"
    DUPLICATE_REPORT = "DUPLICATE_REPORT"
    LATE_REPORT = "LATE_REPORT"
    MALFORMED_SUBJECT = "MALFORMED_SUBJECT"
    MISSING_SUBJECT = "MISSING_SUBJECT"
    UNKNOWN_SENDER = "UNKNOWN_SENDER"


@dataclass
class Employee:
    name: str
    email: str

    @property
    def normalized_email(self) -> str:
        return self.email.strip().lower()


@dataclass
class LeaveEntry:
    email: str
    date: str

    @property
    def normalized_email(self) -> str:
        return self.email.strip().lower()


@dataclass
class EmailMessage:
    id: str
    sender: str
    subject: str
    received_at: Optional[str] = None
    snippet: Optional[str] = None


@dataclass
class ParsedReport:
    raw_message: EmailMessage
    is_valid: bool
    normalized_sender_email: str
    extracted_date: Optional[str] = None
    category: LogCategory = LogCategory.VALID_REPORT
    notes: str = ""


@dataclass
class AttendanceRecord:
    date: str
    person: str
    email: str
    status: AttendanceStatus
    notes: str = ""


@dataclass
class ProcessingLogEntry:
    timestamp: str
    category: LogCategory
    sender: str
    subject: str
    target_date: str
    action: str
    details: str
