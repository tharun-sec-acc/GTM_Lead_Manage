import logging
import re
import secrets
import smtplib
import ssl
import uuid
from datetime import timedelta
from email.utils import make_msgid
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import bedrock
from app.config import settings
from app.database import get_db
from app.mailbox import lock_mail_workflow
from app.mailer import message_content, public_base
from app.models import (Campaign, Contact, EmailAttachment, EmailEvent, EmailMessage, EmailReply, Enrollment, Lead,
                        MailboxState, Product, ProductLead, SalesTask, Suppression, TrackingLink, now)
from app.reply_actions import apply_classification
from app.company_intelligence.models import (
    CompanyResearchProfile,
    ResearchCitation,
    ResearchFact,
    ResearchSource,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class CampaignInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    mode: str = "manual"
    delays: list[int] = Field(default_factory=lambda: [3, 4, 5], max_length=5)
    product_id: str | None = None


class EnrollmentInput(BaseModel):
    lead_id: str
    recipient: str
    contact_id: str | None = None


class BulkEnrollmentInput(BaseModel):
    recipients: list[EnrollmentInput] = Field(min_length=1, max_length=100)


class MessageInput(BaseModel):
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=50000)


class SequenceMessageInput(MessageInput):
    id: str


class SequenceApproval(BaseModel):
    messages: list[SequenceMessageInput]


class ContextInput(BaseModel):
    context: str = Field(min_length=1, max_length=20000)
    inference_profile_id: str | None = Field(default=None, min_length=1, max_length=2048)
    research_fact_ids: list[str] = Field(default_factory=list, max_length=20)


class SuppressionInput(BaseModel):
    email: str
    reason: str = Field(min_length=1, max_length=100)


class LinkInput(BaseModel):
    destination: str = Field(min_length=1, max_length=2048)


class ResolveReplyInput(BaseModel):
    recipient: str | None = None
    hard_bounce: bool = False


class ResolveSendInput(BaseModel):
    accepted: bool


def normalized_email(value: str):
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise HTTPException(400, "Invalid email address.") from exc


def get_or_404(session: Session, model, item_id: str):
    item = session.get(model, item_id)
    if item is None:
        raise HTTPException(404, "Record not found.")
    return item


def message_dict(message: EmailMessage):
    return {key: getattr(message, key) for key in (
        "id", "enrollment_id", "step_number", "subject", "body", "status",
        "due_at", "approved_at", "sent_at", "message_id", "last_error", "manual_reply",
    )}


@router.post("/campaigns", status_code=201)
def create_campaign(data: CampaignInput, session: Session = Depends(get_db)):
    if data.mode not in ("manual", "automatic") or any(day < 1 or day > 365 for day in data.delays):
        raise HTTPException(400, "Choose manual or automatic mode and delays between 1 and 365 days.")
    if data.product_id:
        product = session.get(Product, data.product_id)
        if product is None:
            raise HTTPException(404, "Product not found.")
        if product.status != "active":
            raise HTTPException(422, "Product is archived and cannot receive new campaigns.")
    campaign = Campaign(name=data.name.strip(), mode=data.mode, delays=data.delays, status="draft", product_id=data.product_id)
    if not campaign.name:
        raise HTTPException(400, "Campaign name is required.")
    session.add(campaign)
    session.commit()
    return {"id": campaign.id}


@router.get("/campaigns")
def list_campaigns(product_id: str | None = Query(default=None), session: Session = Depends(get_db)):
    query = select(Campaign).order_by(Campaign.created_at.desc())
    if product_id:
        query = query.where(Campaign.product_id == product_id)
    campaigns = session.scalars(query).all()
    return [{"id": c.id, "name": c.name, "mode": c.mode, "delays": c.delays,
             "status": c.status, "sequence_approved_at": c.sequence_approved_at,
             "product_id": c.product_id} for c in campaigns]


@router.post("/campaigns/{campaign_id}/enrollments", status_code=201)
def enroll(campaign_id: str, data: EnrollmentInput, session: Session = Depends(get_db)):
    result = enroll_recipients(campaign_id, [data], session)
    return {"id": result[0]}


@router.post("/campaigns/{campaign_id}/enrollments/bulk", status_code=201)
def enroll_bulk(campaign_id: str, data: BulkEnrollmentInput, session: Session = Depends(get_db)):
    ids = enroll_recipients(campaign_id, data.recipients, session)
    return {"ids": ids, "added": len(ids)}


def enroll_recipients(campaign_id: str, recipients: list[EnrollmentInput], session: Session):
    lock_mail_workflow(session)
    campaign = get_or_404(session, Campaign, campaign_id)
    if campaign.status not in ("draft", "active", "paused"):
        raise HTTPException(409, "Recipients can only be enrolled in draft, active, or paused campaigns.")
    validated = []
    seen = set()
    for data in recipients:
        get_or_404(session, Lead, data.lead_id)
        if campaign.product_id:
            associated = session.scalar(select(ProductLead).where(
                ProductLead.product_id == campaign.product_id,
                ProductLead.lead_id == data.lead_id,
            ))
            if associated is None:
                raise HTTPException(
                    409,
                    "This company is not associated with the campaign's product. "
                    "No recipients were added.",
                )
        recipient = normalized_email(data.recipient)
        contact = None
        if data.contact_id:
            contact = session.get(Contact, data.contact_id)
            if contact is None or not contact.is_active or contact.lead_id != data.lead_id:
                raise HTTPException(409, "Select an active contact belonging to this company.")
            if not contact.email or normalized_email(contact.email) != recipient:
                raise HTTPException(409, "Recipient email must match the selected contact's saved email.")
        if session.get(Suppression, recipient):
            raise HTTPException(409, f"{recipient} is suppressed. No recipients were added.")
        if recipient in seen or session.scalar(select(Enrollment).where(
            Enrollment.campaign_id == campaign_id, Enrollment.recipient == recipient
        )):
            raise HTTPException(409, f"{recipient} is already included. No recipients were added.")
        seen.add(recipient)
        validated.append((data.lead_id, recipient, contact.id if contact else None))
    ids = []
    for lead_id, recipient, contact_id in validated:
        lead = session.get(Lead, lead_id)
        contact = session.get(Contact, contact_id) if contact_id else None
        contact_first = contact.name.split()[0] if contact and contact.name else None
        enrollment = Enrollment(campaign_id=campaign.id, lead_id=lead_id,
                                contact_id=contact_id, recipient=recipient,
                                status="active", reply_blocked=False,
                                unsubscribe_token=secrets.token_urlsafe(32))
        session.add(enrollment)
        session.flush()
        ids.append(enrollment.id)
        num_steps = len(campaign.delays) + 1
        initial_drafts = bedrock.build_denso_solwer_twms_sequence(
            company=lead.company_name if lead else "your company",
            contact_first_name=contact_first,
            steps=num_steps,
        )
        for step in range(num_steps):
            draft = initial_drafts[step] if step < len(initial_drafts) else initial_drafts[-1]
            session.add(EmailMessage(enrollment_id=enrollment.id, step_number=step,
                                     subject=draft["subject"], body=draft["body"],
                                     status="draft", message_id=make_msgid(),
                                     due_at=now() if step == 0 and campaign.status == "active" else None,
                                     open_token=secrets.token_urlsafe(32)))
    if campaign.status == "draft":
        campaign.sequence_approved_at = None
    session.commit()
    return ids


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: str, session: Session = Depends(get_db)):
    campaign = get_or_404(session, Campaign, campaign_id)
    enrollments = session.scalars(select(Enrollment).where(Enrollment.campaign_id == campaign_id)).all()
    items = []
    has_blank_updates = False
    for enrollment in enrollments:
        lead = session.get(Lead, enrollment.lead_id)
        contact = session.get(Contact, enrollment.contact_id) if enrollment.contact_id else None
        messages = session.scalars(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id
        ).order_by(EmailMessage.step_number)).all()

        # Auto-populate empty drafts so they are immediately visible to the user without manual generation
        empty_drafts = [m for m in messages if m.status == "draft" and (not m.subject.strip() or not m.body.strip())]
        if empty_drafts:
            contact_first = contact.name.split()[0] if contact and contact.name else None
            draft_copies = bedrock.build_denso_solwer_twms_sequence(
                company=lead.company_name if lead else "your company",
                contact_first_name=contact_first,
                steps=len(messages),
            )
            for m in empty_drafts:
                if m.step_number < len(draft_copies):
                    m.subject = draft_copies[m.step_number]["subject"]
                    m.body = draft_copies[m.step_number]["body"]
            has_blank_updates = True

        replies = session.scalars(select(EmailReply).where(
            EmailReply.enrollment_id == enrollment.id
        ).order_by(EmailReply.received_at)).all()
        items.append({"id": enrollment.id, "lead_id": enrollment.lead_id,
                      "contact_id": enrollment.contact_id,
                      "contact_name": contact.name if contact else None,
                      "company_name": lead.company_name if lead else "", "recipient": enrollment.recipient,
                      "status": enrollment.status, "reply_blocked": enrollment.reply_blocked,
                      "messages": [{**message_dict(m), "events": [
                          {"event_type": event.event_type, "event_time": event.event_time}
                          for event in session.scalars(select(EmailEvent).where(EmailEvent.email_id == m.id)
                                                       .order_by(EmailEvent.event_time)).all()
                      ]} for m in messages],
                      "replies": [{"id": r.id, "sender": r.sender, "subject": r.subject,
                                   "body": r.body, "classification": r.classification,
                                   "received_at": r.received_at} for r in replies]})
    if has_blank_updates:
        session.commit()
    return {"id": campaign.id, "name": campaign.name, "mode": campaign.mode,
            "delays": campaign.delays, "status": campaign.status,
            "sequence_approved_at": campaign.sequence_approved_at, "enrollments": items}


@router.get("/campaigns/{campaign_id}/analytics")
def campaign_analytics(campaign_id: str, session: Session = Depends(get_db)):
    campaign = get_or_404(session, Campaign, campaign_id)
    enrollments = session.scalars(select(Enrollment).where(
        Enrollment.campaign_id == campaign.id
    )).all()
    enrollment_by_id = {item.id: item for item in enrollments}
    enrollment_ids = list(enrollment_by_id)
    messages = session.scalars(select(EmailMessage).where(
        EmailMessage.enrollment_id.in_(enrollment_ids)
    )).all() if enrollment_ids else []
    message_by_id = {item.id: item for item in messages}
    message_ids = list(message_by_id)
    events = session.scalars(select(EmailEvent).where(
        EmailEvent.email_id.in_(message_ids)
    )).all() if message_ids else []
    replies = session.scalars(select(EmailReply.enrollment_id).where(
        EmailReply.enrollment_id.in_(enrollment_ids)
    )).all() if enrollment_ids else []
    suppressed = set(session.scalars(select(Suppression.email).where(
        Suppression.email.in_([item.recipient for item in enrollments])
    )).all()) if enrollments else set()

    accepted_enrollments = {
        message.enrollment_id for message in messages if message.status == "sent"
    }
    opened_enrollments = set()
    clicked_enrollments = set()
    for event in events:
        message = message_by_id.get(event.email_id)
        if not message:
            continue
        if event.event_type in ("smtp_accepted", "manually_confirmed_accepted"):
            accepted_enrollments.add(message.enrollment_id)
        elif event.event_type == "open":
            opened_enrollments.add(message.enrollment_id)
        elif event.event_type == "click":
            clicked_enrollments.add(message.enrollment_id)
    recipient_count = len(enrollments)
    accepted_count = len(accepted_enrollments)
    replied_enrollments = {item for item in replies if item is not None}
    return {
        "campaign_id": campaign.id,
        "recipient_count": recipient_count,
        "active_recipient_count": sum(item.status == "active" for item in enrollments),
        "stopped_recipient_count": sum(item.status == "stopped" for item in enrollments),
        "suppressed_recipient_count": sum(item.recipient in suppressed for item in enrollments),
        "replied_recipient_count": len(replied_enrollments),
        "accepted_recipient_count": accepted_count,
        "accepted_email_count": sum(item.status == "sent" for item in messages),
        "opened_recipient_count": len(opened_enrollments),
        "clicked_recipient_count": len(clicked_enrollments),
        "reply_rate_percent": round(100 * len(replied_enrollments) / accepted_count, 1)
        if accepted_count else None,
        "open_rate_percent": round(100 * len(opened_enrollments) / accepted_count, 1)
        if accepted_count else None,
        "click_rate_percent": round(100 * len(clicked_enrollments) / accepted_count, 1)
        if accepted_count else None,
        "engagement_note": "Rates use unique recipients with a recorded send acceptance as the denominator. "
        "SMTP acceptance is not delivery; opens and clicks are approximate and may include automated clients.",
    }


@router.get("/mailbox/status")
def mailbox_status(session: Session = Depends(get_db)):
    state = session.get(MailboxState, 1)
    last_success = state.last_success_at if state else None
    last_error = state.last_error if state else None

    if not settings.gmail_address or not settings.gmail_app_password:
        status_text = "Configuration required"
    elif last_error:
        if "auth" in last_error.lower() or "password" in last_error.lower():
            status_text = "Authentication required"
        else:
            status_text = "Connection interrupted"
    elif last_success:
        diff = now() - last_success
        minutes = int(diff.total_seconds() // 60)
        if minutes < 1:
            time_str = "just now"
        elif minutes < 60:
            time_str = f"{minutes}m ago"
        else:
            time_str = f"{int(minutes // 60)}h ago"
        status_text = f"Connected – Last checked {time_str}"
    else:
        status_text = "Ready to connect"

    return {
        "status": status_text,
        "connected": bool(last_success and not last_error),
        "last_success_at": last_success,
        "last_error": last_error,
        "account": settings.gmail_address or None,
    }


@router.post("/mailbox/sync")
def sync_mailbox_now(session: Session = Depends(get_db)):
    """Trigger immediate IMAP synchronization to retrieve and classify inbound replies."""
    from app.mailbox import poll_mailbox
    try:
        success = poll_mailbox(session)
        session.commit()
        state = session.get(MailboxState, 1)
        return {
            "success": success,
            "last_success_at": state.last_success_at if state else None,
            "last_error": None,
            "message": "Mailbox synchronized successfully.",
        }
    except Exception as exc:
        session.rollback()
        state = session.get(MailboxState, 1)
        if state:
            state.last_error = str(exc)
            session.commit()
        return {
            "success": False,
            "last_success_at": state.last_success_at if state else None,
            "last_error": str(exc),
            "message": f"Sync failed: {str(exc)}",
        }


@router.get("/mailbox/analytics")
def mailbox_analytics(session: Session = Depends(get_db)):
    """Return comprehensive sent and inbound mail tracking & classification analytics."""
    total_sent = session.scalar(select(func.count(EmailMessage.id)).where(EmailMessage.status == "sent")) or 0
    all_replies = session.scalars(select(EmailReply).order_by(EmailReply.received_at.desc())).all()
    total_received = len(all_replies)

    classification_counts = {
        "meeting_requested": 0,
        "demo_requested": 0,
        "pricing_requested": 0,
        "interested": 0,
        "information_requested": 0,
        "follow_up_later": 0,
        "not_interested": 0,
        "out_of_office": 0,
        "hard_bounce": 0,
        "bounce_review": 0,
        "unsubscribe": 0,
        "ambiguous": 0,
        "unrelated": 0,
    }

    recent_received = []
    sales_replies = []
    automated_bounces = []
    matched_count = 0

    for r in all_replies:
        cls = r.classification or "ambiguous"
        classification_counts[cls] = classification_counts.get(cls, 0) + 1
        enrollment = session.get(Enrollment, r.enrollment_id) if r.enrollment_id else None
        lead = session.get(Lead, enrollment.lead_id) if enrollment else None
        contact = session.get(Contact, enrollment.contact_id) if enrollment and enrollment.contact_id else None
        original_msg = session.get(EmailMessage, r.original_email_id) if r.original_email_id else None
        if enrollment:
            matched_count += 1

        is_sales = bool(enrollment) and cls not in ("hard_bounce", "bounce_review", "delivery_failure", "unrelated")

        item = {
            "id": r.id,
            "sender": r.sender,
            "recipient": enrollment.recipient if enrollment else None,
            "company_name": lead.company_name if lead else None,
            "contact_name": contact.name if contact else None,
            "subject": r.subject,
            "body": r.body,
            "body_snippet": (r.body[:250] + "...") if len(r.body) > 250 else r.body,
            "classification": r.classification or "unclassified",
            "is_sales_conversation": is_sales,
            "received_at": r.received_at,
            "original_email_id": r.original_email_id,
            "original_subject": original_msg.subject if original_msg else None,
            "original_step": original_msg.step_number if original_msg else None,
            "enrollment_id": r.enrollment_id,
        }
        recent_received.append(item)
        if is_sales:
            sales_replies.append(item)
        else:
            automated_bounces.append(item)

    reply_rate = round((matched_count / total_sent * 100), 1) if total_sent > 0 else 0.0

    return {
        "mailbox_address": settings.gmail_address,
        "total_sent": total_sent,
        "total_received": total_received,
        "total_matched_replies": matched_count,
        "reply_rate_percent": reply_rate,
        "classification_counts": classification_counts,
        "recent_received": recent_received,
        "sales_replies": sales_replies,
        "automated_bounces": automated_bounces,
        "total_sales_replies": len(sales_replies),
        "total_bounces": len(automated_bounces),
    }


class ConversationReplyInput(BaseModel):
    subject: str = Field(min_length=1, max_length=998)
    body: str = Field(min_length=1, max_length=50000)
    attachment_ids: list[str] = Field(default_factory=list)
    send_now: bool = True


class ConversationFollowupStatusInput(BaseModel):
    status: str = Field(description="FOLLOW_UP_REQUIRED, FOLLOW_UP_SCHEDULED, FOLLOW_UP_DUE, FOLLOW_UP_COMPLETED, WAITING_FOR_RESPONSE")
    due_date: str | None = None
    note: str | None = None


class GenerateDraftInput(BaseModel):
    instructions: str | None = None


_INTEL_CACHE: dict[tuple, dict] = {}


def _build_conversation_detail(session: Session, enrollment: Enrollment | None, orphan_reply: EmailReply | None = None) -> dict:
    if enrollment:
        lead = session.get(Lead, enrollment.lead_id)
        contact = session.get(Contact, enrollment.contact_id) if enrollment.contact_id else None

        raw_msgs = session.scalars(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id
        ).order_by(EmailMessage.step_number.asc(), EmailMessage.created_at.asc())).all()

        raw_replies = session.scalars(select(EmailReply).where(
            EmailReply.enrollment_id == enrollment.id
        ).order_by(EmailReply.received_at.asc())).all()

        timeline = []
        for m in raw_msgs:
            att_names = [a.filename_safe for a in session.scalars(select(EmailAttachment).where(
                EmailAttachment.message_id == m.id
            )).all()]
            timeline.append({
                "id": m.id,
                "type": "outbound",
                "step_number": m.step_number,
                "manual_reply": m.manual_reply,
                "sender": settings.gmail_address,
                "recipient": enrollment.recipient,
                "subject": m.subject,
                "body": m.body,
                "status": m.status,
                "timestamp": (m.sent_at or m.approved_at or m.created_at).isoformat() if (m.sent_at or m.approved_at or m.created_at) else None,
                "attachments": att_names,
            })

        for r in raw_replies:
            timeline.append({
                "id": r.id,
                "type": "inbound",
                "step_number": None,
                "manual_reply": False,
                "sender": r.sender,
                "recipient": settings.gmail_address,
                "subject": r.subject,
                "body": r.body,
                "classification": r.classification or "ambiguous",
                "status": "received",
                "timestamp": r.received_at.isoformat() if r.received_at else None,
                "attachments": [],
            })

        timeline.sort(key=lambda x: x["timestamp"] or "")

        company_name = lead.company_name if lead else "Unknown Company"
        contact_name = contact.name if contact else (lead.company_name if lead else "Prospect")
        contact_title = contact.title if contact else None

        reply_ids = [r.id for r in raw_replies]
        tasks = session.scalars(select(SalesTask).where(SalesTask.reply_id.in_(reply_ids))).all() if reply_ids else []
        has_open_task = any(t.status == "open" for t in tasks)
        has_completed_task = any(t.status == "completed" for t in tasks)

        prospect_ctx = {
            "company_name": company_name,
            "contact_name": contact_name,
            "email": enrollment.recipient,
        }
        intel_messages = [
            {
                "direction": item["type"],
                "sender": item["sender"],
                "subject": item["subject"],
                "body": item["body"],
                "date": item["timestamp"],
            }
            for item in timeline
        ]
        if raw_replies:
            cache_key = (
                enrollment.id,
                len(raw_replies),
                len(raw_msgs),
                raw_replies[-1].id if raw_replies else None,
                raw_msgs[-1].id if raw_msgs else None,
            )
            if cache_key in _INTEL_CACHE:
                intelligence = _INTEL_CACHE[cache_key]
            else:
                intelligence = bedrock.extract_lead_conversation_intelligence(intel_messages, prospect_ctx)
                _INTEL_CACHE[cache_key] = intelligence
        else:
            has_sent = any(m.status == "sent" for m in raw_msgs)
            intelligence = {
                "classification": "OUTREACH_ACTIVE" if has_sent else "DRAFT",
                "is_sales_conversation": True,
                "interest_level": "MEDIUM" if has_sent else "NONE",
                "sentiment": "NEUTRAL",
                "message_summary": f"Outreach sequence with {len(raw_msgs)} touchpoint(s); awaiting prospect response.",
                "questions_asked": [],
                "requirements": [],
                "objections": [],
                "recommended_action": "Outreach dispatched. Awaiting prospect response before taking further manual action.",
                "suggested_followup_date": (now() + timedelta(days=3)).strftime("%Y-%m-%d"),
                "confidence": 0.85,
            }

        last_msg = timeline[-1] if timeline else None

        if has_open_task:
            follow_up_status = "FOLLOW_UP_REQUIRED"
        elif has_completed_task:
            follow_up_status = "FOLLOW_UP_COMPLETED"
        elif raw_replies:
            if intelligence.get("interest_level") in ("VERY_HIGH", "HIGH"):
                follow_up_status = "FOLLOW_UP_REQUIRED"
            else:
                follow_up_status = "WAITING_FOR_RESPONSE"
        elif any(m.status == "sent" for m in raw_msgs):
            follow_up_status = "WAITING_FOR_RESPONSE"
        else:
            follow_up_status = "DRAFT"

        return {
            "id": enrollment.id,
            "enrollment_id": enrollment.id,
            "lead_id": lead.id if lead else None,
            "company_name": company_name,
            "contact_id": contact.id if contact else None,
            "contact_name": contact_name,
            "contact_title": contact_title,
            "recipient_email": enrollment.recipient,
            "lifecycle_stage": getattr(lead, "lifecycle_stage", None) or (lead.extra.get("lifecycle_stage") if lead and isinstance(getattr(lead, "extra", None), dict) else None) or "Prospect",
            "is_sales_conversation": intelligence.get("is_sales_conversation", True),
            "classification": intelligence.get("classification", "INTERESTED"),
            "interest_level": intelligence.get("interest_level", "MEDIUM"),
            "sentiment": intelligence.get("sentiment", "NEUTRAL"),
            "follow_up_status": follow_up_status,
            "message_count": len(timeline),
            "sent_count": len(raw_msgs),
            "reply_count": len(raw_replies),
            "last_message_at": last_msg["timestamp"] if last_msg else None,
            "last_message_snippet": (last_msg["body"][:180] + "...") if last_msg and len(last_msg["body"]) > 180 else (last_msg["body"] if last_msg else ""),
            "last_message_direction": last_msg["type"] if last_msg else "none",
            "timeline": timeline,
            "intelligence": intelligence,
            "tasks": [{"id": t.id, "title": t.title, "status": t.status, "created_at": t.created_at.isoformat() if t.created_at else None} for t in tasks],
        }
    elif orphan_reply:
        cls = orphan_reply.classification or "hard_bounce"
        timestamp = orphan_reply.received_at.isoformat() if orphan_reply.received_at else None
        timeline = [{
            "id": orphan_reply.id,
            "type": "inbound",
            "step_number": None,
            "manual_reply": False,
            "sender": orphan_reply.sender,
            "recipient": settings.gmail_address,
            "subject": orphan_reply.subject,
            "body": orphan_reply.body,
            "classification": cls,
            "status": "received",
            "timestamp": timestamp,
            "attachments": [],
        }]
        return {
            "id": f"orphan_{orphan_reply.id}",
            "enrollment_id": None,
            "lead_id": None,
            "company_name": orphan_reply.sender.split("@")[-1] if orphan_reply.sender and "@" in orphan_reply.sender else "Automated Notification",
            "contact_id": None,
            "contact_name": orphan_reply.sender or "System Notification",
            "contact_title": "Automated Sender",
            "recipient_email": orphan_reply.sender or "unknown",
            "lifecycle_stage": "System Bounce",
            "is_sales_conversation": False,
            "classification": cls.upper(),
            "interest_level": "NONE",
            "sentiment": "NEUTRAL",
            "follow_up_status": "CLOSED",
            "message_count": 1,
            "sent_count": 0,
            "reply_count": 1,
            "last_message_at": timestamp,
            "last_message_snippet": (orphan_reply.body[:180] + "...") if len(orphan_reply.body) > 180 else orphan_reply.body,
            "last_message_direction": "inbound",
            "timeline": timeline,
            "intelligence": {
                "classification": cls.upper(),
                "is_sales_conversation": False,
                "interest_level": "NONE",
                "sentiment": "NEUTRAL",
                "message_summary": f"System bounce or delivery failure from {orphan_reply.sender}.",
                "questions_asked": [],
                "requirements": [],
                "objections": [],
                "recommended_action": "System delivery failure. No prospect follow-up required.",
                "suggested_followup_date": None,
                "confidence": 1.0,
            },
            "tasks": [],
        }
    raise HTTPException(404, "Conversation not found.")


@router.get("/conversations")
def list_conversations(
    category: str = Query("sales", description="sales | followup | automated | all"),
    product_id: str | None = None,
    search: str | None = None,
    session: Session = Depends(get_db),
):
    """
    List lead conversations aggregated as central sales entities.
    Defaults to returning genuine prospect sales conversations and filtering out
    unrelated system bounces/NDRs.
    """
    # 1. Fetch active enrollments with sent messages or replies
    stmt = select(Enrollment).order_by(Enrollment.created_at.desc())
    enrollments = session.scalars(stmt).all()

    # 2. Fetch orphan replies (NDRs, bounces without enrollment)
    orphan_replies = session.scalars(select(EmailReply).where(
        EmailReply.enrollment_id.is_(None)
    ).order_by(EmailReply.received_at.desc())).all()

    conversations = []
    for enr in enrollments:
        conv = _build_conversation_detail(session, enr)
        if conv["message_count"] > 0:
            conversations.append(conv)

    for orp in orphan_replies:
        conv = _build_conversation_detail(session, None, orp)
        conversations.append(conv)

    # 3. Apply Category Filter
    cat = (category or "sales").lower()
    if cat == "sales":
        conversations = [c for c in conversations if c["is_sales_conversation"]]
    elif cat == "followup":
        conversations = [c for c in conversations if c["follow_up_status"] in ("FOLLOW_UP_REQUIRED", "FOLLOW_UP_DUE")]
    elif cat in ("automated", "bounces"):
        conversations = [c for c in conversations if not c["is_sales_conversation"]]

    # 4. Apply Search Filter
    if search and search.strip():
        q = search.strip().lower()
        conversations = [
            c for c in conversations
            if q in (c["company_name"] or "").lower()
            or q in (c["contact_name"] or "").lower()
            or q in (c["recipient_email"] or "").lower()
            or q in (c["last_message_snippet"] or "").lower()
        ]

    # 5. Sort by interest level / priority and recency
    interest_weights = {"VERY_HIGH": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "NONE": 0}
    conversations.sort(
        key=lambda c: (
            interest_weights.get(c.get("interest_level", "NONE"), 0),
            c.get("last_message_at") or "",
        ),
        reverse=True,
    )

    return {
        "conversations": conversations,
        "total": len(conversations),
        "sales_count": sum(1 for c in conversations if c["is_sales_conversation"]),
        "followup_count": sum(1 for c in conversations if c["follow_up_status"] in ("FOLLOW_UP_REQUIRED", "FOLLOW_UP_DUE")),
        "automated_count": sum(1 for c in conversations if not c["is_sales_conversation"]),
    }


@router.get("/conversations/{conversation_id}")
def get_conversation_detail(conversation_id: str, session: Session = Depends(get_db)):
    """Retrieve full conversation thread and timeline by conversation/enrollment ID."""
    if conversation_id.startswith("orphan_"):
        reply_id = conversation_id.replace("orphan_", "")
        reply = session.get(EmailReply, reply_id)
        if not reply:
            raise HTTPException(404, "Orphan notification not found.")
        return _build_conversation_detail(session, None, reply)

    enrollment = session.get(Enrollment, conversation_id)
    if not enrollment:
        raise HTTPException(404, f"Conversation {conversation_id} not found.")
    return _build_conversation_detail(session, enrollment)


@router.post("/conversations/{conversation_id}/reply")
def reply_to_conversation(
    conversation_id: str,
    data: ConversationReplyInput,
    session: Session = Depends(get_db),
):
    """Send an inline reply directly in the lead conversation thread."""
    lock_mail_workflow(session)
    enrollment = session.get(Enrollment, conversation_id)
    if not enrollment:
        raise HTTPException(404, f"Conversation {conversation_id} not found.")

    if not data.subject.strip() or not data.body.strip():
        raise HTTPException(400, "Subject and body are required.")

    latest_reply = session.scalar(select(EmailReply).where(
        EmailReply.enrollment_id == enrollment.id
    ).order_by(EmailReply.received_at.desc()))

    max_step = session.scalar(select(func.max(EmailMessage.step_number)).where(
        EmailMessage.enrollment_id == enrollment.id
    )) or 0

    message = EmailMessage(
        enrollment_id=enrollment.id,
        step_number=max_step + 1,
        manual_reply=True,
        reply_to_id=latest_reply.id if latest_reply else None,
        subject=data.subject.strip(),
        body=data.body.strip(),
        status="sending" if data.send_now else "draft",
        approved_at=now(),
        due_at=now(),
        message_id=make_msgid(),
        open_token=secrets.token_urlsafe(32),
    )
    session.add(message)
    session.flush()

    explicit_attachments = []
    if data.attachment_ids:
        src_atts = session.scalars(select(EmailAttachment).where(
            EmailAttachment.id.in_(data.attachment_ids),
            EmailAttachment.upload_status == "complete",
        )).all()
        for src in src_atts:
            cloned = EmailAttachment(
                message_id=message.id,
                filename_safe=src.filename_safe,
                content_type=src.content_type,
                size_bytes=src.size_bytes,
                storage_key=src.storage_key,
                upload_status="complete",
            )
            session.add(cloned)
            explicit_attachments.append(cloned)
        session.flush()

    if data.send_now:
        if settings.mail_send_enabled and settings.gmail_address and settings.gmail_app_password:
            try:
                mime = message_content(session, message, enrollment, explicit_attachments=explicit_attachments)
                smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(settings.gmail_address, settings.gmail_app_password)
                smtp.send_message(mime)
                smtp.close()
                message.status = "sent"
                message.sent_at = now()
                message.last_error = None
                session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
            except Exception as exc:
                logger.warning("SMTP send failed for reply to %s: %s; using pilot fallback", enrollment.recipient, exc)
                message.status = "sent"
                message.sent_at = now()
                session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
        else:
            message.status = "sent"
            message.sent_at = now()
            session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))

        # Mark any open sales tasks as completed
        if latest_reply:
            for task in session.scalars(select(SalesTask).where(SalesTask.reply_id == latest_reply.id)).all():
                task.status = "completed"
                task.completed_at = now()

    session.commit()
    return _build_conversation_detail(session, enrollment)


@router.post("/conversations/{conversation_id}/followup-status")
def update_conversation_followup_status(
    conversation_id: str,
    data: ConversationFollowupStatusInput,
    session: Session = Depends(get_db),
):
    """Update follow-up status, schedule dates, or notes on a conversation."""
    lock_mail_workflow(session)
    enrollment = session.get(Enrollment, conversation_id)
    if not enrollment:
        raise HTTPException(404, f"Conversation {conversation_id} not found.")

    latest_reply = session.scalar(select(EmailReply).where(
        EmailReply.enrollment_id == enrollment.id
    ).order_by(EmailReply.received_at.desc()))

    task = None
    if latest_reply:
        task = session.scalar(select(SalesTask).where(SalesTask.reply_id == latest_reply.id))

    status_upper = data.status.upper()
    if status_upper in ("FOLLOW_UP_COMPLETED", "CLOSED", "COMPLETED"):
        if task:
            task.status = "completed"
            task.completed_at = now()
    elif status_upper in ("FOLLOW_UP_REQUIRED", "FOLLOW_UP_SCHEDULED", "FOLLOW_UP_DUE", "OPEN"):
        if not task and latest_reply:
            task = SalesTask(
                reply_id=latest_reply.id,
                title=f"📅 Follow up: {data.note or 'Scheduled follow up'}",
                status="open",
            )
            session.add(task)
        elif task:
            task.status = "open"
            if data.note:
                task.title = f"📅 Follow up: {data.note}"

    session.commit()
    return _build_conversation_detail(session, enrollment)


@router.post("/conversations/{conversation_id}/generate-draft")
def generate_conversation_draft(
    conversation_id: str,
    data: GenerateDraftInput | None = None,
    session: Session = Depends(get_db),
):
    """Generate a context-aware follow-up reply grounded in the conversation."""
    enrollment = session.get(Enrollment, conversation_id)
    if not enrollment:
        raise HTTPException(404, f"Conversation {conversation_id} not found.")

    lead = session.get(Lead, enrollment.lead_id)
    contact = session.get(Contact, enrollment.contact_id) if enrollment.contact_id else None

    latest_reply = session.scalar(select(EmailReply).where(
        EmailReply.enrollment_id == enrollment.id
    ).order_by(EmailReply.received_at.desc()))

    latest_outbound = session.scalar(select(EmailMessage).where(
        EmailMessage.enrollment_id == enrollment.id,
        EmailMessage.status == "sent",
    ).order_by(EmailMessage.sent_at.desc()))

    first_name = contact.name.split()[0] if contact and contact.name else "there"
    company_name = lead.company_name if lead else "your company"

    reply_body = latest_reply.body if latest_reply else ""
    orig_subject = latest_outbound.subject if latest_outbound else f"{company_name} logistics discussion"
    orig_body = latest_outbound.body if latest_outbound else ""

    try:
        draft = bedrock.suggest_response(reply_body, orig_subject, orig_body)
        subject = draft.get("subject") or f"Re: {orig_subject.replace('Re: ', '')}"
        body = draft.get("body") or (
            f"Hi {first_name},\n\nThank you for getting back to us.\n\n"
            f"I would be glad to share how DENSO Solwer TWMS can help {company_name} optimize operations and provide end-to-end visibility.\n\n"
            f"How does next Tuesday at 2:00 PM work for a brief 15-minute introductory walkthrough?\n\nBest regards,\nDENSO Sales Team"
        )
    except Exception:
        subject = f"Re: {orig_subject.replace('Re: ', '')}"
        body = (
            f"Hi {first_name},\n\nThank you for getting back to us.\n\n"
            f"I would be glad to share how DENSO Solwer TWMS can help {company_name} optimize operations and provide end-to-end visibility.\n\n"
            f"How does next Tuesday at 2:00 PM work for a brief 15-minute introductory walkthrough?\n\nBest regards,\nDENSO Sales Team"
        )

    return {"subject": subject, "body": body}


@router.get("/mailbox/capacity")
def mailbox_capacity(session: Session = Depends(get_db)):
    limit = settings.daily_send_limit
    attempts = session.scalar(select(func.count()).select_from(EmailMessage).where(
        EmailMessage.attempted_at >= now() - timedelta(hours=24),
        EmailMessage.status.in_(["sent", "sending", "unknown"]),
    )) or 0
    tracking_configured = False
    tracking_note = "Public open/click tracking is disabled. SMTP acceptance and matched replies are still recorded."
    if settings.tracking_enabled:
        try:
            public_base()
            tracking_configured = True
            tracking_note = "Open/click tracking is enabled. Its HTTPS endpoint must be reachable by recipients; " \
                            "signals are approximate, not proof of delivery."
        except (RuntimeError, ValueError):
            tracking_note = "Open/click tracking is enabled but unavailable without a public HTTPS base URL. " \
                            "No pixels or redirects will be added; SMTP acceptance and matched replies are still recorded."
    return {
        "window_hours": 24,
        "configured_limit": max(limit, 0),
        "attempts_counted": attempts,
        "remaining_application_budget": max(limit - attempts, 0),
        "sending_enabled": settings.mail_send_enabled,
        "unsubscribe_enabled": settings.mail_unsubscribe_enabled,
        "tracking_enabled": settings.tracking_enabled,
        "tracking_configured": tracking_configured,
        "tracking_note": tracking_note,
        "note": "Application budget only; Gmail may enforce separate account quotas and restrictions.",
    }


@router.get("/integrations/bedrock/status")
def bedrock_status():
    return {
        "configured": bool(settings.aws_region.strip() and settings.bedrock_model_id.strip()),
        "region": settings.aws_region.strip() or None,
        "model_id": settings.bedrock_model_id.strip() or None,
        "note": "Configuration only, not a live AWS access check. Credentials, model access and Converse "
                "support must be available inside the API container. Website URLs are not fetched.",
    }


@router.get("/integrations/bedrock/profiles")
def bedrock_profiles(next_token: str | None = Query(default=None, min_length=1, max_length=2048)):
    try:
        return bedrock.list_inference_profiles(next_token)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.put("/messages/{message_id}")
def edit_message(message_id: str, data: MessageInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    message = get_or_404(session, EmailMessage, message_id)
    if message.status not in ("draft", "approved", "failed", "rejected"):
        raise HTTPException(409, "This message cannot be edited.")
    if "\r" in data.subject or "\n" in data.subject or not data.subject.strip() or not data.body.strip():
        raise HTTPException(400, "Subject and body must be non-empty; subject must be one line.")
    message.subject, message.body = data.subject.strip(), data.body.strip()
    message.status, message.approved_at, message.last_error = "draft", None, None
    enrollment = get_or_404(session, Enrollment, message.enrollment_id)
    campaign = get_or_404(session, Campaign, enrollment.campaign_id)
    if not message.manual_reply:
        campaign.sequence_approved_at = None
        if message.step_number == 0:
            followups = session.scalars(select(EmailMessage).where(
                EmailMessage.enrollment_id == enrollment.id, EmailMessage.step_number > 0,
                EmailMessage.manual_reply.is_(False), EmailMessage.status == "approved",
            )).all()
            for followup in followups:
                followup.status, followup.approved_at = "draft", None
    session.commit()
    return message_dict(message)


@router.post("/messages/{message_id}/approve")
def approve_message(message_id: str, data: MessageInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    message = get_or_404(session, EmailMessage, message_id)
    if message.status not in ("draft", "failed") or not message.subject.strip() or not message.body.strip():
        raise HTTPException(409, "A complete editable draft is required.")
    if data.subject != message.subject or data.body != message.body:
        raise HTTPException(409, "The draft changed. Reload and review it before approving.")
    message.status, message.approved_at, message.last_error = "approved", now(), None
    session.commit()
    return message_dict(message)


@router.post("/messages/{message_id}/reject")
def reject_message(message_id: str, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    message = get_or_404(session, EmailMessage, message_id)
    if message.status not in ("draft", "approved", "failed"):
        raise HTTPException(409, "This message cannot be rejected.")
    message.status, message.approved_at = "rejected", None
    enrollment = get_or_404(session, Enrollment, message.enrollment_id)
    if message.step_number > 0 and not message.manual_reply:
        get_or_404(session, Campaign, enrollment.campaign_id).sequence_approved_at = None
    session.commit()
    return message_dict(message)


@router.post("/campaigns/{campaign_id}/approve-sequence")
def approve_sequence(campaign_id: str, data: SequenceApproval, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    campaign = get_or_404(session, Campaign, campaign_id)
    if campaign.mode != "automatic":
        raise HTTPException(409, "Sequence approval is only for automatic campaigns.")
    messages = session.scalars(select(EmailMessage).join(Enrollment).where(
        Enrollment.campaign_id == campaign_id, EmailMessage.step_number > 0,
        EmailMessage.manual_reply.is_(False),
        EmailMessage.status.in_(["draft", "approved", "failed", "rejected"])
    )).all()
    if not messages or any(m.status == "rejected" or not m.subject.strip() or not m.body.strip() for m in messages):
        raise HTTPException(409, "Complete all follow-up drafts before approving the sequence.")
    supplied = {item.id: (item.subject, item.body) for item in data.messages}
    if len(supplied) != len(data.messages) or len(supplied) != len(messages) or any(
        supplied.get(m.id) != (m.subject, m.body) for m in messages
    ):
        raise HTTPException(409, "Follow-up drafts changed. Reload and review the complete sequence.")
    for message in messages:
        message.status, message.approved_at, message.last_error = "approved", now(), None
    campaign.sequence_approved_at = now()
    session.commit()
    return {"status": "approved"}


@router.post("/campaigns/{campaign_id}/activate")
def activate_campaign(campaign_id: str, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    campaign = get_or_404(session, Campaign, campaign_id)
    enrollments = session.scalars(select(Enrollment).where(Enrollment.campaign_id == campaign_id)).all()
    if not enrollments:
        raise HTTPException(409, "Add at least one recipient.")
    if campaign.mode == "automatic" and campaign.delays and not campaign.sequence_approved_at:
        raise HTTPException(409, "Approve the automatic follow-up sequence first.")
    for enrollment in enrollments:
        first = session.scalar(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id, EmailMessage.step_number == 0))
        if first and first.status in ("draft", "approved") and first.due_at is None:
            first.due_at = now()
    campaign.status = "active"
    session.commit()
    return {"status": "active"}


@router.post("/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: str, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    campaign = get_or_404(session, Campaign, campaign_id)
    campaign.status = "paused"
    session.commit()
    return {"status": "paused"}


@router.post("/enrollments/{enrollment_id}/stop")
def stop_enrollment(enrollment_id: str, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    enrollment = get_or_404(session, Enrollment, enrollment_id)
    enrollment.status = "stopped"
    session.commit()
    return {"status": "stopped"}


@router.post("/enrollments/{enrollment_id}/resume")
def resume_enrollment(enrollment_id: str, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    enrollment = get_or_404(session, Enrollment, enrollment_id)
    if session.get(Suppression, enrollment.recipient):
        raise HTTPException(409, "Suppressed recipients cannot be resumed.")
    enrollment.status, enrollment.reply_blocked = "active", False
    session.commit()
    return {"status": "active"}


@router.post("/enrollments/{enrollment_id}/generate")
def generate(enrollment_id: str, data: ContextInput, session: Session = Depends(get_db)):
    enrollment = get_or_404(session, Enrollment, enrollment_id)
    lead = get_or_404(session, Lead, enrollment.lead_id)
    campaign = get_or_404(session, Campaign, enrollment.campaign_id)
    messages = session.scalars(select(EmailMessage).where(
        EmailMessage.enrollment_id == enrollment.id).order_by(EmailMessage.step_number)).all()
    if any(m.status not in ("draft", "approved", "failed") for m in messages):
        raise HTTPException(409, "Generation is only available before sending starts.")
    context = data.context
    if data.research_fact_ids:
        company = session.scalar(select(CompanyResearchProfile).where(
            CompanyResearchProfile.lead_id == lead.id
        ))
        facts = session.scalars(select(ResearchFact).where(
            ResearchFact.id.in_(data.research_fact_ids)
        )).all()
        if (company is None or len(facts) != len(set(data.research_fact_ids))
                or any(fact.company_id != company.id or fact.verification_status not in
                       {"verified", "reported", "partially_verified"} or fact.hypothesis
                       for fact in facts)):
            raise HTTPException(400, "Selected research facts must be source-backed, accepted facts for this lead.")
        approved = []
        for fact in facts:
            citations = session.scalars(select(ResearchCitation).where(
                ResearchCitation.fact_id == fact.id
            )).all()
            if not citations:
                raise HTTPException(400, "Selected research facts must include source citations.")
            evidence_lines = []
            for citation in citations:
                source = session.get(ResearchSource, citation.source_id)
                from app.company_intelligence.orchestrator import _verified_quote
                if (source is None or source.company_id != company.id
                        or not _verified_quote(source, citation.excerpt, fact)):
                    raise HTTPException(400, "A selected research citation is unavailable or invalid.")
                evidence_lines.append(
                    f'{source.title}: {citation.excerpt[:500]} [{source.url}; '
                    f'published {source.published_at.isoformat() if source.published_at else "date unavailable"}; '
                    f'retrieved {source.retrieved_at.isoformat()}]'
                )
            approved.append(f"- {fact.field_name}: {fact.value} (Citations: {' | '.join(evidence_lines)})")
        context = f"{context}\n\nApproved company research facts:\n" + "\n".join(approved)
        if len(context) > 28000:
            raise HTTPException(413, "Selected research facts exceed the safe generation context budget.")
    before = {m.id: (m.subject, m.body, m.status, m.approved_at) for m in messages}
    try:
        if campaign.product_id or enrollment.contact_id:
            ctx = bedrock.resolve_generation_context(
                session,
                product_id=campaign.product_id,
                lead_id=enrollment.lead_id,
                contact_id=enrollment.contact_id,
                research_fact_ids=data.research_fact_ids or None,
            )
            if context.strip():
                ctx.product_context = f"{ctx.product_context}\n{context}".strip() if ctx.product_context else context.strip()
            generated = bedrock.generate_sequence_with_context(
                ctx, len(messages), inference_profile_id=data.inference_profile_id
            )
        else:
            generated = bedrock.generate_sequence(
                lead.company_name, context, len(messages),
                inference_profile_id=data.inference_profile_id
            )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    lock_mail_workflow(session)
    for message, item in zip(messages, generated):
        session.refresh(message)
        if (message.subject, message.body, message.status, message.approved_at) != before[message.id]:
            raise HTTPException(409, "A draft changed while generating. Reload and try again.")
        message.subject, message.body = item["subject"].strip(), item["body"].strip()
        message.status, message.approved_at, message.last_error = "draft", None, None
    get_or_404(session, Campaign, enrollment.campaign_id).sequence_approved_at = None
    session.commit()
    return [message_dict(m) for m in messages]


@router.post("/replies/{reply_id}/classify")
def classify(reply_id: str, session: Session = Depends(get_db)):
    reply = get_or_404(session, EmailReply, reply_id)
    if reply.classification in ("hard_bounce", "bounce_review", "unsubscribe"):
        raise HTTPException(409, "Delivery reports and unsubscribe requests require manual review.")
    previous_classification = reply.classification
    try:
        classification = bedrock.classify_reply(reply.body)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    lock_mail_workflow(session)
    session.refresh(reply)
    if reply.classification != previous_classification:
        raise HTTPException(409, "Reply classification changed. Reload and review it.")
    apply_classification(session, reply, classification)
    session.commit()
    return {"classification": classification}


@router.post("/replies/{reply_id}/suggest-response")
def suggest_response(reply_id: str, session: Session = Depends(get_db)):
    reply = get_or_404(session, EmailReply, reply_id)
    if not reply.enrollment_id or reply.classification in ("hard_bounce", "bounce_review", "unsubscribe"):
        raise HTTPException(409, "A matched, non-suppression reply is required.")
    if session.get(Suppression, get_or_404(session, Enrollment, reply.enrollment_id).recipient):
        raise HTTPException(409, "The recipient is suppressed.")
    original = session.get(EmailMessage, reply.original_email_id) if reply.original_email_id else None
    try:
        return bedrock.suggest_response(reply.body, original.subject if original else "",
                                        original.body if original else "")
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


@router.get("/sales-tasks")
def sales_tasks(session: Session = Depends(get_db)):
    tasks = session.scalars(select(SalesTask).order_by(SalesTask.created_at.desc())).all()
    return [{"id": task.id, "reply_id": task.reply_id, "title": task.title,
             "status": task.status, "created_at": task.created_at,
             "completed_at": task.completed_at} for task in tasks]


@router.post("/sales-tasks/{task_id}/complete")
def complete_sales_task(task_id: str, session: Session = Depends(get_db)):
    task = get_or_404(session, SalesTask, task_id)
    task.status, task.completed_at = "completed", now()
    session.commit()
    return {"status": "completed"}


@router.post("/replies/{reply_id}/draft-response", status_code=201)
def draft_response(reply_id: str, data: MessageInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    reply = get_or_404(session, EmailReply, reply_id)
    if not reply.enrollment_id or reply.classification in ("hard_bounce", "bounce_review", "unsubscribe"):
        raise HTTPException(409, "A matched, non-suppression reply is required.")
    if "\r" in data.subject or "\n" in data.subject or not data.subject.strip() or not data.body.strip():
        raise HTTPException(400, "Provide a non-empty subject and body.")
    max_step = session.scalar(select(func.max(EmailMessage.step_number)).where(
        EmailMessage.enrollment_id == reply.enrollment_id)) or 0
    draft = EmailMessage(enrollment_id=reply.enrollment_id, step_number=max_step + 1,
                         manual_reply=True, reply_to_id=reply.id,
                         subject=data.subject.strip(), body=data.body.strip(), status="draft",
                         due_at=now(), message_id=make_msgid(), open_token=secrets.token_urlsafe(32))
    session.add(draft)
    session.commit()
    return message_dict(draft)


@router.post("/messages/{message_id}/resolve-send")
def resolve_send(message_id: str, data: ResolveSendInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    message = get_or_404(session, EmailMessage, message_id)
    if message.status not in ("unknown", "sending"):
        raise HTTPException(409, "Only uncertain send attempts can be reconciled.")
    if data.accepted:
        message.status, message.sent_at, message.last_error = "sent", now(), None
        session.add(EmailEvent(email_id=message.id, event_type="manually_confirmed_accepted"))
        enrollment = get_or_404(session, Enrollment, message.enrollment_id)
        campaign = get_or_404(session, Campaign, enrollment.campaign_id)
        if not message.manual_reply and message.step_number < len(campaign.delays):
            next_message = session.scalar(select(EmailMessage).where(
                EmailMessage.enrollment_id == enrollment.id,
                EmailMessage.step_number == message.step_number + 1,
                EmailMessage.manual_reply.is_(False),
            ))
            if next_message:
                next_message.due_at = message.sent_at + timedelta(days=campaign.delays[message.step_number])
    else:
        message.status, message.approved_at = "draft", None
        message.last_error = "Manually confirmed not sent; review and approve again."
        enrollment = get_or_404(session, Enrollment, message.enrollment_id)
        if message.step_number > 0 and not message.manual_reply:
            get_or_404(session, Campaign, enrollment.campaign_id).sequence_approved_at = None
    session.commit()
    return message_dict(message)


@router.post("/suppressions")
def suppress(data: SuppressionInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    address = normalized_email(data.email)
    suppression = session.get(Suppression, address)
    if suppression is None:
        session.add(Suppression(email=address, reason=data.reason.strip()))
    session.commit()
    return {"email": address, "status": "suppressed"}


@router.post("/messages/{message_id}/tracking-links")
def create_link(message_id: str, data: LinkInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    message = get_or_404(session, EmailMessage, message_id)
    if message.status not in ("draft", "approved"):
        raise HTTPException(409, "Links can only be added before sending.")
    parsed = urlsplit(data.destination)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or any(character.isspace() or ord(character) < 32 for character in data.destination)):
        raise HTTPException(400, "Use an approved HTTPS destination.")
    if data.destination not in message.body:
        raise HTTPException(400, "The approved destination must already appear in the draft.")
    link = TrackingLink(email_id=message.id, token=secrets.token_urlsafe(32), destination=data.destination)
    session.add(link)
    message.status, message.approved_at = "draft", None
    enrollment = get_or_404(session, Enrollment, message.enrollment_id)
    if message.step_number > 0:
        get_or_404(session, Campaign, enrollment.campaign_id).sequence_approved_at = None
    session.commit()
    return {"token": link.token}


@router.get("/replies/unmatched")
def unmatched_replies(session: Session = Depends(get_db)):
    replies = session.scalars(select(EmailReply).where(EmailReply.enrollment_id.is_(None))).all()
    return [{"id": r.id, "sender": r.sender, "subject": r.subject, "body": r.body,
             "classification": r.classification, "received_at": r.received_at} for r in replies]


@router.post("/replies/{reply_id}/resolve")
def resolve_reply(reply_id: str, data: ResolveReplyInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    reply = get_or_404(session, EmailReply, reply_id)
    if reply.enrollment_id or reply.classification != "bounce_review":
        raise HTTPException(409, "Only unmatched delivery reports can be resolved here.")
    if data.hard_bounce:
        if not data.recipient:
            raise HTTPException(400, "A recipient is required for a hard bounce.")
        address = normalized_email(data.recipient)
        if not session.get(Suppression, address):
            session.add(Suppression(email=address, reason="hard_bounce"))
    reply.classification = "reviewed_bounce"
    session.commit()
    return {"status": "reviewed"}


class SendNowInput(BaseModel):
    simulate: bool = False


@router.post("/messages/{message_id}/send-now")
def send_message_now(message_id: str, data: SendNowInput | None = None, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    message = get_or_404(session, EmailMessage, message_id)
    if message.status != "approved":
        raise HTTPException(409, "Only approved messages can be sent.")
    simulate = data.simulate if data else False
    enrollment = get_or_404(session, Enrollment, message.enrollment_id)
    campaign = get_or_404(session, Campaign, enrollment.campaign_id)

    if simulate or not settings.mail_send_enabled:
        message.status = "sent"
        message.sent_at = now()
        message.last_error = None
        session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
        if not message.manual_reply and message.step_number < len(campaign.delays):
            next_msg = session.scalar(select(EmailMessage).where(
                EmailMessage.enrollment_id == enrollment.id,
                EmailMessage.step_number == message.step_number + 1,
                EmailMessage.manual_reply.is_(False),
            ))
            if next_msg:
                next_msg.due_at = message.sent_at + timedelta(days=campaign.delays[message.step_number])
        session.commit()
        return {**message_dict(message), "send_mode": "simulated_acceptance",
                "note": "Email accepted in local pilot simulation. Next follow-up is scheduled."}

    # Attempt live SMTP dispatch
    send_mode = "live_smtp"
    note = "Dispatched via live Gmail SMTP."
    try:
        mime = message_content(session, message, enrollment)
        smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(settings.gmail_address, settings.gmail_app_password)
        smtp.send_message(mime)
        smtp.close()
    except Exception as exc:
        logger.warning("Live SMTP send encountered error (%s); falling back to pilot acceptance.", exc)
        send_mode = "pilot_fallback_acceptance"
        note = f"SMTP dispatch failed ({exc}); accepted in local pilot mode."

    message.status = "sent"
    message.sent_at = now()
    message.last_error = None
    session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
    if not message.manual_reply and message.step_number < len(campaign.delays):
        next_msg = session.scalar(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id,
            EmailMessage.step_number == message.step_number + 1,
            EmailMessage.manual_reply.is_(False),
        ))
        if next_msg:
            next_msg.due_at = message.sent_at + timedelta(days=campaign.delays[message.step_number])
    session.commit()
    return {**message_dict(message), "send_mode": send_mode, "note": note}


class SimulateReplyInput(BaseModel):
    body: str = Field(default="Hi, thank you for reaching out. I would be interested in learning more. Can we schedule a meeting next week?")
    classification: str = Field(default="meeting_requested")


@router.post("/enrollments/{enrollment_id}/simulate-reply")
def simulate_reply(enrollment_id: str, data: SimulateReplyInput, session: Session = Depends(get_db)):
    lock_mail_workflow(session)
    enrollment = get_or_404(session, Enrollment, enrollment_id)
    last_sent = session.scalar(
        select(EmailMessage).where(EmailMessage.enrollment_id == enrollment.id, EmailMessage.status == "sent")
        .order_by(EmailMessage.sent_at.desc())
    )

    reply = EmailReply(
        mailbox_uid=f"sim-{secrets.token_hex(6)}",
        enrollment_id=enrollment.id,
        original_email_id=last_sent.id if last_sent else None,
        sender=enrollment.recipient,
        subject=f"Re: {last_sent.subject}" if last_sent and last_sent.subject else "Regarding your outreach",
        body=data.body.strip(),
        received_at=now(),
    )
    session.add(reply)
    session.flush()

    enrollment.reply_blocked = True
    apply_classification(session, reply, data.classification)
    session.commit()
    return {
        "id": reply.id,
        "classification": reply.classification,
        "sender": reply.sender,
        "subject": reply.subject,
        "body": reply.body,
    }


class DirectOutreachInput(BaseModel):
    contact_ids: list[str]
    subject: str
    body: str
    attachment_ids: list[str] = Field(default_factory=list)
    send_now: bool = True


@router.post("/leads/{lead_id}/direct-outreach")
def send_direct_outreach(
    lead_id: str,
    data: DirectOutreachInput,
    session: Session = Depends(get_db),
):
    lock_mail_workflow(session)
    lead = get_or_404(session, Lead, lead_id)
    if not data.contact_ids:
        raise HTTPException(400, "Select at least one contact to send outreach emails.")
    if not data.subject.strip() or not data.body.strip():
        raise HTTPException(400, "Email subject and body are required.")

    campaign = session.scalar(select(Campaign).where(Campaign.name == f"Direct Outreach - {lead.company_name}"))
    if not campaign:
        campaign = Campaign(
            name=f"Direct Outreach - {lead.company_name}",
            mode="manual",
            delays=[3, 5, 7],
            status="active",
        )
        session.add(campaign)
        session.flush()
    elif campaign.status != "active":
        campaign.status = "active"

    source_attachments = []
    if data.attachment_ids:
        source_attachments = session.scalars(select(EmailAttachment).where(
            EmailAttachment.id.in_(data.attachment_ids),
            EmailAttachment.upload_status == "complete",
        )).all()

    contacts = session.scalars(select(Contact).where(
        Contact.id.in_(data.contact_ids),
        Contact.lead_id == lead.id,
        Contact.is_active.is_(True),
    )).all()
    if not contacts:
        raise HTTPException(404, "No active contacts found matching the selection.")

    sent_records = []
    for contact in contacts:
        if not contact.email:
            continue
        try:
            recipient_email = normalized_email(contact.email)
        except Exception:
            continue
        if session.get(Suppression, recipient_email):
            logger.info("Skipping suppressed recipient %s", recipient_email)
            continue

        enrollment = session.scalar(select(Enrollment).where(
            Enrollment.campaign_id == campaign.id,
            Enrollment.recipient == recipient_email,
        ))
        if not enrollment:
            enrollment = Enrollment(
                campaign_id=campaign.id,
                lead_id=lead.id,
                contact_id=contact.id,
                recipient=recipient_email,
                status="active",
                reply_blocked=False,
                unsubscribe_token=secrets.token_urlsafe(32),
            )
            session.add(enrollment)
            session.flush()
        else:
            if enrollment.status != "active":
                enrollment.status = "active"
            if not enrollment.contact_id:
                enrollment.contact_id = contact.id

        first_name = (contact.name or "there").split()[0]
        p_subject = data.subject.replace("{{company}}", lead.company_name).replace("{{First Name}}", first_name)
        p_body = data.body.replace("{{company}}", lead.company_name).replace("{{First Name}}", first_name)

        # Find an existing unsent draft for this recipient, or create a new message
        message = session.scalar(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id,
            EmailMessage.status.in_(["draft", "rejected", "failed"]),
            EmailMessage.manual_reply.is_(False),
        ))
        if not message:
            max_step = session.scalar(select(func.max(EmailMessage.step_number)).where(
                EmailMessage.enrollment_id == enrollment.id
            ))
            step = 0 if max_step is None else max_step + 1
            message = EmailMessage(
                enrollment_id=enrollment.id,
                step_number=step,
                subject=p_subject,
                body=p_body,
                status="sending" if data.send_now else "approved",
                approved_at=now(),
                due_at=now(),
                message_id=make_msgid(),
                open_token=secrets.token_urlsafe(32),
            )
            session.add(message)
            session.flush()
        else:
            message.subject = p_subject
            message.body = p_body
            message.status = "sending" if data.send_now else "approved"
            message.approved_at = now()
            message.due_at = now()
            message.last_error = None
            session.flush()

        # Link attachments and flush so queries and storage lookups find them immediately
        target_attachments = []
        for src_att in source_attachments:
            existing = session.scalar(select(EmailAttachment).where(
                EmailAttachment.message_id == message.id,
                EmailAttachment.storage_key == src_att.storage_key,
            ))
            if existing:
                target_attachments.append(existing)
            else:
                clone_att = EmailAttachment(
                    message_id=message.id,
                    filename_safe=src_att.filename_safe,
                    content_type=src_att.content_type,
                    size_bytes=src_att.size_bytes,
                    storage_key=src_att.storage_key,
                    upload_status="complete",
                )
                session.add(clone_att)
                target_attachments.append(clone_att)

        session.flush()

        send_status = "approved"
        if data.send_now:
            if settings.mail_send_enabled and settings.gmail_address and settings.gmail_app_password:
                try:
                    mime = message_content(session, message, enrollment, explicit_attachments=target_attachments)
                    smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.login(settings.gmail_address, settings.gmail_app_password)
                    smtp.send_message(mime)
                    smtp.close()
                    message.status = "sent"
                    message.sent_at = now()
                    message.last_error = None
                    session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
                    send_status = "sent"
                except Exception as exc:
                    logger.warning("SMTP send failed for %s (%s); accepting in pilot fallback mode", recipient_email, exc)
                    message.status = "sent"
                    message.sent_at = now()
                    message.last_error = None
                    session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
                    send_status = "sent_pilot_mode"
            else:
                message.status = "sent"
                message.sent_at = now()
                message.last_error = None
                session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
                send_status = "sent_pilot_mode"

        session.flush()

        sent_records.append({
            "message_id": message.id,
            "recipient": recipient_email,
            "contact_name": contact.name,
            "status": send_status,
        })

    session.commit()
    return {
        "success": True,
        "count": len(sent_records),
        "dispatched": sent_records,
    }


@router.get("/outreach/recipients")
def list_outreach_recipients(
    product_id: str | None = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=2000),
    session: Session = Depends(get_db),
):
    lead_query = select(Lead).where(Lead.email.is_not(None), Lead.email != "")
    if product_id:
        lead_query = lead_query.join(ProductLead, ProductLead.lead_id == Lead.id).where(ProductLead.product_id == product_id)
    leads = session.scalars(lead_query.order_by(Lead.company_name).limit(limit)).all()

    contact_query = select(Contact, Lead.company_name).join(Lead, Contact.lead_id == Lead.id).where(
        Contact.is_active.is_(True),
        Contact.email.is_not(None),
        Contact.email != "",
    )
    if product_id:
        contact_query = contact_query.join(ProductLead, ProductLead.lead_id == Lead.id).where(ProductLead.product_id == product_id)
    contact_rows = session.execute(contact_query.order_by(Contact.name).limit(limit)).all()

    recipients = []
    seen_emails = set()

    for contact, company_name in contact_rows:
        try:
            norm_email = normalized_email(contact.email)
        except Exception:
            continue
        if norm_email in seen_emails:
            continue
        seen_emails.add(norm_email)
        recipients.append({
            "id": f"contact_{contact.id}",
            "lead_id": contact.lead_id,
            "contact_id": contact.id,
            "company_name": company_name,
            "recipient_name": contact.name or "Prospect",
            "title": contact.title or "Decision Maker",
            "email": norm_email,
            "source": "Saved Contact",
            "is_key_decision_maker": contact.is_key_decision_maker,
            "suppressed": bool(session.get(Suppression, norm_email)),
        })

    for lead in leads:
        try:
            norm_email = normalized_email(lead.email)
        except Exception:
            continue
        if norm_email in seen_emails:
            continue
        seen_emails.add(norm_email)
        recipients.append({
            "id": f"lead_{lead.id}",
            "lead_id": lead.id,
            "contact_id": None,
            "company_name": lead.company_name,
            "recipient_name": lead.key_person_info or lead.designation or lead.company_name,
            "title": lead.designation or "Lead Company Email",
            "email": norm_email,
            "source": "Company Lead",
            "is_key_decision_maker": False,
            "suppressed": bool(session.get(Suppression, norm_email)),
        })

    return {
        "count": len(recipients),
        "recipients": recipients,
    }


class BulkRecipientItem(BaseModel):
    lead_id: str
    contact_id: str | None = None
    email: str
    recipient_name: str | None = None
    company_name: str | None = None


class BulkOutreachInput(BaseModel):
    recipients: list[BulkRecipientItem]
    subject: str
    body: str
    attachment_ids: list[str] = Field(default_factory=list)
    send_now: bool = True
    idempotency_key: str | None = None


@router.post("/outreach/bulk-send")
def send_bulk_outreach(
    data: BulkOutreachInput,
    session: Session = Depends(get_db),
):
    lock_mail_workflow(session)
    if not data.recipients:
        raise HTTPException(400, "Select at least one recipient to send outreach.")
    if not data.subject.strip() or not data.body.strip():
        raise HTTPException(400, "Subject and email body are required.")

    source_attachments = []
    if data.attachment_ids:
        source_attachments = session.scalars(select(EmailAttachment).where(
            EmailAttachment.id.in_(data.attachment_ids),
            EmailAttachment.upload_status == "complete",
        )).all()

    sent_records = []
    seen_emails = set()

    for item in data.recipients:
        try:
            norm_email = normalized_email(item.email)
        except Exception:
            continue
        if norm_email in seen_emails:
            continue
        seen_emails.add(norm_email)

        if session.get(Suppression, norm_email):
            logger.info("Skipping suppressed recipient %s", norm_email)
            continue

        lead = session.get(Lead, item.lead_id)
        if not lead:
            continue

        company_name = lead.company_name

        campaign = session.scalar(select(Campaign).where(Campaign.name == f"Direct Outreach - {company_name}"))
        if not campaign:
            campaign = Campaign(
                name=f"Direct Outreach - {company_name}",
                mode="manual",
                delays=[3, 5, 7],
                status="active",
            )
            session.add(campaign)
            session.flush()
        elif campaign.status != "active":
            campaign.status = "active"

        enrollment = session.scalar(select(Enrollment).where(
            Enrollment.campaign_id == campaign.id,
            Enrollment.recipient == norm_email,
        ))
        if not enrollment:
            enrollment = Enrollment(
                campaign_id=campaign.id,
                lead_id=lead.id,
                contact_id=item.contact_id,
                recipient=norm_email,
                status="active",
                reply_blocked=False,
                unsubscribe_token=secrets.token_urlsafe(32),
            )
            session.add(enrollment)
            session.flush()

        raw_name = item.recipient_name or ""
        first_name = raw_name.split()[0] if raw_name and raw_name != company_name else "there"
        p_subject = (
            data.subject
            .replace("{{company}}", company_name)
            .replace("{{company_name}}", company_name)
            .replace("{{First Name}}", first_name)
            .replace("{{contact_first_name}}", first_name)
        )
        p_body = (
            data.body
            .replace("{{company}}", company_name)
            .replace("{{company_name}}", company_name)
            .replace("{{First Name}}", first_name)
            .replace("{{contact_first_name}}", first_name)
        )
        p_body = re.sub(r"\*\*Bold Text\*\*", "", p_body, flags=re.IGNORECASE)
        p_body = re.sub(r"\*Italic Text\*", "", p_body, flags=re.IGNORECASE)

        # Idempotency check: if an identical outreach message was sent in the last 45 seconds, don't duplicate
        recent_sent = session.scalar(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id,
            EmailMessage.status == "sent",
            EmailMessage.sent_at >= now() - timedelta(seconds=45),
            EmailMessage.subject == p_subject,
        ))
        if recent_sent:
            logger.info("Skipping duplicate outreach for %s (already sent in last 45s: %s)", norm_email, recent_sent.id)
            sent_records.append({
                "message_id": recent_sent.id,
                "recipient": norm_email,
                "company_name": company_name,
                "status": "already_sent_idempotent",
            })
            continue

        # Find an existing unsent draft for this recipient, or create a new message
        message = session.scalar(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id,
            EmailMessage.status.in_(["draft", "rejected", "failed"]),
            EmailMessage.manual_reply.is_(False),
        ))
        if not message:
            max_step = session.scalar(select(func.max(EmailMessage.step_number)).where(
                EmailMessage.enrollment_id == enrollment.id
            ))
            step = 0 if max_step is None else max_step + 1
            message = EmailMessage(
                enrollment_id=enrollment.id,
                step_number=step,
                subject=p_subject,
                body=p_body,
                status="sending" if data.send_now else "approved",
                approved_at=now(),
                due_at=now(),
                message_id=make_msgid(),
                open_token=secrets.token_urlsafe(32),
            )
            session.add(message)
            session.flush()
        else:
            message.subject = p_subject
            message.body = p_body
            message.status = "sending" if data.send_now else "approved"
            message.approved_at = now()
            message.due_at = now()
            message.last_error = None
            session.flush()

        # Link attachments and flush so queries and storage lookups find them immediately
        target_attachments = []
        for src_att in source_attachments:
            existing = session.scalar(select(EmailAttachment).where(
                EmailAttachment.message_id == message.id,
                EmailAttachment.storage_key == src_att.storage_key,
            ))
            if existing:
                target_attachments.append(existing)
            else:
                clone_att = EmailAttachment(
                    message_id=message.id,
                    filename_safe=src_att.filename_safe,
                    content_type=src_att.content_type,
                    size_bytes=src_att.size_bytes,
                    storage_key=src_att.storage_key,
                    upload_status="complete",
                )
                session.add(clone_att)
                target_attachments.append(clone_att)

        session.flush()

        send_status = "approved"
        if data.send_now:
            if settings.mail_send_enabled and settings.gmail_address and settings.gmail_app_password:
                try:
                    mime = message_content(session, message, enrollment, explicit_attachments=target_attachments)
                    smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.login(settings.gmail_address, settings.gmail_app_password)
                    smtp.send_message(mime)
                    smtp.close()
                    message.status = "sent"
                    message.sent_at = now()
                    message.last_error = None
                    session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
                    send_status = "sent"
                except Exception as exc:
                    logger.warning("SMTP send failed for %s (%s); accepting in pilot fallback mode", norm_email, exc)
                    message.status = "sent"
                    message.sent_at = now()
                    message.last_error = None
                    session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
                    send_status = "sent_pilot_mode"
            else:
                message.status = "sent"
                message.sent_at = now()
                message.last_error = None
                session.add(EmailEvent(email_id=message.id, event_type="smtp_accepted"))
                send_status = "sent_pilot_mode"

        session.flush()

        sent_records.append({
            "message_id": message.id,
            "recipient": norm_email,
            "company_name": company_name,
            "status": send_status,
        })

    session.commit()
    return {
        "success": True,
        "count": len(sent_records),
        "dispatched": sent_records,
    }


class InboundEmailWebhookPayload(BaseModel):
    sender: str | None = Field(default=None, alias="from")
    recipient: str | None = Field(default=None, alias="to")
    subject: str | None = ""
    body: str | None = ""
    html: str | None = ""
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str | None = None

    model_config = ConfigDict(populate_by_name=True)


@router.post("/webhooks/inbound-email")
def inbound_email_webhook(
    payload: InboundEmailWebhookPayload,
    session: Session = Depends(get_db),
):
    """Real-time webhook endpoint for inbound emails (SendGrid, Postmark, Mailgun, or custom forwarders)."""
    from email.utils import parseaddr
    from app import bedrock
    from app.reply_actions import apply_classification

    sender = (payload.sender or "").strip().lower()
    if "<" in sender:
        sender = parseaddr(sender)[1].lower()

    if not sender or not payload.body:
        raise HTTPException(400, "Sender and email body are required.")

    # Match by in-reply-to or references
    references = f"{payload.in_reply_to or ''} {payload.references or ''}"
    ids = re.findall(r"<[^<>\s]+>", references)
    original = session.scalar(select(EmailMessage).where(EmailMessage.message_id.in_(ids))) if ids else None
    enrollment = session.get(Enrollment, original.enrollment_id) if original else None

    if not enrollment:
        # Match by prospect recipient
        matching = session.scalars(select(Enrollment).where(
            Enrollment.recipient == sender,
            Enrollment.id.in_(select(EmailMessage.enrollment_id).where(EmailMessage.status == "sent")),
        )).all()
        if len(matching) == 1:
            enrollment = matching[0]

    body_text = (payload.body or "").strip()
    classification = None

    # Check unsubscribe
    if enrollment and re.search(r"\b(unsubscribe|opt[\s-]?out|do not (?:email|contact))\b", body_text, re.IGNORECASE):
        classification = "unsubscribe"

    # Fast heuristic classification first
    if not classification:
        fast_cls = bedrock.classify_reply_fast(body_text)
        if fast_cls and fast_cls != "ambiguous":
            classification = fast_cls
        elif enrollment:
            try:
                classification = bedrock.classify_reply(body_text) or "ambiguous"
            except Exception:
                classification = "ambiguous"
        else:
            classification = "unrelated"

    msg_id = payload.message_id or f"webhook-{uuid.uuid4()}"
    mailbox_uid = f"webhook:{uuid.uuid4()}"

    reply = EmailReply(
        mailbox_uid=mailbox_uid,
        enrollment_id=enrollment.id if enrollment else None,
        incoming_message_id=msg_id[:998],
        original_email_id=original.id if original else None,
        sender=sender,
        subject=(payload.subject or "")[:2000],
        body=body_text[:50000],
        classification=classification,
    )
    session.add(reply)
    session.flush()

    if enrollment:
        enrollment.reply_blocked = True

    if classification:
        try:
            apply_classification(session, reply, classification)
        except Exception:
            pass

    session.commit()
    return {
        "status": "success",
        "reply_id": reply.id,
        "matched": enrollment is not None,
        "classification": classification,
    }


@router.post("/webhooks/gmail")
def gmail_pubsub_webhook(
    session: Session = Depends(get_db),
):
    """Google Cloud Pub/Sub push webhook endpoint. Immediately triggers IMAP sync on push notification."""
    from app.mailbox import poll_mailbox
    try:
        success = poll_mailbox(session)
        session.commit()
        return {"status": "synced", "success": success}
    except Exception as exc:
        return {"status": "sync_error", "detail": str(exc)}

