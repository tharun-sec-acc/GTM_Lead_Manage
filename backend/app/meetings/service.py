import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.meetings.artifacts.storage_service import storage_service
from app.meetings.intelligence.meeting_analyzer import analyze_meeting_transcript
from app.meetings.models import (
    Meeting,
    MeetingActionItem,
    MeetingAnalysis,
    MeetingParticipant,
    MeetingRecording,
    MeetingTranscript,
    MeetingTranscriptEntry,
    new_id,
    now,
)
from app.meetings.providers import get_meeting_provider
from app.meetings.schemas import (
    MeetingActionItemCreate,
    MeetingActionItemUpdate,
    MeetingCreateRequest,
    MeetingDetailSchema,
    MeetingSummarySchema,
)
from app.models import Contact, Lead, Product

logger = logging.getLogger(__name__)


class MeetingService:
    def create_meeting(self, session: Session, request: MeetingCreateRequest) -> Meeting:
        """Create an instant or scheduled meeting across Microsoft Teams or Google Meet."""
        provider = get_meeting_provider(request.provider)

        # 1. Dispatch creation to provider
        if request.meeting_type == "instant":
            ext_id, join_url, meta = provider.create_instant_meeting(session, request)
        else:
            ext_id, join_url, meta = provider.schedule_meeting(session, request)

        # 2. Identify organizer email
        status_info = provider.get_status(session)
        organizer_email = status_info.get("organizer_email")

        # 3. Create Meeting record
        meeting = Meeting(
            id=new_id(),
            provider=request.provider,
            external_meeting_id=ext_id,
            organizer_email=organizer_email,
            lead_id=request.lead_id,
            contact_id=request.contact_id,
            product_id=request.product_id,
            title=request.title,
            description=request.description,
            meeting_type=request.meeting_type,
            join_url=join_url,
            scheduled_start=request.scheduled_start,
            scheduled_end=request.scheduled_end,
            timezone=request.timezone or "UTC",
            status="scheduled" if request.meeting_type == "scheduled" else "in_progress",
            provider_metadata=meta or {},
            created_at=now(),
            updated_at=now(),
        )
        session.add(meeting)
        session.flush()

        # 4. Add Organizer Participant
        if organizer_email:
            session.add(
                MeetingParticipant(
                    id=new_id(),
                    meeting_id=meeting.id,
                    email=organizer_email,
                    display_name="Organizer",
                    participant_role="organizer",
                    created_at=now(),
                )
            )

        # 5. Add Contact and Participant emails
        added_emails = {organizer_email.lower()} if organizer_email else set()
        if request.contact_id:
            contact = session.get(Contact, request.contact_id)
            if contact and contact.email and contact.email.lower() not in added_emails:
                session.add(
                    MeetingParticipant(
                        id=new_id(),
                        meeting_id=meeting.id,
                        email=contact.email,
                        display_name=contact.name,
                        participant_role="attendee",
                        created_at=now(),
                    )
                )
                added_emails.add(contact.email.lower())

        for email in request.participant_emails:
            clean_email = email.strip().lower()
            if clean_email and clean_email not in added_emails:
                session.add(
                    MeetingParticipant(
                        id=new_id(),
                        meeting_id=meeting.id,
                        email=clean_email,
                        display_name=clean_email.split("@")[0],
                        participant_role="attendee",
                        created_at=now(),
                    )
                )
                added_emails.add(clean_email)

        # 6. Update Lead Stage if applicable
        if request.lead_id:
            lead = session.get(Lead, request.lead_id)
            if lead:
                if hasattr(lead, "stage"):
                    setattr(lead, "stage", "Meeting Scheduled")
                extra = dict(lead.extra or {})
                extra["stage"] = "Meeting Scheduled"
                lead.extra = extra

        session.commit()
        session.refresh(meeting)

        # Automatically generate initial AI meeting intelligence and MoM framework upon creation
        try:
            self.analyze_meeting(session, meeting.id)
            session.expire(meeting)
            meeting = session.get(Meeting, meeting.id)
        except Exception as e:
            logger.info("Automatic initial analysis for meeting %s deferred: %s", meeting.id, e)

        return meeting

    def list_meetings(
        self,
        session: Session,
        provider: str | None = None,
        status: str | None = None,
        lead_id: str | None = None,
        product_id: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        """List meetings with associated company, contact, and artifact indicator badges."""
        stmt = select(Meeting).order_by(Meeting.created_at.desc())
        if provider:
            stmt = stmt.where(Meeting.provider == provider.lower())
        if status:
            stmt = stmt.where(Meeting.status == status.lower())
        if lead_id:
            stmt = stmt.where(Meeting.lead_id == lead_id)
        if product_id:
            stmt = stmt.where(Meeting.product_id == product_id)

        meetings = session.scalars(stmt).all()
        results = []

        for m in meetings:
            # Auto-synthesize initial AI meeting analysis & MoM if not yet generated
            if m.analysis is None:
                try:
                    self.analyze_meeting(session, m.id)
                    session.expire(m)
                    m = session.get(Meeting, m.id) or m
                except Exception as e:
                    logger.debug("Auto-analysis during meeting listing deferred for %s: %s", m.id, e)

            lead = session.get(Lead, m.lead_id) if m.lead_id else None
            contact = session.get(Contact, m.contact_id) if m.contact_id else None
            product = session.get(Product, m.product_id) if m.product_id else None

            # Automatically ensure AI analysis & MoM exists for every meeting so sales reps never have to wait
            if not m.analysis:
                try:
                    self.analyze_meeting(session, m.id)
                    session.expire(m)
                except Exception as e:
                    logger.warning("Auto-analysis in list_meetings deferred for %s: %s", m.id, e)

            # Filters search string against title or company
            if search and search.strip():
                q = search.strip().lower()
                company_str = (lead.company_name if lead else "").lower()
                title_str = (m.title or "").lower()
                if q not in company_str and q not in title_str:
                    continue

            results.append({
                "id": m.id,
                "provider": m.provider,
                "external_meeting_id": m.external_meeting_id,
                "organizer_email": m.organizer_email,
                "lead_id": m.lead_id,
                "company_name": lead.company_name if lead else None,
                "contact_id": m.contact_id,
                "contact_name": contact.name if contact else None,
                "product_id": m.product_id,
                "product_name": product.name if product else None,
                "title": m.title,
                "description": m.description,
                "meeting_type": m.meeting_type,
                "join_url": m.join_url,
                "scheduled_start": m.scheduled_start,
                "scheduled_end": m.scheduled_end,
                "timezone": m.timezone,
                "status": m.status,
                "has_recording": len(m.recordings) > 0,
                "has_transcript": len(m.transcripts) > 0,
                "has_analysis": m.analysis is not None,
                "action_items_count": len(m.action_items),
                "created_at": m.created_at,
            })

        return results

    def get_meeting_detail(self, session: Session, meeting_id: str) -> dict[str, Any] | None:
        """Fetch full detailed view of meeting including timeline, artifacts, MoM and action items."""
        m = session.get(Meeting, meeting_id)
        if not m:
            return None

        # Automatically generate AI analysis & MoM if missing so sales reps never have to click
        if not m.analysis:
            try:
                self.analyze_meeting(session, m.id)
                session.expire(m)
                m = session.get(Meeting, meeting_id)
                if not m:
                    return None
            except Exception as e:
                logger.warning("Auto-analysis in get_meeting_detail deferred for %s: %s", meeting_id, e)

        lead = session.get(Lead, m.lead_id) if m.lead_id else None
        contact = session.get(Contact, m.contact_id) if m.contact_id else None
        product = session.get(Product, m.product_id) if m.product_id else None

        # Build recording schemas with presigned URLs
        recordings_data = []
        for r in m.recordings:
            download_url = storage_service.generate_presigned_download_url(r.s3_key, r.s3_bucket) if r.s3_key else None
            recordings_data.append({
                "id": r.id,
                "filename": r.filename,
                "mime_type": r.mime_type,
                "duration_seconds": r.duration_seconds,
                "s3_key": r.s3_key,
                "source_location": r.source_location,
                "download_url": download_url,
                "processing_status": r.processing_status,
                "created_at": r.created_at,
            })

        # Build transcripts with normalized entries
        transcripts_data = []
        for t in m.transcripts:
            entries = [
                {
                    "id": e.id,
                    "speaker_name": e.speaker_name,
                    "text": e.text,
                    "start_timestamp": e.start_timestamp,
                    "end_timestamp": e.end_timestamp,
                }
                for e in t.entries
            ]
            transcripts_data.append({
                "id": t.id,
                "language": t.language,
                "source": t.source,
                "processing_status": t.processing_status,
                "entries": entries,
                "created_at": t.created_at,
            })

        analysis_data = None
        if m.analysis:
            a = m.analysis
            analysis_data = {
                "id": a.id,
                "analysis_version": a.analysis_version,
                "executive_summary": a.executive_summary,
                "customer_requirements": a.customer_requirements or [],
                "customer_pain_points": a.customer_pain_points or [],
                "technical_requirements": a.technical_requirements or [],
                "objections": a.objections or [],
                "buying_signals": a.buying_signals or [],
                "decisions": a.decisions or [],
                "next_steps": a.next_steps or [],
                "meeting_minutes": a.meeting_minutes,
                "followup_draft_subject": a.followup_draft_subject,
                "followup_draft_body": a.followup_draft_body,
                "recommended_sales_stage": a.recommended_sales_stage,
                "recommended_next_action": a.recommended_next_action,
                "analysis_status": a.analysis_status,
                "confidence": a.confidence,
                "created_at": a.created_at,
            }

        action_items = session.query(MeetingActionItem).filter(MeetingActionItem.meeting_id == meeting_id).order_by(MeetingActionItem.created_at.asc()).all()
        action_items_data = [
            {
                "id": item.id,
                "meeting_id": item.meeting_id,
                "lead_id": item.lead_id,
                "title": item.title,
                "description": item.description,
                "owner": item.owner,
                "due_date": item.due_date,
                "priority": item.priority,
                "status": item.status,
                "source_timestamp": item.source_timestamp,
                "created_at": item.created_at,
            }
            for item in action_items
        ]

        participants_data = [
            {
                "id": p.id,
                "email": p.email,
                "display_name": p.display_name,
                "participant_role": p.participant_role,
                "join_time": p.join_time,
                "leave_time": p.leave_time,
                "provider_metadata": p.provider_metadata or {},
            }
            for p in m.participants
        ]

        return {
            "id": m.id,
            "provider": m.provider,
            "external_meeting_id": m.external_meeting_id,
            "organizer_email": m.organizer_email,
            "lead_id": m.lead_id,
            "company_name": lead.company_name if lead else None,
            "contact_id": m.contact_id,
            "contact_name": contact.name if contact else None,
            "product_id": m.product_id,
            "product_name": product.name if product else None,
            "title": m.title,
            "description": m.description,
            "meeting_type": m.meeting_type,
            "join_url": m.join_url,
            "scheduled_start": m.scheduled_start,
            "scheduled_end": m.scheduled_end,
            "actual_start": m.actual_start,
            "actual_end": m.actual_end,
            "timezone": m.timezone,
            "status": m.status,
            "provider_metadata": m.provider_metadata or {},
            "participants": participants_data,
            "recordings": recordings_data,
            "transcripts": transcripts_data,
            "analysis": analysis_data,
            "action_items": action_items_data,
            "created_at": m.created_at,
            "updated_at": m.updated_at,
        }

    def sync_meeting_artifacts(self, session: Session, meeting_id: str) -> dict[str, Any]:
        """Discover and retrieve recordings, transcripts, and participants from the provider."""
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found.")

        provider = get_meeting_provider(meeting.provider)
        ext_id = meeting.external_meeting_id
        if not ext_id:
            return {"recordings": 0, "transcripts": 0, "status": "No external ID"}

        synced_recordings = 0
        synced_transcripts = 0

        # 1. Sync Participants
        participants = provider.get_participants(session, ext_id)
        existing_emails = {p.email.lower() for p in meeting.participants}
        for p in participants:
            email = p.get("email", "").strip().lower()
            if email and email not in existing_emails:
                session.add(
                    MeetingParticipant(
                        id=new_id(),
                        meeting_id=meeting.id,
                        email=email,
                        display_name=p.get("display_name"),
                        participant_role=p.get("participant_role", "attendee"),
                        join_time=p.get("join_time"),
                        leave_time=p.get("leave_time"),
                        provider_metadata=p.get("provider_metadata", {}),
                        created_at=now(),
                    )
                )
                existing_emails.add(email)

        # 2. Sync Recordings
        recordings_meta = provider.discover_recordings(session, ext_id)
        for r in recordings_meta:
            existing = session.scalar(
                select(MeetingRecording).where(
                    MeetingRecording.meeting_id == meeting.id,
                    MeetingRecording.external_recording_id == r.get("external_recording_id"),
                )
            )
            if not existing:
                filename = r.get("filename") or f"{meeting.provider}_recording_{meeting.id}.mp4"
                s3_key = storage_service.generate_s3_key(meeting.lead_id, meeting.id, "recordings", filename)

                # Attempt download if source available
                data_bytes = provider.download_recording(session, r)
                s3_info = storage_service.store_bytes(data_bytes or b"", s3_key, "video/mp4") if data_bytes else {}

                rec_obj = MeetingRecording(
                    id=new_id(),
                    meeting_id=meeting.id,
                    external_recording_id=r.get("external_recording_id"),
                    external_file_id=r.get("external_file_id"),
                    filename=filename,
                    mime_type=r.get("mime_type", "video/mp4"),
                    duration_seconds=r.get("duration_seconds"),
                    source_location=r.get("source_location"),
                    s3_bucket=s3_info.get("s3_bucket"),
                    s3_key=s3_key,
                    processing_status="archived" if data_bytes else "discovered",
                    created_at=now(),
                )
                session.add(rec_obj)
                synced_recordings += 1

        # 3. Sync Transcripts
        transcripts_meta = provider.discover_transcripts(session, ext_id)
        for t in transcripts_meta:
            t_ext_id = t.get("external_transcript_id")
            existing_t = session.scalar(
                select(MeetingTranscript).where(
                    MeetingTranscript.meeting_id == meeting.id,
                    MeetingTranscript.external_transcript_id == t_ext_id,
                )
            )
            if not existing_t:
                transcript_info = dict(t)
                transcript_info["external_meeting_id"] = ext_id
                entries = provider.fetch_transcript_entries(session, transcript_info)

                raw_text = "\n".join(f"{e['speaker_name']}: {e['text']}" for e in entries)
                s3_key = storage_service.generate_s3_key(meeting.lead_id, meeting.id, "transcripts", "transcript.txt")
                s3_info = storage_service.store_bytes(raw_text.encode("utf-8"), s3_key, "text/plain")

                trans_obj = MeetingTranscript(
                    id=new_id(),
                    meeting_id=meeting.id,
                    external_transcript_id=t_ext_id,
                    language=t.get("language", "en"),
                    source=t.get("source", meeting.provider),
                    s3_bucket=s3_info.get("s3_bucket"),
                    s3_key=s3_key,
                    raw_content=raw_text,
                    processing_status="normalized" if entries else "discovered",
                    created_at=now(),
                )
                session.add(trans_obj)
                session.flush()

                for entry in entries:
                    session.add(
                        MeetingTranscriptEntry(
                            id=new_id(),
                            transcript_id=trans_obj.id,
                            speaker_name=entry.get("speaker_name", "Speaker"),
                            text=entry.get("text", ""),
                            start_timestamp=entry.get("start_timestamp"),
                            end_timestamp=entry.get("end_timestamp"),
                            original_metadata=entry.get("original_metadata", {}),
                            created_at=now(),
                        )
                    )
                synced_transcripts += 1

        meeting.status = "completed"
        session.commit()

        # 4. Trigger AI analysis if transcripts are available and no analysis exists
        if synced_transcripts > 0 or len(meeting.transcripts) > 0:
            if not meeting.analysis:
                self.analyze_meeting(session, meeting.id)

        return {
            "recordings_discovered": synced_recordings,
            "transcripts_discovered": synced_transcripts,
            "status": "synchronized",
        }

    def analyze_meeting(self, session: Session, meeting_id: str) -> MeetingAnalysis:
        """Run Amazon Bedrock meeting intelligence analysis on meeting transcript."""
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found.")

        lead = session.get(Lead, meeting.lead_id) if meeting.lead_id else None
        contact = session.get(Contact, meeting.contact_id) if meeting.contact_id else None
        product = session.get(Product, meeting.product_id) if meeting.product_id else None

        company_name = lead.company_name if lead else "Prospect Organization"
        contact_name = contact.name if contact else (meeting.title or "Prospect")
        product_name = product.name if product else "DENSO Enterprise Platform"

        # Assemble transcript text
        transcript_text = ""
        for t in meeting.transcripts:
            if t.entries:
                transcript_text += "\n".join(f"{e.speaker_name}: {e.text}" for e in t.entries) + "\n"
            elif t.raw_content:
                transcript_text += t.raw_content + "\n"

        if not transcript_text.strip():
            transcript_text = (
                f"Sales meeting between DENSO Sales Representative and {contact_name} representing {company_name}. "
                f"Topic: {meeting.title}. Description: {meeting.description or 'Platform walkthrough and discovery'}."
            )

        # Run Bedrock analysis
        intel = analyze_meeting_transcript(
            transcript_text=transcript_text,
            company_name=company_name,
            contact_name=contact_name,
            product_name=product_name,
        )

        # Upsert MeetingAnalysis
        analysis = session.query(MeetingAnalysis).filter(MeetingAnalysis.meeting_id == meeting.id).first()
        if not analysis:
            analysis = MeetingAnalysis(
                id=new_id(),
                meeting_id=meeting.id,
                analysis_version="v1",
                executive_summary=intel.executive_summary,
                customer_requirements=intel.customer_requirements,
                customer_pain_points=intel.customer_pain_points,
                technical_requirements=intel.technical_requirements,
                objections=intel.objections,
                buying_signals=intel.buying_signals,
                decisions=intel.decisions,
                next_steps=intel.next_steps,
                meeting_minutes=intel.meeting_minutes,
                followup_draft_subject=intel.followup_draft_subject,
                followup_draft_body=intel.followup_draft_body,
                recommended_sales_stage=intel.recommended_sales_stage,
                recommended_next_action=intel.recommended_next_action,
                structured_analysis=intel.model_dump(),
                analysis_status="completed",
                confidence=intel.confidence,
                created_at=now(),
                updated_at=now(),
            )
            session.add(analysis)
        else:
            analysis.executive_summary = intel.executive_summary
            analysis.customer_requirements = intel.customer_requirements
            analysis.customer_pain_points = intel.customer_pain_points
            analysis.technical_requirements = intel.technical_requirements
            analysis.objections = intel.objections
            analysis.buying_signals = intel.buying_signals
            analysis.decisions = intel.decisions
            analysis.next_steps = intel.next_steps
            analysis.meeting_minutes = intel.meeting_minutes
            analysis.followup_draft_subject = intel.followup_draft_subject
            analysis.followup_draft_body = intel.followup_draft_body
            analysis.recommended_sales_stage = intel.recommended_sales_stage
            analysis.recommended_next_action = intel.recommended_next_action
            analysis.structured_analysis = intel.model_dump()
            analysis.analysis_status = "completed"
            analysis.confidence = intel.confidence
            analysis.updated_at = now()

        # Add Action Items
        existing_titles = {item.title for item in meeting.action_items}
        for item in intel.action_items:
            title = item.get("title", "")
            if title and title not in existing_titles:
                session.add(
                    MeetingActionItem(
                        id=new_id(),
                        meeting_id=meeting.id,
                        lead_id=meeting.lead_id,
                        title=title,
                        description=item.get("description"),
                        owner=item.get("owner", "Sales Rep"),
                        due_date=item.get("due_date", "Next week"),
                        priority=item.get("priority", "medium"),
                        status="open",
                        created_at=now(),
                    )
                )
                existing_titles.add(title)

        # Update lead stage
        if lead and intel.recommended_sales_stage:
            if hasattr(lead, "stage"):
                setattr(lead, "stage", intel.recommended_sales_stage)
            extra = dict(lead.extra or {})
            extra["stage"] = intel.recommended_sales_stage
            lead.extra = extra

        session.commit()
        session.refresh(analysis)

        # Phase 9: Sync meeting intelligence and MoM to Zoho CRM
        try:
            from app.zoho.service import ZohoService
            ZohoService(session).sync_meeting_intelligence_to_zoho(meeting.id)
            session.commit()
        except Exception as ze:
            logger.warning("Zoho CRM meeting intelligence sync skipped or deferred: %s", ze)

        return analysis

    def add_action_item(
        self, session: Session, meeting_id: str, data: MeetingActionItemCreate
    ) -> MeetingActionItem:
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found.")
        item = MeetingActionItem(
            id=new_id(),
            meeting_id=meeting.id,
            lead_id=meeting.lead_id,
            title=data.title,
            description=data.description,
            owner=data.owner,
            due_date=data.due_date,
            priority=data.priority,
            status="open",
            created_at=now(),
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    def update_action_item(
        self, session: Session, item_id: str, data: MeetingActionItemUpdate
    ) -> MeetingActionItem:
        item = session.get(MeetingActionItem, item_id)
        if not item:
            raise ValueError("Action item not found.")
        if data.status is not None:
            item.status = data.status
        if data.title is not None:
            item.title = data.title
        if data.owner is not None:
            item.owner = data.owner
        if data.due_date is not None:
            item.due_date = data.due_date
        if data.priority is not None:
            item.priority = data.priority
        session.commit()
        session.refresh(item)
        return item

    def resend_invitations(self, session: Session, meeting_id: str) -> dict[str, Any]:
        """Dispatch or re-send calendar invitation emails for a meeting."""
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            return {"success": False, "message": "Meeting not found."}

        provider = get_meeting_provider(meeting.provider)
        attendees = [
            p.email
            for p in (meeting.participants or [])
            if p.email and p.participant_role != "organizer"
        ]
        return provider.resend_invitations(
            session,
            external_meeting_id=meeting.external_meeting_id or "",
            participant_emails=attendees,
        )

    def add_manual_transcript(self, session: Session, meeting_id: str, raw_text: str) -> MeetingTranscript:
        """Store manually entered call notes or pasted transcript dialog and create structured entries."""
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found.")

        trans_obj = MeetingTranscript(
            id=new_id(),
            meeting_id=meeting.id,
            external_transcript_id=f"manual_{new_id()[:8]}",
            language="en",
            source="manual_notes",
            raw_content=raw_text,
            processing_status="completed",
            created_at=now(),
        )
        session.add(trans_obj)
        session.flush()

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            speaker = "Participant"
            text = line
            if ":" in line and len(line.split(":", 1)[0]) < 35:
                parts = line.split(":", 1)
                speaker = parts[0].strip()
                text = parts[1].strip()
            session.add(
                MeetingTranscriptEntry(
                    id=new_id(),
                    meeting_transcript_id=trans_obj.id,
                    speaker_name=speaker,
                    text=text,
                    entry_order=i,
                    created_at=now(),
                )
            )

        session.commit()
        session.refresh(meeting)
        return trans_obj

    def reschedule_meeting(
        self, session: Session, meeting_id: str, new_start: datetime, new_end: datetime, timezone: str = "UTC", note: str | None = None
    ) -> Meeting:
        """Reschedule or postpone a meeting to a new time and update calendar event with sendUpdates=all."""
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found.")
        if meeting.status == "cancelled":
            raise ValueError("Cannot reschedule a cancelled meeting.")

        provider = get_meeting_provider(meeting.provider)
        if meeting.external_meeting_id:
            try:
                provider.reschedule_meeting(
                    session,
                    external_meeting_id=meeting.external_meeting_id,
                    new_start=new_start,
                    new_end=new_end,
                    timezone=timezone or meeting.timezone or "UTC",
                    note=note,
                )
            except Exception as e:
                logger.warning("Provider reschedule error for meeting %s: %s", meeting_id, e)

        meeting.scheduled_start = new_start
        meeting.scheduled_end = new_end
        meeting.timezone = timezone or meeting.timezone
        meeting.status = "scheduled"
        meeting.updated_at = now()

        if meeting.lead_id:
            lead = session.get(Lead, meeting.lead_id)
            if lead:
                if hasattr(lead, "stage"):
                    setattr(lead, "stage", "Meeting Rescheduled")
                extra = dict(lead.extra or {})
                extra["stage"] = "Meeting Rescheduled"
                lead.extra = extra

        session.commit()
        session.refresh(meeting)
        return meeting

    def cancel_meeting(
        self, session: Session, meeting_id: str, cancellation_reason: str | None = None
    ) -> Meeting:
        """Cancel a meeting, notify all participants via cancellation email, and update CRM status."""
        meeting = session.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found.")

        provider = get_meeting_provider(meeting.provider)
        if meeting.external_meeting_id:
            try:
                provider.cancel_meeting(
                    session,
                    external_meeting_id=meeting.external_meeting_id,
                    cancellation_reason=cancellation_reason,
                )
            except Exception as e:
                logger.warning("Provider cancellation error for meeting %s: %s", meeting_id, e)

        meeting.status = "cancelled"
        meeting.updated_at = now()

        if meeting.lead_id:
            lead = session.get(Lead, meeting.lead_id)
            if lead:
                if hasattr(lead, "stage"):
                    setattr(lead, "stage", "Meeting Cancelled")
                extra = dict(lead.extra or {})
                extra["stage"] = "Meeting Cancelled"
                lead.extra = extra

        session.commit()
        session.refresh(meeting)
        return meeting


meeting_service = MeetingService()
