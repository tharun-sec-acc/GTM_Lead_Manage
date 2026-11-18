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
from app.models import (Campaign, EmailAttachment, EmailEvent, EmailMessage, EmailReply, Enrollment,
                        MailboxState, Suppression, TrackingLink, now)

logger = logging.getLogger(__name__)


def public_base():
    base = settings.public_base_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError("PUBLIC_BASE_URL must be an approved public HTTPS URL for unsubscribe or tracking links.")
    return base


def _clean_plain_text(text: str) -> str:
    """Clean plain-text version of email: strip dummy placeholder text and markdown delimiters."""
    if not text:
        return ""
    # Strip accidental unedited placeholder tokens
    cleaned = re.sub(r"\*\*Bold Text\*\*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*Italic Text\*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*\*bold\*\*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*italic\*", "", cleaned, flags=re.IGNORECASE)

    # Strip markdown bold & italic delimiters: **word** -> word, *word* -> word
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"\1", cleaned)
    cleaned = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"\1", cleaned)

    # Markdown links: [anchor](url) -> anchor (url)
    cleaned = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", r"\1 (\2)", cleaned)
    return cleaned.strip()


def _inline_markdown_to_html(text: str) -> str:
    """Format inline markdown elements: bold, italic, links, URLs."""
    s = html.escape(text)

    # Markdown bold: **text** or __text__ -> <strong>text</strong>
    s = re.sub(r"\*\*(.+?)\*\*", r'<strong style="font-weight: 600; color: #0f172a;">\1</strong>', s)
    s = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r'<strong style="font-weight: 600; color: #0f172a;">\1</strong>', s)

    # Markdown italic: *text* or _text_ -> <em>text</em>
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"(?<!\w)_([^_]+?)_(?!\w)", r"<em>\1</em>", s)

    # Markdown link: [text](https://...) -> <a href="...">text</a>
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)", r'<a href="\2" style="color: #0284c7; text-decoration: underline;">\1</a>', s)

    # Autolink raw URLs (not already inside href="...")
    def _link_replace(m):
        u = m.group(0)
        return f'<a href="{u}" style="color: #0284c7; text-decoration: underline;">{u}</a>'

    s = re.sub(r'(?<!href=")(?<!">)https?://[^\s<"\']+', _link_replace, s)
    return s


def _markdown_to_email_html(text: str, tracking_pixel_url: str | None = None) -> str:
    """
    Render email body markdown into clean, sanitized HTML email with proper
    bold (<strong>), italic (<em>), bullet lists (<ul><li>), paragraphs (<p>),
    and links (<a>) suitable for Gmail, Outlook, Apple Mail, and mobile clients.
    """
    if not text:
        text = ""

    # Strip accidental unedited placeholder tokens
    t = re.sub(r"\*\*Bold Text\*\*", "", text, flags=re.IGNORECASE)
    t = re.sub(r"\*Italic Text\*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\*\*bold\*\*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\*italic\*", "", t, flags=re.IGNORECASE)
    t = t.strip()

    raw_blocks = re.split(r"\n\s*\n", t)
    html_blocks = []

    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        is_list = all(re.match(r"^\s*([*\-•]|\d+\.)\s+", l) for l in lines if l.strip())

        if is_list:
            items = []
            for line in lines:
                m = re.match(r"^\s*([*\-•]|\d+\.)\s+(.*)$", line)
                item_content = m.group(2) if m else line
                item_html = _inline_markdown_to_html(item_content)
                items.append(f'<li style="margin-bottom: 6px;">{item_html}</li>')
            html_blocks.append(
                f'<ul style="margin: 0 0 16px 0; padding-left: 22px; font-size: 15px; line-height: 1.6; color: #1e293b;">\n'
                + "\n".join(items)
                + "\n</ul>"
            )
        else:
            line_htmls = [_inline_markdown_to_html(l) for l in lines]
            content = "<br>\n".join(line_htmls)
            html_blocks.append(
                f'<p style="margin: 0 0 16px 0; line-height: 1.6; font-size: 15px; color: #1e293b;">{content}</p>'
            )

    pixel_html = ""
    if tracking_pixel_url:
        pixel_safe = html.escape(tracking_pixel_url, quote=True)
        pixel_html = f'<img src="{pixel_safe}" width="1" height="1" alt="" style="display:none !important;" />'

    body_content = "\n".join(html_blocks)
    return (
        '<!DOCTYPE html>\n'
        '<html>\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        '<style>\n'
        'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; font-size: 15px; line-height: 1.6; color: #1e293b; margin: 0; padding: 16px; background-color: #ffffff; }\n'
        'p { margin: 0 0 16px 0; line-height: 1.6; font-size: 15px; color: #1e293b; }\n'
        'strong { font-weight: 600; color: #0f172a; }\n'
        'em { font-style: italic; }\n'
        'ul { margin: 0 0 16px 0; padding-left: 22px; }\n'
        'li { margin-bottom: 6px; }\n'
        'a { color: #0284c7; text-decoration: underline; }\n'
        '</style>\n</head>\n'
        '<body>\n'
        f'<div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">\n'
        f'{body_content}\n'
        f'{pixel_html}\n'
        '</div>\n</body>\n</html>'
    )


def message_content(
    session: Session,
    message: EmailMessage,
    enrollment: Enrollment,
    explicit_attachments: list[EmailAttachment] | None = None,
):
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

    # Only thread follow-ups or replies; initial outreach (step 0 without reply_to) should be a fresh conversation
    if message.step_number > 0 or message.reply_to_id:
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

    # Set clean text/plain body as the base payload (markdown stripped)
    clean_text = _clean_plain_text(body)
    mime.set_content(clean_text)

    # Attach all files into the same MIME multipart envelope
    if explicit_attachments is not None:
        attachments = explicit_attachments
    else:
        attachments = session.scalars(
            select(EmailAttachment).where(
                EmailAttachment.message_id == message.id,
                EmailAttachment.upload_status == "complete",
            )
        ).all()

    # Add HTML alternative when tracking is enabled, attachments are present, or body has rich formatting
    has_rich_formatting = bool(
        re.search(r"\*\*|\*|_|\[.+?\]\(.+?\)|^\s*[*\-•]\s+", body, re.MULTILINE)
        or "<p>" in body or "<br>" in body or "<strong>" in body or "<b>" in body or "<ul>" in body
    )
    if tracking or attachments or has_rich_formatting:
        pixel = f"{base}/public/open/{message.open_token}" if (tracking and base) else None
        html_markup = _markdown_to_email_html(body, tracking_pixel_url=pixel)
        mime.add_alternative(html_markup, subtype="html")

    if attachments:
        from app.storage import get_storage
        storage = get_storage()
        for att in attachments:
            try:
                raw_bytes = storage.retrieve(att.storage_key)
                mtype, _, stype = (att.content_type or "application/octet-stream").partition("/")
                safe_name = getattr(att, "filename_safe", getattr(att, "file_name", "attachment.pdf"))
                mime.add_attachment(
                    raw_bytes,
                    maintype=mtype or "application",
                    subtype=stype or "octet-stream",
                    filename=safe_name,
                )
                logger.info(
                    "Attached file %s (%d bytes) to message %s along with body",
                    safe_name, len(raw_bytes), message.id,
                )
            except Exception as exc:
                logger.warning("Failed to attach file %s: %s", getattr(att, "filename_safe", "unknown"), exc)
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
