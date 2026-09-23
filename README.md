# BELVO ATTENDANCE TRACKER

### Automated Employee Attendance Processing from Gmail Work Reports

---

## Project Information

- **Project**: Belvo Attendance Tracker
- **Purpose**: Automated employee attendance processing from Gmail work reports
- **Input**: Daily Work Report emails
- **Integration**: Gmail API + Google OAuth 2.0
- **Access**: Gmail read-only (`https://www.googleapis.com/auth/gmail.readonly`)
- **Backend**: Python (3.10+) with FastAPI local service
- **Interfaces**: Chrome Extension (Manifest V3), CLI (`main.py`), and Streamlit Web UI
- **Output**: Attendance Excel report (`output/attendance.xlsx`)

---

## 2. Executive Summary

The **Belvo Attendance Tracker** is an automated attendance-processing solution engineered to eliminate the manual overhead of daily attendance reconciliation. In distributed and asynchronous workplaces, team members confirm their daily activities by submitting end-of-day work-report emails. Manually cross-referencing individual inboxes against employee rosters and leave schedules is labor-intensive, slow, and prone to human error.

This system connects directly to a designated mailbox using the official **Gmail API** with **OAuth 2.0 authentication**, enforcing a strict **read-only scope** (`gmail.readonly`) that guarantees no messages can be altered, moved, trashed, or sent. Incoming messages are retrieved and evaluated by a deterministic parsing engine that inspects RFC 5322 email headers, extracts explicit ISO calendar work dates from standardized subject lines (`Daily Work Report - YYYY-MM-DD`), and normalizes sender addresses.

The normalized reports are fed into a centralized **Attendance Engine** that cross-references a configurable employee roster (`employees.csv`) and an approved leave schedule (`leave.csv`). The engine deterministically classifies every expected team member as **Present (`P`)**, **Absent (`A`)**, or on **Leave (`L`)**, applying strict precedence rules (such as leave overriding submitted reports) and resolving real-world edge cases like duplicate submissions, late-night filings, malformed subjects, and unauthorized senders.

The system produces a structured, presentation-ready Excel workbook (`output/attendance.xlsx`) using `openpyxl`. The workbook contains two distinct sheets: an **`Attendance`** sheet with visual color fills and frozen headers for management review, and an exhaustive **`Processing Log`** sheet that records every ingestion decision and rejected message for full auditability.

Users can interact with the system through three complementary interfaces:
1. **Chrome Extension (Manifest V3)**: A lightweight browser popup to scan inboxes, trigger processing, view P/A/L metrics, and download the Excel sheet directly from the browser.
2. **Command-Line Interface (CLI)**: A direct terminal tool for automated runs, scripting, and batch operations (`main.py`).
3. **Streamlit Web Dashboard**: An interactive local analytics dashboard (`python main.py --ui`).

A self-contained **Mock Mode** is built-in across all interfaces, enabling complete offline testing, demonstrations, and automated verification without requiring Google Cloud credentials.

---

## 3. Project Objectives

The core objectives implemented in the Belvo Attendance Tracker are:

1. **Automate Collection**: Programmatically query and retrieve employee work-report emails from a Gmail inbox using modern REST APIs.
2. **Reduce Manual Overhead**: Replace manual inbox searching and spreadsheet data entry with a one-command or one-click automated pipeline.
3. **Deterministic Attendance Evaluation**: Apply consistent, unambiguous business rules to classify every expected person as Present (`P`), Absent (`A`), or on Leave (`L`).
4. **Handle Missing Reports**: Accurately mark expected employees as Absent (`A`) when no qualifying report is received and no approved leave exists.
5. **Handle Duplicate Submissions**: Consolidate multiple reports sent by the same employee for the same date into a single attendance record without double-counting.
6. **Handle Late Submissions**: Accurately associate reports received past midnight with their intended work date based on explicit subject metadata rather than receipt timestamps.
7. **Handle Malformed & Missing Subjects**: Refuse to guess sender intent; safely ignore invalid or blank subjects while capturing the occurrence in an audit log.
8. **Handle Unknown Senders**: Isolate and ignore emails from unlisted senders, ensuring external parties cannot alter internal attendance rosters.
9. **Structured Excel Reporting**: Generate a styled, dual-sheet spreadsheet with visual color badges and complete decision traceability.
10. **Chrome Extension Interface**: Provide a seamless Manifest V3 browser extension for one-click operations while preserving the backend engine.
11. **Zero-Trust Security**: Maintain strict read-only Gmail access, zero DOM scraping, local credential isolation, and clean version-control protection against accidental secret leakage.

---

## 4. System Workflow

The architecture follows a modular, unidirectional data pipeline:

```
Chrome Extension (Manifest V3 Popup)  /  CLI (main.py)  /  Streamlit UI
                             │
                             ▼ (REST API: http://127.0.0.1:8000)
                  FastAPI Backend (app/api.py)
                             │
                             ▼
                    Email Source Selection
                 ┌───────────┴───────────┐
                 ▼                       ▼
       Gmail API (OAuth2)         Mock Email Store
       (gmail.readonly)          (mock_emails.json)
                 │                       │
                 └───────────┬───────────┘
                             ▼
             Email Provider (app/gmail_client.py)
            Extracts Message ID, Sender, Subject,
                    Timestamp & Snippet
                             │
                             ▼
           Deterministic Parser (app/parser.py)
           • RFC 5322 Address Normalization
           • Strict Regex Subject Matcher
           • Explicit Work-Date Extraction
           • Late Submission Flagging
                             │
                             ▼
          Attendance Engine (app/attendance.py)
           • Match against sample_data/employees.csv
           • Cross-reference sample_data/leave.csv
           • Apply Leave Precedence (L > P > A)
           • Deduplicate Same-Day Submissions
                             │
                             ▼
           Excel Generator (app/excel_writer.py)
           • Sheet 1: "Attendance" (Date, Person, Email, Status)
           • Sheet 2: "Processing Log" (Timestamp, Category, Action, Details)
                             │
                             ▼
                  output/attendance.xlsx
                             │
                             ▼
      Direct Download via Extension / Web API / Local Disk
```

### Pipeline Stage Details

1. **User Action (Chrome Extension / CLI / UI)**:
   - User selects an attendance date and mode (Gmail API vs Mock Mode).
   - The Chrome extension issues requests to `http://127.0.0.1:8000` via `popup.js`.
2. **Email Ingestion (`app/gmail_client.py`)**:
   - In **Gmail Mode**: Authenticates via Google OAuth 2.0 Desktop flow, builds date-window queries (`subject:"Daily Work Report" after:... before:...`), and retrieves message headers (`From`, `Subject`, `Date`) and snippet content.
   - In **Mock Mode**: Loads pre-defined email fixtures from `sample_data/mock_emails.json` directly into standard `EmailMessage` models without network calls.
3. **Deterministic Parsing (`app/parser.py`)**:
   - Parses raw sender headers (e.g. `Pavan Atchyuta <pavan@example.com>`) down to a clean, lowercase email address (`pavan@example.com`).
   - Evaluates the subject line against the strict regex `^\s*daily\s+work\s+report\s*[-:]\s*(\d{4}-\d{2}-\d{2})\s*$`.
   - Validates that the extracted string is a legitimate calendar date via `datetime.strptime`.
   - Compares email receipt timestamp against the extracted work date to flag whether a report was submitted late.
4. **Attendance Determination (`app/attendance.py`)**:
   - Loads the expected roster from `employees.csv` and approved leaves from `leave.csv`.
   - Filters out unknown senders, malformed subjects, and missing subjects into the processing log.
   - Evaluates each expected employee:
     - If the employee has an entry in `leave.csv` for the target date &rarr; **`L`** (Leave).
     - Else if one or more valid work reports exist for that date &rarr; **`P`** (Present).
     - Else &rarr; **`A`** (Absent).
5. **Report Generation (`app/excel_writer.py`)**:
   - Builds an openpyxl workbook with frozen top panes, navy headers, grid lines, and custom column widths.
   - Applies cell fill formatting to the Status column (Green for `P`, Red for `A`, Amber for `L`).
   - Appends all audit log entries to the `Processing Log` sheet.
6. **Download / Delivery**:
   - The extension triggers an automatic download of `attendance.xlsx` via the browser's downloads API or blob response.

---

## 5. Technology Stack

The project uses the following technologies and libraries:

| Layer | Component / Package | Version / Specification | Purpose |
| :--- | :--- | :--- | :--- |
| **Language** | Python | `>=3.10` (Tested on `3.13.14`) | Core runtime language |
| **API Layer** | FastAPI & Uvicorn | `fastapi>=0.100.0`, `uvicorn>=0.20.0` | Local REST service connecting extension to engine |
| **Frontend** | Chrome Extension | Manifest V3 (HTML5, CSS3, JS) | Browser popup interface for scanning and processing |
| **Email API** | Google Gmail API v1 | `google-api-python-client>=2.100.0` | Querying and fetching email message metadata |
| **OAuth 2.0 Flow** | Google Auth OAuthlib | `google-auth-oauthlib>=1.0.0` | Desktop client authorization and local server callback |
| **Auth Transport** | Google Auth HTTP Lib2 | `google-auth-httplib2>=0.2.0` | HTTP transport layer for token refresh and API calls |
| **Spreadsheet Engine** | OpenPyXL | `openpyxl>=3.1.2` | Native `.xlsx` workbook generation, styling, and formatting |
| **Web Dashboard** | Streamlit | `streamlit>=1.30.0` | Interactive UI for run execution, metrics, and file download |
| **Testing** | Pytest | `pytest>=8.0.0` | Automated test suite execution (Engine + API) |
| **Date Utilities** | Python Dateutil | `python-dateutil>=2.8.2` | Parsing RFC 2822 email timestamps |
| **Offline Testing** | Mock Email Provider | Custom (`app/gmail_client.py`) | Local JSON-backed email simulation for zero-dependency execution |

---

## 6. Gmail Integration

The Gmail integration is encapsulated entirely inside `app/gmail_client.py`.

### Architectural Design
- **Abstract Base Class (`EmailProvider`)**: Defines the standard interface `fetch_messages(target_date: str) -> List[EmailMessage]`.
- **`GmailProvider`**: Implements the live Gmail integration.
- **`MockEmailProvider`**: Implements the offline mock provider using file fixtures.

### Gmail API Scope
The application requests only a single, read-only OAuth scope:
```
https://www.googleapis.com/auth/gmail.readonly
```
This guarantees:
- **No email deletion**: The application cannot delete or trash messages.
- **No email modification**: The application cannot mark messages as read, change labels, or draft replies.
- **No message sending**: The application cannot compose or transmit emails.

### Message Retrieval Strategy
To capture late-night reports that arrive after midnight, the search window in `GmailProvider.fetch_messages()` queries messages spanning from one day prior (`target_date - 1 day`) to two days after (`target_date + 2 days`):
```python
query = f'subject:"Daily Work Report" after:{after_date} before:{before_date}'
results = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
```
For every message ID returned, `service.users().messages().get(..., format="metadata", metadataHeaders=["From", "Subject", "Date"])` extracts the specific header fields. The resulting data is translated into unified `EmailMessage` objects and passed into the parser.

---

## 7. Authentication & Configuration

The application uses Google OAuth 2.0 Desktop Application credentials.

### Authentication Lifecycle
1. **Credentials Detection**: On startup, `app/config.py` searches for client credentials in candidate locations:
   - `credentials/credentials.json`
   - `credentials.json` (project root)
2. **Token Inspection**: If `token.json` exists, credentials are restored and checked for validity.
3. **Token Refresh**: If the access token has expired but contains a valid `refresh_token`, it is silently refreshed in the background via `google.auth.transport.requests.Request()`.
4. **Local Consent Flow**: If no token exists, `InstalledAppFlow.from_client_secrets_file(..., scopes)` opens a local web browser window allowing the user to sign in to Google and authorize read-only access. The generated credentials are then written to `token.json`.

### Safe Credentials Template
A template file is provided at `credentials/credentials.json.example` and `credentials.json.example`:
```json
{
  "installed": {
    "client_id": "YOUR_CLIENT_ID.apps.googleusercontent.com",
    "project_id": "your-google-cloud-project-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "YOUR_CLIENT_SECRET",
    "redirect_uris": [
      "http://localhost"
    ]
  }
}
```

> **Security Rule**: Actual `credentials.json` and `token.json` files must never be committed. They are covered by `.gitignore`.

---

## 8. Attendance Processing

The attendance evaluation is performed in `app/attendance.py` by `AttendanceEngine.process_attendance()`.

### The Deterministic P / A / L Rules
Attendance status is evaluated for **every expected employee** in the configured roster for a selected target date:

- **`P` (Present)**: A valid work report was received for that employee, matching the target date.
- **`A` (Absent)**: No valid work report was received, and the employee is not recorded as on leave.
- **`L` (Leave)**: The employee is explicitly listed in the leave schedule for that date.

### Strict Precedence Hierarchy
```
Is (employee.email, target_date) in leave schedule?
       │
      ├─── YES ───► Status = "L" (Leave Precedence)
      │
       └─── NO  ───► Did employee submit a valid report for target_date?
                            │
                           ├─── YES ───► Status = "P" (Present)
                           │
                            └─── NO  ───► Status = "A" (Absent)
```

**Key Precedence Invariant**: Leave strictly overrides Present. If an employee is scheduled on leave on `2026-09-17` but nevertheless submits a valid work report, their status remains **`L`**. The occurrence is accepted and documented in the audit log as:
`"On leave as recorded in leave registry. (Work report also received, overridden by leave precedence)."`

---

## 9. Email Parsing

Email normalization and subject line validation are performed by `app/parser.py`.

### Sender Extraction & Normalization
1. The header value is parsed using `email.utils.parseaddr` to separate display names from addresses (e.g. `"Pavan Atchyuta <pavan@example.com>"` &rarr; `"pavan@example.com"`).
2. The extracted address is converted to lowercase and stripped of leading and trailing whitespace.
3. The normalized address is cross-referenced against the `email` field of expected employees.

### Subject Format Specification
The parser enforces strict adherence to the pattern:
```regex
^\s*daily\s+work\s+report\s*[-:]\s*(\d{4}-\d{2}-\d{2})\s*$
```
*(Compiled with `re.IGNORECASE`).*

- **Prefix**: `Daily Work Report`
- **Separator**: Hyphen (`-`) or colon (`:`)
- **Date**: ISO 8601 calendar date (`YYYY-MM-DD`)
- **Whitespace**: Tolerant of extra spaces around delimiters and margins.

#### Accepted Subject Lines:
- `Daily Work Report - 2026-09-17`
- `daily work report - 2026-09-17`
- `Daily Work Report: 2026-09-17`
- `  Daily Work Report - 2026-09-17  `
- `Daily Work Report: 2026-09-20`

#### Rejected Subject Lines:
- `Hello`
- `Work`
- `Daily update`
- `Report`
- `Daily Work Report` (missing date)
- `Daily Work Report - yesterday` (relative wording not supported)
- `Daily Work Report - 17-09-2026` (invalid date format)
- `Daily Work Report - 2026-99-99` (invalid calendar day)

### Non-Guessing Policy
If an email subject is missing or malformed, the system does not attempt to guess or inspect email body contents. The message is classified as `MISSING_SUBJECT` or `MALFORMED_SUBJECT`, ignored for attendance, and recorded in the audit log.

---

## 10. Employee Configuration

Expected employees are configured externally via `sample_data/employees.csv`.

### CSV Structure
```csv
name,email
Pavan Atchyuta,pavan@example.com
Thrija,thrija@example.com
Sai,sai@example.com
Ravi,ravi@example.com
Ananya,ananya@example.com
```

### Identity Rules
- **Primary Identity**: The employee's normalized email address is the unique primary key.
- **Roster Stability**: The generated attendance report always outputs **exactly one row per expected employee** in the order defined in the CSV.
- **Configurability**: Custom rosters can be passed via the `--employees PATH` CLI parameter without altering code.

---

## 11. Leave Configuration

Approved employee leaves are configured externally via `sample_data/leave.csv`.

### CSV Structure
```csv
email,date
ananya@example.com,2026-09-17
```

### Integration Rules
- Matches composite key `(normalized_email, date)`.
- If a match is found for the evaluated date, the employee is assigned status **`L`**.
- Leave entries take precedence over any valid work report submitted by that employee on that day.
- Custom leave files can be passed via the `--leave PATH` CLI parameter.

---

## 12. Edge Case Handling

The following table documents the exact system behavior implemented in the codebase for every edge case:

| Edge Case | System Behavior | Log Category | Status Assigned |
| :--- | :--- | :--- | :---: |
| **Duplicate report** | The first valid report marks the employee as Present. Any subsequent valid reports from the same person for the same work date are deduplicated. Only one attendance row is output. | `DUPLICATE_REPORT` | **P** |
| **Very late report** | If an email for work date `2026-09-17` arrives past midnight (e.g. `2026-09-18 01:15 AM`), the system associates it with `2026-09-17` using the explicit subject date. | `LATE_REPORT` | **P** (for 2026-09-17) |
| **Missing subject** | The email has an empty or whitespace-only subject line. It is ignored and logged. Senders remain Absent unless on leave. | `MISSING_SUBJECT` | **A** |
| **Malformed subject** | The subject does not match `Daily Work Report - YYYY-MM-DD` (e.g., `"Hello team"`). It is ignored and logged. Senders remain Absent unless on leave. | `MALFORMED_SUBJECT` | **A** |
| **Unknown sender** | A valid report format is received from an address not listed in `employees.csv`. It is ignored and logged; no employee is added to the roster. | `UNKNOWN_SENDER` | *Excluded from roster* |
| **Leave + valid report** | An employee is in `leave.csv` and also submitted a valid work report for that same date. Leave strictly takes precedence. | `VALID_REPORT` | **L** |
| **Date mismatch** | A valid report subject specifies a date other than the target date (e.g. `2026-09-16` report evaluated during a `2026-09-17` run). The report is ignored for the current run. | `VALID_REPORT` | *Ignored for target date* |

---

## 13. Duplicate Report Handling

Employees occasionally submit multiple work reports for the same day (e.g., correcting notes or sending an addendum).

### Implementation Details
- In `app/attendance.py`, `AttendanceEngine` tracks accepted reports in `valid_reports_by_employee: Dict[str, List[ParsedReport]]`.
- The first valid submission is recorded and audited as `VALID_REPORT` (or `LATE_REPORT`).
- Subsequent submissions for that employee on that work date trigger:
  ```python
  stats["duplicate_reports"] += 1
  valid_reports_by_employee[normalized_sender].append(parsed)
  processing_logs.append(
      ProcessingLogEntry(
          category=LogCategory.DUPLICATE_REPORT,
          action="Deduplicated",
          details=f"Multiple reports received from '{normalized_sender}' for {target_date}. Attendance row remains unique."
      )
  )
  ```
- In the final attendance sheet, the employee receives **exactly one row** with status **`P`**. The note specifies: `"Present (2 reports received, deduplicated)"`.

---

## 14. Late Report Handling

In real work environments, employees often submit daily reports late at night or early the following morning.

### Implementation Details
- The application separates the **receipt timestamp** (`received_at`) from the **work date** (`extracted_date`).
- **Receipt Timestamp**: Extracted from the RFC 2822 `Date` email header (e.g. `2026-09-18T01:15:00+00:00`).
- **Work Date**: Extracted from the subject (e.g. `Daily Work Report - 2026-09-17` &rarr; `2026-09-17`).
- When processing date `2026-09-17`, the email is matched to the work date `2026-09-17`.
- Because `received_at.date() > extracted_date`, it is categorized as `LATE_REPORT`.
- The employee is correctly established as **`P` (Present)** for `2026-09-17`, with an audit note indicating late submission.

---

## 15. Malformed / Missing Subject Handling

To ensure data integrity, the system strictly enforces the principle of non-guessing:

- **Missing Subjects**: Messages with no subject or empty string headers are flagged as `MISSING_SUBJECT` with details `"Email subject is missing or empty. Cannot determine work report."`
- **Malformed Subjects**: Messages with subjects like `"Daily update"`, `"Hello team"`, or `"Daily Work Report"` without a valid ISO date are flagged as `MALFORMED_SUBJECT` with details `"Subject '...' does not match pattern 'Daily Work Report - YYYY-MM-DD'."`
- **Impact**: Both classifications result in `is_valid = False`. They cannot mark an employee present. If the sender is an expected employee who submitted no other valid report, they are marked **`A` (Absent)**.

---

## 16. Unknown Senders

External emails, vendor notices, or unlisted contractor messages may enter the mailbox.

### Implementation Details
- When a report matches the subject pattern, `app/attendance.py` checks whether `normalized_sender in self.employee_by_email`.
- If the sender is not present in `employees.csv`:
  - It is classified as `LogCategory.UNKNOWN_SENDER`.
  - Action taken: `"Ignored"`.
  - Details recorded: `"Sender '...' is not in the expected employee list. Ignored for attendance."`
  - The sender is **never** added to the employee list.
  - No existing employee's attendance status is affected.

---

## 17. Mock / Test Mode

Mock Mode allows full testing and evaluation of the end-to-end pipeline without needing Google Cloud credentials or internet access.

### Why Mock Mode Exists
1. **Zero-Dependency Onboarding**: New developers and evaluators can immediately execute the project without setting up Google Cloud OAuth.
2. **Deterministic Reproducibility**: Guarantees repeatable test scenarios that cover all required edge cases.
3. **Safe Demonstration**: Allows demonstrating the system without exposing live personal or company mailboxes.

### Mock Files
- **`sample_data/employees.csv`**: Team roster of 5 members.
- **`sample_data/leave.csv`**: Leave record for `ananya@example.com` on `2026-09-17`.
- **`sample_data/mock_emails.json`**: 9 mock email objects simulating:
  1. `msg_001`: Pavan Atchyuta (On-time valid report) &rarr; `P`
  2. `msg_002`: Pavan Atchyuta (Duplicate report sent 10 minutes later) &rarr; `P` (deduplicated)
  3. `msg_003`: Thrija (Valid report with colon separator) &rarr; `P`
  4. `msg_004`: Sai (Late report received 01:15 AM next morning, whitespace padding) &rarr; `P`
  5. `msg_005`: Ravi (Malformed subject `"Hello team"`) &rarr; `A`
  6. `msg_006`: Ravi (Empty subject line) &rarr; `A`
  7. `msg_007`: Ananya (Valid report while on scheduled leave) &rarr; `L` (Leave precedence)
  8. `msg_008`: External contractor (Unknown sender) &rarr; Ignored
  9. `msg_009`: Pavan Atchyuta (Report for `2026-09-16`) &rarr; Ignored for `2026-09-17`

### Execution
- In CLI: `python main.py --mode mock --date 2026-09-17`
- In Extension: Select **"Mock Mode"** from the dropdown and click **Process Attendance**.

---

## 18. Excel Reporting

The application generates an openpyxl workbook saved at `output/attendance.xlsx`.

### Sheet 1: `Attendance`
Contains the final daily roster. Exactly one row per expected employee.

| Column Name | Description | Cell Alignment | Visual Styling |
| :--- | :--- | :--- | :--- |
| **Date** | Selected work date (`YYYY-MM-DD`) | Center | Regular text |
| **Person** | Employee name from `employees.csv` | Left | Regular text |
| **Email** | Employee email from `employees.csv` | Left | Regular text |
| **Status** | Final calculated status: `P`, `A`, or `L` | Center | Bold text with specific background fills |

#### Status Styling Palette:
- **`P` (Present)**: Soft green background fill (`#D4EDDA`) with dark green bold font (`#155724`).
- **`A` (Absent)**: Soft red background fill (`#F8D7DA`) with dark red bold font (`#721C24`).
- **`L` (Leave)**: Soft amber background fill (`#FFF3CD`) with dark brown bold font (`#856404`).

#### Layout Enhancements:
- **Header Fill**: Dark Navy (`#1F4E79`) with white bold text (`#FFFFFF`).
- **Row Heights**: Header row is 26pt; data rows are 22pt.
- **Freeze Panes**: Header row is frozen (`freeze_panes = "A2"`).
- **Auto-fitted Widths**: Column widths are dynamically computed with safety margins.
- **Grid Lines**: Explicitly enabled (`ws.views.sheetView[0].showGridLines = True`).

### Sheet 2: `Processing Log`
Provides complete audit visibility into every email evaluated.

| Column Name | Description | Alignment |
| :--- | :--- | :--- |
| **Timestamp** | ISO receipt timestamp or evaluation time | Center |
| **Category** | Reason code enum (e.g. `VALID_REPORT`, `DUPLICATE_REPORT`) | Center |
| **Sender** | Raw sender header string | Left |
| **Subject** | Raw subject string or `(empty)` | Left |
| **Target Date** | The attendance date evaluated | Center |
| **Action** | Outcome: `Accepted`, `Accepted (Late)`, `Deduplicated`, `Ignored` | Center |
| **Details** | Specific rationale explaining the categorization decision | Left |

---

## 19. Processing / Audit Log

The `Processing Log` sheet (and CLI logging) categorizes every message under standardized enumerations from `app.models.LogCategory`:

| Category Enum | When Used | Example Trigger | Action Recorded |
| :--- | :--- | :--- | :--- |
| `VALID_REPORT` | Email subject matches pattern and sender is an expected employee on time. | `"Daily Work Report - 2026-09-17"` | `Accepted` |
| `DUPLICATE_REPORT` | Employee already has a valid report recorded for this work date. | Second email sent by Pavan at 18:10 | `Deduplicated` |
| `LATE_REPORT` | Email received after the work date, but subject explicitly identifies the work date. | Email received 2026-09-18 01:15 AM | `Accepted (Late)` |
| `MALFORMED_SUBJECT` | Subject does not match regex or contains invalid date values. | `"Hello team"` or `"Daily update"` | `Ignored` |
| `MISSING_SUBJECT` | Email has no subject or whitespace-only subject. | Subject is `""` or `None` | `Ignored` |
| `UNKNOWN_SENDER` | Valid subject format, but sender address not in `employees.csv`. | Report from `partner@external.com` | `Ignored` |

### Value for Auditing & Governance
- **Transparency**: Evaluators and HR administrators can trace why any employee was marked Absent.
- **Troubleshooting**: Senders who used incorrect subject formats can be identified immediately.
- **Security Audit**: Unauthorized senders attempting to submit reports are cataloged without polluting company attendance records.

---

## 20. Chrome Extension (Manifest V3)

The application includes a complete **Chrome Extension (Manifest V3)** located in the `extension/` directory.

### Extension Architecture
```
Chrome Browser
      │
      ▼
extension/popup.html + popup.js
      │
      ▼ (HTTP calls via localhost:8000)
FastAPI Backend (app/api.py)
      │
      ▼
Core Engine (app/attendance.py & app/gmail_client.py)
```

- **Manifest V3 Standards**: Uses declarative Manifest V3 configuration without deprecated background persistent scripts.
- **Zero DOM Scraping**: The extension does not inspect, scrape, or inject scripts into the Gmail web page DOM. It queries the backend API which executes official, authenticated Gmail API queries.
- **Zero Secrets in Frontend**: No OAuth client secrets, API keys, or access tokens exist in the extension files. All sensitive tokens remain securely encapsulated in the local backend (`token.json`).

### File Structure of Extension
```
extension/
├── manifest.json       # Manifest V3 metadata and permissions
├── popup.html          # Clean popup UI
├── popup.css           # Styling with Belvo brand colors and status badges
├── popup.js            # API communication, state management, and file download
└── icons/              # Extension icons (16px, 48px, 128px)
    ├── icon16.png
    ├── icon48.png
    └── icon128.png
```

### Loading the Extension in Google Chrome
1. Open Google Chrome.
2. Navigate to `chrome://extensions/` in the address bar.
3. In the top right corner, toggle **Developer mode** to **ON**.
4. Click the **Load unpacked** button in the top left.
5. In the file browser, select the `extension/` folder inside this repository:
   ```
   c:\Users\pavan\OneDrive\Pictures\Desktop\Belvo\extension
   ```
6. The extension **Belvo Attendance Tracker** will now appear in your Chrome toolbar.
7. Click the extension icon to open the popup dashboard.

---

## 21. Command-Line Operation & API Server

All operations are managed through `main.py`:

### 1. Launch FastAPI Backend Server (For Chrome Extension)
```bash
python main.py --server
```
*Starts the local API service on `http://127.0.0.1:8000` consumed by the Chrome extension.*

*(Optional custom port: `python main.py --server --port 8080`)*

### 2. Run CLI in Mock Mode (Default)
Runs offline attendance processing using the sample email dataset:
```bash
python main.py --mode mock --date 2026-09-17
```

### 3. Run CLI in Gmail Mode
Queries the connected Gmail account via OAuth 2.0:
```bash
python main.py --mode gmail --date 2026-09-17
```

### 4. Launch Streamlit Web UI
Starts the interactive browser analytics dashboard:
```bash
python main.py --ui
```

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

## 22. Project Structure

The actual file tree of the project is structured as follows:

```
Belvo/
├── app/
│   ├── __init__.py          # Package metadata and version info
│   ├── api.py               # FastAPI backend REST service for Chrome Extension
│   ├── attendance.py        # Core AttendanceEngine, CSV loaders, and P/A/L logic
│   ├── config.py            # Path constants, subject regex, and credentials detection
│   ├── excel_writer.py      # openpyxl workbook generator (Attendance & Processing Log)
│   ├── gmail_client.py      # EmailProvider interface, GmailProvider, and MockEmailProvider
│   ├── models.py            # Domain dataclasses & Enums (AttendanceStatus, LogCategory, etc.)
│   ├── parser.py            # RFC 5322 normalization, regex validation, date extraction
│   └── streamlit_app.py     # Streamlit web dashboard implementation
├── credentials/
│   └── credentials.json.example  # Template for Google OAuth 2.0 desktop credentials
├── extension/               # Complete Manifest V3 Chrome Extension
│   ├── icons/               # 16px, 48px, 128px PNG icons
│   │   ├── icon16.png
│   │   ├── icon48.png
│   │   └── icon128.png
│   ├── manifest.json        # Manifest V3 specification
│   ├── popup.css            # Extension styling with status badges
│   ├── popup.html           # Modern popup interface
│   └── popup.js             # Client logic connecting to localhost:8000
├── output/
│   └── attendance.xlsx      # Generated sample Excel attendance report
├── sample_data/
│   ├── employees.csv        # Configurable expected employee roster (name, email)
│   ├── leave.csv            # Configurable leave entries (email, date)
│   └── mock_emails.json     # 9 mock email fixtures covering all edge cases
├── tests/
│   ├── test_api.py          # Automated tests for FastAPI REST endpoints (5 tests)
│   └── test_attendance.py   # Complete automated attendance tests (14 tests)
├── .gitignore               # Excludes secrets (credentials.json, token.json, .env)
├── credentials.json.example # Root-level template for OAuth credentials
├── main.py                  # Primary CLI application entrypoint
├── README.md                # Complete technical source documentation
└── requirements.txt         # Required Python package dependencies
```

---

## 23. Testing

The repository includes a comprehensive automated test suite with **19/19 passing tests** across unit logic and API integration.

### Test Execution Command
```bash
python -m pytest -v
```

### Verified Test Results
```
tests/test_api.py::test_api_status PASSED                                [  5%]
tests/test_api.py::test_api_scan_mock_mode PASSED                        [ 10%]
tests/test_api.py::test_api_scan_invalid_date PASSED                     [ 15%]
tests/test_api.py::test_api_process_mock_mode PASSED                     [ 21%]
tests/test_api.py::test_api_download_excel PASSED                        [ 26%]
tests/test_attendance.py::TestEmailParser::test_extract_clean_email PASSED [ 31%]
tests/test_attendance.py::TestEmailParser::test_valid_subject_formats PASSED [ 36%]
tests/test_attendance.py::TestEmailParser::test_malformed_subjects PASSED [ 42%]
tests/test_attendance.py::TestEmailParser::test_missing_subject PASSED   [ 47%]
tests/test_attendance.py::TestAttendanceEngine::test_normal_present PASSED [ 52%]
tests/test_attendance.py::TestAttendanceEngine::test_absent PASSED       [ 57%]
tests/test_attendance.py::TestAttendanceEngine::test_leave_status PASSED [ 63%]
tests/test_attendance.py::TestAttendanceEngine::test_leave_precedence_over_report PASSED [ 68%]
tests/test_attendance.py::TestAttendanceEngine::test_duplicate_reports_deduplicated PASSED [ 73%]
tests/test_attendance.py::TestAttendanceEngine::test_late_report_handling PASSED [ 78%]
tests/test_attendance.py::TestAttendanceEngine::test_malformed_and_missing_subjects PASSED [ 84%]
tests/test_attendance.py::TestAttendanceEngine::test_unknown_sender PASSED [ 89%]
tests/test_attendance.py::TestAttendanceEngine::test_case_insensitive_matching PASSED [ 94%]
tests/test_attendance.py::TestExcelWriter::test_excel_export_structure PASSED [100%]

============================== 19 passed in 1.71s ==============================
```

**Status: 19/19 automated tests passing.**

---

## 24. Testing & Troubleshooting Journey

During the implementation and verification phases, the following practical issues were encountered and resolved:

### 1. Missing Google API Dependencies
- **Issue**: Initial test execution failed with `ModuleNotFoundError: No module named 'google_auth_oauthlib'`.
- **Resolution**: Ran `pip install -r requirements.txt` to install `google-api-python-client`, `google-auth-oauthlib`, and `google-auth-httplib2`.

### 2. Pytest Executable Discovery on Windows
- **Issue**: Running bare `pytest` in PowerShell returned `The term 'pytest' is not recognized as a cmdlet...` because Python script directories were not added to Windows user PATH.
- **Resolution**: Executed tests consistently using Python module invocation: `python -m pytest -v`.

### 3. OAuth Credentials Location Flexibility
- **Issue**: A user or evaluator might place `credentials.json` either in the root directory or inside the `credentials/` folder.
- **Resolution**: Refactored `app/config.py` with `get_credentials_path()`, which inspects both `BASE_DIR / "credentials" / "credentials.json"` and `BASE_DIR / "credentials.json"`, automatically resolving whichever file exists.

### 4. Recursive Gitignore Protection for Nested Secrets
- **Issue**: A standard `credentials.json` rule in `.gitignore` only ignored root files, leaving `credentials/credentials.json` vulnerable to being tracked.
- **Resolution**: Updated `.gitignore` to include recursive patterns: `**/credentials.json` and `**/token.json`. Verified with `git status -u` that no secrets appear in untracked lists.

### 5. Live Token Refresh Validation
- **Issue**: A test run in Gmail mode encountered an expired OAuth access token.
- **Resolution**: Verified that `GmailProvider._get_credentials()` automatically invoked `creds.refresh(Request())` against Google OAuth token endpoints, refreshed the token without user intervention, and updated `token.json` on disk.

### 6. Chrome Extension Cross-Origin Requests
- **Issue**: Chrome Extension popups running under origin `chrome-extension://...` require CORS authorization to call `http://127.0.0.1:8000`.
- **Resolution**: Configured `CORSMiddleware` in `app/api.py` with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, and `allow_headers=["*"]`.

---

## 25. Security Practices

The Belvo Attendance Tracker follows industry-standard security and credential hygiene:

1. **Least-Privilege Gmail Scope**:
   Uses exclusively `https://www.googleapis.com/auth/gmail.readonly`. The application cannot send emails, modify existing emails, delete records, or access other Google services.
2. **Zero DOM Scraping**:
   The extension does not inspect web pages or inject scripts into the Gmail interface. All data access occurs over secure, official Google APIs.
3. **No Secrets in Extension Frontend**:
   All OAuth client secrets and access tokens remain strictly on the local backend server. The extension bundle contains zero sensitive tokens.
4. **Local Credential Storage**:
   OAuth client secrets (`credentials.json`) and authorized tokens (`token.json`) remain strictly local to the runtime environment. No credentials or tokens are logged or transmitted to third-party endpoints.
5. **Strict Version Control Exclusion**:
   The repository `.gitignore` explicitly excludes:
   ```gitignore
   credentials.json
   **/credentials.json
   token.json
   **/token.json
   *.env
   .env*
   ```
6. **Sanitized Templates**:
   Only sanitized placeholder templates (`credentials.json.example` and `credentials/credentials.json.example`) are committed to version control.
7. **No Password Storage**:
   The system never requests, stores, or handles Google account passwords. All authentication relies on secure OAuth 2.0 authorization codes and access tokens.

---

## 26. Setup Guide

Follow this step-by-step procedure to set up and run the project:

### Step A: Install Dependencies
```bash
git clone https://github.com/pavankarthikeyaatchyuta-lab/BELVO.git
cd BELVO
pip install -r requirements.txt
```

### Step B: Verify with Automated Tests
```bash
python -m pytest -v
```
Ensure all 19 tests pass.

### Step C: Run in Mock Mode (CLI)
```bash
python main.py --mode mock --date 2026-09-17
```
Inspect the output at `output/attendance.xlsx`.

### Step D: Launch the Backend API Server
```bash
python main.py --server
```
Leave this terminal running. The server listens on `http://127.0.0.1:8000`.

### Step E: Load Extension in Google Chrome
1. Open Google Chrome &rarr; Navigate to `chrome://extensions/`.
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** &rarr; select the `extension/` folder in the project root.
4. Pin the **Belvo Attendance Tracker** icon to your toolbar.

### Step F: Test the Extension in Mock Mode
1. Click the Belvo extension icon in Chrome.
2. Verify the badge shows **"Backend Connected"** in green.
3. Keep mode as **"Mock Mode (Safe / Offline Demo)"**.
4. Click **"Scan Inbox"** &rarr; Verify it reports 9 emails found.
5. Click **"Process Attendance"** &rarr; View Present: 3, Absent: 1, Leave: 1, and the roster table.
6. Click **"Download attendance.xlsx"** &rarr; The file downloads to your machine.

### Step G: (Optional) Test against Real Gmail Account
1. Place your Google Cloud desktop credentials at `credentials/credentials.json`.
2. In the Chrome Extension, switch the mode to **"Gmail API (Real Mailbox)"**.
3. Click **"Test / Connect Gmail OAuth"** to authorize.
4. Set your attendance date, click **Scan Inbox**, and click **Process Attendance**.

---

## 27. Sample Output

Running the tested mock dataset for date `2026-09-17` produces the following deterministic results:

### Console Output:
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
Output: ...\output\attendance.xlsx
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

### Scenario Explanation:
1. **Pavan Atchyuta (`P`)**: Sent an on-time valid report (`msg_001`) and a duplicate report 10 minutes later (`msg_002`). The duplicate was deduplicated into a single Present row.
2. **Thrija (`P`)**: Sent a valid report with a colon delimiter (`msg_003`). Marked Present.
3. **Sai (`P`)**: Sent a late report received at 01:15 AM on 2026-09-18 (`msg_004`). Because the subject explicitly designated `2026-09-17`, it was accepted as Present for the target date.
4. **Ravi (`A`)**: Sent one email with subject `"Hello team"` (`msg_005`) and one email with an empty subject (`msg_006`). Both were rejected as malformed/missing. With no valid report, Ravi is marked Absent.
5. **Ananya (`L`)**: Listed in `leave.csv` for `2026-09-17`. Even though she also submitted a valid report (`msg_007`), approved leave took precedence, resulting in status **`L`**.
6. **Unknown Contractor (Ignored)**: Sent a valid report format (`msg_008`), but because the sender was not in `employees.csv`, the email was safely audited and excluded from the roster.

---

## 28. Limitations

The current implementation has the following genuine architectural boundaries:

1. **Fixed Subject Syntax**: The parser accepts `Daily Work Report - YYYY-MM-DD` (and colon variation), but does not support arbitrary free-form or natural language subjects (e.g. `"Work report for yesterday"`).
2. **File-Based Configuration**: Employee rosters and leave records are stored in local CSV files rather than an external HRIS database.
3. **Local Backend Requirement**: The Chrome Extension requires the local Python FastAPI service (`python main.py --server`) to be running on the host machine.
4. **Single Mailbox Query**: The current implementation authenticates against one configured user mailbox (`userId="me"`) rather than querying across multiple delegator accounts via Google Workspace service account impersonation.
5. **No Scheduled Execution**: Attendance runs are invoked on demand via Extension, CLI, or Streamlit, rather than through an integrated cron or background worker.

---

## 29. Future Improvements

With additional development time, the following production features would be added:

1. **Incremental Sync via Gmail History API**:
   - Store `historyId` across runs to perform delta queries, fetching only new messages rather than querying date windows.
2. **Persistent Relational Database**:
   - Migrate employee, leave, and attendance records into PostgreSQL/SQLite with SQLAlchemy and Alembic migrations to support multi-year attendance queries.
3. **Hosted Cloud Backend**:
   - Package the FastAPI service as a container deployed to Google Cloud Run or AWS Lambda so the Chrome extension can operate without a local terminal running.
4. **Configurable Matching Rules Engine**:
   - Support a YAML-based rule configuration allowing administrators to define custom regex patterns and accepted subject templates.
5. **Interactive Exception Resolution UI**:
   - Add a review screen in the Chrome Extension or Streamlit allowing HR staff to manually approve edge cases (e.g., matching a report with a minor typo in the subject line).
6. **Automated Notification Webhooks**:
   - Post daily attendance summaries directly to Slack or Microsoft Teams channels upon pipeline completion.

---

## 30. Final Project Status

The current implementation status of all project components is summarized below:

| Component | Status | Implementation Details |
| :--- | :---: | :--- |
| **Attendance Application** | **Completed** | Full deterministic pipeline implemented in `app/attendance.py` |
| **Gmail API Integration** | **Completed** | Implemented in `app/gmail_client.py` using `google-api-python-client` |
| **OAuth Authentication** | **Completed** | InstalledAppFlow with automatic token refresh in `token.json` |
| **Read-Only Gmail Access** | **Completed** | Enforces scope `https://www.googleapis.com/auth/gmail.readonly` |
| **Attendance Processing** | **Completed** | P/A/L logic, leave precedence, and edge case categorization |
| **Excel Reporting** | **Completed** | Formatted dual-sheet workbook created via `app/excel_writer.py` |
| **Mock Testing** | **Completed** | Standalone mode with 9 test scenarios in `sample_data/mock_emails.json` |
| **Automated Tests** | **Completed** | 19/19 automated pytest tests passing (`test_attendance.py` & `test_api.py`) |
| **FastAPI Backend Server** | **Completed** | Implemented in `app/api.py`, launched via `python main.py --server` |
| **Chrome Extension (MV3)** | **Completed** | Manifest V3 popup in `extension/` connecting to local backend |
| **Streamlit Dashboard** | **Completed** | Interactive dashboard runnable via `python main.py --ui` |
| **Documentation** | **Completed** | Full source documentation in `README.md` with Chrome setup steps |
| **Security Cleanup** | **Completed** | Verified `.gitignore` prevents tracking of credentials and tokens |

---

## 31. Final Conclusion

The **Belvo Attendance Tracker** provides a complete, deterministic, and verifiable solution for automating employee attendance tracking from email work reports. By combining the official **Gmail API** (under a strict read-only OAuth scope) with a robust deterministic parser and a modern **Manifest V3 Chrome Extension**, the application eliminates manual reconciliation while guaranteeing that email messages are never modified or compromised.

The system handles real-world email ambiguities—such as duplicate submissions, late reports submitted past midnight, malformed subjects, missing headers, and external senders—logging every occurrence into a comprehensive audit sheet. Verified with a **19/19 passing automated test suite** and equipped with an intuitive Chrome extension, a CLI, and a Streamlit web interface, the project is immediately runnable in offline Mock Mode or connected to an active Google Cloud Gmail integration.
