import logging
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingEventLog
from app.booking.providers.google_calendar_provider import GoogleCalendarProvider
from app.booking.services.availability_service import (
    AvailabilityService,
    AvailabilityServiceError,
)
from app.booking.services.reservation_service import hash_token
from app.booking.services.slot_generator import normalize_utc
from app.meetings.models import Meeting

logger = logging.getLogger(__name__)


class RescheduleService:
    @staticmethod
    def get_by_token(session: Session, raw_token: str) -> Booking | None:
        token_hash = hash_token(raw_token)
        return session.scalar(
            select(Booking).where(
                or_(
                    Booking.reschedule_token_hash == token_hash,
                    Booking.cancellation_token_hash == token_hash,
                )
            )
        )

    @staticmethod
    def reschedule_booking(
        session: Session,
        raw_token: str,
        new_start: datetime,
        new_end: datetime,
        timezone_str: str = "UTC",
        reason: str | None = None,
        require_both_calendars: bool = True,
    ) -> Booking:
        booking = RescheduleService.get_by_token(session, raw_token)
        if not booking:
            raise ValueError("Invalid reschedule token.")

        if booking.status == "cancelled":
            raise ValueError("Cancelled bookings cannot be rescheduled. Please book a new meeting.")

        new_start_utc = normalize_utc(new_start)
        new_end_utc = normalize_utc(new_end)
        now_utc = datetime.now(timezone.utc)

        if new_end_utc <= new_start_utc:
            raise ValueError("New end time must be after start time.")
        earliest_allowed = min(now_utc, normalize_utc(booking.start_time))
        if new_start_utc < earliest_allowed:
            raise ValueError("Cannot reschedule into the past.")

        profile = booking.profile

        # Check calendar availability for new slot
        busy_intervals = AvailabilityService.get_busy_intervals(
            session=session,
            profile=profile,
            start_time=new_start_utc,
            end_time=new_end_utc,
            require_both_calendars=require_both_calendars,
        )

        for b_start, b_end in busy_intervals:
            # Skip conflict with current booking itself
            if normalize_utc(b_start) == normalize_utc(booking.start_time) and normalize_utc(b_end) == normalize_utc(booking.end_time):
                continue
            if max(new_start_utc, normalize_utc(b_start)) < min(new_end_utc, normalize_utc(b_end)):
                raise ValueError("The requested new slot is not available.")

        # Update Google Calendar event
        if booking.google_calendar_event_id:
            try:
                GoogleCalendarProvider.update_calendar_event(
                    session=session,
                    event_id=booking.google_calendar_event_id,
                    start_time=new_start_utc,
                    end_time=new_end_utc,
                    timezone_str=timezone_str,
                    reason=reason,
                )
            except Exception as exc:
                logger.warning("Could not update Google Calendar event: %s", exc)

        # Update Booking
        booking.start_time = new_start_utc
        booking.end_time = new_end_utc
        booking.timezone = timezone_str
        booking.status = "confirmed"

        # Update linked Meeting
        if booking.meeting_id:
            meeting = session.get(Meeting, booking.meeting_id)
            if meeting:
                meeting.scheduled_start = new_start_utc
                meeting.scheduled_end = new_end_utc
                meeting.timezone = timezone_str
                meeting.status = "scheduled"

        # Log event
        log = BookingEventLog(
            booking_id=booking.id,
            event_type="booking_rescheduled",
            provider="google_meet",
            provider_event_id=booking.google_calendar_event_id,
            status="success",
            details={
                "new_start": new_start_utc.isoformat(),
                "new_end": new_end_utc.isoformat(),
                "reason": reason or "Customer requested reschedule",
            },
        )
        session.add(log)
        session.commit()
        session.refresh(booking)

        return booking
