/**
 * Belvo Attendance Tracker - Extension Popup Logic
 * Communicates with the local FastAPI backend (http://127.0.0.1:8000).
 */

const API_BASE_URL = "http://127.0.0.1:8000";

// DOM Elements
const connectionBadge = document.getElementById("connection-status");
const connectionText = document.getElementById("connection-text");
const modeSelect = document.getElementById("mode-select");
const targetDateInput = document.getElementById("target-date");
const btnScan = document.getElementById("btn-scan");
const btnProcess = document.getElementById("btn-process");
const btnConnect = document.getElementById("btn-connect");
const btnDownload = document.getElementById("btn-download");
const gmailAuthRow = document.getElementById("gmail-auth-row");
const authStatusText = document.getElementById("auth-status-text");
const statusConsole = document.getElementById("status-console");

const metricTotal = document.getElementById("metric-total");
const metricP = document.getElementById("metric-p");
const metricA = document.getElementById("metric-a");
const metricL = document.getElementById("metric-l");

const resultsCard = document.getElementById("results-card");
const rosterTbody = document.getElementById("roster-tbody");
const scanSummaryBadge = document.getElementById("scan-summary-badge");

// Helpers
function logStatus(message, type = "normal") {
  statusConsole.textContent = message;
  statusConsole.className = "status-console";
  if (type === "error") {
    statusConsole.classList.add("error");
  } else if (type === "success") {
    statusConsole.classList.add("success");
  }
}

function setConnectionState(isOnline, info = "") {
  if (isOnline) {
    connectionBadge.className = "status-badge status-online";
    connectionText.textContent = "Backend Connected";
  } else {
    connectionBadge.className = "status-badge status-offline";
    connectionText.textContent = "Backend Offline";
    logStatus("Backend not detected at http://127.0.0.1:8000.\nRun `python main.py --server` to start it.", "error");
  }
}

// 1. Health Check & Status
async function checkBackendStatus() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    setConnectionState(true);

    if (data.credentials_present) {
      authStatusText.textContent = "✅ credentials.json found";
    } else {
      authStatusText.textContent = "⚠️ credentials.json not found";
    }

    if (data.excel_available) {
      btnDownload.disabled = false;
    }
  } catch (err) {
    setConnectionState(false);
  }
}

// 2. Mode Change
modeSelect.addEventListener("change", () => {
  const isGmail = modeSelect.value === "gmail";
  if (isGmail) {
    gmailAuthRow.classList.remove("hidden");
  } else {
    gmailAuthRow.classList.add("hidden");
  }
  logStatus(`Mode switched to: ${isGmail ? "Gmail API" : "Mock Mode"}`);
});

// 3. Connect / Verify Gmail Auth
btnConnect.addEventListener("click", async () => {
  logStatus("Verifying Gmail OAuth credentials...");
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/connect`, {
      method: "POST",
    });
    const data = await res.json();
    if (res.ok && data.authenticated) {
      logStatus("Gmail connected successfully!", "success");
      authStatusText.textContent = "✅ Connected to Gmail";
    } else {
      logStatus(`Gmail Auth: ${data.detail || data.message || "Failed"}`, "error");
    }
  } catch (err) {
    logStatus(`Error connecting to Gmail: ${err.message}`, "error");
  }
});

// 4. Scan Inbox
btnScan.addEventListener("click", async () => {
  const date = targetDateInput.value;
  const mode = modeSelect.value;
  if (!date) {
    logStatus("Please select a valid date.", "error");
    return;
  }

  btnScan.disabled = true;
  logStatus(`Scanning ${mode.toUpperCase()} for ${date}...`);

  try {
    const res = await fetch(`${API_BASE_URL}/api/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date, mode }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Scan request failed");
    }

    scanSummaryBadge.textContent = `${data.total_found} emails found`;
    logStatus(`Scan complete: Found ${data.total_found} relevant emails for ${date}.`, "success");
  } catch (err) {
    logStatus(`Scan error: ${err.message}`, "error");
  } finally {
    btnScan.disabled = false;
  }
});

// 5. Process Attendance
btnProcess.addEventListener("click", async () => {
  const date = targetDateInput.value;
  const mode = modeSelect.value;
  if (!date) {
    logStatus("Please select a valid date.", "error");
    return;
  }

  btnProcess.disabled = true;
  logStatus(`Processing attendance for ${date} via ${mode.toUpperCase()}...`);

  try {
    const res = await fetch(`${API_BASE_URL}/api/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ date, mode }),
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Processing request failed");
    }

    // Update KPI metrics
    metricTotal.textContent = data.stats.total_employees;
    metricP.textContent = data.stats.present_count;
    metricA.textContent = data.stats.absent_count;
    metricL.textContent = data.stats.leave_count;

    // Populate Roster Table
    rosterTbody.innerHTML = "";
    data.records.forEach((rec) => {
      const tr = document.createElement("tr");

      const tdPerson = document.createElement("td");
      tdPerson.textContent = rec.person;

      const tdStatus = document.createElement("td");
      const spanBadge = document.createElement("span");
      spanBadge.textContent = rec.status;
      spanBadge.className = `status-cell-${rec.status.toLowerCase()}`;
      tdStatus.appendChild(spanBadge);

      const tdNotes = document.createElement("td");
      tdNotes.textContent = rec.notes;
      tdNotes.style.fontSize = "10px";
      tdNotes.style.color = "#64748b";

      tr.appendChild(tdPerson);
      tr.appendChild(tdStatus);
      tr.appendChild(tdNotes);
      rosterTbody.appendChild(tr);
    });

    resultsCard.classList.remove("hidden");
    btnDownload.disabled = false;

    logStatus(
      `Attendance processed successfully!\nP: ${data.stats.present_count} | A: ${data.stats.absent_count} | L: ${data.stats.leave_count}\nExcel workbook ready for download.`,
      "success"
    );
  } catch (err) {
    logStatus(`Processing error: ${err.message}`, "error");
  } finally {
    btnProcess.disabled = false;
  }
});

// 6. Download Excel
btnDownload.addEventListener("click", async () => {
  logStatus("Downloading attendance.xlsx...");
  const downloadUrl = `${API_BASE_URL}/api/download`;

  try {
    // Check if chrome.downloads is available
    if (typeof chrome !== "undefined" && chrome.downloads && chrome.downloads.download) {
      chrome.downloads.download({
        url: downloadUrl,
        filename: "attendance.xlsx",
        saveAs: false,
      });
      logStatus("File download initiated via Chrome Downloads API.", "success");
    } else {
      // Fallback standard browser blob download
      const res = await fetch(downloadUrl);
      if (!res.ok) throw new Error("Failed to fetch file from backend");
      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = "attendance.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(blobUrl);
      logStatus("File download completed.", "success");
    }
  } catch (err) {
    logStatus(`Download failed: ${err.message}`, "error");
  }
});

// Initialize on load
document.addEventListener("DOMContentLoaded", () => {
  checkBackendStatus();
});
