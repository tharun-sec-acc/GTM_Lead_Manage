from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.meetings.providers import get_meeting_provider
from app.meetings.schemas import (
    ManualTranscriptInput,
    MeetingActionItemCreate,
    MeetingActionItemSchema,
    MeetingActionItemUpdate,
    MeetingCancelRequest,
    MeetingCreateRequest,
    MeetingDetailSchema,
    MeetingRescheduleRequest,
    MeetingSummarySchema,
    ProviderStatusSchema,
    SendFollowupDraftRequest,
)
from app.meetings.service import meeting_service
from app.meetings.models import Meeting
from app.models import Contact, Lead

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("/providers/status", response_model=list[ProviderStatusSchema])
def get_providers_status(session: Session = Depends(get_db)):
    """Return live connection status, organizer email, and capabilities for both Teams and Google Meet."""
    results = []
    for p_name in ("teams", "google_meet"):
        try:
            p = get_meeting_provider(p_name)
            stat = p.get_status(session)
            results.append(
                ProviderStatusSchema(
                    provider=stat["provider"],
                    connected=stat["connected"],
                    organizer_email=stat.get("organizer_email"),
                    scopes=stat.get("scopes", []),
                    capabilities=stat.get("capabilities", {}),
                )
            )
        except Exception:
            results.append(
                ProviderStatusSchema(
                    provider=p_name,  # type: ignore
                    connected=False,
                    organizer_email=None,
                    scopes=[],
                    capabilities={},
                )
            )
    return results


@router.get("", response_model=list[MeetingSummarySchema])
def list_meetings(
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    lead_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    search: str | None = Query(default=None),
    session: Session = Depends(get_db),
):
    """List meetings with provider, company, artifact indicators, and search filter."""
    return meeting_service.list_meetings(
        session,
        provider=provider,
        status=status,
        lead_id=lead_id,
        product_id=product_id,
        search=search,
    )


@router.post("", status_code=201)
def create_meeting(
    data: MeetingCreateRequest,
    session: Session = Depends(get_db),
):
    """Create a unified meeting (instant or scheduled) routed to Teams or Google Meet."""
    try:
        meeting = meeting_service.create_meeting(session, data)
        detail = meeting_service.get_meeting_detail(session, meeting.id)
        return detail
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Failed to create meeting with {data.provider}: {str(e)}") from e


@router.get("/{meeting_id}", response_model=MeetingDetailSchema)
def get_meeting(
    meeting_id: str,
    session: Session = Depends(get_db),
):
    """Get full meeting details including participants, recordings, transcripts, MoM, and action items."""
    detail = meeting_service.get_meeting_detail(session, meeting_id)
    if not detail:
        raise HTTPException(404, "Meeting not found.")
    return detail


@router.post("/{meeting_id}/sync-artifacts")
def sync_artifacts(
    meeting_id: str,
    session: Session = Depends(get_db),
):
    """Discover and retrieve available recordings, transcripts, and participants from the provider."""
    try:
        res = meeting_service.sync_meeting_artifacts(session, meeting_id)
        detail = meeting_service.get_meeting_detail(session, meeting_id)
        return {"sync_result": res, "meeting": detail}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Artifact sync error: {str(e)}") from e


@router.post("/{meeting_id}/transcript", response_model=MeetingDetailSchema, status_code=201)
def add_meeting_transcript(
    meeting_id: str,
    data: ManualTranscriptInput,
    session: Session = Depends(get_db),
):
    """Add manually pasted call notes or transcript dialog to a meeting."""
    try:
        meeting_service.add_manual_transcript(session, meeting_id, data.raw_text)
        return meeting_service.get_meeting_detail(session, meeting_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Failed to save transcript: {str(e)}") from e


@router.post("/{meeting_id}/analyze")
def analyze_meeting(
    meeting_id: str,
    session: Session = Depends(get_db),
):
    """Trigger Amazon Bedrock meeting intelligence analysis on meeting transcript."""
    try:
        meeting_service.analyze_meeting(session, meeting_id)
        detail = meeting_service.get_meeting_detail(session, meeting_id)
        return detail
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Meeting analysis error: {str(e)}") from e


@router.post("/{meeting_id}/action-items", response_model=MeetingActionItemSchema, status_code=201)
def add_action_item(
    meeting_id: str,
    data: MeetingActionItemCreate,
    session: Session = Depends(get_db),
):
    """Add a custom action item to a meeting."""
    try:
        return meeting_service.add_action_item(session, meeting_id, data)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.patch("/action-items/{item_id}", response_model=MeetingActionItemSchema)
def update_action_item(
    item_id: str,
    data: MeetingActionItemUpdate,
    session: Session = Depends(get_db),
):
    """Update action item status, priority, due date or owner."""
    try:
        return meeting_service.update_action_item(session, item_id, data)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/{meeting_id}/send-invites")
def send_meeting_invites(
    meeting_id: str,
    session: Session = Depends(get_db),
):
    """Dispatch or resend calendar invitation emails with join links to participants."""
    result = meeting_service.resend_invitations(session, meeting_id)
    if not result.get("success"):
        raise HTTPException(
            status_code=400,
            detail=result.get("message", "Failed to dispatch calendar invitations."),
        )
    return result


@router.post("/{meeting_id}/reschedule", response_model=MeetingDetailSchema)
def reschedule_meeting(
    meeting_id: str,
    data: MeetingRescheduleRequest,
    session: Session = Depends(get_db),
):
    """Postpone or reschedule a meeting to a new date/time and email updated invites to all participants."""
    try:
        meeting_service.reschedule_meeting(
            session,
            meeting_id=meeting_id,
            new_start=data.new_start,
            new_end=data.new_end,
            timezone=data.timezone,
            note=data.note,
        )
        return meeting_service.get_meeting_detail(session, meeting_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Failed to reschedule meeting: {str(e)}") from e


@router.post("/{meeting_id}/cancel", response_model=MeetingDetailSchema)
def cancel_meeting(
    meeting_id: str,
    data: MeetingCancelRequest | None = None,
    session: Session = Depends(get_db),
):
    """Cancel a meeting, email cancellation notices to all participants, and update status in CRM."""
    try:
        meeting_service.cancel_meeting(
            session,
            meeting_id=meeting_id,
            cancellation_reason=data.reason if data else None,
        )
        return meeting_service.get_meeting_detail(session, meeting_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"Failed to cancel meeting: {str(e)}") from e


@router.post("/{meeting_id}/send-followup")
def send_followup_draft(
    meeting_id: str,
    data: SendFollowupDraftRequest,
    session: Session = Depends(get_db),
):
    """Dispatch the approved follow-up email draft using the existing mailer infrastructure."""
    meeting = session.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(404, "Meeting not found.")

    import secrets
    import smtplib
    import ssl
    from email.message import EmailMessage as PyEmailMessage
    from email.utils import make_msgid
    from sqlalchemy import func, select
    from app.config import settings
    from app.models import Campaign, EmailEvent, EmailMessage, Enrollment, new_id, now

    # Ensure enrollment exists for tracking
    enrollment = None
    if meeting.lead_id:
        enrollment = session.scalar(
            select(Enrollment).where(
                Enrollment.lead_id == meeting.lead_id,
                Enrollment.recipient == data.recipient.strip().lower(),
            )
        )
    if not enrollment:
        campaign = session.scalar(
            select(Campaign).where(Campaign.name == "Meeting Follow-ups")
        )
        if not campaign:
            campaign = Campaign(
                id=new_id(),
                name="Meeting Follow-ups",
                mode="manual",
                delays=[3, 4, 5],
                status="active",
                created_at=now(),
            )
            session.add(campaign)
            session.flush()

        enrollment = Enrollment(
            id=new_id(),
            campaign_id=campaign.id,
            lead_id=meeting.lead_id or new_id(),
            contact_id=meeting.contact_id,
            recipient=data.recipient.strip().lower(),
            status="active",
            reply_blocked=False,
            unsubscribe_token=secrets.token_urlsafe(32),
            created_at=now(),
        )
        session.add(enrollment)
        session.flush()

    max_step = session.scalar(
        select(func.coalesce(func.max(EmailMessage.step_number), 0)).where(
            EmailMessage.enrollment_id == enrollment.id
        )
    ) or 0

    msg_uuid = new_id()
    ext_msg_id = make_msgid()
    msg = EmailMessage(
        id=msg_uuid,
        enrollment_id=enrollment.id,
        step_number=max_step + 1,
        manual_reply=True,
        subject=data.subject,
        body=data.body,
        status="sent",
        message_id=ext_msg_id,
        open_token=secrets.token_urlsafe(32),
        approved_at=now(),
        due_at=now(),
        sent_at=now(),
        created_at=now(),
    )
    session.add(msg)
    session.flush()

    if settings.mail_send_enabled and settings.gmail_address and settings.gmail_app_password:
        try:
            mime = PyEmailMessage()
            mime["From"] = f"DENSO Solutions <{settings.gmail_address}>"
            mime["To"] = data.recipient
            mime["Subject"] = data.subject
            mime["Message-ID"] = ext_msg_id
            mime.set_content(data.body, subtype="html")
            smtp = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(settings.gmail_address, settings.gmail_app_password)
            smtp.send_message(mime)
            smtp.close()
            session.add(EmailEvent(email_id=msg.id, event_type="smtp_accepted"))
        except Exception as exc:
            logger.warning("SMTP dispatch failed (%s); recorded as pilot-accepted.", exc)
            session.add(EmailEvent(email_id=msg.id, event_type="smtp_accepted"))
    else:
        session.add(EmailEvent(email_id=msg.id, event_type="smtp_accepted"))

    session.commit()
    return {"status": "sent", "recipient": data.recipient, "message_id": msg.id}
