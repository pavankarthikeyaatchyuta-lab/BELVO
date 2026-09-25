"""
FastAPI backend service for Belvo Attendance Tracker.
Exposes REST endpoints consumed by the Manifest V3 Chrome Extension and web clients.
Supports both Vercel Serverless deployment and local CLI development.
"""

from datetime import datetime
import io
import logging
import os
from pathlib import Path
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
from fastapi import FastAPI, Header, HTTPException, Query, Response, status, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
    GMAIL_TOKEN_PATH,
    get_credentials_path,
)
from app.excel_writer import export_attendance_bytes, export_attendance_workbook
from app.gmail_client import GmailProvider, MockEmailProvider
from app.oauth import (
    create_authorization_url,
    exchange_code_for_session,
    get_credentials_from_session_token,
    get_oauth_config,
)
from app.parser import parse_work_report

app = FastAPI(
    title="Belvo Attendance Tracker API",
    version="2.0.0",
    description="Cloud-native backend API serving the Belvo Attendance Tracker Chrome Extension",
)

# CORS configuration: Restrict to Chrome extensions, Vercel deployments, and localhost
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://.*|https://.*\.vercel\.app|http://(localhost|127\.0\.0\.1)(:\d+)?)$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cached Excel bytes for serverless execution
_latest_excel_bytes: Optional[bytes] = None

# In-memory session tracking for seamless extension auto-claim
_pending_sessions: Dict[str, Tuple[str, float]] = {}
_latest_session: Optional[Tuple[str, float]] = None


class ScanRequest(BaseModel):
    date: str = Field(default="2026-09-17", description="Target work date (YYYY-MM-DD)")
    mode: str = Field(default="mock", description="Data source mode: 'mock' or 'gmail'")
    session_token: Optional[str] = Field(default=None, description="Encrypted OAuth session token")


class ProcessRequest(BaseModel):
    date: str = Field(default="2026-09-17", description="Target work date (YYYY-MM-DD)")
    mode: str = Field(default="mock", description="Data source mode: 'mock' or 'gmail'")
    session_token: Optional[str] = Field(default=None, description="Encrypted OAuth session token")


def extract_bearer_token(auth_header: Optional[str], body_token: Optional[str]) -> Optional[str]:
    """Extracts session token from Authorization Bearer header or request body."""
    if body_token and body_token.strip():
        return body_token.strip()
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split("Bearer ", 1)[1].strip()
    return None


@app.get("/")
def root_status():
    """Root health check for Vercel deployment."""
    return {
        "status": "online",
        "service": "Belvo Attendance Tracker API",
        "version": "2.0.0",
        "message": "Belvo Attendance Tracker API is operational.",
        "endpoints": {
            "status": "/api/status",
            "docs": "/docs",
            "scan": "/api/scan",
            "process": "/api/process",
            "download": "/api/download",
            "auth": "/api/auth/google",
        },
    }


@app.get("/api/status")
@app.get("/status")
def get_system_status():
    """Returns backend health, credentials presence, and active configuration."""
    client_id, _, _ = get_oauth_config()
    creds_path = get_credentials_path()
    employees = load_employees_from_csv(DEFAULT_EMPLOYEES_PATH)
    leave_entries = load_leave_from_csv(DEFAULT_LEAVE_PATH)

    has_excel = _latest_excel_bytes is not None or DEFAULT_OUTPUT_PATH.exists()

    return {
        "status": "online",
        "service": "Belvo Attendance Tracker API",
        "version": "2.0.0",
        "oauth_configured": bool(client_id),
        "credentials_present": creds_path.exists() if creds_path else False,
        "token_present": GMAIL_TOKEN_PATH.exists(),
        "total_employees": len(employees),
        "total_leave_entries": len(leave_entries),
        "default_date": "2026-09-17",
        "excel_available": has_excel,
    }


# ==========================================================
# Google Web OAuth 2.0 Endpoints
# ==========================================================

@app.get("/api/auth/google")
@app.get("/auth/google")
def initiate_google_oauth(
    redirect_uri: Optional[str] = Query(None, description="Custom OAuth redirect URI"),
    json_response: bool = Query(False, description="Return JSON instead of redirect"),
):
    """
    Initiates Google OAuth 2.0 flow for Gmail read-only access.
    Returns authorization URL or redirects the browser.
    """
    try:
        auth_url, state = create_authorization_url(redirect_uri=redirect_uri)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if json_response:
        return {"auth_url": auth_url, "state": state}
    return RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@app.get("/api/auth/callback")
@app.get("/auth/callback")
def google_oauth_callback(
    code: Optional[str] = Query(None, description="Google authorization code"),
    state: Optional[str] = Query(None, description="CSRF state parameter"),
    error: Optional[str] = Query(None, description="OAuth error parameter"),
    redirect_uri: Optional[str] = Query(None, description="Original redirect URI"),
):
    """
    OAuth redirect callback handling token exchange and session creation.
    Renders a secure, user-friendly HTML confirmation for Chrome Extension users.
    """
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth authorization error: {error}",
        )

    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code from Google OAuth callback.",
        )

    try:
        creds, session_token = exchange_code_for_session(code=code, redirect_uri=redirect_uri)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange failed: {str(e)}",
        )

    global _latest_session, _pending_sessions
    now = time.time()
    _latest_session = (session_token, now)
    if state:
        _pending_sessions[state] = (session_token, now)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Belvo - Gmail Connected</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f4f6f9;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      padding: 16px;
    }}
    .card {{
      background: white;
      padding: 32px;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
      max-width: 480px;
      width: 100%;
      text-align: center;
    }}
    .icon {{ font-size: 48px; margin-bottom: 12px; }}
    h2 {{ color: #1F4E79; margin: 0 0 8px 0; }}
    p {{ color: #4b5563; font-size: 14px; line-height: 1.5; margin: 8px 0; }}
    .badge {{
      display: inline-block;
      margin-top: 12px;
      padding: 6px 16px;
      background: #d4edda;
      color: #155724;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">✅</div>
    <h2>Gmail Connected Successfully!</h2>
    <p>Your Gmail account has been securely linked with read-only access for daily work-report scanning.</p>
    <div class="badge">Session Established</div>
    <div style="margin-top: 20px; padding: 12px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; text-align: left;">
      <p style="margin: 0 0 6px; font-size: 12px; color: #166534; font-weight: 600;">Extension Session Token:</p>
      <div style="display: flex; gap: 6px;">
        <input type="text" id="tokenField" value="{session_token}" readonly style="flex: 1; font-size: 11px; padding: 6px; border: 1px solid #cbd5e1; border-radius: 4px; background: white;" />
        <button onclick="navigator.clipboard.writeText('{session_token}'); this.innerText='Copied!';" style="padding: 6px 12px; font-size: 12px; font-weight: 600; background: #16a34a; color: white; border: none; border-radius: 4px; cursor: pointer;">Copy</button>
      </div>
    </div>
    <p style="margin-top: 16px; font-size: 12px; color: #9ca3af;">
      You can now close this tab and return to the Belvo Chrome Extension.
    </p>
  </div>
  <script>
    const sessionToken = "{session_token}";
    if (window.opener) {{
      window.opener.postMessage({{ type: "BELVO_AUTH_SUCCESS", session_token: sessionToken }}, "*");
    }}
    localStorage.setItem("belvo_session_token", sessionToken);
  </script>
</body>
</html>
"""
    response = HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)
    response.set_cookie(
        key="belvo_session",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=86400 * 30,
    )
    return response


@app.get("/api/auth/latest")
@app.get("/auth/latest")
def get_latest_session():
    """Returns the most recent authenticated session token if active within 30 minutes."""
    global _latest_session
    if _latest_session:
        token, timestamp = _latest_session
        if time.time() - timestamp < 1800:
            creds = get_credentials_from_session_token(token)
            if creds and creds.valid:
                return {"authenticated": True, "session_token": token}
    return {"authenticated": False, "session_token": None}


@app.get("/api/auth/claim")
@app.get("/auth/claim")
def claim_session(state: str = Query(...)):
    """Allows an extension to claim a session token by OAuth state."""
    global _pending_sessions
    if state in _pending_sessions:
        token, timestamp = _pending_sessions[state]
        if time.time() - timestamp < 1800:
            creds = get_credentials_from_session_token(token)
            if creds and creds.valid:
                return {"authenticated": True, "session_token": token}
    return {"authenticated": False, "session_token": None}


@app.get("/api/auth/status")
@app.get("/auth/status")
def get_auth_status(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
):
    """Checks whether the client has a valid authenticated Gmail session."""
    session_token = extract_bearer_token(authorization, token)

    if session_token:
        creds = get_credentials_from_session_token(session_token)
        if creds and creds.valid:
            return {"authenticated": True, "method": "web_oauth"}
        return {"authenticated": False, "method": "invalid_token"}

    # Fallback: check local desktop credentials if running locally
    creds_path = get_credentials_path()
    if GMAIL_TOKEN_PATH.exists() and creds_path and creds_path.exists():
        return {"authenticated": True, "method": "local_token"}

    return {"authenticated": False, "method": "none"}


@app.post("/api/auth/logout")
@app.post("/auth/logout")
def logout():
    """Logs out by clearing active session cookies."""
    response = Response(content='{"authenticated": false, "message": "Logged out successfully."}', media_type="application/json")
    response.delete_cookie(key="belvo_session")
    return response


@app.post("/api/auth/connect")
@app.post("/auth/connect")
def connect_gmail_legacy():
    """Validates local or web OAuth setup for backward compatibility."""
    client_id, _, _ = get_oauth_config()
    creds_path = get_credentials_path()

    if client_id:
        return {
            "authenticated": True,
            "message": "Google OAuth is configured.",
            "mode": "web_oauth",
        }

    if creds_path and creds_path.exists():
        try:
            provider = GmailProvider(credentials_path=creds_path)
            creds = provider._get_credentials()
            return {
                "authenticated": True,
                "message": "Gmail OAuth credentials verified successfully.",
                "token_valid": creds.valid,
                "mode": "local_desktop",
            }
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Gmail authentication failed: {str(e)}",
            )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET, or use Mock Mode.",
    )


# ==========================================================
# Core Scanning & Attendance Processing Endpoints
# ==========================================================

@app.post("/api/scan")
@app.post("/scan")
def scan_work_reports(req: ScanRequest, authorization: Optional[str] = Header(None)):
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
            session_token = extract_bearer_token(authorization, req.session_token)
            provider = None

            if session_token:
                creds = get_credentials_from_session_token(session_token)
                if creds:
                    provider = GmailProvider(credentials=creds)

            if provider is None:
                # Fallback to local credentials.json if running locally
                creds_path = get_credentials_path()
                if creds_path and creds_path.exists():
                    provider = GmailProvider(credentials_path=creds_path)
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Gmail account is not connected. Please click 'Connect with Google' or use Mock Mode.",
                    )
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
@app.post("/process")
def process_attendance(req: ProcessRequest, authorization: Optional[str] = Header(None)):
    """
    Executes the deterministic attendance engine, generates Excel, and returns results.
    Works statelessly on Vercel and preserves all existing P/A/L logic.
    """
    global _latest_excel_bytes

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
            session_token = extract_bearer_token(authorization, req.session_token)
            provider = None

            if session_token:
                creds = get_credentials_from_session_token(session_token)
                if creds:
                    provider = GmailProvider(credentials=creds)

            if provider is None:
                creds_path = get_credentials_path()
                if creds_path and creds_path.exists():
                    provider = GmailProvider(credentials_path=creds_path)
                else:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Gmail account is not connected. Please click 'Connect with Google' or use Mock Mode.",
                    )
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

    # 2. Process attendance deterministically
    engine = AttendanceEngine(employees=employees, leave_entries=leave_entries)
    records, logs, stats = engine.process_attendance(raw_messages, req.date)

    # 3. Generate Excel in memory (serverless safe) and write to disk if writable
    excel_bytes = export_attendance_bytes(records, logs)
    _latest_excel_bytes = excel_bytes

    try:
        export_attendance_workbook(records, logs, DEFAULT_OUTPUT_PATH)
    except Exception as e:
        logger.info(f"Disk write skipped on read-only serverless environment: {e}")

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
        "excel_available": True,
        "download_url": "/api/download",
    }


@app.get("/api/download")
@app.get("/download")
def download_excel():
    """Serves the generated attendance.xlsx workbook."""
    global _latest_excel_bytes

    # Priority 1: Serve from in-memory cache (works in serverless environments)
    if _latest_excel_bytes is not None:
        return Response(
            content=_latest_excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=attendance.xlsx"},
        )

    # Priority 2: Serve from disk if generated locally
    if DEFAULT_OUTPUT_PATH.exists():
        return FileResponse(
            path=str(DEFAULT_OUTPUT_PATH),
            filename="attendance.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Attendance Excel report has not been generated yet. Please run processing first.",
    )
