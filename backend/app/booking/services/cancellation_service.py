import logging
from typing import Any
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingEventLog
from app.booking.providers.google_calendar_provider import GoogleCalendarProvider
from app.booking.services.reservation_service import hash_token
from app.meetings.models import Meeting

logger = logging.getLogger(__name__)


class CancellationService:
    @staticmethod
    def get_by_token(session: Session, raw_token: str) -> Booking | None:
        token_hash = hash_token(raw_token)
        return session.scalar(
            select(Booking).where(
                or_(
                    Booking.cancellation_token_hash == token_hash,
                    Booking.reschedule_token_hash == token_hash,
                )
            )
        )

    @staticmethod
    def cancel_booking(
        session: Session,
        raw_token: str,
        reason: str | None = None,
    ) -> Booking:
        booking = CancellationService.get_by_token(session, raw_token)
        if not booking:
            raise ValueError("Invalid cancellation token.")

        if booking.status == "cancelled":
            return booking

        # Cancel/delete Google Calendar event
        if booking.google_calendar_event_id:
            try:
                GoogleCalendarProvider.delete_calendar_event(
                    session, booking.google_calendar_event_id
                )
            except Exception as exc:
                logger.warning("Could not delete Google Calendar event: %s", exc)

        booking.status = "cancelled"

        # Update linked Meeting record
        if booking.meeting_id:
            meeting = session.get(Meeting, booking.meeting_id)
            if meeting:
                meeting.status = "cancelled"

        # Log event
        log = BookingEventLog(
            booking_id=booking.id,
            event_type="booking_cancelled",
            provider="google_meet",
            provider_event_id=booking.google_calendar_event_id,
            status="cancelled",
            details={"reason": reason or "Customer requested cancellation"},
        )
        session.add(log)
        session.commit()
        session.refresh(booking)

        return booking
