"""
Automated tests for FastAPI endpoints (app/api.py).
Ensures Chrome Extension API communication works reliably in Mock and Gmail modes.
"""

from fastapi.testclient import TestClient
import pytest
from app.api import app

client = TestClient(app)


def test_api_status():
    """Verify backend health and metadata endpoint."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert data["service"] == "Belvo Attendance Tracker API"
    assert data["total_employees"] == 5
    assert data["total_leave_entries"] == 1
    assert data["default_date"] == "2026-09-17"


def test_api_scan_mock_mode():
    """Verify scanning emails in mock mode."""
    response = client.post("/api/scan", json={"date": "2026-09-17", "mode": "mock"})
    assert response.status_code == 200
    data = response.json()
    assert data["total_found"] == 9
    assert data["mode"] == "mock"
    assert data["date"] == "2026-09-17"
    assert len(data["messages"]) == 9


def test_api_scan_invalid_date():
    """Verify error handling on invalid date format."""
    response = client.post("/api/scan", json={"date": "invalid-date", "mode": "mock"})
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["detail"]


def test_api_process_mock_mode():
    """Verify attendance processing via API in mock mode."""
    response = client.post("/api/process", json={"date": "2026-09-17", "mode": "mock"})
    assert response.status_code == 200
    data = response.json()
    stats = data["stats"]
    assert stats["total_employees"] == 5
    assert stats["present_count"] == 3
    assert stats["absent_count"] == 1
    assert stats["leave_count"] == 1
    assert stats["duplicate_reports"] == 1
    assert stats["late_reports"] == 1
    assert stats["malformed_subjects"] == 1
    assert stats["missing_subjects"] == 1
    assert stats["unknown_senders"] == 1

    records = data["records"]
    assert len(records) == 5
    # Verify Ananya on Leave
    ananya = next(r for r in records if r["email"] == "ananya@example.com")
    assert ananya["status"] == "L"

    # Verify Ravi Absent
    ravi = next(r for r in records if r["email"] == "ravi@example.com")
    assert ravi["status"] == "A"

    assert data["excel_available"] is True
    assert data["download_url"] == "/api/download"


def test_api_download_excel():
    """Verify downloading the generated attendance.xlsx file."""
    # Ensure file is generated
    client.post("/api/process", json={"date": "2026-09-17", "mode": "mock"})

    response = client.get("/api/download")
    assert response.status_code == 200
    assert (
        response.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(response.content) > 0
