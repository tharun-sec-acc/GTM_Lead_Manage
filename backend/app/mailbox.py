import email
import imaplib
import hashlib
import re
from datetime import timedelta
from email import policy
from email.utils import parseaddr

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import EmailMessage, EmailReply, Enrollment, MailboxState, Suppression, now

LOCK_ID = 776281946


def lock_mail_workflow(session: Session):
    if session.bind and session.bind.dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_ID})


def plain_body(message):
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
            content = part.get_content()
            return str(content)[:50000]
    return ""


def process_incoming(session: Session, raw: bytes, mailbox_uid: str):
    if session.scalar(select(EmailReply.id).where(EmailReply.mailbox_uid == mailbox_uid)):
        return
    message = email.message_from_bytes(raw, policy=policy.default)
    sender = parseaddr(message.get("From", ""))[1].lower()
    if sender == settings.gmail_address.lower():
        return
    references = " ".join(message.get_all("In-Reply-To", []) + message.get_all("References", []))
    ids = re.findall(r"<[^<>\s]+>", references)
    original = session.scalar(select(EmailMessage).where(EmailMessage.message_id.in_(ids))) if ids else None
    enrollment = session.get(Enrollment, original.enrollment_id) if original else None
    is_dsn = message.get_content_type() == "multipart/report" and (
        message.get_param("report-type", "") or ""
    ).lower() == "delivery-status"
    status_codes = []
    dsn_recipient = ""
    if is_dsn:
        for part in message.walk():
            if part.get_content_type() == "message/delivery-status":
                for block in part.get_payload():
                    status_codes.append(str(block.get("Status", "")))
                    address = str(block.get("Final-Recipient", "")).split(";")[-1].strip().lower()
                    dsn_recipient = address or dsn_recipient
            elif part.get_content_type() == "message/rfc822":
                payload = part.get_payload()
                if payload:
                    original_id = str(payload[0].get("Message-ID", ""))
                    if original_id:
                        original = session.scalar(select(EmailMessage).where(EmailMessage.message_id == original_id))
                        if original:
                            enrollment = session.get(Enrollment, original.enrollment_id)
    matching = []
    if not enrollment and sender and not is_dsn:
        matching = session.scalars(select(Enrollment).where(
            Enrollment.recipient == sender,
            Enrollment.id.in_(select(EmailMessage.enrollment_id).where(EmailMessage.status == "sent")),
        )).all()
        for item in matching:
            item.reply_blocked = True
        if len(matching) == 1:
            enrollment = matching[0]
    if enrollment:
        enrollment.reply_blocked = True
    if sender and not is_dsn:
        for item in session.scalars(select(Enrollment).where(Enrollment.recipient == sender)).all():
            item.reply_blocked = True
    if not enrollment and not matching:
        return
    classification = None
    body = plain_body(message)
    if not is_dsn and enrollment and re.search(
        r"\b(unsubscribe|opt[\s-]?out|do not (?:email|contact))\b", body, re.IGNORECASE
    ):
        if session.get(Suppression, enrollment.recipient) is None:
            session.add(Suppression(email=enrollment.recipient, reason="unsubscribe"))
        classification = "unsubscribe"
    if is_dsn:
        classification = "bounce_review"
        recipient = enrollment.recipient if enrollment else dsn_recipient
        if recipient and any(code.startswith("5.") for code in status_codes):
            if session.get(Suppression, recipient) is None:
                session.add(Suppression(email=recipient, reason="hard_bounce"))
            classification = "hard_bounce"
    try:
        with session.begin_nested():
            reply = EmailReply(
                mailbox_uid=mailbox_uid, enrollment_id=enrollment.id if enrollment else None,
                incoming_message_id=str(message.get("Message-ID", ""))[:998] or None,
                original_email_id=original.id if original else None,
                sender=sender or None, subject=str(message.get("Subject", ""))[:2000],
                body=body, classification=classification,
            )
            session.add(reply)
            session.flush()
    except Exception:
        return

    # Fast heuristic classification first to avoid blocking IMAP synchronization
    if not classification and body:
        from app import bedrock
        fast_cls = bedrock.classify_reply_fast(body)
        if fast_cls and fast_cls != "ambiguous":
            classification = fast_cls
        elif enrollment:
            # Only run Bedrock Claude if email is matched to an active GTM prospect
            try:
                inferred = bedrock.classify_reply(body)
                if inferred:
                    classification = inferred
            except Exception:
                classification = "ambiguous"
        else:
            classification = "unrelated"

    if classification:
        reply.classification = classification
        try:
            from app.reply_actions import apply_classification
            apply_classification(session, reply, classification)
        except Exception:
            pass


def poll_mailbox(session: Session):
    if not settings.gmail_address or not settings.gmail_app_password:
        raise RuntimeError("Gmail address and app password are required for inbox monitoring.")
    state = session.get(MailboxState, 1)
    if state is None:
        state = MailboxState(id=1, last_uid=0)
        session.add(state)
        session.flush()
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=30) as client:
            client.login(settings.gmail_address, settings.gmail_app_password)
            status, _ = client.select("INBOX", readonly=True)
            if status != "OK":
                raise RuntimeError("Could not select the Gmail inbox.")
            _, validity_values = client.response("UIDVALIDITY")
            if not validity_values or not validity_values[0]:
                raise RuntimeError("Gmail did not provide UIDVALIDITY.")
            validity = validity_values[0].decode("ascii")
            account = settings.gmail_address.lower()
            if state.uid_validity != validity or state.account != account:
                state.uid_validity, state.last_uid = validity, 0
                state.account = account
            since_date = (now() - timedelta(days=3)).strftime("%d-%b-%Y")
            status, result = client.uid("search", None, "SINCE", since_date)
            if status != "OK" or not result or not result[0]:
                status, result = client.uid("search", None, "ALL")
            if status != "OK":
                raise RuntimeError("Gmail inbox search failed.")
            all_uids = [int(value) for value in (result[0] or b"").split()]
            max_uid = max(all_uids) if all_uids else 0

            # Prevent historical backlog starvation:
            # If state.last_uid is far behind (> 500 messages behind newest mailbox UID),
            # fast-forward state.last_uid so recent live emails are never starved by months of old personal mail.
            if max_uid - state.last_uid > 500:
                state.last_uid = max(state.last_uid, max_uid - 100)

            uids = [uid for uid in all_uids if uid > state.last_uid]
            account_id = hashlib.sha256(account.encode()).hexdigest()[:16]
            for uid in sorted(uids)[:100]:
                status, parts = client.uid("fetch", str(uid), "(BODY.PEEK[])")
                if status != "OK":
                    raise RuntimeError("Gmail message retrieval failed.")
                raw = next((part[1] for part in parts if isinstance(part, tuple)), None)
                if not isinstance(raw, bytes):
                    raise RuntimeError("Gmail returned an incomplete message.")
                process_incoming(session, raw, f"{account_id}:{validity}:{uid}")
                state.last_uid = uid
            state.last_success_at = now() if len(uids) <= 100 else None
            state.last_error = None
    except TimeoutError as exc:
        state.last_error = "Connection timed out to imap.gmail.com:993"
        session.flush()
        raise RuntimeError("Gmail inbox connection timed out. Check network/firewall access to imap.gmail.com:993.") from exc
    except (imaplib.IMAP4.error, OSError, UnicodeError) as exc:
        state.last_error = f"Authentication/connection failed: {exc}"
        session.flush()
        raise RuntimeError("Gmail inbox connection or authentication failed.") from exc
    return state.last_success_at is not None
