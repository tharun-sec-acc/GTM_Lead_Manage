import base64
import email
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.message import EmailMessage as PyEmailMessage
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.auth.models import OAuthConnection, now
from app.auth.security import decrypt_token, encrypt_token
from app.config import settings
from app.reply_sync import ingest_incoming_email

logger = logging.getLogger(__name__)


class EmailProviderError(Exception):
    """Base exception for email provider operations."""
    pass


class BaseEmailProvider(ABC):
    def __init__(self, conn: OAuthConnection):
        self.conn = conn

    @abstractmethod
    def refresh_credentials(self, session: Session) -> str:
        """Obtain a valid access token, refreshing if necessary."""
        pass

    @abstractmethod
    def send_email(
        self,
        session: Session,
        recipient: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        lead_id: str | None = None,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch an email and return message identifiers."""
        pass

    @abstractmethod
    def sync_inbox(self, session: Session, max_messages: int = 50) -> dict[str, Any]:
        """Fetch recent incoming emails, match customer replies, and update GTM leads."""
        pass


class GmailAPIProvider(BaseEmailProvider):
    """Implementation for Google Gmail REST API."""

    def refresh_credentials(self, session: Session) -> str:
        refresh_token = decrypt_token(self.conn.refresh_token_encrypted)
        if not settings.google_client_id or not settings.google_client_secret:
            raise EmailProviderError("Google client ID and secret are not configured on the server.")

        try:
            res = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=15,
            )
            if res.status_code != 200:
                err_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                err_desc = err_data.get("error_description") or err_data.get("error") or res.text
                self.conn.status = "reauth_required"
                self.conn.error_message = f"Token refresh failed: {err_desc}"
                session.flush()
                raise EmailProviderError(f"Google authorization expired. Please reconnect your Gmail account ({err_desc}).")

            data = res.json()
            new_access_token = data["access_token"]
            self.conn.access_token_encrypted = encrypt_token(new_access_token)
            self.conn.access_token_expires_at = datetime.now(timezone.utc)
            self.conn.status = "connected"
            self.conn.error_message = None
            session.flush()
            return new_access_token
        except httpx.RequestError as exc:
            raise EmailProviderError(f"Failed to connect to Google OAuth service: {exc}") from exc

    def send_email(
        self,
        session: Session,
        recipient: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        lead_id: str | None = None,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        access_token = self.refresh_credentials(session)

        msg = PyEmailMessage()
        msg["From"] = self.conn.account_email
        msg["To"] = recipient
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg["Subject"] = subject

        plain = body_text or body_html.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n\n")
        msg.set_content(plain)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        raw_base64 = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        try:
            res = httpx.post(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"raw": raw_base64},
                timeout=20,
            )
            if res.status_code not in (200, 201):
                err = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                err_msg = err.get("error", {}).get("message") or res.text
                raise EmailProviderError(f"Gmail rejected sending: {err_msg}")

            data = res.json()
            return {
                "provider": "google",
                "message_id": data.get("id"),
                "thread_id": data.get("threadId"),
                "from_email": self.conn.account_email,
                "to_email": recipient,
            }
        except httpx.RequestError as exc:
            raise EmailProviderError(f"Failed to communicate with Gmail API: {exc}") from exc

    def sync_inbox(self, session: Session, max_messages: int = 50) -> dict[str, Any]:
        """Synchronize incoming messages using Gmail API."""
        access_token = self.refresh_credentials(session)
        headers = {"Authorization": f"Bearer {access_token}"}

        # Query messages from the last 7 days
        list_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_messages}&q=newer_than:7d"
        try:
            res = httpx.get(list_url, headers=headers, timeout=20)
            if res.status_code != 200:
                err = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                raise EmailProviderError(f"Gmail messages list failed: {err.get('error', {}).get('message') or res.text}")
            msg_list = res.json().get("messages", [])
        except httpx.RequestError as exc:
            raise EmailProviderError(f"Failed to fetch Gmail message list: {exc}") from exc

        synced_count = 0
        matched_replies = 0

        for m_item in msg_list:
            msg_id = m_item["id"]
            mailbox_uid = f"gmail:{self.conn.account_email}:{msg_id}"

            try:
                detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full"
                detail_res = httpx.get(detail_url, headers=headers, timeout=15)
                if detail_res.status_code != 200:
                    continue
                d = detail_res.json()

                # Parse headers
                headers_dict = {
                    h["name"].lower(): h["value"]
                    for h in d.get("payload", {}).get("headers", [])
                }
                from_header = headers_dict.get("from", "")
                to_header = headers_dict.get("to", "")
                subject_header = headers_dict.get("subject", "")
                in_reply_to = headers_dict.get("in-reply-to")
                references = headers_dict.get("references")
                message_id = headers_dict.get("message-id", msg_id)

                # Extract sender email address from "Name <email@domain>"
                import email.utils
                sender_email = email.utils.parseaddr(from_header)[1].lower()

                # Extract body
                body_content = ""
                payload = d.get("payload", {})
                if "parts" in payload:
                    for part in payload["parts"]:
                        mime_type = part.get("mimeType", "")
                        data = part.get("body", {}).get("data")
                        if data and mime_type in ("text/plain", "text/html"):
                            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                            if mime_type == "text/plain":
                                body_content = decoded
                                break
                            elif not body_content:
                                body_content = decoded
                elif "body" in payload and "data" in payload["body"]:
                    body_content = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="ignore")

                # Parse internal date
                received_ts = int(d.get("internalDate", 0)) / 1000.0
                received_at = datetime.fromtimestamp(received_ts, tz=timezone.utc) if received_ts else now()

                reply = ingest_incoming_email(
                    session=session,
                    org_id=self.conn.organization_id,
                    mailbox_account_email=self.conn.account_email,
                    mailbox_uid=mailbox_uid,
                    incoming_message_id=message_id,
                    in_reply_to=in_reply_to,
                    references=references,
                    sender=sender_email,
                    recipient=to_header,
                    subject=subject_header,
                    body=body_content,
                    received_at=received_at,
                )
                synced_count += 1
                if reply and reply.enrollment_id:
                    matched_replies += 1
            except Exception as item_err:
                logger.warning("Error ingesting Gmail message %s: %s", msg_id, item_err)

        # Update sync metadata
        meta = dict(self.conn.connection_metadata or {})
        meta["last_sync_at"] = now().isoformat()
        meta["last_synced_count"] = synced_count
        self.conn.connection_metadata = meta
        session.flush()

        return {
            "synced_count": synced_count,
            "matched_replies": matched_replies,
            "provider": "google",
            "account_email": self.conn.account_email,
        }


class MicrosoftGraphProvider(BaseEmailProvider):
    """Implementation for Microsoft 365 Outlook via Microsoft Graph API."""

    def refresh_credentials(self, session: Session) -> str:
        refresh_token = decrypt_token(self.conn.refresh_token_encrypted)
        tenant = settings.microsoft_tenant_id or "common"
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"

        try:
            res = httpx.post(
                token_url,
                data={
                    "client_id": settings.microsoft_client_id,
                    "client_secret": settings.microsoft_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "offline_access User.Read Mail.Send Mail.Read",
                },
                timeout=15,
            )
            if res.status_code != 200:
                err_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                err_desc = err_data.get("error_description") or res.text
                self.conn.status = "reauth_required"
                self.conn.error_message = f"Token refresh failed: {err_desc}"
                session.flush()
                raise EmailProviderError(f"Microsoft authorization expired. Please reconnect your Outlook account ({err_desc}).")

            data = res.json()
            new_access_token = data["access_token"]
            self.conn.access_token_encrypted = encrypt_token(new_access_token)
            self.conn.access_token_expires_at = datetime.now(timezone.utc)
            self.conn.status = "connected"
            self.conn.error_message = None
            session.flush()
            return new_access_token
        except httpx.RequestError as exc:
            raise EmailProviderError(f"Failed to connect to Microsoft OAuth service: {exc}") from exc

    def send_email(
        self,
        session: Session,
        recipient: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        lead_id: str | None = None,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        access_token = self.refresh_credentials(session)

        message_payload: dict[str, Any] = {
            "subject": subject,
            "body": {
                "contentType": "HTML" if body_html else "Text",
                "content": body_html or body_text or "",
            },
            "toRecipients": [{"emailAddress": {"address": recipient}}],
        }
        if cc:
            message_payload["ccRecipients"] = [{"emailAddress": {"address": c}} for c in cc]
        if bcc:
            message_payload["bccRecipients"] = [{"emailAddress": {"address": b}} for b in bcc]

        graph_url = f"{settings.microsoft_graph_base_url.rstrip('/')}/me/sendMail"

        try:
            res = httpx.post(
                graph_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"message": message_payload, "saveToSentItems": "true"},
                timeout=20,
            )
            if res.status_code not in (200, 202):
                err = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                err_msg = err.get("error", {}).get("message") or res.text
                raise EmailProviderError(f"Microsoft Graph rejected sending: {err_msg}")

            return {
                "provider": "microsoft",
                "message_id": f"ms-{int(now().timestamp())}",
                "from_email": self.conn.account_email,
                "to_email": recipient,
            }
        except httpx.RequestError as exc:
            raise EmailProviderError(f"Failed to communicate with Microsoft Graph: {exc}") from exc

    def sync_inbox(self, session: Session, max_messages: int = 50) -> dict[str, Any]:
        """Synchronize incoming messages using Microsoft Graph API."""
        access_token = self.refresh_credentials(session)
        headers = {"Authorization": f"Bearer {access_token}"}

        # Query inbox messages ordered by receivedDateTime desc
        url = (
            f"{settings.microsoft_graph_base_url.rstrip('/')}/me/mailFolders/inbox/messages"
            f"?$top={max_messages}&$orderby=receivedDateTime desc"
        )

        try:
            res = httpx.get(url, headers=headers, timeout=20)
            if res.status_code != 200:
                err = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
                raise EmailProviderError(f"Microsoft Graph messages list failed: {err.get('error', {}).get('message') or res.text}")
            msg_list = res.json().get("value", [])
        except httpx.RequestError as exc:
            raise EmailProviderError(f"Failed to fetch Microsoft Graph messages: {exc}") from exc

        synced_count = 0
        matched_replies = 0

        for item in msg_list:
            msg_id = item.get("id")
            mailbox_uid = f"ms:{self.conn.account_email}:{msg_id}"

            try:
                sender_email = (
                    item.get("from", {}).get("emailAddress", {}).get("address", "")
                ).lower().strip()
                subject_header = item.get("subject", "")
                internet_message_id = item.get("internetMessageId")
                body_content = item.get("body", {}).get("content") or item.get("bodyPreview", "")

                received_str = item.get("receivedDateTime")
                received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00")) if received_str else now()

                # Recipient
                recipients = [
                    r.get("emailAddress", {}).get("address", "")
                    for r in item.get("toRecipients", [])
                ]
                to_header = ", ".join(recipients)

                reply = ingest_incoming_email(
                    session=session,
                    org_id=self.conn.organization_id,
                    mailbox_account_email=self.conn.account_email,
                    mailbox_uid=mailbox_uid,
                    incoming_message_id=internet_message_id,
                    in_reply_to=None,
                    references=None,
                    sender=sender_email,
                    recipient=to_header,
                    subject=subject_header,
                    body=body_content,
                    received_at=received_at,
                )
                synced_count += 1
                if reply and reply.enrollment_id:
                    matched_replies += 1
            except Exception as item_err:
                logger.warning("Error ingesting Microsoft message %s: %s", msg_id, item_err)

        # Update sync metadata
        meta = dict(self.conn.connection_metadata or {})
        meta["last_sync_at"] = now().isoformat()
        meta["last_synced_count"] = synced_count
        self.conn.connection_metadata = meta
        session.flush()

        return {
            "synced_count": synced_count,
            "matched_replies": matched_replies,
            "provider": "microsoft",
            "account_email": self.conn.account_email,
        }


def get_email_provider(conn: OAuthConnection) -> BaseEmailProvider:
    """Factory creating the appropriate provider adapter."""
    if conn.provider == "google":
        return GmailAPIProvider(conn)
    elif conn.provider == "microsoft":
        return MicrosoftGraphProvider(conn)
    else:
        raise EmailProviderError(f"Unsupported email provider: {conn.provider}")
