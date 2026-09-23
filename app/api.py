"""
FastAPI backend service for Belvo Attendance Tracker.
Exposes REST endpoints consumed by the Manifest V3 Chrome Extension.
Integrates directly with existing core modules without rewriting logic.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

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
    GMAIL_CREDENTIALS_PATH,
    GMAIL_TOKEN_PATH,
    get_credentials_path,
)
from app.excel_writer import export_attendance_workbook
from app.gmail_client import GmailProvider, MockEmailProvider
from app.parser import parse_work_report

app = FastAPI(
    title="Belvo Attendance Tracker API",
    version="1.0.0",
    description="Backend API serving the Belvo Attendance Tracker Chrome Extension",
)

# Enable CORS for Chrome Extension and local clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanRequest(BaseModel):
    date: str = Field(default="2026-09-17", description="Target work date (YYYY-MM-DD)")
    mode: str = Field(default="mock", description="Data source mode: 'mock' or 'gmail'")


class ProcessRequest(BaseModel):
    date: str = Field(default="2026-09-17", description="Target work date (YYYY-MM-DD)")
    mode: str = Field(default="mock", description="Data source mode: 'mock' or 'gmail'")


@app.get("/api/status")
def get_system_status():
    """Returns backend health, credentials presence, and active configuration."""
    creds_path = get_credentials_path()
    employees = load_employees_from_csv(DEFAULT_EMPLOYEES_PATH)
    leave_entries = load_leave_from_csv(DEFAULT_LEAVE_PATH)

    return {
        "status": "online",
        "service": "Belvo Attendance Tracker API",
        "credentials_present": creds_path.exists(),
        "credentials_path": str(creds_path.name) if creds_path.exists() else None,
        "token_present": GMAIL_TOKEN_PATH.exists(),
        "total_employees": len(employees),
        "total_leave_entries": len(leave_entries),
        "default_date": "2026-09-17",
        "excel_available": DEFAULT_OUTPUT_PATH.exists(),
    }


@app.post("/api/auth/connect")
def connect_gmail():
    """Validates or triggers the Google OAuth 2.0 connection."""
    creds_path = get_credentials_path()
    if not creds_path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Gmail credentials not found at '{creds_path}'. "
                "Please place 'credentials.json' in the root or credentials/ folder, "
                "or switch to Mock Mode."
            ),
        )

    try:
        provider = GmailProvider(credentials_path=creds_path)
        # Attempt to get or refresh credentials
        creds = provider._get_credentials()
        return {
            "authenticated": True,
            "message": "Gmail OAuth credentials verified successfully.",
            "token_valid": creds.valid,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gmail authentication failed: {str(e)}",
        )


@app.post("/api/scan")
def scan_work_reports(req: ScanRequest):
    """
    Scans Gmail (or mock store) for work reports matching the target date.
    Returns message count and parsed preview.
    """
    try:
        datetime.strptime(req.date, DATE_FORMAT)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format '{req.date}'. Expected YYYY-MM-DD.",
        )

    try:
        if req.mode == "gmail":
            creds_path = get_credentials_path()
            if not creds_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Gmail credentials.json not found. Run in Mock Mode or configure credentials.",
                )
            provider = GmailProvider(credentials_path=creds_path)
        else:
            provider = MockEmailProvider(data_path=DEFAULT_MOCK_EMAILS_PATH)

        raw_messages = provider.fetch_messages(req.date)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch messages: {str(e)}",
        )

    # Parse and categorize messages for preview
    parsed_items = []
    for msg in raw_messages:
        parsed = parse_work_report(msg, req.date)
        parsed_items.append({
            "id": msg.id,
            "sender": msg.sender,
            "subject": msg.subject,
            "received_at": msg.received_at,
            "is_valid": parsed.is_valid,
            "extracted_date": parsed.extracted_date,
            "category": parsed.category.value if hasattr(parsed.category, "value") else str(parsed.category),
            "notes": parsed.notes,
        })

    return {
        "date": req.date,
        "mode": req.mode,
        "total_found": len(raw_messages),
        "messages": parsed_items,
    }


@app.post("/api/process")
def process_attendance(req: ProcessRequest):
    """
    Executes the deterministic attendance engine, generates Excel, and returns results.
    """
    try:
        datetime.strptime(req.date, DATE_FORMAT)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format '{req.date}'. Expected YYYY-MM-DD.",
        )

    employees = load_employees_from_csv(DEFAULT_EMPLOYEES_PATH)
    if not employees:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No employees found in '{DEFAULT_EMPLOYEES_PATH}'.",
        )

    leave_entries = load_leave_from_csv(DEFAULT_LEAVE_PATH)

    # 1. Fetch raw messages
    try:
        if req.mode == "gmail":
            creds_path = get_credentials_path()
            if not creds_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Gmail credentials.json not found. Run in Mock Mode or configure credentials.",
                )
            provider = GmailProvider(credentials_path=creds_path)
        else:
            provider = MockEmailProvider(data_path=DEFAULT_MOCK_EMAILS_PATH)

        raw_messages = provider.fetch_messages(req.date)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch emails: {str(e)}",
        )

    # 2. Process attendance
    engine = AttendanceEngine(employees=employees, leave_entries=leave_entries)
    records, logs, stats = engine.process_attendance(raw_messages, req.date)

    # 3. Export Excel workbook
    output_file = export_attendance_workbook(records, logs, DEFAULT_OUTPUT_PATH)

    return {
        "date": req.date,
        "mode": req.mode,
        "stats": stats,
        "records": [
            {
                "date": r.date,
                "person": r.person,
                "email": r.email,
                "status": r.status.value,
                "notes": r.notes,
            }
            for r in records
        ],
        "logs": [
            {
                "timestamp": l.timestamp,
                "category": l.category.value if hasattr(l.category, "value") else str(l.category),
                "sender": l.sender,
                "subject": l.subject,
                "target_date": l.target_date,
                "action": l.action,
                "details": l.details,
            }
            for l in logs
        ],
        "excel_available": output_file.exists(),
        "download_url": "/api/download",
    }


@app.get("/api/download")
def download_excel():
    """Serves the generated attendance.xlsx workbook."""
    if not DEFAULT_OUTPUT_PATH.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance Excel report has not been generated yet. Please run processing first.",
        )

    return FileResponse(
        path=str(DEFAULT_OUTPUT_PATH),
        filename="attendance.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
