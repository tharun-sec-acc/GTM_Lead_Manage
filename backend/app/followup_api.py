import secrets
from datetime import timedelta
from email.utils import make_msgid
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import bedrock
from app.config import settings
from app.database import get_db
from app.mailbox import lock_mail_workflow
from app.mailer import public_base
from app.models import (Campaign, Contact, EmailEvent, EmailMessage, EmailReply, Enrollment, Lead,
                        MailboxState, Product, ProductLead, SalesTask, Suppression, TrackingLink, now)
from app.reply_actions import apply_classification
from app.company_intelligence.models import (
    CompanyResearchProfile,
    ResearchCitation,
    ResearchFact,
    ResearchSource,
)

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
    if campaign.status != "draft":
        raise HTTPException(409, "Add recipients before activating the campaign.")
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
        enrollment = Enrollment(campaign_id=campaign.id, lead_id=lead_id,
                                contact_id=contact_id, recipient=recipient,
                                status="active", reply_blocked=False,
                                unsubscribe_token=secrets.token_urlsafe(32))
        session.add(enrollment)
        session.flush()
        ids.append(enrollment.id)
        for step in range(len(campaign.delays) + 1):
            session.add(EmailMessage(enrollment_id=enrollment.id, step_number=step, subject="", body="",
                                     status="draft", message_id=make_msgid(),
                                     open_token=secrets.token_urlsafe(32)))
    campaign.sequence_approved_at = None
    session.commit()
    return ids


@router.get("/campaigns/{campaign_id}")
def campaign_detail(campaign_id: str, session: Session = Depends(get_db)):
    campaign = get_or_404(session, Campaign, campaign_id)
    enrollments = session.scalars(select(Enrollment).where(Enrollment.campaign_id == campaign_id)).all()
    items = []
    for enrollment in enrollments:
        lead = session.get(Lead, enrollment.lead_id)
        contact = session.get(Contact, enrollment.contact_id) if enrollment.contact_id else None
        messages = session.scalars(select(EmailMessage).where(
            EmailMessage.enrollment_id == enrollment.id
        ).order_by(EmailMessage.step_number)).all()
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
    return {"last_success_at": state.last_success_at if state else None,
            "last_error": state.last_error if state else "Inbox has not been synchronized yet."}


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
        generated = bedrock.generate_sequence(lead.company_name, context, len(messages),
                                              inference_profile_id=data.inference_profile_id)
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
