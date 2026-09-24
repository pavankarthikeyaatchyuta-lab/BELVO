# BELVO ATTENDANCE TRACKER

### Automated Employee Attendance Processing from Gmail Work Reports
#### Cloud-Deployable Web Architecture • Chrome Extension (Manifest V3) • Vercel Serverless FastAPI • Google OAuth 2.0 • In-Memory Excel Engine

---

## 1. Project Information

- **Project**: Belvo Attendance Tracker
- **Purpose**: Automated employee attendance processing from Gmail daily work-report emails
- **Input**: Daily Work Report emails received in Gmail inbox
- **Architecture**: Chrome Extension (Manifest V3) ➔ HTTPS ➔ Vercel Serverless FastAPI ➔ Google Gmail API ➔ Attendance Engine ➔ In-Memory Excel Export
- **Authentication**: Web-Server OAuth 2.0 with symmetric session encryption (`cryptography.fernet`) + Local Desktop OAuth fallback
- **Access Scope**: Google Gmail Read-Only (`https://www.googleapis.com/auth/gmail.readonly`)
- **Backend Runtime**: Python (3.10+ / 3.13) deployed as a serverless ASGI application on Vercel
- **Frontend Interfaces**:
  1. **Chrome Extension (Manifest V3)**: Zero-install client for end-users (no local Python, pip, or terminal required)
  2. **Command-Line Interface (CLI)**: Terminal automation tool (`main.py`)
  3. **Streamlit Web Dashboard**: Interactive local data visualization interface (`python main.py --ui`)
- **Reporting Engine**: OpenPyXL dual-sheet formatted workbook (`Attendance` and `Processing Log`) with in-memory streaming
- **Testing**: 28/28 Passing Automated Pytest Suite (14 Core Engine + 5 API + 9 Cloud OAuth/Serverless tests)

---

## 2. Executive Summary

The **Belvo Attendance Tracker** is an enterprise-grade automated attendance reconciliation system engineered to eliminate manual inbox auditing in distributed and asynchronous organizations. In modern remote teams, employees verify their work activities by submitting standardized end-of-day work-report emails. Manually cross-referencing inbox submissions against employee rosters and leave records is slow, repetitive, and vulnerable to human error.

The application automates this entire lifecycle by querying a designated mailbox via the official **Google Gmail API** under a strict **read-only OAuth 2.0 scope** (`gmail.readonly`). An RFC 5322-compliant parser normalizes email headers, extracts explicit ISO calendar work dates from standardized subject lines (`Daily Work Report - YYYY-MM-DD`), and detects late submissions filed after midnight.

The normalized reports are evaluated by a deterministic **Attendance Engine** that cross-references a configurable employee roster (`sample_data/employees.csv`) and an approved leave schedule (`sample_data/leave.csv`). The engine classifies each expected team member as:
- **`P` (Present)**: A qualifying, valid work report was received for that person for the selected date.
- **`A` (Absent)**: No valid report was received, and the person is not on leave.
- **`L` (Leave)**: The person is recorded on leave in the registry (with **Leave strictly overriding Present** if both occur).

The system seamlessly resolves real-world email edge cases including duplicate submissions, past-midnight reports, malformed or blank subjects, and unauthorized senders. Results are compiled into an executive-ready Excel workbook featuring color-coded visual badges and an exhaustive, auditable processing log.

To deliver zero-friction user access, the project is structured as a **cloud-deployable solution**:
- End-users simply load the **Manifest V3 Chrome Extension** in their browser.
- The extension communicates over HTTPS with a **Vercel-hosted FastAPI backend**.
- Users authenticate directly via Google's web consent screen; tokens are securely encrypted on the server side using symmetric cryptography (`Fernet`), allowing completely stateless serverless execution without external database overhead.
- Attendance reports are generated and streamed entirely in memory (`io.BytesIO`), overcoming serverless read-only filesystem limits and eliminating the need for local Python, virtual environments, or credentials files on the end-user's machine.
- 100% backward compatibility is preserved for local CLI automation, local development servers, and offline Mock Mode.

---

## 3. Project Objectives

1. **Eliminate Manual Overhead**: Replace manual inbox reviews with a one-click automated workflow accessible directly from a browser extension.
2. **Zero-Setup End-User Experience**: Enable non-technical users to track attendance without installing Python, configuring pip packages, or managing API credentials locally.
3. **Deterministic Classification**: Apply consistent, auditable business logic to classify every expected employee as Present (`P`), Absent (`A`), or Leave (`L`).
4. **Enforce Leave Precedence**: Guarantee that approved leave records override submitted work reports (`L > P > A`).
5. **Handle Real-World Edge Cases**:
   - Deduplicate same-day multiple submissions from the same employee without double-counting.
   - Associate late reports (filed past midnight) with their intended work date using subject metadata.
   - Reject and audit malformed or missing subjects without unverified guessing of sender intent.
   - Isolate unknown or external senders without altering internal rosters.
6. **Stateless Serverless Deployment**: Enable deployment on Vercel's serverless architecture with in-memory streaming and encrypted session tokens.
7. **Zero-Trust Security**: Maintain strict read-only access, zero DOM scraping, zero plaintext token storage in extension code, and robust `.gitignore` secrets isolation.
8. **Dual-Mode Operation**: Provide live Gmail API integration alongside a self-contained offline **Mock Mode** for demonstrations and automated testing.

---

## 4. System Architecture & Workflow

### Cloud & Extension Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Chrome Browser (MV3)                      │
│                                                              │
│  [Popup UI: popup.html / popup.js / popup.css]               │
│   • Google OAuth Sign-In (chrome.identity / Web popup)       │
│   • Date Picker & Mode Selector (Mock vs. Gmail API)         │
│   • Scan Inbox & Process Attendance Actions                  │
│   • Live P/A/L Metrics & Detailed Roster Table               │
│   • In-Memory Excel Direct Download                          │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTPS REST API
                               ▼
┌──────────────────────────────────────────────────────────────┐
│             Vercel Serverless ASGI Backend                   │
│                                                              │
│  [api/index.py ➔ app/api.py]                                 │
│   • Stateless Bearer Session Validation                      │
│   • Fernet Symmetric Token Decryption (SESSION_SECRET)       │
│   • CORS Origin Authorization                                │
│   • In-Memory Excel Bytes Streaming (io.BytesIO)             │
└──────────────┬───────────────────────────────┬───────────────┘
               │                               │
       Gmail Mode (OAuth)               Mock Mode (Offline)
               │                               │
               ▼                               ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│       Google Gmail API       │ │      Sample Data Store       │
│  • users.messages.list()     │ │  • sample_data/              │
│  • users.messages.get()      │ │    mock_emails.json          │
│  • Scope: gmail.readonly     │ │  (9 test scenarios)          │
└──────────────┬───────────────┘ └─────────────┬────────────────┘
               │                               │
               └───────────────┬───────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                  Core Processing Engine                      │
│                                                              │
│  1. Deterministic Parser (app/parser.py)                     │
│     • RFC 5322 Sender Normalization                          │
│     • Strict Subject Regex Matching                          │
│     • Explicit Calendar Work-Date Extraction                 │
│     • Late Submission Detection (Past Midnight)              │
│                                                              │
│  2. Attendance Engine (app/attendance.py)                    │
│     • Match against employees.csv                            │
│     • Cross-reference leave.csv                              │
│     • Precedence Rule Enforcement (L > P > A)                │
│     • Duplicate Submission Consolidation                     │
│                                                              │
│  3. In-Memory Excel Generator (app/excel_writer.py)          │
│     • Sheet 1: "Attendance" (Styled Badges & Frozen Panes)   │
│     • Sheet 2: "Processing Log" (Exhaustive Audit Trail)     │
│     • io.BytesIO In-Memory Streaming                         │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│             Presentation-Ready Excel Workbook                │
│                 (Direct Browser Download)                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Technology Stack

| Layer | Component | Specification | Purpose |
| :--- | :--- | :--- | :--- |
| **Language** | Python | `>=3.10` (Tested on `3.13.14`) | Core execution runtime |
| **Cloud Platform** | Vercel Serverless | Python Serverless Functions (`@vercel/python`) | Zero-maintenance serverless ASGI hosting |
| **Web Framework** | FastAPI & Uvicorn | `fastapi>=0.100.0`, `uvicorn>=0.20.0` | High-performance asynchronous REST API |
| **Browser Extension** | Chrome Extension | Manifest V3 (HTML5, Modern CSS, Vanilla JS) | User frontend with zero local installation |
| **Session Security** | Cryptography | `cryptography>=41.0.0` (`Fernet`) | Symmetric AES-128-CBC encryption of session tokens |
| **Email Ingestion** | Google Gmail API v1 | `google-api-python-client>=2.100.0` | Official REST queries for Gmail messages |
| **OAuth Integration** | Google Auth OAuthlib | `google-auth-oauthlib>=1.0.0` | Web-server & installed-app OAuth 2.0 flows |
| **Spreadsheet Engine** | OpenPyXL | `openpyxl>=3.1.2` | Native `.xlsx` workbook generation & styling |
| **Local Web UI** | Streamlit | `streamlit>=1.30.0` | Interactive local data visualization interface |
| **Test Framework** | Pytest | `pytest>=9.0.0` | Comprehensive unit and integration test suite |

---

## 6. Google Gmail API & Cloud Web-Server OAuth Flow

The application implements a secure **Web-Server OAuth 2.0 flow** engineered specifically for serverless hosting:

### Web-Server OAuth Architecture

```
User (Chrome Extension)       Vercel FastAPI Backend        Google Accounts
         │                              │                          │
         │─── 1. Click "Connect" ──────►│                          │
         │    GET /api/auth/google      │                          │
         │                              │─── 2. Build Auth URL ───►│
         │◄── 3. Return Auth URL ───────│    (offline access,      │
         │    (or 307 Redirect)         │     prompt=consent)      │
         │                              │                          │
         │─── 4. User Consents to Read-Only Scope in Browser ─────►│
         │                              │                          │
         │                              │◄── 5. Redirect Callback ─│
         │                              │    GET /api/auth/callback│
         │                              │    ?code=...&state=...   │
         │                              │                          │
         │                              │─── 6. Exchange Code ────►│
         │                              │◄── 7. Access & Refresh ──│
         │                              │                          │
         │                              │─── 8. Fernet Encrypt ────│
         │◄── 9. Post Session Token ────│    Credentials into      │
         │    via Window Message /      │    Stateless Session     │
         │    Browser LocalStorage      │    Token                 │
         │                              │                          │
         │─── 10. Scan / Process ──────►│                          │
         │    Authorization: Bearer     │─── 11. Decrypt Token ────│
         │    <session_token>           │    Query Gmail API ─────►│
```

### OAuth Endpoints Implemented

1. **`GET /api/auth/google`**:
   - Generates the official Google consent URL with:
     - `scope`: `https://www.googleapis.com/auth/gmail.readonly`
     - `access_type`: `offline` (ensures refresh token issuance)
     - `prompt`: `consent` (guarantees refresh token return)
     - `state`: Cryptographically secure random CSRF token
   - Supports both direct JSON response (`?json=true`) for the Chrome extension and standard 307 HTTP redirects for browser navigation.

2. **`GET /api/auth/callback`**:
   - Receives the authorization code from Google.
   - Exchanges the authorization code for access and refresh tokens.
   - Encrypts credentials into a stateless Fernet session token.
   - Serves an elegant HTML confirmation page that transmits the session token to the extension via `window.opener.postMessage` and stores it in `localStorage`.

3. **`GET /api/auth/status`**:
   - Accepts `Authorization: Bearer <session_token>` header or query param.
   - Validates whether the token can be decrypted and possesses valid/refreshable Google credentials.
   - Returns `{"authenticated": true, "method": "web_oauth"}`.
   - Falls back to inspecting local `token.json` if run locally without a bearer token.

4. **`POST /api/auth/logout`**:
   - Clears active session cookies and instructs the client to purge stored tokens.

---

## 7. Stateless Token Encryption & Security

Serverless deployments like Vercel have ephemeral execution instances and no built-in persistent disk. To avoid requiring external database infrastructure (such as Redis or Postgres) solely for session storage, the Belvo Attendance Tracker implements **Stateless Symmetric Token Encryption**:

1. When Google returns the OAuth tokens, `app/oauth.py` packages:
   ```json
   {
     "token": "<access_token>",
     "refresh_token": "<refresh_token>",
     "token_uri": "https://oauth2.googleapis.com/token",
     "client_id": "<client_id>",
     "client_secret": "<client_secret>",
     "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
     "expiry": "2026-09-24T12:00:00Z"
   }
   ```
2. The JSON payload is encrypted using the server's private `SESSION_SECRET` via **`cryptography.fernet.Fernet`** (AES-128-CBC with SHA-256 HMAC authentication).
3. The resulting ciphertext string is returned to the Chrome Extension as a secure session token.
4. On subsequent API calls (`/api/scan`, `/api/process`), the extension passes the token in the `Authorization: Bearer <token>` header.
5. Any serverless worker decrypts the token on the fly, reconstructs a `google.oauth2.credentials.Credentials` instance, refreshes it automatically if expired, and queries the Gmail API.
6. **Key Security Guarantees**:
   - The refresh token is encrypted with the server secret and is **never visible in plaintext** to the browser or extension.
   - The token cannot be forged or tampered with due to Fernet's cryptographic signature verification.
   - No tokens are stored on the server's filesystem.

---

## 8. Attendance Processing Engine

The core business logic resides in `app/attendance.py`. It is 100% deterministic, reproducible, and decoupled from the delivery layer.

### The P / A / L Classification Rules

For every employee listed in `sample_data/employees.csv` for the selected work date:

| Status Code | Meaning | Condition |
| :---: | :--- | :--- |
| **`P`** | **Present** | At least one valid work report was received for this employee matching the target work date, and the employee is **not** on approved leave. |
| **`A`** | **Absent** | No valid work report was received for this employee for the target date, and the employee is **not** on approved leave. |
| **`L`** | **Leave** | The employee is recorded in `sample_data/leave.csv` for the target date. **Leave strictly overrides Present.** |

### Precedence Hierarchy

```
Is (employee.email, target_date) in approved leave schedule?
       │
      ├─── YES ───► Status = "L" (Leave Precedence)
      │             (Even if a valid report was received, report is logged as overridden)
      │
       └─── NO  ───► Did employee submit a valid work report for target_date?
                            │
                           ├─── YES ───► Status = "P" (Present)
                           │
                            └─── NO  ───► Status = "A" (Absent)
```

### Comprehensive Edge Case Handling

1. **Duplicate Submissions**:
   - If an employee submits multiple reports for the same date (e.g. initial report and an updated report), the engine registers the employee as **`P` (Present)** exactly once.
   - The additional reports are logged as `DUPLICATE_REPORT` in the processing log.
2. **Late Submissions (Past Midnight)**:
   - Employees often finish shifts late and email reports at 1:00 AM or 2:00 AM the following calendar day.
   - The engine associates the report with the work date **explicitly stated in the subject line**, not the email receipt timestamp.
   - The report is counted as valid **`P`**, and a `LATE_REPORT` notice is logged for auditability.
3. **Malformed & Missing Subjects**:
   - Emails with subjects like `"Hello"`, `"Daily update"`, `"Work report"`, or blank subjects are rejected.
   - The engine follows a strict **Non-Guessing Policy**: it never inspects the email body to infer an intended date.
   - The occurrences are recorded as `MALFORMED_SUBJECT` or `MISSING_SUBJECT`.
4. **Unknown / External Senders**:
   - Reports sent from addresses not in `sample_data/employees.csv` are quarantined.
   - They cannot alter the attendance status of any rostered employee and are logged as `UNKNOWN_SENDER`.
5. **Case-Insensitive Address Matching**:
   - `User@Example.COM` and `user@example.com` are normalized and matched identically.

---

## 9. Deterministic Email Parsing

Implemented in `app/parser.py`:

### Sender Normalization
- Uses standard RFC 5322 parsing via `email.utils.parseaddr` to isolate email addresses from display names (e.g., `"Pavan Atchyuta" <pavan@example.com>` ➔ `pavan@example.com`).
- Normalizes to lowercase and strips surrounding whitespace.

### Strict Subject Pattern
The subject line is matched against the regular expression:
```regex
^\s*daily\s+work\s+report\s*[-:]\s*(\d{4}-\d{2}-\d{2})\s*$
```
*(Compiled with `re.IGNORECASE`).*

- Accepts hyphen (`-`) or colon (`:`) delimiters.
- Requires ISO 8601 calendar format (`YYYY-MM-DD`).
- Validates the calendar validity via `datetime.strptime(..., "%Y-%m-%d")` (rejecting invalid dates like `2026-02-30`).

---

## 10. Presentation-Ready Excel Generation

Implemented in `app/excel_writer.py` using `openpyxl`. The workbook is engineered to meet executive reporting standards:

### Dual-Sheet Structure

#### Sheet 1: `Attendance`
- **Columns**: `Date`, `Person`, `Email`, `Status`
- **Styling**:
  - Dark Navy Header (`#1B365D`) with bold white text.
  - Frozen top pane so headers remain visible when scrolling.
  - Soft Status Fills:
    - **`P` (Present)**: Light Green Fill (`#E2EFDA`) with Dark Green text (`#375623`).
    - **`A` (Absent)**: Light Red Fill (`#FCE4D6`) with Dark Red text (`#C65911`).
    - **`L` (Leave)**: Light Yellow Fill (`#FFF2CC`) with Dark Yellow text (`#806000`).
  - Auto-fitted column widths and thin border gridlines.

#### Sheet 2: `Processing Log`
- **Columns**: `Timestamp`, `Message ID`, `Sender`, `Subject`, `Category`, `Action Taken`, `Details`
- Records every ingested email, duplicate resolution, late submission notice, malformed subject rejection, and unknown sender event for 100% auditability.

### Serverless In-Memory Streaming
To support serverless deployment on Vercel without relying on ephemeral local disk:
```python
def export_attendance_bytes(records: List[AttendanceRecord], log_entries: List[ProcessingLogEntry]) -> bytes:
    wb = build_attendance_workbook(records, log_entries)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
```
The FastAPI endpoint `/api/download` serves these bytes directly via `StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")`.

---

## 11. Chrome Extension Frontend (Manifest V3)

The extension inside the `extension/` directory provides a clean, zero-install interface for end users.

### Extension Features
- **Modern Belvo Popup**: Styled with clean typography, status pills, and responsive layout.
- **Backend URL Configurator**: Allows toggling between production Vercel backend (`https://<project>.vercel.app`) and local development server (`http://127.0.0.1:8000`). Stored persistently in `chrome.storage.local`.
- **One-Click Google Connect**: Initiates the Web OAuth consent flow and securely receives the session token without exposing credentials.
- **Mode Switcher**: Easily switch between **Gmail API** (live mailbox) and **Mock Mode** (instant offline demo).
- **Date Selector**: Select any target work date (defaults to `2026-09-17` for mock demonstration).
- **Two-Step Processing**:
  - **Scan Inbox**: Fetches matching reports, showing sender, subject, and snippet previews.
  - **Process Attendance**: Runs the Attendance Engine and displays interactive P/A/L summary badges and the complete employee roster table.
- **Direct Excel Download**: Streams the generated `.xlsx` workbook directly to the user's downloads folder.

### File Structure of Extension
```
extension/
├── icons/               # Extension icons (16px, 48px, 128px)
│   ├── icon16.png
│   ├── icon48.png
│   └── icon128.png
├── manifest.json        # Manifest V3 specification and permissions
├── popup.css            # Professional stylesheet with Belvo color theme
├── popup.html           # Popup user interface
└── popup.js             # API communication, state management, and file download
```

---

## 12. Vercel Cloud Serverless Deployment Guide

Deploying the Belvo Attendance Tracker to Vercel allows anyone on your team to use the Chrome Extension without running Python locally.

### Step 1: Vercel Configuration Files
The repository includes pre-configured serverless configuration files:
- **`vercel.json`**:
  ```json
  {
    "version": 2,
    "builds": [
      {
        "src": "api/index.py",
        "use": "@vercel/python"
      }
    ],
    "routes": [
      {
        "src": "/(.*)",
        "dest": "api/index.py"
      }
    ]
  }
  ```
- **`api/index.py`**: Exports the ASGI `app` instance from `app.api`.

### Step 2: Configure Google Cloud OAuth Credentials
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Select your project and navigate to **APIs & Services > Credentials**.
3. Enable the **Gmail API**.
4. Click **Create Credentials > OAuth client ID**.
5. Select **Web application** as the Application Type.
6. Configure the URIs:
   - **Authorized JavaScript origins**:
     - `https://<your-project-name>.vercel.app`
     - `http://127.0.0.1:8000` (for local development)
   - **Authorized redirect URIs**:
     - `https://<your-project-name>.vercel.app/api/auth/callback`
     - `http://127.0.0.1:8000/api/auth/callback`
7. Save and note your **Client ID** and **Client Secret**.

### Step 3: Deploy to Vercel

#### Option A: Via GitHub (Recommended)
1. Push this repository to GitHub:
   ```bash
   git push origin main
   ```
2. Open the [Vercel Dashboard](https://vercel.com/new).
3. Import your GitHub repository (`pavankarthikeyaatchyuta-lab/BELVO`).
4. In **Project Settings > Environment Variables**, add the four required variables:
   - `GOOGLE_CLIENT_ID`: Your Google OAuth Client ID
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth Client Secret
   - `GOOGLE_REDIRECT_URI`: `https://<your-project-name>.vercel.app/api/auth/callback`
   - `SESSION_SECRET`: A secure 32-byte Fernet key (generated via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
5. Click **Deploy**.

#### Option B: Via Vercel CLI
```bash
# Log in to Vercel
vercel login

# Deploy to preview
vercel

# Set environment variables
vercel env add GOOGLE_CLIENT_ID
vercel env add GOOGLE_CLIENT_SECRET
vercel env add GOOGLE_REDIRECT_URI
vercel env add SESSION_SECRET

# Deploy to production
vercel --prod
```

### Step 4: Configure the Chrome Extension
1. Open Google Chrome and navigate to `chrome://extensions/`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked** and select the `extension/` directory.
4. Click the extension icon in your Chrome toolbar.
5. Click **⚙️ Settings**, enter your Vercel deployment URL (e.g. `https://belvo-attendance.vercel.app`), and click **Save**.
6. The extension is now live and communicating with your cloud backend!

---

## 13. Local Development & CLI Operations

The application supports complete local execution for developers and automated terminal pipelines:

### 1. Run Local API Server (For Extension Local Testing)
```bash
python main.py --server
```
*Starts the FastAPI backend at `http://127.0.0.1:8000`.*

### 2. Run CLI in Mock Mode (Default)
```bash
python main.py --mode mock --date 2026-09-17
```
*Processes offline test emails and writes `output/attendance.xlsx`.*

### 3. Run CLI in Gmail Mode
```bash
python main.py --mode gmail --date 2026-09-17
```
*Queries the live Gmail inbox via OAuth 2.0.*

### 4. Run Streamlit Analytics UI
```bash
python main.py --ui
```
*Launches the interactive dashboard in your default browser.*

### Full CLI Options Reference
```
options:
  -h, --help            show this help message and exit
  --date DATE           Target work date (YYYY-MM-DD), default: 2026-09-17
  --mode {mock,gmail}   Email provider mode: 'mock' (default) or 'gmail'
  --employees EMPLOYEES Path to employees CSV (default: sample_data/employees.csv)
  --leave LEAVE         Path to leave CSV (default: sample_data/leave.csv)
  --mock-data MOCK_DATA Path to mock emails JSON (default: sample_data/mock_emails.json)
  --output OUTPUT       Output path for Excel report (default: output/attendance.xlsx)
  --ui                  Launch the interactive Streamlit web dashboard
  --server, --api       Launch the FastAPI backend server for the Chrome Extension
  --port PORT           Port for the API server (default: 8000)
```

---

## 14. Project Directory Structure

```
Belvo/
├── api/
│   └── index.py             # Vercel serverless entrypoint exporting FastAPI app
├── app/
│   ├── __init__.py          # Package initialization
│   ├── api.py               # FastAPI REST service & CORS configuration
│   ├── attendance.py        # Core AttendanceEngine & P/A/L business logic
│   ├── config.py            # Environment settings, constants, and paths
│   ├── excel_writer.py      # Dual-sheet OpenPyXL workbook generator & in-memory exporter
│   ├── gmail_client.py      # Abstract EmailProvider, GmailProvider, MockEmailProvider
│   ├── models.py            # Dataclasses & Enums (AttendanceRecord, ProcessingLogEntry, etc.)
│   ├── oauth.py             # Web-Server OAuth flow & Fernet symmetric token encryption
│   ├── parser.py            # RFC 5322 parsing, subject regex matching, date extraction
│   └── streamlit_app.py     # Streamlit web dashboard interface
├── credentials/
│   └── credentials.json.example  # Example credentials template
├── extension/               # Complete Manifest V3 Chrome Extension
│   ├── icons/               # 16px, 48px, 128px PNG icons
│   │   ├── icon16.png
│   │   ├── icon48.png
│   │   └── icon128.png
│   ├── manifest.json        # Manifest V3 specification
│   ├── popup.css            # UI styling and status badges
│   ├── popup.html           # Popup HTML layout
│   └── popup.js             # Client logic connecting to cloud/local API
├── output/
│   └── attendance.xlsx      # Generated sample Excel attendance report
├── sample_data/
│   ├── employees.csv        # Configurable expected employee roster (5 employees)
│   ├── leave.csv            # Approved leave registry
│   └── mock_emails.json     # 9 mock emails covering all edge case scenarios
├── tests/
│   ├── test_api.py          # FastAPI endpoint integration tests (5 tests)
│   ├── test_attendance.py   # Core engine, parsing, and precedence tests (14 tests)
│   └── test_cloud_oauth.py  # Web OAuth, Fernet encryption, and serverless tests (9 tests)
├── .gitignore               # Strict exclusion of tokens, secrets, cache, and env files
├── credentials.json.example # Root-level template for OAuth credentials
├── main.py                  # CLI application entrypoint
├── README.md                # Technical source documentation
├── requirements.txt         # Project dependencies
└── vercel.json              # Vercel serverless routing configuration
```

---

## 15. Automated Testing Suite

The repository features an exhaustive automated test suite with **28 passing tests** verifying the core engine, edge-case resolution, REST endpoints, Web OAuth flows, and serverless Excel streaming.

### Running the Test Suite
```bash
python -m pytest -v
```

### Verified Test Results
```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\pavan\OneDrive\Pictures\Desktop\Belvo
collected 28 items

tests/test_api.py::test_api_status PASSED                                [  3%]
tests/test_api.py::test_api_scan_mock_mode PASSED                        [  7%]
tests/test_api.py::test_api_scan_invalid_date PASSED                     [ 10%]
tests/test_api.py::test_api_process_mock_mode PASSED                     [ 14%]
tests/test_api.py::test_api_download_excel PASSED                        [ 17%]
tests/test_attendance.py::TestEmailParser::test_extract_clean_email PASSED [ 21%]
tests/test_attendance.py::TestEmailParser::test_valid_subject_formats PASSED [ 25%]
tests/test_attendance.py::TestEmailParser::test_malformed_subjects PASSED [ 28%]
tests/test_attendance.py::TestEmailParser::test_missing_subject PASSED   [ 32%]
tests/test_attendance.py::TestAttendanceEngine::test_normal_present PASSED [ 35%]
tests/test_attendance.py::TestAttendanceEngine::test_absent PASSED       [ 39%]
tests/test_attendance.py::TestAttendanceEngine::test_leave_status PASSED [ 42%]
tests/test_attendance.py::TestAttendanceEngine::test_leave_precedence_over_report PASSED [ 46%]
tests/test_attendance.py::TestAttendanceEngine::test_duplicate_reports_deduplicated PASSED [ 50%]
tests/test_attendance.py::TestAttendanceEngine::test_late_report_handling PASSED [ 53%]
tests/test_attendance.py::TestAttendanceEngine::test_malformed_and_missing_subjects PASSED [ 57%]
tests/test_attendance.py::TestAttendanceEngine::test_unknown_sender PASSED [ 60%]
tests/test_attendance.py::TestAttendanceEngine::test_case_insensitive_matching PASSED [ 64%]
tests/test_attendance.py::TestExcelWriter::test_excel_export_structure PASSED [ 67%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_auth_google_json_response PASSED [ 71%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_auth_google_redirect PASSED [ 75%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_auth_callback_missing_code PASSED [ 78%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_auth_callback_error_param PASSED [ 82%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_auth_callback_successful_exchange PASSED [ 85%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_session_token_encryption_and_decryption PASSED [ 89%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_auth_status_with_valid_and_invalid_token PASSED [ 92%]
tests/test_cloud_oauth.py::TestCloudOAuthFlow::test_auth_logout PASSED   [ 96%]
tests/test_cloud_oauth.py::TestServerlessExcelBytes::test_export_attendance_bytes PASSED [100%]

======================= 28 passed, 2 warnings in 1.74s ========================
```

---

## 16. Sample Deterministic Execution Output

Executing against the mock dataset for date `2026-09-17` yields deterministic, verifiable results:

### Terminal Output:
```
==================================================
  Belvo Attendance Tracker
  Target Date: 2026-09-17 | Mode: MOCK
==================================================
Loaded 5 expected employees and 1 leave entries.
Fetching work reports...
Processing 9 emails...
Valid reports:     3
Duplicates:        1
Late reports:      1
Malformed subjects:1
Missing subjects:  1
Unknown senders:   1
--------------------------------------------------
Attendance generated successfully.
P (Present): 3
A (Absent):  1
L (Leave):   1
Output: output\attendance.xlsx
--------------------------------------------------

Attendance Summary Table:
Date         | Person             | Email                        | Status
------------------------------------------------------------------------
2026-09-17   | Pavan Atchyuta     | pavan@example.com            | P     
2026-09-17   | Thrija             | thrija@example.com           | P     
2026-09-17   | Sai                | sai@example.com              | P     
2026-09-17   | Ravi               | ravi@example.com             | A     
2026-09-17   | Ananya             | ananya@example.com           | L     
```

### Scenario Breakdown:
1. **Pavan Atchyuta (`P`)**: Sent a valid report (`msg_001`) and a duplicate report 10 minutes later (`msg_002`). The duplicate was deduplicated into a single Present record.
2. **Thrija (`P`)**: Sent a valid report using a colon delimiter (`msg_003`). Correctly parsed and marked Present.
3. **Sai (`P`)**: Sent a late report received at 01:15 AM on 2026-09-18 (`msg_004`). Because the subject explicitly designated `2026-09-17`, it was accepted as Present for the intended date.
4. **Ravi (`A`)**: Sent one email with subject `"Hello team"` (`msg_005`) and one with an empty subject (`msg_006`). Both were rejected as malformed/missing. With no valid report, Ravi is marked Absent.
5. **Ananya (`L`)**: Listed in `leave.csv` for `2026-09-17`. Even though she submitted a valid report (`msg_007`), approved leave took precedence, resulting in status **`L`**.
6. **Unknown Contractor (Ignored)**: Sent a valid report format (`msg_008`), but because the sender address was not in `employees.csv`, the email was audited and safely excluded from the roster.

---

## 17. Security & Credential Hygiene

1. **Least-Privilege Gmail Access**: Uses strictly `https://www.googleapis.com/auth/gmail.readonly`. The application cannot compose, send, modify, trash, or delete any user emails.
2. **Zero DOM Scraping**: The Chrome extension does not inspect web pages or inject scripts into the Gmail DOM. All data access occurs over secure, official Google APIs.
3. **Server-Side Token Encryption**: Session tokens passed to the browser are symmetrically encrypted via Fernet. Plaintext refresh tokens and client secrets are never exposed to the extension frontend.
4. **Zero-Trust Git Configuration**: The repository `.gitignore` strictly excludes credentials, tokens, environment files, and local output:
   ```gitignore
   credentials.json
   **/credentials.json
   token.json
   **/token.json
   *.env
   .env*
   ```
5. **No Password Storage**: The system never handles, sees, or stores Google passwords. All authentication uses standard OAuth 2.0 authorization grants.

---

## 18. Final Project Status

| Component | Status | Implementation Details |
| :--- | :---: | :--- |
| **Attendance Processing Engine** | **Completed** | Deterministic P/A/L logic, leave precedence, and edge case rules in `app/attendance.py` |
| **Gmail API Integration** | **Completed** | Implemented in `app/gmail_client.py` using `google-api-python-client` |
| **Cloud Web OAuth Flow** | **Completed** | Implemented in `app/oauth.py` and `app/api.py` with redirect and JSON support |
| **Stateless Token Encryption** | **Completed** | AES-128 Fernet encryption (`cryptography`) protecting refresh tokens |
| **Vercel Serverless Hosting** | **Completed** | Configured via `vercel.json` and `api/index.py` for serverless execution |
| **Chrome Extension (MV3)** | **Completed** | Modern popup with OAuth connect, live metrics, and direct Excel download |
| **In-Memory Excel Streaming** | **Completed** | Implemented in `app/excel_writer.py` via `io.BytesIO` for serverless environments |
| **Mock Mode Pipeline** | **Completed** | Full offline execution with 9 edge-case email fixtures (`P:3, A:1, L:1`) |
| **CLI & Streamlit Interfaces** | **Completed** | Maintained in `main.py` and `app/streamlit_app.py` |
| **Automated Test Suite** | **Completed** | 28/28 tests passing (`pytest`) covering engine, API, OAuth, and serverless logic |
| **Documentation & Security** | **Completed** | Complete README source documentation and verified `.gitignore` protection |

---

## 19. Conclusion

The **Belvo Attendance Tracker** provides a complete, modern, and production-ready solution for automated attendance tracking from Gmail work reports. By transforming the original desktop-only application into a cloud-ready system, it enables zero-install usage via a **Manifest V3 Chrome Extension** backed by a **Vercel serverless FastAPI backend** while retaining full capability for local terminal automation.

With a **100% passing test suite (28/28 tests)**, robust handling of all real-world email edge cases, strict leave precedence enforcement, and cryptographic session protection, the system represents an optimal balance of engineering rigor, operational security, and user convenience.
