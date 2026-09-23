"""
Belvo Attendance Tracker - CLI Entrypoint
"""

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys

from app.attendance import (
    AttendanceEngine,
    load_employees_from_csv,
    load_leave_from_csv,
)
from app.config import (
    DATE_FORMAT,
    DEFAULT_EMPLOYEES_PATH,
    DEFAULT_LEAVE_PATH,
    DEFAULT_MOCK_EMAILS_PATH,
    DEFAULT_OUTPUT_PATH,
)
from app.excel_writer import export_attendance_workbook
from app.gmail_client import GmailProvider, MockEmailProvider


def run_pipeline(
    target_date: str,
    mode: str = "mock",
    employees_path: Path = DEFAULT_EMPLOYEES_PATH,
    leave_path: Path = DEFAULT_LEAVE_PATH,
    mock_data_path: Path = DEFAULT_MOCK_EMAILS_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
):
    """Executes the complete attendance evaluation and reporting pipeline."""
    # Validate target date format
    try:
        datetime.strptime(target_date, DATE_FORMAT)
    except ValueError:
        print(f"Error: Invalid date format '{target_date}'. Expected format: YYYY-MM-DD (e.g. 2026-09-17).")
        sys.exit(1)

    print(f"==================================================")
    print(f"  Belvo Attendance Tracker")
    print(f"  Target Date: {target_date} | Mode: {mode.upper()}")
    print(f"==================================================")

    # 1. Load configuration files
    employees = load_employees_from_csv(employees_path)
    if not employees:
        print(f"Error: No employees found in '{employees_path}'. Please check the file.")
        sys.exit(1)

    leave_entries = load_leave_from_csv(leave_path)
    print(f"Loaded {len(employees)} expected employees and {len(leave_entries)} leave entries.")

    # 2. Initialize email provider and fetch messages
    print(f"Fetching work reports...")
    try:
        if mode == "gmail":
            provider = GmailProvider()
        else:
            provider = MockEmailProvider(data_path=mock_data_path)

        raw_messages = provider.fetch_messages(target_date)
    except Exception as e:
        print(f"\n[Error connecting to email source]: {e}")
        if mode == "gmail":
            print("\nHint: To run without Gmail OAuth, use mock mode:\n  python main.py --mode mock --date " + target_date)
        sys.exit(1)

    print(f"Processing {len(raw_messages)} emails...")

    # 3. Process attendance
    engine = AttendanceEngine(employees=employees, leave_entries=leave_entries)
    records, logs, stats = engine.process_attendance(raw_messages, target_date)

    # Display processing summary
    print(f"Valid reports:     {stats['valid_reports']}")
    print(f"Duplicates:        {stats['duplicate_reports']}")
    print(f"Late reports:      {stats['late_reports']}")
    print(f"Malformed subjects:{stats['malformed_subjects']}")
    print(f"Missing subjects:  {stats['missing_subjects']}")
    print(f"Unknown senders:   {stats['unknown_senders']}")

    # 4. Generate Excel
    saved_path = export_attendance_workbook(records, logs, output_path)

    print(f"--------------------------------------------------")
    print(f"Attendance generated successfully.")
    print(f"P (Present): {stats['present_count']}")
    print(f"A (Absent):  {stats['absent_count']}")
    print(f"L (Leave):   {stats['leave_count']}")
    print(f"Output: {saved_path.resolve()}")
    print(f"--------------------------------------------------")

    # Display table in terminal for quick review
    print(f"\nAttendance Summary Table:")
    print(f"{'Date':<12} | {'Person':<18} | {'Email':<28} | {'Status':<6}")
    print("-" * 72)
    for rec in records:
        print(f"{rec.date:<12} | {rec.person:<18} | {rec.email:<28} | {rec.status.value:<6}")

    return records, logs, stats


def launch_ui():
    """Launches the Streamlit web dashboard."""
    import subprocess
    ui_script = Path(__file__).resolve().parent / "app" / "streamlit_app.py"
    print(f"Launching Streamlit UI: {ui_script}")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ui_script)])


def launch_server(host: str = "127.0.0.1", port: int = 8000):
    """Launches the FastAPI backend server for the Chrome Extension."""
    import uvicorn
    print(f"==================================================")
    print(f"  Belvo Attendance Tracker - API Server")
    print(f"  Serving at http://{host}:{port}")
    print(f"  Chrome Extension Endpoint: http://{host}:{port}/api/status")
    print(f"==================================================")
    uvicorn.run("app.api:app", host=host, port=port, reload=False)


def main():
    parser = argparse.ArgumentParser(description="Belvo Attendance Tracker")
    parser.add_argument(
        "--date",
        type=str,
        default="2026-09-17",
        help="Target work date (YYYY-MM-DD), default: 2026-09-17",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["mock", "gmail"],
        default="mock",
        help="Email provider mode: 'mock' (default) or 'gmail'",
    )
    parser.add_argument(
        "--employees",
        type=Path,
        default=DEFAULT_EMPLOYEES_PATH,
        help=f"Path to employees CSV (default: {DEFAULT_EMPLOYEES_PATH})",
    )
    parser.add_argument(
        "--leave",
        type=Path,
        default=DEFAULT_LEAVE_PATH,
        help=f"Path to leave CSV (default: {DEFAULT_LEAVE_PATH})",
    )
    parser.add_argument(
        "--mock-data",
        type=Path,
        default=DEFAULT_MOCK_EMAILS_PATH,
        help=f"Path to mock emails JSON (default: {DEFAULT_MOCK_EMAILS_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output path for Excel report (default: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--ui",
        action="store_true",
        help="Launch the interactive Streamlit web dashboard",
    )
    parser.add_argument(
        "--server",
        "--api",
        action="store_true",
        help="Launch the FastAPI backend server for the Chrome Extension",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for the API server (default: 8000)",
    )

    args = parser.parse_args()

    if args.ui:
        launch_ui()
    elif args.server:
        launch_server(port=args.port)
    else:
        run_pipeline(
            target_date=args.date,
            mode=args.mode,
            employees_path=args.employees,
            leave_path=args.leave,
            mock_data_path=args.mock_data,
            output_path=args.output,
        )


if __name__ == "__main__":
    main()

