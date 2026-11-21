from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingProfile, BookingReservation
from app.booking.providers.google_calendar_provider import GoogleCalendarProvider
from app.booking.providers.microsoft_calendar_provider import MicrosoftCalendarProvider
from app.booking.schemas import AvailabilityResponse, SlotItem
from app.booking.services.slot_generator import generate_available_slots, normalize_utc
from app.config import settings


class AvailabilityServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Sort and merge overlapping or contiguous datetime intervals in UTC."""
    if not intervals:
        return []

    # Normalize to UTC
    normalized = []
    for s, e in intervals:
        s_utc = normalize_utc(s)
        e_utc = normalize_utc(e)
        if e_utc > s_utc:
            normalized.append((s_utc, e_utc))

    if not normalized:
        return []

    normalized.sort(key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = [normalized[0]]

    for current_start, current_end in normalized[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            # Overlaps or touches
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))

    return merged


class AvailabilityService:
    @staticmethod
    def check_calendar_connections(session: Session) -> dict[str, bool]:
        """Check status of Google Calendar and Microsoft Outlook connections."""
        google_ok = GoogleCalendarProvider.is_connected(session)
        outlook_ok = MicrosoftCalendarProvider.is_connected(session)
        return {
            "google_connected": google_ok,
            "microsoft_connected": outlook_ok,
            "both_connected": google_ok and outlook_ok,
        }

    @staticmethod
    def get_busy_intervals(
        session: Session,
        profile: BookingProfile,
        start_time: datetime,
        end_time: datetime,
        require_both_calendars: bool = True,
    ) -> list[tuple[datetime, datetime]]:
        """
        Aggregate busy intervals from:
        1. Google Calendar FreeBusy API
        2. Microsoft Outlook Calendar getSchedule API
        3. Pending, non-expired BookingReservations
        4. Confirmed Bookings in the system
        """
        start_utc = normalize_utc(start_time)
        end_utc = normalize_utc(end_time)
        now_utc = datetime.now(timezone.utc)

        all_intervals: list[tuple[datetime, datetime]] = []

        # 1. Google Calendar FreeBusy
        try:
            google_busy = GoogleCalendarProvider.get_busy_intervals(session, start_utc, end_utc)
            all_intervals.extend(google_busy)
        except Exception as exc:
            if require_both_calendars:
                raise AvailabilityServiceError(
                    f"Google Calendar availability is unavailable: {exc}", status_code=502
                ) from exc

        # 2. Microsoft Outlook Calendar FreeBusy
        if MicrosoftCalendarProvider.is_connected(session):
            try:
                ms_busy = MicrosoftCalendarProvider.get_busy_intervals(session, start_utc, end_utc)
                all_intervals.extend(ms_busy)
            except Exception as exc:
                if require_both_calendars:
                    raise AvailabilityServiceError(
                        f"Microsoft Outlook availability is unavailable: {exc}", status_code=502
                    ) from exc
        elif require_both_calendars and getattr(settings, "microsoft_organizer_email", None) and settings.microsoft_organizer_email.strip():
            raise AvailabilityServiceError(
                "Microsoft Outlook organizer account is configured but not connected.", status_code=502
            )

        # 3. Active pending database reservations
        reservations = session.scalars(
            select(BookingReservation).where(
                and_(
                    BookingReservation.booking_profile_id == profile.id,
                    BookingReservation.status == "pending",
                    BookingReservation.expires_at > now_utc,
                    BookingReservation.start_time < end_utc,
                    BookingReservation.end_time > start_utc,
                )
            )
        ).all()
        for res in reservations:
            all_intervals.append((res.start_time, res.end_time))

        # 4. Confirmed Bookings
        confirmed_bookings = session.scalars(
            select(Booking).where(
                and_(
                    Booking.booking_profile_id == profile.id,
                    Booking.status == "confirmed",
                    Booking.start_time < end_utc,
                    Booking.end_time > start_utc,
                )
            )
        ).all()
        for b in confirmed_bookings:
            all_intervals.append((b.start_time, b.end_time))

        return merge_intervals(all_intervals)

    @staticmethod
    def get_daily_meeting_counts(
        session: Session,
        profile: BookingProfile,
        start_date: date,
        end_date: date,
    ) -> dict[date, int]:
        """Count confirmed meetings per calendar date in profile timezone."""
        try:
            profile_tz = ZoneInfo(profile.timezone or "Asia/Kolkata")
        except (ZoneInfoNotFoundError, ValueError):
            profile_tz = ZoneInfo("Asia/Kolkata")

        # Range query
        query_start = datetime.combine(start_date, datetime.min.time(), tzinfo=profile_tz).astimezone(timezone.utc)
        query_end = datetime.combine(end_date, datetime.max.time(), tzinfo=profile_tz).astimezone(timezone.utc)

        bookings = session.scalars(
            select(Booking).where(
                and_(
                    Booking.booking_profile_id == profile.id,
                    Booking.status == "confirmed",
                    Booking.start_time >= query_start,
                    Booking.start_time <= query_end,
                )
            )
        ).all()

        counts: dict[date, int] = {}
        for b in bookings:
            local_dt = normalize_utc(b.start_time).astimezone(profile_tz)
            d = local_dt.date()
            counts[d] = counts.get(d, 0) + 1

        return counts

    @staticmethod
    def get_available_slots(
        session: Session,
        profile: BookingProfile,
        target_timezone_str: str,
        start_dt: datetime,
        end_dt: datetime,
        require_both_calendars: bool = True,
        duration_minutes: int | None = None,
    ) -> AvailabilityResponse:
        """Calculate and return available slots for the customer."""
        busy_intervals = AvailabilityService.get_busy_intervals(
            session=session,
            profile=profile,
            start_time=start_dt,
            end_time=end_dt,
            require_both_calendars=require_both_calendars,
        )

        try:
            profile_tz = ZoneInfo(profile.timezone or "Asia/Kolkata")
        except Exception:
            profile_tz = ZoneInfo("Asia/Kolkata")

        start_date = start_dt.astimezone(profile_tz).date()
        end_date = end_dt.astimezone(profile_tz).date()

        daily_counts = AvailabilityService.get_daily_meeting_counts(
            session, profile, start_date, end_date
        )

        slots = generate_available_slots(
            profile=profile,
            target_timezone_str=target_timezone_str,
            range_start=start_dt,
            range_end=end_dt,
            busy_intervals=busy_intervals,
            daily_meeting_counts=daily_counts,
            duration_minutes=duration_minutes,
        )

        effective_duration = duration_minutes if (duration_minutes and duration_minutes >= 10) else profile.duration_minutes

        return AvailabilityResponse(
            profile_slug=profile.public_slug,
            timezone=target_timezone_str,
            duration_minutes=effective_duration,
            slots=slots,
        )
