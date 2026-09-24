"""
Web-Server OAuth 2.0 Flow and Session Management for Belvo Attendance Tracker.
Designed for serverless cloud execution (Vercel) and local development.
Does not depend on InstalledAppFlow, localhost callbacks, or persistent server disk.
"""

import base64
import hashlib
import json
import logging
import os
from typing import Any, Dict, Optional, Tuple
import urllib.parse
import urllib.request
from cryptography.fernet import Fernet
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from app.config import (
    GMAIL_SCOPES,
    get_credentials_path,
)

logger = logging.getLogger(__name__)

# Default Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def get_oauth_config() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Retrieves Google OAuth client ID, client secret, and redirect URI.
    Checks environment variables first, then falls back to local credentials.json if available.
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")

    if not client_id or not client_secret:
        # Fallback to local credentials.json if present
        creds_path = get_credentials_path()
        if creds_path and creds_path.exists():
            try:
                with open(creds_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    installed = data.get("installed") or data.get("web") or {}
                    if not client_id:
                        client_id = installed.get("client_id")
                    if not client_secret:
                        client_secret = installed.get("client_secret")
                    if not redirect_uri and installed.get("redirect_uris"):
                        redirect_uri = installed["redirect_uris"][0]
            except Exception as e:
                logger.warning(f"Could not parse local credentials file: {e}")

    return client_id, client_secret, redirect_uri


def get_fernet_cipher() -> Fernet:
    """
    Generates a deterministic Fernet cipher from SESSION_SECRET environment variable.
    Ensures secure symmetric encryption of tokens in serverless environments.
    """
    secret = os.getenv("SESSION_SECRET", "belvo-attendance-tracker-default-secret-key-32")
    # Derive a 32-byte urlsafe base64 key
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_session_data(data: Dict[str, Any]) -> str:
    """Encrypts a credentials payload into an opaque URL-safe session token."""
    cipher = get_fernet_cipher()
    serialized = json.dumps(data).encode("utf-8")
    return cipher.encrypt(serialized).decode("utf-8")


def decrypt_session_data(token_str: str) -> Optional[Dict[str, Any]]:
    """Decrypts an opaque session token back into a credentials dictionary."""
    try:
        cipher = get_fernet_cipher()
        decrypted = cipher.decrypt(token_str.encode("utf-8"))
        return json.loads(decrypted.decode("utf-8"))
    except Exception as e:
        logger.warning(f"Failed to decrypt session token: {e}")
        return None


def create_authorization_url(redirect_uri: Optional[str] = None, state: Optional[str] = None) -> Tuple[str, str]:
    """
    Generates the Google OAuth 2.0 consent URL for web server flow.
    Enforces read-only Gmail access with offline refresh capabilities.
    """
    client_id, _, configured_redirect = get_oauth_config()
    if not client_id:
        raise ValueError(
            "Google Client ID is not configured. Please set GOOGLE_CLIENT_ID environment variable "
            "or configure credentials.json."
        )

    target_redirect = redirect_uri or configured_redirect or "http://127.0.0.1:8000/api/auth/callback"
    csrf_state = state or base64.urlsafe_b64encode(os.urandom(16)).decode("utf-8")

    params = {
        "client_id": client_id,
        "redirect_uri": target_redirect,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": csrf_state,
    }

    url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return url, csrf_state


def exchange_code_for_session(code: str, redirect_uri: Optional[str] = None) -> Tuple[Credentials, str]:
    """
    Exchanges an authorization code for access and refresh tokens.
    Returns (Google Credentials object, encrypted session token).
    """
    client_id, client_secret, configured_redirect = get_oauth_config()
    if not client_id or not client_secret:
        raise ValueError("Google Client ID and Client Secret must be configured.")

    target_redirect = redirect_uri or configured_redirect or "http://127.0.0.1:8000/api/auth/callback"

    payload = urllib.parse.urlencode({
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": target_redirect,
        "grant_type": "authorization_code",
    }).encode("utf-8")

    req = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_msg = e.read().decode("utf-8")
        logger.error(f"Google token exchange failed ({e.code}): {error_msg}")
        raise ValueError(f"Failed to exchange OAuth code: {error_msg}")

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    scopes = data.get("scope", "").split() or GMAIL_SCOPES

    if not access_token:
        raise ValueError("Google token response did not include access_token.")

    # Prepare credentials data dictionary for encryption
    creds_dict = {
        "token": access_token,
        "refresh_token": refresh_token,
        "token_uri": GOOGLE_TOKEN_URL,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": scopes,
    }

    session_token = encrypt_session_data(creds_dict)

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes,
    )

    return creds, session_token


def get_credentials_from_session_token(session_token: str) -> Optional[Credentials]:
    """
    Restores and refreshes a Google Credentials object from an encrypted session token.
    Works statelessly on Vercel without local filesystem storage.
    """
    creds_dict = decrypt_session_data(session_token)
    if not creds_dict:
        return None

    try:
        creds = Credentials(
            token=creds_dict.get("token"),
            refresh_token=creds_dict.get("refresh_token"),
            token_uri=creds_dict.get("token_uri", GOOGLE_TOKEN_URL),
            client_id=creds_dict.get("client_id"),
            client_secret=creds_dict.get("client_secret"),
            scopes=creds_dict.get("scopes", GMAIL_SCOPES),
        )

        # Refresh token if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return creds
    except Exception as e:
        logger.error(f"Failed to restore/refresh credentials from session: {e}")
        return None
