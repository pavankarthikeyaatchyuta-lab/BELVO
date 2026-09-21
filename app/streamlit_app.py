"""
Belvo Attendance Tracker - Streamlit Demo UI
Simple, clean dashboard to execute attendance runs, inspect metrics, and download reports.
"""

from datetime import datetime
import io
from pathlib import Path
import pandas as pd
import streamlit as st

from app.attendance import (
    AttendanceEngine,
    load_employees_from_csv,
    load_leave_from_csv,
)
from app.config import (
    DEFAULT_EMPLOYEES_PATH,
    DEFAULT_LEAVE_PATH,
    DEFAULT_MOCK_EMAILS_PATH,
    DEFAULT_OUTPUT_PATH,
    GMAIL_CREDENTIALS_PATH,
)
from app.excel_writer import export_attendance_workbook
from app.gmail_client import GmailProvider, MockEmailProvider

st.set_page_config(
    page_title="Belvo Attendance Tracker",
    page_icon="📅",
    layout="wide",
)

st.title("📅 Belvo Attendance Tracker")
st.caption("Automated daily attendance generator from Gmail work-report emails")

# Sidebar Configuration
st.sidebar.header("Run Settings")

selected_date = st.sidebar.date_input(
    "Select Attendance Date",
    value=datetime.strptime("2026-09-17", "%Y-%m-%d").date(),
)
date_str = selected_date.strftime("%Y-%m-%d")

provider_mode = st.sidebar.radio(
    "Data Source Mode",
    options=["Mock Mode (Safe / No Auth)", "Gmail API (Real Mailbox)"],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.markdown("### Configuration Files")
st.sidebar.caption(f"**Employees File:** `{DEFAULT_EMPLOYEES_PATH.name}`")
st.sidebar.caption(f"**Leave File:** `{DEFAULT_LEAVE_PATH.name}`")

if provider_mode == "Gmail API (Real Mailbox)":
    if not GMAIL_CREDENTIALS_PATH.exists():
        st.sidebar.warning("⚠️ `credentials.json` not found. Please follow the setup instructions in README.md.")
    else:
        st.sidebar.success("✅ `credentials.json` detected.")

process_button = st.sidebar.button("🚀 Fetch Reports & Generate Attendance", type="primary", use_container_width=True)

if process_button or "records" in st.session_state:
    if process_button:
        with st.spinner("Processing work reports..."):
            try:
                # Load roster and leave records
                employees = load_employees_from_csv(DEFAULT_EMPLOYEES_PATH)
                leave_entries = load_leave_from_csv(DEFAULT_LEAVE_PATH)

                # Initialize provider
                if provider_mode.startswith("Mock"):
                    provider = MockEmailProvider(data_path=DEFAULT_MOCK_EMAILS_PATH)
                else:
                    provider = GmailProvider()

                raw_messages = provider.fetch_messages(date_str)

                engine = AttendanceEngine(employees=employees, leave_entries=leave_entries)
                records, logs, stats = engine.process_attendance(raw_messages, date_str)

                # Export workbook to disk
                export_attendance_workbook(records, logs, DEFAULT_OUTPUT_PATH)

                # Store in session state
                st.session_state["records"] = records
                st.session_state["logs"] = logs
                st.session_state["stats"] = stats
                st.session_state["date_str"] = date_str
            except Exception as e:
                st.error(f"Error processing attendance: {e}")
                st.stop()

    records = st.session_state.get("records", [])
    logs = st.session_state.get("logs", [])
    stats = st.session_state.get("stats", {})
    cur_date = st.session_state.get("date_str", date_str)

    # Metric Cards
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Expected", stats.get("total_employees", 0))
    col2.metric("Present (P)", stats.get("present_count", 0), delta="Present", delta_color="normal")
    col3.metric("Absent (A)", stats.get("absent_count", 0), delta="-Absent", delta_color="inverse")
    col4.metric("On Leave (L)", stats.get("leave_count", 0), delta="Leave", delta_color="off")

    st.markdown("---")

    # Attendance Records Table
    st.subheader(f"📋 Attendance Results for {cur_date}")
    df_att = pd.DataFrame([
        {
            "Date": r.date,
            "Person": r.person,
            "Email": r.email,
            "Status": r.status.value,
            "Reason / Note": r.notes,
        }
        for r in records
    ])

    def highlight_status(row):
        val = row["Status"]
        if val == "P":
            return ["background-color: #d4edda; color: #155724; font-weight: bold;"] * len(row)
        elif val == "A":
            return ["background-color: #f8d7da; color: #721c24; font-weight: bold;"] * len(row)
        elif val == "L":
            return ["background-color: #fff3cd; color: #856404; font-weight: bold;"] * len(row)
        return [""] * len(row)

    styled_df = df_att.style.apply(highlight_status, axis=1)
    st.dataframe(styled_df, use_container_width=True)

    # Download Button
    if DEFAULT_OUTPUT_PATH.exists():
        with open(DEFAULT_OUTPUT_PATH, "rb") as f:
            excel_bytes = f.read()
        st.download_button(
            label="📥 Download attendance.xlsx",
            data=excel_bytes,
            file_name="attendance.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )

    # Audit & Processing Logs Section
    st.markdown("---")
    st.subheader("🔍 Processing & Audit Log")
    st.caption("Detailed classification of received emails, edge cases, deduplication, and rejected messages.")

    df_logs = pd.DataFrame([
        {
            "Timestamp": l.timestamp,
            "Category": l.category.value if hasattr(l.category, "value") else str(l.category),
            "Sender": l.sender,
            "Subject": l.subject,
            "Target Date": l.target_date,
            "Action": l.action,
            "Details": l.details,
        }
        for l in logs
    ])
    st.dataframe(df_logs, use_container_width=True)

else:
    st.info("👈 Select a date and click **'Fetch Reports & Generate Attendance'** in the sidebar to run.")
