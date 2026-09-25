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
from app.parser import extract_sender_name_and_email, parse_work_report

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

    def __init__(
        self,
        employees: List[Employee],
        leave_entries: List[LeaveEntry],
        auto_discover: bool = False,
        only_present_and_leave: bool = False,
        allow_fuzzy: bool = False,
    ):
        self.employees = list(employees)
        self.leave_entries = list(leave_entries)
        self.auto_discover = auto_discover
        self.only_present_and_leave = only_present_and_leave
        self.allow_fuzzy = allow_fuzzy

        # Indexed lookups for O(1) matching
        self.employee_by_email: Dict[str, Employee] = {
            emp.normalized_email: emp for emp in self.employees
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
            - attendance_records: exactly one row per evaluated employee
            - processing_logs: audit log of all decisions and edge cases
            - summary_stats: count metrics for reporting
        """
        processing_logs: List[ProcessingLogEntry] = []

        # Tracking employee valid submissions (work reports & leave notices) for target_date
        valid_submissions_by_employee: Dict[str, List[ParsedReport]] = {}

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

        # Step 0: Ensure any person recorded on leave for target_date is in employee roster
        for entry in self.leave_entries:
            if entry.date == target_date and entry.normalized_email not in self.employee_by_email:
                disp_name, _ = extract_sender_name_and_email(entry.email)
                leave_emp = Employee(name=disp_name or entry.email, email=entry.email)
                self.employees.append(leave_emp)
                self.employee_by_email[entry.normalized_email] = leave_emp

        # Step 1: Parse and classify each received email
        for msg in raw_messages:
            parsed = parse_work_report(msg, target_date, allow_fuzzy=self.allow_fuzzy)
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

            # Verify if extracted report date matches the target attendance date FIRST
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

            # Subject is valid and matches target_date
            # Check if sender is an expected employee (or auto-discover if enabled)
            normalized_sender = parsed.normalized_sender_email
            if normalized_sender not in self.employee_by_email:
                if self.auto_discover:
                    disp_name, _ = extract_sender_name_and_email(msg.sender)
                    new_emp = Employee(name=disp_name or normalized_sender, email=normalized_sender)
                    self.employees.append(new_emp)
                    self.employee_by_email[normalized_sender] = new_emp
                else:
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

            # Record valid submission (leave notice, absent notice, or work report)
            is_subsequent = normalized_sender in valid_submissions_by_employee
            valid_submissions_by_employee.setdefault(normalized_sender, []).append(parsed)

            if parsed.is_absent:
                stats["valid_reports"] += 1
                if is_subsequent:
                    stats["duplicate_reports"] += 1
                    action = "Subsequent Absent Notice"
                    details = f"Subsequent absent email received from '{normalized_sender}' for {target_date}. Latest submission timestamp will determine status."
                else:
                    action = "Absent Recorded"
                    details = f"Email absent notice received for {target_date}."
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.VALID_REPORT,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action=action,
                        details=details,
                    )
                )
            elif parsed.is_leave:
                stats["valid_reports"] += 1
                if is_subsequent:
                    stats["duplicate_reports"] += 1
                    action = "Subsequent Leave Notice"
                    details = f"Subsequent leave email received from '{normalized_sender}' for {target_date}. Latest submission timestamp will determine status."
                else:
                    action = "Leave Recorded"
                    details = f"Email leave notice received for {target_date}."
                processing_logs.append(
                    ProcessingLogEntry(
                        timestamp=timestamp,
                        category=LogCategory.VALID_REPORT,
                        sender=msg.sender,
                        subject=msg.subject,
                        target_date=target_date,
                        action=action,
                        details=details,
                    )
                )
            else:
                if is_subsequent:
                    stats["duplicate_reports"] += 1
                    processing_logs.append(
                        ProcessingLogEntry(
                            timestamp=timestamp,
                            category=LogCategory.DUPLICATE_REPORT,
                            sender=msg.sender,
                            subject=msg.subject,
                            target_date=target_date,
                            action="Subsequent Work Report",
                            details=f"Subsequent report received from '{normalized_sender}' for {target_date}. Latest submission timestamp will determine status.",
                        )
                    )
                else:
                    if parsed.category == LogCategory.LATE_REPORT:
                        stats["late_reports"] += 1
                        action = "Accepted (Late)"
                        details = f"Email received after work date ({msg.received_at}), but explicitly marked for {target_date}. Present status established."
                    else:
                        stats["valid_reports"] += 1
                        action = "Accepted"
                        details = f"Valid on-time work report received for {target_date}."
                    processing_logs.append(
                        ProcessingLogEntry(
                            timestamp=timestamp,
                            category=parsed.category,
                            sender=msg.sender,
                            subject=msg.subject,
                            target_date=target_date,
                            action=action,
                            details=details,
                        )
                    )

        # Step 2: Determine P / A / L status for every expected employee
        attendance_records: List[AttendanceRecord] = []
        status_counts = {"P": 0, "A": 0, "L": 0}

        def get_submission_time(rep: ParsedReport) -> datetime:
            ts = rep.raw_message.received_at
            if not ts:
                return datetime.min
            try:
                clean = ts.replace("Z", "+00:00")
                return datetime.fromisoformat(clean)
            except Exception:
                return datetime.min

        for emp in self.employees:
            emp_email = emp.normalized_email
            has_scheduled_leave = (emp_email, target_date) in self.leave_set
            submissions = valid_submissions_by_employee.get(emp_email, [])

            if submissions:
                # If multiple emails received, sort chronologically and determine status by the latest email
                sorted_subs = sorted(submissions, key=get_submission_time)
                latest_sub = sorted_subs[-1]
                count = len(sorted_subs)

                # In strict mock mode (allow_fuzzy=False), scheduled CSV leave registry takes precedence
                if not self.allow_fuzzy and has_scheduled_leave:
                    status = AttendanceStatus.LEAVE
                    note = "On leave as recorded in leave registry. (Work report also received, overridden by leave precedence)."
                elif latest_sub.is_absent:
                    status = AttendanceStatus.ABSENT
                    if count > 1:
                        note = f"Absent as per latest submission ({count} emails received, latest is absent notice)."
                    else:
                        note = "Absent as reported via email notice."
                elif latest_sub.is_leave:
                    status = AttendanceStatus.LEAVE
                    if count > 1:
                        note = f"On leave as per latest submission ({count} emails received, latest is leave notice)."
                    else:
                        note = "On leave as per email notice received for date."
                else:
                    status = AttendanceStatus.PRESENT
                    if count > 1:
                        had_leave_or_absent = any(s.is_leave or s.is_absent for s in sorted_subs[:-1])
                        if had_leave_or_absent:
                            note = f"Present as per latest work report ({count} emails received, superseded earlier absence/leave notice)."
                        else:
                            note = f"Present ({count} reports received, latest is work report)."
                    else:
                        note = "Present (1 valid report)"
            else:
                if has_scheduled_leave:
                    status = AttendanceStatus.LEAVE
                    note = "On leave as recorded in leave registry."
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

        if self.only_present_and_leave:
            attendance_records = [
                r for r in attendance_records
                if r.status in (AttendanceStatus.PRESENT, AttendanceStatus.LEAVE)
            ]
            summary_stats = {
                "total_employees": len(attendance_records),
                "present_count": status_counts["P"],
                "absent_count": 0,
                "leave_count": status_counts["L"],
                **stats,
            }
        else:
            summary_stats = {
                "total_employees": len(self.employees),
                "present_count": status_counts["P"],
                "absent_count": status_counts["A"],
                "leave_count": status_counts["L"],
                **stats,
            }

        return attendance_records, processing_logs, summary_stats
