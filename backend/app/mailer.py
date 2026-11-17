import html
import logging
import re
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage as MimeMessage
from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.mailbox import lock_mail_workflow, poll_mailbox
from app.models import (Campaign, EmailEvent, EmailMessage, EmailReply, Enrollment,
                        MailboxState, Suppression, TrackingLink, now)

logger = logging.getLogger(__name__)


def public_base():
    base = settings.public_base_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("PUBLIC_BASE_URL must be an approved public HTTPS URL for unsubscribe or tracking links.")
    return base


def message_content(session: Session, message: EmailMessage, enrollment: Enrollment):
    base = public_base() if settings.mail_unsubscribe_enabled else None
    tracking = settings.tracking_enabled
    if tracking and base is None:
        try:
            base = public_base()
        except (RuntimeError, ValueError):
            logger.warning("Open/click tracking is enabled but PUBLIC_BASE_URL is not configured as HTTPS. "
                           "Sending without tracking pixels or redirects; SMTP acceptance and replies remain recorded.")
            tracking = False
    body = message.body
    if tracking:
        links = session.scalars(select(TrackingLink).where(TrackingLink.email_id == message.id)).all()
        for link in links:
            body = body.replace(link.destination, f"{base}/public/r/{link.token}")
    unsubscribe_url = None
    if settings.mail_unsubscribe_enabled:
        unsubscribe_url = f"{base}/public/unsubscribe/{enrollment.unsubscribe_token}"
        body += f"\n\nTo unsubscribe: {unsubscribe_url}"
    mime = MimeMessage()
    mime["From"] = settings.gmail_address
    mime["To"] = enrollment.recipient
    mime["Subject"] = message.subject
    mime["Message-ID"] = message.message_id
    if unsubscribe_url:
        mime["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        mime["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    previous = session.scalars(select(EmailMessage).where(
        EmailMessage.enrollment_id == enrollment.id, EmailMessage.id != message.id,
        EmailMessage.status == "sent").order_by(EmailMessage.sent_at)).all()
    reply = session.get(EmailReply, message.reply_to_id) if message.reply_to_id else None
    thread_ids = [item.message_id for item in previous]
    if reply and reply.incoming_message_id and "\n" not in reply.incoming_message_id and "\r" not in reply.incoming_message_id:
        thread_ids.append(reply.incoming_message_id)
    if thread_ids:
        mime["In-Reply-To"] = thread_ids[-1]
        mime["References"] = " ".join(thread_ids)
    mime.set_content(body)
    if tracking:
        pixel = f'{base}/public/open/{message.open_token}'
        parts = []
        cursor = 0
        for match in re.finditer(r"https://[^\s<>'\"]+", body):
            parts.append(html.escape(body[cursor:match.start()]))
            url = html.escape(match.group(), quote=True)
            parts.append(f'<a href="{url}">{url}</a>')
            cursor = match.end()
        parts.append(html.escape(body[cursor:]))
        mime.add_alternative(
            f'<html><body><p>{"".join(parts).replace(chr(10), "<br>")}</p>'
            f'<img src="{html.escape(pixel, quote=True)}" width="1" height="1" alt=""></body></html>',
            subtype="html",
        )
    return mime


def claim(message_id: str):
    with SessionLocal.begin() as session:
        lock_mail_workflow(session)
        result = session.execute(update(EmailMessage).where(
            EmailMessage.id == message_id, EmailMessage.status == "approved",
            EmailMessage.due_at <= now(),
        ).values(status="sending", attempted_at=now(), last_error=None))
        return result.rowcount == 1


def send_claimed(message_id: str):
    with SessionLocal.begin() as session:
        lock_mail_workflow(session)
        message = session.get(EmailMessage, message_id)
        if not message or message.status != "sending":
            return
        enrollment = session.get(Enrollment, message.enrollment_id)
        campaign = session.get(Campaign, enrollment.campaign_id) if enrollment else None
        if not enrollment or not campaign:
            message.status, message.last_error = "failed", "Campaign or recipient is missing."
            return
        if not settings.mail_send_enabled:
            message.status, message.last_error = "approved", "Sending is disabled in configuration."
            return
        if not settings.gmail_address or not settings.gmail_app_password:
            message.status, message.last_error = "failed", "Gmail credentials are not configured."
            return
        if not message.approved_at:
            message.status, message.last_error = "draft", "This email requires approval."
            return
        if campaign.status != "active" or enrollment.status != "active" or (enrollment.reply_blocked and not message.manual_reply):
            message.status, message.last_error = "approved", "Campaign or recipient is paused."
            return
        if message.step_number > 0 and not message.manual_reply and campaign.mode == "automatic" and not campaign.sequence_approved_at:
            message.status, message.last_error = "approved", "Automatic sequence approval is required."
            return
        if session.get(Suppression, enrollment.recipient):
            message.status, message.last_error = "approved", "Recipient is suppressed."
            return
        uncertain = session.scalar(select(EmailMessage.id).join(Enrollment).where(
            Enrollment.recipient == enrollment.recipient, EmailMessage.id != message.id,
            EmailMessage.status.in_(["sending", "unknown"]),
        ))
        if uncertain:
            message.status, message.last_error = "approved", "A previous send to this recipient needs reconciliation."
            return
        try:
            synced = poll_mailbox(session)
        except RuntimeError as exc:
            state = session.get(MailboxState, 1)
            if state:
                state.last_success_at, state.last_error = None, str(exc)
            message.status, message.last_error = "approved", str(exc)
            return
        if not synced:
            message.status, message.last_error = "approved", "Inbox sync is incomplete."
            return
        session.flush()
        if (enrollment.reply_blocked and not message.manual_reply) or session.get(Suppression, enrollment.recipient):
            message.status, message.last_error = "approved", "Reply or suppression detected."
            return
        unresolved = session.scalar(select(EmailReply.id).where(
            EmailReply.enrollment_id.is_(None), EmailReply.classification == "bounce_review"))
        if unresolved:
            message.status, message.last_error = "approved", "Review unmatched delivery reports before sending."
            return
        cutoff = now() - timedelta(hours=24)
        attempts = session.scalar(select(func.count()).select_from(EmailMessage).where(
            EmailMessage.attempted_at >= cutoff,
            EmailMessage.status.in_(["sent", "sending", "unknown"]),
        ))
        if settings.daily_send_limit < 1 or attempts > settings.daily_send_limit:
            message.status, message.last_error = "approved", "Configured daily sending limit reached."
            return
        try:
            mime = message_content(session, message, enrollment)
        except (RuntimeError, ValueError) as exc:
            message.status, message.last_error = "failed", str(exc)
            return
        smtp = None
        try:
            smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(settings.gmail_address, settings.gmail_app_password)
        except (smtplib.SMTPException, OSError) as exc:
            if smtp:
                smtp.close()
            message.status, message.last_error = "failed", f"SMTP connection or authentication failed: {type(exc).__name__}"
            return
        try:
            smtp.send_message(mime)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError) as exc:
            message.status, message.last_error = "failed", f"SMTP rejected the message: {type(exc).__name__}"
            return
        except (smtplib.SMTPException, OSError) as exc:
            message.status, message.last_error = "unknown", f"SMTP outcome is unknown: {type(exc).__name__}"
            return
        finally:
            smtp.close()
        message.status, message.sent_at, message.last_error = "sent", now(), None
        session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
        next_message = session.scalar(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id,
            EmailMessage.step_number == message.step_number + 1,
            EmailMessage.manual_reply.is_(False),
        ))
        if next_message and not message.manual_reply:
            next_message.due_at = message.sent_at + timedelta(days=campaign.delays[message.step_number])
