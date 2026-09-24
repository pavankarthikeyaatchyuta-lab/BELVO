/**
 * Belvo Attendance Tracker - Extension Popup Logic
 * Supports both Vercel Cloud Backend (HTTPS) and Local FastAPI Backend (http://127.0.0.1:8000).
 * Implements Web OAuth 2.0 flow with session token caching.
 */

// Default cloud and local fallbacks
const DEFAULT_CLOUD_URL = "https://belvo-attendence-tracker.vercel.app";
const DEFAULT_LOCAL_URL = "http://127.0.0.1:8000";
let apiBaseUrl = DEFAULT_CLOUD_URL;
let sessionToken = null;

// DOM Elements
const connectionBadge = document.getElementById("connection-status");
const connectionText = document.getElementById("connection-text");
const modeSelect = document.getElementById("mode-select");
const targetDateInput = document.getElementById("target-date");
const btnScan = document.getElementById("btn-scan");
const btnProcess = document.getElementById("btn-process");
const btnConnect = document.getElementById("btn-connect");
const btnLogout = document.getElementById("btn-logout");
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

const btnToggleSettings = document.getElementById("btn-toggle-settings");
const settingsPanel = document.getElementById("settings-panel");
const inputApiUrl = document.getElementById("input-api-url");
const btnSaveUrl = document.getElementById("btn-save-url");

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
    logStatus(`Backend not reachable at ${apiBaseUrl}.\nCheck settings or run \`python main.py --server\` if local.`, "error");
  }
}

// Storage helpers (Chrome extension storage with localStorage fallback)
async function getStoredValue(key, fallback = null) {
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    return new Promise((resolve) => {
      chrome.storage.local.get([key], (result) => {
        resolve(result[key] !== undefined ? result[key] : fallback);
      });
    });
  }
  const val = localStorage.getItem(key);
  return val !== null ? val : fallback;
}

async function setStoredValue(key, value) {
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    return new Promise((resolve) => {
      chrome.storage.local.set({ [key]: value }, resolve);
    });
  }
  localStorage.setItem(key, value);
}

async function removeStoredValue(key) {
  if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
    return new Promise((resolve) => {
      chrome.storage.local.remove([key], resolve);
    });
  }
  localStorage.removeItem(key);
}

// 1. Health Check & Status
async function checkBackendStatus() {
  try {
    const headers = {};
    if (sessionToken) {
      headers["Authorization"] = `Bearer ${sessionToken}`;
    }

    const res = await fetch(`${apiBaseUrl}/api/status`, { headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    setConnectionState(true);

    if (data.excel_available) {
      btnDownload.disabled = false;
    }

    await checkAuthStatus();
  } catch (err) {
    setConnectionState(false);
  }
}

// Check Gmail OAuth connection status
async function checkAuthStatus() {
  try {
    const headers = {};
    if (sessionToken) {
      headers["Authorization"] = `Bearer ${sessionToken}`;
    }

    const res = await fetch(`${apiBaseUrl}/api/auth/status`, { headers });
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated) {
        authStatusText.textContent = "✅ Gmail Connected";
        authStatusText.style.color = "#155724";
        btnConnect.classList.add("hidden");
        btnLogout.classList.remove("hidden");
        return true;
      }
    }
  } catch (e) {
    // Ignore error
  }

  authStatusText.textContent = "⚠️ Not connected";
  authStatusText.style.color = "#6b7280";
  btnConnect.classList.remove("hidden");
  btnLogout.classList.add("hidden");
  return false;
}

// 2. Mode Change
modeSelect.addEventListener("change", () => {
  const isGmail = modeSelect.value === "gmail";
  if (isGmail) {
    gmailAuthRow.classList.remove("hidden");
    checkAuthStatus();
  } else {
    gmailAuthRow.classList.add("hidden");
  }
  logStatus(`Mode switched to: ${isGmail ? "Gmail API" : "Mock Mode"}`);
});

// 3. Connect with Google OAuth (Web flow)
btnConnect.addEventListener("click", async () => {
  logStatus("Opening Google OAuth consent screen...");
  try {
    const res = await fetch(`${apiBaseUrl}/api/auth/google?json_response=true`);
    const data = await res.json();

    if (!res.ok || !data.auth_url) {
      throw new Error(data.detail || "Failed to generate authorization URL");
    }

    // Open Google OAuth consent page
    if (typeof chrome !== "undefined" && chrome.tabs && chrome.tabs.create) {
      chrome.tabs.create({ url: data.auth_url });
    } else {
      window.open(data.auth_url, "_blank");
    }

    logStatus("Authorizing in browser... Return here once completed.", "normal");

    // Poll for authentication status for 45 seconds
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      const isAuthed = await checkAuthStatus();
      if (isAuthed) {
        clearInterval(interval);
        logStatus("✅ Gmail connected successfully!", "success");
      } else if (attempts > 30) {
        clearInterval(interval);
      }
    }, 1500);
  } catch (err) {
    logStatus(`OAuth error: ${err.message}`, "error");
  }
});

// Logout / Disconnect
btnLogout.addEventListener("click", async () => {
  sessionToken = null;
  await removeStoredValue("belvo_session_token");
  try {
    await fetch(`${apiBaseUrl}/api/auth/logout`, { method: "POST" });
  } catch (e) {}
  await checkAuthStatus();
  logStatus("Disconnected from Gmail.", "normal");
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
    const headers = { "Content-Type": "application/json" };
    if (sessionToken) {
      headers["Authorization"] = `Bearer ${sessionToken}`;
    }

    const res = await fetch(`${apiBaseUrl}/api/scan`, {
      method: "POST",
      headers,
      body: JSON.stringify({ date, mode, session_token: sessionToken }),
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
    const headers = { "Content-Type": "application/json" };
    if (sessionToken) {
      headers["Authorization"] = `Bearer ${sessionToken}`;
    }

    const res = await fetch(`${apiBaseUrl}/api/process`, {
      method: "POST",
      headers,
      body: JSON.stringify({ date, mode, session_token: sessionToken }),
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
  const downloadUrl = `${apiBaseUrl}/api/download`;

  try {
    if (typeof chrome !== "undefined" && chrome.downloads && chrome.downloads.download) {
      chrome.downloads.download({
        url: downloadUrl,
        filename: "attendance.xlsx",
        saveAs: false,
      });
      logStatus("File download initiated via Chrome Downloads API.", "success");
    } else {
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

// 7. Settings / Custom Backend URL
btnToggleSettings.addEventListener("click", () => {
  settingsPanel.classList.toggle("hidden");
});

btnSaveUrl.addEventListener("click", async () => {
  const newUrl = inputApiUrl.value.trim().replace(/\/+$/, "");
  if (!newUrl) return;

  apiBaseUrl = newUrl;
  await setStoredValue("belvo_api_url", newUrl);
  settingsPanel.classList.add("hidden");
  logStatus(`Backend URL saved: ${apiBaseUrl}`);
  checkBackendStatus();
});

// Listen for postMessage from OAuth callback tab
window.addEventListener("message", async (event) => {
  if (event.data && event.data.type === "BELVO_AUTH_SUCCESS" && event.data.session_token) {
    sessionToken = event.data.session_token;
    await setStoredValue("belvo_session_token", sessionToken);
    await checkAuthStatus();
    logStatus("✅ Gmail connected successfully via OAuth callback!", "success");
  }
});

// Initialize on load
document.addEventListener("DOMContentLoaded", async () => {
  // Load saved API URL or default
  apiBaseUrl = await getStoredValue("belvo_api_url", DEFAULT_CLOUD_URL);
  inputApiUrl.value = apiBaseUrl;

  // Load saved session token
  sessionToken = await getStoredValue("belvo_session_token", null);

  await checkBackendStatus();
});
