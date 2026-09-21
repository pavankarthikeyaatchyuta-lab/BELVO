"""
Attendance engine for Belvo Attendance Tracker.
Applies deterministic P / A / L logic, leave precedence, deduplication,
and generates comprehensive audit processing logs.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.models import (
    AttendanceRecord,
    AttendanceStatus,
    EmailMessage,
    Employee,
    LeaveEntry,
    LogCategory,
    ParsedReport,
    ProcessingLogEntry,
)
from app.parser import parse_work_report

logger = logging.getLogger(__name__)


def load_employees_from_csv(csv_path: Path) -> List[Employee]:
    """Reads expected employees from CSV file (columns: name, email)."""
    employees: List[Employee] = []
    if not Path(csv_path).exists():
        logger.warning(f"Employees CSV not found at {csv_path}")
        return employees

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            email = (row.get("email") or "").strip()
            if name and email:
                employees.append(Employee(name=name, email=email))
    return employees


def load_leave_from_csv(csv_path: Path) -> List[LeaveEntry]:
    """Reads scheduled leave entries from CSV file (columns: email, date)."""
    leave_entries: List[LeaveEntry] = []
    if not Path(csv_path).exists():
        logger.warning(f"Leave CSV not found at {csv_path}")
        return leave_entries

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            email = (row.get("email") or "").strip()
            date = (row.get("date") or "").strip()
            if email and date:
                leave_entries.append(LeaveEntry(email=email, date=date))
    return leave_entries


class AttendanceEngine:
    """Core deterministic attendance computation engine."""

    def __init__(self, employees: List[Employee], leave_entries: List[LeaveEntry]):
        self.employees = employees
        self.leave_entries = leave_entries

        # Indexed lookups for O(1) matching
        self.employee_by_email: Dict[str, Employee] = {
            emp.normalized_email: emp for emp in employees
        }
        self.leave_set: Set[Tuple[str, str]] = {
            (entry.normalized_email, entry.date) for entry in leave_entries
        }

    def process_attendance(
        self,
        raw_messages: List[EmailMessage],
        target_date: str,
    ) -> Tuple[List[AttendanceRecord], List[ProcessingLogEntry], Dict[str, int]]:
        """
        Processes work report messages against expected employees and leave records.
        Returns:
            - attendance_records: exactly one row per expected employee
            - processing_logs: audit log of all decisions and edge cases
            - summary_stats: count metrics for reporting
        """
        processing_logs: List[ProcessingLogEntry] = []

        # Tracking employee valid submissions for the target date
        valid_reports_by_employee: Dict[str, List[ParsedReport]] = {}

        stats = {
            "total_emails": len(raw_messages),
            "valid_reports": 0,
            "duplicate_reports": 0,
            "late_reports": 0,
            "malformed_subjects": 0,
            "missing_subjects": 0,
            "unknown_senders": 0,
            "date_mismatches": 0,
        }

        # Step 1: Parse and classify each received email
        for msg in raw_messages:
            parsed = parse_work_report(msg, target_date)
            timestamp = msg.received_at or datetime.now().isoformat()

            if parsed.category == LogCategory.MISSING_SUBJECT:
                stats["missing_subjects"] += 1
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.MISSING_SUBJECT,
                        sender=msg.sender,
                        subject=msg.subject or "(empty)",
                        target_date=target_date,
                        action="Ignored",
                        details="Email subject is missing or empty. Cannot determine work report.",
                    )
                )
                continue

            if parsed.category == LogCategory.MALFORMED_SUBJECT:
                stats["malformed_subjects"] += 1
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.MALFORMED_SUBJECT,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action="Ignored",
                        details=parsed.notes,
                    )
                )
                continue

            # Subject is valid and extracted_date is present
            # Verify if sender is an expected employee
            normalized_sender = parsed.normalized_sender_email
            if normalized_sender not in self.employee_by_email:
                stats["unknown_senders"] += 1
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.UNKNOWN_SENDER,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action="Ignored",
                        details=f"Sender '{normalized_sender}' is not in the expected employee list. Ignored for attendance.",
                    )
                )
                continue

            # Verify if extracted report date matches the target attendance date
            if parsed.extracted_date != target_date:
                stats["date_mismatches"] += 1
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.VALID_REPORT,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action="Ignored Date Mismatch",
                        details=f"Report specifies work date '{parsed.extracted_date}', which does not match target date '{target_date}'.",
                    )
                )
                continue

            # Handle duplicate submissions from the same employee
            if normalized_sender in valid_reports_by_employee:
                stats["duplicate_reports"] += 1
                valid_reports_by_employee[normalized_sender].append(parsed)
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.DUPLICATE_REPORT,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action="Deduplicated",
                        details=f"Multiple reports received from '{normalized_sender}' for {target_date}. Attendance row remains unique.",
                    )
                )
                continue

            # First valid submission for this employee
            valid_reports_by_employee[normalized_sender] = [parsed]

            if parsed.category == LogCategory.LATE_REPORT:
                stats["late_reports"] += 1
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.LATE_REPORT,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action="Accepted (Late)",
                        details=f"Email received after work date ({msg.received_at}), but explicitly marked for {target_date}. Present status established.",
                    )
                )
            else:
                stats["valid_reports"] += 1
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.VALID_REPORT,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action="Accepted",
                        details=f"Valid on-time work report received for {target_date}.",
                    )
                )

        # Step 2: Determine P / A / L status for every expected employee
        attendance_records: List[AttendanceRecord] = []
        status_counts = {"P": 0, "A": 0, "L": 0}

        for emp in self.employees:
            emp_email = emp.normalized_email
            is_on_leave = (emp_email, target_date) in self.leave_set
            has_report = emp_email in valid_reports_by_employee

            # Leave precedence rule:
            # IF person is in leave list for selected date: L
            # ELSE IF valid report exists: P
            # ELSE: A
            if is_on_leave:
                status = AttendanceStatus.LEAVE
                note = "On leave as recorded in leave registry."
                if has_report:
                    note += " (Work report also received, overridden by leave precedence)."
            elif has_report:
                status = AttendanceStatus.PRESENT
                report_count = len(valid_reports_by_employee[emp_email])
                note = f"Present (1 valid report)" if report_count == 1 else f"Present ({report_count} reports received, deduplicated)"
            else:
                status = AttendanceStatus.ABSENT
                note = "Absent (no valid work report received for date)."

            status_counts[status.value] += 1
            attendance_records.append(
                AttendanceRecord(
                    date=target_date,
                    person=emp.name,
                    email=emp.email,
                    status=status,
                    notes=note,
                )
            )

        summary_stats = {
            "total_employees": len(self.employees),
            "present_count": status_counts["P"],
            "absent_count": status_counts["A"],
            "leave_count": status_counts["L"],
            **stats,
        }

        return attendance_records, processing_logs, summary_stats
