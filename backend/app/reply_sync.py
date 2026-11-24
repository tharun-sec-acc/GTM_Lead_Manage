import email
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AuditLog
from app.models import (
    Contact,
    EmailMessage,
    EmailReply,
    Enrollment,
    Lead,
    Suppression,
    now,
)

logger = logging.getLogger(__name__)


def extract_plain_text(html_or_plain: str) -> str:
    """Strip basic HTML tags to produce a clean plain-text excerpt for classification."""
    if not html_or_plain:
        return ""
    text = re.sub(r"<style.*?</style>", "", html_or_plain, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()[:50000]


def ingest_incoming_email(
    session: Session,
    org_id: str | None,
    mailbox_account_email: str,
    mailbox_uid: str,
    incoming_message_id: str | None,
    in_reply_to: str | None,
    references: str | None,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    received_at: datetime | None = None,
) -> EmailReply | None:
    """
    Unified entry point for ingesting incoming emails and customer replies
    across Gmail API, Microsoft Graph API, and IMAP.
    
    Ensures:
    1. Idempotency via unique mailbox_uid.
    2. Header-based matching via In-Reply-To and References.
    3. Sender-based matching against active Enrollments, Leads, and Contacts.
    4. Immediate reply-blocking to stop automated campaign followups.
    5. Reply classification and sales task assignment.
    """
    clean_sender = (sender or "").lower().strip()
    mailbox_email = (mailbox_account_email or "").lower().strip()

    # Ignore outbound messages sent from the mailbox itself
    if clean_sender == mailbox_email:
        return None

    # Idempotency check
    existing = session.scalar(select(EmailReply).where(EmailReply.mailbox_uid == mailbox_uid))
    if existing:
        return existing

    # 1. Match original sent message via Message-ID in In-Reply-To or References
    all_refs = f"{in_reply_to or ''} {references or ''}".strip()
    ref_ids = re.findall(r"<[^<>\s]+>", all_refs)
    original: EmailMessage | None = None
    if ref_ids:
        original = session.scalar(select(EmailMessage).where(EmailMessage.message_id.in_(ref_ids)))

    enrollment: Enrollment | None = None
    if original and original.enrollment_id:
        enrollment = session.get(Enrollment, original.enrollment_id)

    # 2. Fallback matching: match by sender email address against active enrollments
    matching_enrollments: list[Enrollment] = []
    if not enrollment and clean_sender:
        stmt = (
            select(Enrollment)
            .where(
                Enrollment.recipient == clean_sender,
                Enrollment.id.in_(select(EmailMessage.enrollment_id).where(EmailMessage.status == "sent")),
            )
        )
        matching_enrollments = list(session.scalars(stmt).all())
        if len(matching_enrollments) == 1:
            enrollment = matching_enrollments[0]

    # 3. Stop automated follow-up sequences for matched enrollments
    if enrollment:
        enrollment.reply_blocked = True
    for item in matching_enrollments:
        item.reply_blocked = True

    # Also block any other active enrollment matching this sender
    if clean_sender:
        for other in session.scalars(select(Enrollment).where(Enrollment.recipient == clean_sender)).all():
            other.reply_blocked = True

    # 4. Check for Unsubscribe keywords
    clean_body = extract_plain_text(body)
    classification: str | None = None
    if re.search(r"\b(unsubscribe|opt[\s-]?out|do not (?:email|contact)|remove me)\b", clean_body, re.IGNORECASE):
        if clean_sender and session.get(Suppression, clean_sender) is None:
            session.add(Suppression(email=clean_sender, reason="unsubscribe"))
        classification = "unsubscribe"
        if enrollment:
            enrollment.status = "unsubscribed"

    # 5. Insert EmailReply record
    reply = EmailReply(
        mailbox_uid=mailbox_uid,
        enrollment_id=enrollment.id if enrollment else None,
        incoming_message_id=incoming_message_id[:998] if incoming_message_id else None,
        original_email_id=original.id if original else None,
        sender=clean_sender or None,
        subject=(subject or "")[:2000],
        body=clean_body,
        classification=classification,
        received_at=received_at or now(),
    )
    session.add(reply)
    session.flush()

    # 6. AI Intent Classification (Fast heuristic first, then Claude Bedrock if active prospect)
    if not classification and clean_body:
        from app import bedrock

        fast_cls = bedrock.classify_reply_fast(clean_body)
        if fast_cls and fast_cls != "ambiguous":
            classification = fast_cls
        elif enrollment:
            try:
                inferred = bedrock.classify_reply(clean_body)
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
        except Exception as exc:
            logger.warning("Failed to apply reply classification: %s", exc)

    # 7. Record Audit Log & Activity on the associated Lead
    lead_id: str | None = None
    if enrollment:
        lead_id = enrollment.lead_id
    elif clean_sender:
        lead = session.scalar(select(Lead).where(Lead.email == clean_sender))
        if lead:
            lead_id = lead.id
        else:
            contact = session.scalar(select(Contact).where(Contact.email == clean_sender))
            if contact and contact.lead_id:
                lead_id = contact.lead_id

    audit = AuditLog(
        organization_id=org_id,
        user_id=None,
        action="customer_reply_received",
        resource_type="lead" if lead_id else "email_reply",
        resource_id=lead_id or reply.id,
        details={
            "mailbox": mailbox_account_email,
            "sender": clean_sender,
            "subject": subject,
            "classification": classification,
            "reply_id": reply.id,
            "enrollment_id": enrollment.id if enrollment else None,
            "followups_blocked": True if enrollment else False,
        },
    )
    session.add(audit)
    session.commit()

    logger.info(
        "Successfully ingested incoming email from %s (Subject: %s, Reply ID: %s, Classification: %s)",
        clean_sender,
        subject,
        reply.id,
        classification,
    )
    return reply
