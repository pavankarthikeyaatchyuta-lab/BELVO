from __future__ import annotations

"""
Email provider interfaces and implementations for Gmail API and Mock testing.
"""

from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from app.config import (
    GMAIL_CREDENTIALS_PATH,
    GMAIL_TOKEN_PATH,
    GMAIL_SCOPES,
    DEFAULT_MOCK_EMAILS_PATH,
    DATE_FORMAT,
)
from app.models import EmailMessage

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    """Abstract interface for fetching work report emails."""

    @abstractmethod
    def fetch_messages(self, target_date: str) -> List[EmailMessage]:
        """Fetch email messages relevant to the given target work date."""
        pass


class MockEmailProvider(EmailProvider):
    """Mock email provider for safe local development, testing, and demos."""

    def __init__(self, data_path: Optional[Path] = None, in_memory_messages: Optional[List[EmailMessage]] = None):
        self.data_path = data_path or DEFAULT_MOCK_EMAILS_PATH
        self.in_memory_messages = in_memory_messages

    def fetch_messages(self, target_date: str) -> List[EmailMessage]:
        """Loads mock messages from memory or JSON file."""
        if self.in_memory_messages is not None:
            return self.in_memory_messages

        if not Path(self.data_path).exists():
            logger.warning(f"Mock data file not found at {self.data_path}. Returning empty list.")
            return []

        with open(self.data_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        messages: List[EmailMessage] = []
        for item in raw_data:
            messages.append(
                EmailMessage(
                    id=item.get("id", f"mock_{len(messages) + 1}"),
                    sender=item.get("sender", ""),
                    subject=item.get("subject", ""),
                    received_at=item.get("received_at"),
                    snippet=item.get("snippet", ""),
                )
            )
        return messages


class GmailProvider(EmailProvider):
    """
    Gmail API integration using Google OAuth 2.0 with minimal read-only scope.
    Handles token refreshing, local web server consent flow, and batch message fetching.
    """

    def __init__(
        self,
        credentials_path: Path = GMAIL_CREDENTIALS_PATH,
        token_path: Path = GMAIL_TOKEN_PATH,
        scopes: Optional[List[str]] = None,
        credentials: Optional[Credentials] = None,
    ):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.scopes = scopes or GMAIL_SCOPES
        self._credentials = credentials
        self._service = None

    def _get_credentials(self):
        """Authenticates with OAuth 2.0 and returns valid Google credentials."""
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        if self._credentials is not None:
            if self._credentials.expired and self._credentials.refresh_token:
                logger.info("Refreshing expired in-memory Gmail OAuth token...")
                self._credentials.refresh(Request())
            return self._credentials

        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
            except Exception as e:
                logger.warning(f"Could not load token from {self.token_path}: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Gmail OAuth token...")
                creds.refresh(Request())
            else:
                if not self.credentials_path.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials file not found at '{self.credentials_path}'. "
                        "Please download OAuth client credentials from Google Cloud Console "
                        "and save as 'credentials.json', or run in mock mode using '--mode mock'."
                    )
                logger.info("Starting local OAuth consent flow...")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), self.scopes)
                creds = flow.run_local_server(port=0)

            # Save the refreshed or new credentials
            with open(self.token_path, "w", encoding="utf-8") as token_file:
                token_file.write(creds.to_json())

        return creds

    def _get_service(self):
        """Builds and caches the Gmail API resource service."""
        if self._service is None:
            from googleapiclient.discovery import build
            creds = self._get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def fetch_messages(self, target_date: str) -> List[EmailMessage]:
        """
        Fetches messages from Gmail inbox matching work report patterns.
        Expands search window around target_date to accommodate late reports.
        """
        service = self._get_service()

        # Build date query window (target_date - 1 day to target_date + 2 days)
        try:
            target_dt = datetime.strptime(target_date, DATE_FORMAT)
            after_date = (target_dt - timedelta(days=1)).strftime("%Y/%m/%d")
            before_date = (target_dt + timedelta(days=2)).strftime("%Y/%m/%d")
            query = f'subject:"Daily Work Report" after:{after_date} before:{before_date}'
        except Exception:
            query = 'subject:"Daily Work Report"'

        logger.info(f"Querying Gmail API with query: {query}")

        try:
            results = service.users().messages().list(userId="me", q=query, maxResults=100).execute()
            messages_meta = results.get("messages", [])
        except Exception as e:
            logger.error(f"Failed to list messages from Gmail: {e}")
            raise

        email_messages: List[EmailMessage] = []
        for meta in messages_meta:
            msg_id = meta["id"]
            try:
                msg_data = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=msg_id,
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    )
                    .execute()
                )

                headers = msg_data.get("payload", {}).get("headers", [])
                header_dict = {h["name"].lower(): h["value"] for h in headers}

                sender = header_dict.get("from", "")
                subject = header_dict.get("subject", "")
                raw_date = header_dict.get("date", "")
                snippet = msg_data.get("snippet", "")

                received_at_iso = None
                if raw_date:
                    try:
                        parsed_dt = parsedate_to_datetime(raw_date)
                        received_at_iso = parsed_dt.isoformat()
                    except Exception:
                        received_at_iso = None

                email_messages.append(
                    EmailMessage(
                        id=msg_id,
                        sender=sender,
                        subject=subject,
                        received_at=received_at_iso,
                        snippet=snippet,
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to retrieve details for message ID {msg_id}: {e}")

        logger.info(f"Retrieved {len(email_messages)} messages from Gmail.")
        return email_messages
