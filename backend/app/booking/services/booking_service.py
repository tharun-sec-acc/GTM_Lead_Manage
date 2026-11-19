import re
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingEventLog, BookingProfile, BookingReservation
from app.booking.providers.google_calendar_provider import GoogleCalendarProvider
from app.booking.schemas import BookingConfirmRequest
from app.booking.services.booking_profile_service import BookingProfileService
from app.booking.services.reservation_service import (
    ReservationConflictError,
    ReservationService,
    hash_token,
)
from app.config import settings
from app.meetings.models import Meeting, MeetingParticipant
from app.models import Contact, Lead


def clean_company_key(company_name: str) -> str:
    return re.sub(r"\s+", " ", company_name.casefold()).strip()


class BookingService:
    @staticmethod
    def get_by_id(session: Session, booking_id: str) -> Booking | None:
        return session.get(Booking, booking_id)

    @staticmethod
    def list_bookings(
        session: Session,
        profile_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Booking]:
        query = select(Booking).order_by(Booking.start_time.desc()).limit(limit)
        if profile_id:
            query = query.where(Booking.booking_profile_id == profile_id)
        if status:
            query = query.where(Booking.status == status)
        return list(session.scalars(query).all())

    @staticmethod
    def confirm_booking(
        session: Session,
        profile_slug: str,
        data: BookingConfirmRequest,
    ) -> tuple[Booking, str, str]:
        """
        Finalize a public booking:
        - Check idempotency.
        - Verify reservation hold.
        - Create Google Calendar event with Google Meet conference and sendUpdates=all.
        - Link/Create Lead and Contact records in CRM.
        - Create core Meeting entity.
        - Create Booking record and log audit entry.
        Returns (booking, cancellation_token, reschedule_token).
        """
        # Idempotency check
        if data.idempotency_key:
            existing = session.scalar(
                select(Booking).where(Booking.idempotency_key == data.idempotency_key)
            )
            if existing:
                return existing, "", ""

        profile = BookingProfileService.get_by_slug(session, profile_slug)
        if not profile:
            raise ValueError(f"Booking profile '{profile_slug}' not found.")
        if not profile.is_active:
            raise ValueError(f"Booking profile '{profile.display_name}' is currently inactive.")

        # Validate reservation hold
        reservation = ReservationService.get_valid_reservation(
            session=session,
            profile_id=profile.id,
            raw_token=data.reservation_token,
        )

        customer_email = data.customer_email.strip().lower()
        customer_name = data.customer_name.strip()
        customer_company = data.customer_company.strip() if data.customer_company else None
        customer_phone = data.customer_phone.strip() if data.customer_phone else None
        meeting_purpose = data.meeting_purpose.strip() if data.meeting_purpose else None

        # Build meeting summary and description
        event_title = profile.meeting_title
        if customer_company:
            event_title = f"{profile.meeting_title} - {customer_company}"
        elif customer_name:
            event_title = f"{profile.meeting_title} - {customer_name}"

        event_desc = (
            f"{profile.meeting_description or profile.meeting_title}\n\n"
            f"Customer: {customer_name}\n"
            f"Email: {customer_email}\n"
            f"Company: {customer_company or 'N/A'}\n"
            f"Phone: {customer_phone or 'N/A'}\n"
            f"Purpose: {meeting_purpose or 'N/A'}\n"
            f"Source: GTMProspecting Public Booking"
        )

        # Create Google Calendar event with Google Meet conference
        google_event_id, google_meet_uri, raw_resp = GoogleCalendarProvider.create_calendar_event(
            session=session,
            title=event_title,
            description=event_desc,
            start_time=reservation.start_time,
            end_time=reservation.end_time,
            timezone_str=data.timezone,
            customer_name=customer_name,
            customer_email=customer_email,
        )

        # CRM Integration: Match or create Contact & Lead
        contact = session.scalar(
            select(Contact).where(Contact.email == customer_email)
        )
        lead = None
        if contact and contact.lead_id:
            lead = session.get(Lead, contact.lead_id)

        if not lead and customer_company:
            comp_key = clean_company_key(customer_company)
            lead = session.scalar(select(Lead).where(Lead.company_key == comp_key))

        if not lead:
            comp_name = customer_company or f"{customer_name} (Inbound)"
            comp_key = clean_company_key(comp_name)
            lead = Lead(
                company_name=comp_name,
                company_key=comp_key,
                email=customer_email,
                phone=customer_phone,
                industry="General",
                extra={"source": "public_booking", "booking_profile": profile.public_slug},
            )
            session.add(lead)
            session.flush()

        if not contact:
            contact = Contact(
                lead_id=lead.id,
                name=customer_name,
                email=customer_email,
                title="Inbound Prospect",
                source="public_booking",
            )
            session.add(contact)
            session.flush()
        elif not contact.lead_id:
            contact.lead_id = lead.id

        # Core Meeting record
        meeting = Meeting(
            provider="google_meet",
            external_meeting_id=google_event_id,
            organizer_email=settings.google_workspace_organizer_email,
            lead_id=lead.id,
            contact_id=contact.id,
            title=event_title,
            description=meeting_purpose or profile.meeting_description,
            meeting_type="scheduled",
            join_url=google_meet_uri,
            scheduled_start=reservation.start_time,
            scheduled_end=reservation.end_time,
            timezone=data.timezone,
            status="scheduled",
            provider_metadata=raw_resp if isinstance(raw_resp, dict) else {},
        )
        session.add(meeting)
        session.flush()

        # Add customer participant
        cust_participant = MeetingParticipant(
            meeting_id=meeting.id,
            email=customer_email,
            display_name=customer_name,
            participant_role="external",
        )
        session.add(cust_participant)

        # Generate tokens
        cancellation_token = secrets.token_urlsafe(32)
        reschedule_token = secrets.token_urlsafe(32)
        cancellation_hash = hash_token(cancellation_token)
        reschedule_hash = hash_token(reschedule_token)

        # Booking entity
        booking = Booking(
            booking_profile_id=profile.id,
            meeting_id=meeting.id,
            lead_id=lead.id,
            contact_id=contact.id,
            provider="google_meet",
            customer_name=customer_name,
            customer_email=customer_email,
            customer_company=customer_company,
            customer_phone=customer_phone,
            meeting_purpose=meeting_purpose,
            start_time=reservation.start_time,
            end_time=reservation.end_time,
            timezone=data.timezone,
            google_calendar_event_id=google_event_id,
            google_meet_uri=google_meet_uri,
            status="confirmed",
            cancellation_token_hash=cancellation_hash,
            reschedule_token_hash=reschedule_hash,
            idempotency_key=data.idempotency_key,
        )
        session.add(booking)
        session.flush()

        # Mark reservation as confirmed
        reservation.status = "confirmed"

        # Log event
        log = BookingEventLog(
            booking_id=booking.id,
            event_type="booking_confirmed",
            provider="google_meet",
            provider_event_id=google_event_id,
            status="success",
            details={
                "customer_email": customer_email,
                "start_time": reservation.start_time.isoformat(),
                "end_time": reservation.end_time.isoformat(),
                "meet_uri": google_meet_uri,
                "lead_id": lead.id,
                "meeting_id": meeting.id,
            },
        )
        session.add(log)
        session.commit()
        session.refresh(booking)

        return booking, cancellation_token, reschedule_token
