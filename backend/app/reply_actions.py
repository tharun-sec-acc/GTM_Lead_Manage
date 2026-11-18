from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contact, EmailReply, Enrollment, Lead, SalesTask, Suppression


def _set_lead_stage(lead: Lead | None, stage: str):
    if not lead:
        return
    if hasattr(lead, "lifecycle_stage"):
        try:
            lead.lifecycle_stage = stage
            return
        except Exception:
            pass
    lead.extra = {**(lead.extra or {}), "lifecycle_stage": stage}


def apply_classification(session: Session, reply: EmailReply, classification: str):
    cls_clean = (classification or "ambiguous").lower().strip()
    reply.classification = cls_clean
    enrollment = session.get(Enrollment, reply.enrollment_id) if reply.enrollment_id else None
    if not enrollment:
        return

    # Find associated lead if available
    lead = None
    if enrollment.contact_id:
        contact = session.get(Contact, enrollment.contact_id)
        if contact and contact.lead_id:
            lead = session.get(Lead, contact.lead_id)
    if not lead and enrollment.lead_id:
        lead = session.get(Lead, enrollment.lead_id)

    if cls_clean in ("unsubscribe", "opt_out"):
        enrollment.status = "unsubscribed"
        if not session.get(Suppression, enrollment.recipient):
            session.add(Suppression(email=enrollment.recipient, reason="unsubscribe"))
    elif cls_clean in ("hard_bounce", "bounce_review", "delivery_failure"):
        enrollment.status = "bounced"
        if not session.get(Suppression, enrollment.recipient):
            session.add(Suppression(email=enrollment.recipient, reason="hard_bounce"))
    elif cls_clean in ("meeting_requested", "highly_interested"):
        enrollment.status = "meeting_requested"
        if not session.scalar(
            select(SalesTask.id).where(SalesTask.reply_id == reply.id)
        ):
            session.add(SalesTask(
                reply_id=reply.id,
                title=f"📅 Meeting Requested: Arrange discussion with {enrollment.recipient}",
                status="open",
            ))
        _set_lead_stage(lead, "Meeting Requested")
    elif cls_clean in ("demo_requested",):
        enrollment.status = "meeting_requested"
        if not session.scalar(
            select(SalesTask.id).where(SalesTask.reply_id == reply.id)
        ):
            session.add(SalesTask(
                reply_id=reply.id,
                title=f"🎯 Demo Requested: Schedule TWMS walkthrough with {enrollment.recipient}",
                status="open",
            ))
        _set_lead_stage(lead, "Demo Requested")
    elif cls_clean in ("pricing_requested",):
        enrollment.status = "info_requested"
        if not session.scalar(
            select(SalesTask.id).where(SalesTask.reply_id == reply.id)
        ):
            session.add(SalesTask(
                reply_id=reply.id,
                title=f"💰 Pricing Requested: Share commercials with {enrollment.recipient}",
                status="open",
            ))
        _set_lead_stage(lead, "Pricing Discussion")
    elif cls_clean in ("interested",):
        enrollment.status = "interested"
        if not session.scalar(
            select(SalesTask.id).where(SalesTask.reply_id == reply.id)
        ):
            session.add(SalesTask(
                reply_id=reply.id,
                title=f"💡 High Interest: Follow up with {enrollment.recipient}",
                status="open",
            ))
        _set_lead_stage(lead, "Qualified")
    elif cls_clean in ("information_requested", "info_requested"):
        enrollment.status = "info_requested"
        if not session.scalar(
            select(SalesTask.id).where(SalesTask.reply_id == reply.id)
        ):
            session.add(SalesTask(
                reply_id=reply.id,
                title=f"📄 Collateral Requested: Share details with {enrollment.recipient}",
                status="open",
            ))
    elif cls_clean in ("follow_up_later", "follow_up_requested"):
        enrollment.status = "follow_up_later"
        if not session.scalar(
            select(SalesTask.id).where(SalesTask.reply_id == reply.id)
        ):
            session.add(SalesTask(
                reply_id=reply.id,
                title=f"⏰ Follow-up Requested: Touch base with {enrollment.recipient}",
                status="open",
            ))
    elif cls_clean in ("not_interested", "rejected"):
        enrollment.status = "not_interested"
        _set_lead_stage(lead, "Disqualified")
    elif cls_clean in ("out_of_office",):
        enrollment.status = "out_of_office"
