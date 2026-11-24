import base64
import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.auth.models import AuditLog, OAuthConnection, now
from app.auth.security import decrypt_token, encrypt_token
from app.config import settings

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Raised when an email cannot be sent via the selected provider."""
    pass


def refresh_google_access_token(conn: OAuthConnection, session: Session) -> str:
    """Refresh Google OAuth access token using encrypted refresh token."""
    refresh_token = decrypt_token(conn.refresh_token_encrypted)
    if not settings.google_client_id or not settings.google_client_secret:
        raise EmailSendError("Google client ID and secret are not configured on the server.")

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
            conn.status = "reauth_required"
            conn.error_message = f"Token refresh failed: {err_desc}"
            session.commit()
            raise EmailSendError(f"Google authorization expired. Please reconnect your Gmail account ({err_desc}).")

        data = res.json()
        new_access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        conn.access_token_encrypted = encrypt_token(new_access_token)
        conn.access_token_expires_at = datetime.now(timezone.utc)
        conn.status = "connected"
        conn.error_message = None
        session.commit()
        return new_access_token
    except httpx.RequestError as exc:
        raise EmailSendError(f"Failed to connect to Google OAuth service: {exc}") from exc


def refresh_microsoft_access_token(conn: OAuthConnection, session: Session) -> str:
    """Refresh Microsoft Graph access token using encrypted refresh token."""
    refresh_token = decrypt_token(conn.refresh_token_encrypted)
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
                "scope": "offline_access User.Read Mail.Send",
            },
            timeout=15,
        )
        if res.status_code != 200:
            err_data = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            err_desc = err_data.get("error_description") or res.text
            conn.status = "reauth_required"
            conn.error_message = f"Token refresh failed: {err_desc}"
            session.commit()
            raise EmailSendError(f"Microsoft authorization expired. Please reconnect your Outlook account ({err_desc}).")

        data = res.json()
        new_access_token = data["access_token"]
        conn.access_token_encrypted = encrypt_token(new_access_token)
        conn.access_token_expires_at = datetime.now(timezone.utc)
        conn.status = "connected"
        conn.error_message = None
        session.commit()
        return new_access_token
    except httpx.RequestError as exc:
        raise EmailSendError(f"Failed to connect to Microsoft OAuth service: {exc}") from exc


def send_email_via_gmail(
    conn: OAuthConnection,
    recipient: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    session: Session = None,
) -> dict[str, Any]:
    """Send an email using user's authorized Gmail account via users.messages.send."""
    access_token = refresh_google_access_token(conn, session)

    msg = EmailMessage()
    msg["From"] = conn.account_email
    msg["To"] = recipient
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject

    # Plain text version first, then HTML alternative
    plain_content = body_text or body_html.replace("<br>", "\n").replace("<p>", "").replace("</p>", "\n\n")
    msg.set_content(plain_content)
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
            err_body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_body.get("error", {}).get("message") or res.text
            logger.error("Gmail API sending error: %s", err_msg)
            raise EmailSendError(f"Gmail rejected message sending: {err_msg}")

        result = res.json()
        logger.info("Successfully sent email via Gmail [ID: %s] from %s to %s", result.get("id"), conn.account_email, recipient)
        return {
            "provider": "google",
            "message_id": result.get("id"),
            "thread_id": result.get("threadId"),
            "from_email": conn.account_email,
            "to_email": recipient,
        }
    except httpx.RequestError as exc:
        raise EmailSendError(f"Failed to communicate with Gmail API: {exc}") from exc


def send_email_via_microsoft(
    conn: OAuthConnection,
    recipient: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    session: Session = None,
) -> dict[str, Any]:
    """Send an email using user's authorized Microsoft Outlook account via Microsoft Graph me/sendMail."""
    access_token = refresh_microsoft_access_token(conn, session)

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
            err_body = res.json() if res.headers.get("content-type", "").startswith("application/json") else {}
            err_msg = err_body.get("error", {}).get("message") or res.text
            logger.error("Microsoft Graph mail send error: %s", err_msg)
            raise EmailSendError(f"Microsoft Graph rejected message sending: {err_msg}")

        logger.info("Successfully sent email via Microsoft Outlook from %s to %s", conn.account_email, recipient)
        return {
            "provider": "microsoft",
            "message_id": f"ms-{int(now().timestamp())}",
            "from_email": conn.account_email,
            "to_email": recipient,
        }
    except httpx.RequestError as exc:
        raise EmailSendError(f"Failed to communicate with Microsoft Graph: {exc}") from exc


def send_email_via_account(
    session: Session,
    conn: OAuthConnection,
    recipient: str,
    subject: str,
    body_html: str,
    body_text: str | None = None,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    lead_id: str | None = None,
    contact_id: str | None = None,
    user_id: str | None = None,
    org_id: str | None = None,
) -> dict[str, Any]:
    """
    Dispatch email through the connected OAuth provider, ensure Sent folder persistence,
    and log the interaction to the lead audit trail.
    """
    if conn.provider == "google":
        result = send_email_via_gmail(
            conn=conn,
            recipient=recipient,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            cc=cc,
            bcc=bcc,
            session=session,
        )
    elif conn.provider == "microsoft":
        result = send_email_via_microsoft(
            conn=conn,
            recipient=recipient,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            cc=cc,
            bcc=bcc,
            session=session,
        )
    else:
        raise EmailSendError(f"Provider {conn.provider} does not support direct email sending.")

    # Record audit log
    audit = AuditLog(
        organization_id=org_id or conn.organization_id,
        user_id=user_id or conn.user_id,
        action="sent_customer_email",
        resource_type="lead" if lead_id else "email",
        resource_id=lead_id or result.get("message_id"),
        details={
            "provider": conn.provider,
            "from": conn.account_email,
            "to": recipient,
            "subject": subject,
            "lead_id": lead_id,
            "contact_id": contact_id,
            "message_id": result.get("message_id"),
        },
    )
    session.add(audit)
    session.commit()

    return result
