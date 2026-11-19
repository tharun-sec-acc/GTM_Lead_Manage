import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingProfile
from app.booking.providers.google_calendar_provider import GoogleCalendarProvider
from app.booking.providers.microsoft_calendar_provider import MicrosoftCalendarProvider
from app.booking.schemas import (
    AvailabilityResponse,
    BookingConfirmRequest,
    BookingProfileCreate,
    BookingProfileResponse,
    BookingProfileUpdate,
    BookingPublicDetails,
    CancellationRequest,
    PublicBookingProfileResponse,
    ReservationRequest,
    ReservationResponse,
    RescheduleRequest,
    WeekdayAvailabilitySchema,
)
from app.booking.services.availability_service import (
    AvailabilityService,
    AvailabilityServiceError,
)
from app.booking.services.booking_profile_service import BookingProfileService
from app.booking.services.booking_service import BookingService
from app.booking.services.cancellation_service import CancellationService
from app.booking.services.reschedule_service import RescheduleService
from app.booking.services.reservation_service import (
    ReservationConflictError,
    ReservationExpiredError,
    ReservationService,
)
from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


def _format_profile_response(profile: BookingProfile) -> BookingProfileResponse:
    return BookingProfileResponse(
        id=profile.id,
        owner_user_id=profile.owner_user_id,
        public_slug=profile.public_slug,
        public_url=f"/book/{profile.public_slug}",
        display_name=profile.display_name,
        description=profile.description,
        company_name=profile.company_name,
        meeting_title=profile.meeting_title,
        meeting_description=profile.meeting_description,
        default_provider=profile.default_provider,
        duration_minutes=profile.duration_minutes,
        buffer_before_minutes=profile.buffer_before_minutes,
        buffer_after_minutes=profile.buffer_after_minutes,
        minimum_notice_minutes=profile.minimum_notice_minutes,
        booking_horizon_days=profile.booking_horizon_days,
        max_meetings_per_day=profile.max_meetings_per_day,
        timezone=profile.timezone,
        is_active=profile.is_active,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        availabilities=[
            WeekdayAvailabilitySchema(
                weekday=av.weekday,
                start_time=av.start_time,
                end_time=av.end_time,
                is_enabled=av.is_enabled,
            )
            for av in (profile.availabilities or [])
        ],
    )


def _format_booking_public_details(
    booking: Booking,
    token: str | None = None,
) -> BookingPublicDetails:
    return BookingPublicDetails(
        id=booking.id,
        customer_name=booking.customer_name,
        customer_email=booking.customer_email,
        customer_company=booking.customer_company,
        meeting_title=booking.profile.meeting_title if booking.profile else "DENSO Discovery Call",
        meeting_description=booking.profile.meeting_description if booking.profile else None,
        start_time=booking.start_time.isoformat(),
        end_time=booking.end_time.isoformat(),
        timezone=booking.timezone,
        google_meet_uri=booking.google_meet_uri,
        status=booking.status,
        created_at=booking.created_at.isoformat(),
        management_token=token,
        reschedule_url=f"/book/manage/{token}" if token else None,
        cancellation_url=f"/book/manage/{token}" if token else None,
    )


# -----------------------------------------------------------------------------
# PUBLIC ENDPOINTS (No Auth Required)
# -----------------------------------------------------------------------------

@router.get("/public/book/{slug}", response_model=PublicBookingProfileResponse)
def get_public_booking_profile(slug: str, session: Session = Depends(get_db)):
    """Retrieve public booking profile information by slug."""
    profile = BookingProfileService.get_by_slug(session, slug)
    if not profile or not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking page not found or is currently inactive.",
        )
    return PublicBookingProfileResponse(
        public_slug=profile.public_slug,
        display_name=profile.display_name,
        description=profile.description,
        company_name=profile.company_name,
        meeting_title=profile.meeting_title,
        meeting_description=profile.meeting_description,
        duration_minutes=profile.duration_minutes,
        timezone=profile.timezone,
        booking_horizon_days=profile.booking_horizon_days,
        minimum_notice_minutes=profile.minimum_notice_minutes,
    )


@router.get("/public/book/{slug}/availability", response_model=AvailabilityResponse)
def get_public_availability(
    slug: str,
    start: str = Query(..., description="Start date/time (ISO format or YYYY-MM-DD)"),
    end: str = Query(..., description="End date/time (ISO format or YYYY-MM-DD)"),
    timezone_param: str | None = Query(None, alias="timezone", description="Customer timezone"),
    session: Session = Depends(get_db),
):
    """Calculate combined free slots aggregating Google and Outlook calendars."""
    profile = BookingProfileService.get_by_slug(session, slug)
    if not profile or not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking page not found or is currently inactive.",
        )

    target_tz = timezone_param or profile.timezone or "Asia/Kolkata"
    try:
        tz_obj = ZoneInfo(target_tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {target_tz}",
        ) from exc

    # Parse dates
    try:
        if "T" in start:
            start_dt = datetime.fromisoformat(start)
        else:
            start_date = datetime.strptime(start, "%Y-%m-%d").date()
            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=tz_obj)

        if "T" in end:
            end_dt = datetime.fromisoformat(end)
        else:
            end_date = datetime.strptime(end, "%Y-%m-%d").date()
            end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=tz_obj)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use ISO format or YYYY-MM-DD.",
        ) from exc

    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=tz_obj)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=tz_obj)

    try:
        return AvailabilityService.get_available_slots(
            session=session,
            profile=profile,
            target_timezone_str=target_tz,
            start_dt=start_dt,
            end_dt=end_dt,
        )
    except AvailabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except Exception as exc:
        logger.exception("Error calculating availability for %s", slug)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not calculate calendar availability: {exc}",
        ) from exc


@router.post("/public/book/{slug}/reserve", response_model=ReservationResponse)
def reserve_slot(
    slug: str,
    data: ReservationRequest,
    session: Session = Depends(get_db),
):
    """Place a 10-minute temporary reservation hold on a slot to prevent double-booking."""
    profile = BookingProfileService.get_by_slug(session, slug)
    if not profile or not profile.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking page not found or is currently inactive.",
        )

    try:
        token, expires_at = ReservationService.create_reservation(
            session=session,
            profile=profile,
            start_time=data.start_time,
            end_time=data.end_time,
            timezone_str=data.timezone,
        )
        return ReservationResponse(
            reservation_token=token,
            expires_at=expires_at,
            start_time=data.start_time,
            end_time=data.end_time,
        )
    except ReservationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except AvailabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/public/book/{slug}/confirm", response_model=BookingPublicDetails)
def confirm_booking(
    slug: str,
    data: BookingConfirmRequest,
    session: Session = Depends(get_db),
):
    """Confirm appointment: validates reservation, creates Google Calendar event with Meet, links CRM."""
    try:
        booking, canc_token, resched_token = BookingService.confirm_booking(
            session=session,
            profile_slug=slug,
            data=data,
        )
        # Use reschedule token as primary management token
        token = resched_token or canc_token
        return _format_booking_public_details(booking, token)
    except ReservationExpiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=exc.message,
        ) from exc
    except ReservationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.message,
        ) from exc
    except AvailabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Error confirming booking for %s", slug)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not confirm booking: {exc}",
        ) from exc


@router.get("/public/bookings/{secure_token}", response_model=BookingPublicDetails)
def get_booking_by_token(secure_token: str, session: Session = Depends(get_db)):
    """Retrieve booking details using the secure self-service token."""
    booking = RescheduleService.get_by_token(session, secure_token)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found or invalid token.",
        )
    return _format_booking_public_details(booking, secure_token)


@router.post("/public/bookings/{secure_token}/reschedule", response_model=BookingPublicDetails)
def reschedule_booking(
    secure_token: str,
    data: RescheduleRequest,
    session: Session = Depends(get_db),
):
    """Reschedule an existing booking to a new time."""
    try:
        booking = RescheduleService.reschedule_booking(
            session=session,
            raw_token=secure_token,
            new_start=data.new_start_time,
            new_end=data.new_end_time,
            timezone_str=data.timezone,
            reason=data.reason,
        )
        return _format_booking_public_details(booking, secure_token)
    except AvailabilityServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/public/bookings/{secure_token}/cancel", response_model=BookingPublicDetails)
def cancel_booking(
    secure_token: str,
    data: CancellationRequest,
    session: Session = Depends(get_db),
):
    """Cancel an existing booking."""
    try:
        booking = CancellationService.cancel_booking(
            session=session,
            raw_token=secure_token,
            reason=data.reason,
        )
        return _format_booking_public_details(booking, secure_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# -----------------------------------------------------------------------------
# AUTHENTICATED / INTERNAL ENDPOINTS
# -----------------------------------------------------------------------------

@router.get("/bookings/profiles", response_model=list[BookingProfileResponse])
def list_booking_profiles(session: Session = Depends(get_db)):
    """List all booking profiles."""
    profiles = BookingProfileService.list_all(session)
    if not profiles:
        # Seed default profile if none exists
        default_profile = BookingProfileService.get_or_create_default(session)
        profiles = [default_profile]
    return [_format_profile_response(p) for p in profiles]


@router.post("/bookings/profiles", response_model=BookingProfileResponse, status_code=status.HTTP_201_CREATED)
def create_booking_profile(
    data: BookingProfileCreate,
    session: Session = Depends(get_db),
):
    """Create a new booking profile."""
    profile = BookingProfileService.create_profile(session, data)
    return _format_profile_response(profile)


@router.get("/bookings/profiles/{profile_id}", response_model=BookingProfileResponse)
def get_booking_profile(profile_id: str, session: Session = Depends(get_db)):
    """Get single booking profile by ID."""
    profile = BookingProfileService.get_by_id(session, profile_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking profile not found.",
        )
    return _format_profile_response(profile)


@router.patch("/bookings/profiles/{profile_id}", response_model=BookingProfileResponse)
def update_booking_profile(
    profile_id: str,
    data: BookingProfileUpdate,
    session: Session = Depends(get_db),
):
    """Update booking profile settings, working hours, and buffers."""
    try:
        profile = BookingProfileService.update_profile(session, profile_id, data)
        return _format_profile_response(profile)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/bookings/profiles/{profile_id}/activate", response_model=BookingProfileResponse)
def activate_booking_profile(profile_id: str, session: Session = Depends(get_db)):
    """Activate a booking profile."""
    try:
        profile = BookingProfileService.set_active(session, profile_id, True)
        return _format_profile_response(profile)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post("/bookings/profiles/{profile_id}/deactivate", response_model=BookingProfileResponse)
def deactivate_booking_profile(profile_id: str, session: Session = Depends(get_db)):
    """Deactivate a booking profile."""
    try:
        profile = BookingProfileService.set_active(session, profile_id, False)
        return _format_profile_response(profile)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/bookings/calendar-connections")
def get_calendar_connections_status(session: Session = Depends(get_db)):
    """Status of Google Calendar and Microsoft Outlook connections."""
    status_info = AvailabilityService.check_calendar_connections(session)
    return {
        **status_info,
        "google_organizer": settings.google_workspace_organizer_email,
        "microsoft_organizer": settings.microsoft_organizer_email,
        "default_provider": "google_meet",
    }


@router.get("/bookings")
def list_bookings(
    profile_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    session: Session = Depends(get_db),
):
    """List bookings with filters."""
    bookings = BookingService.list_bookings(
        session, profile_id=profile_id, status=status_filter
    )
    return [
        {
            "id": b.id,
            "profile_slug": b.profile.public_slug if b.profile else None,
            "profile_title": b.profile.display_name if b.profile else None,
            "customer_name": b.customer_name,
            "customer_email": b.customer_email,
            "customer_company": b.customer_company,
            "customer_phone": b.customer_phone,
            "meeting_purpose": b.meeting_purpose,
            "start_time": b.start_time.isoformat(),
            "end_time": b.end_time.isoformat(),
            "timezone": b.timezone,
            "google_calendar_event_id": b.google_calendar_event_id,
            "google_meet_uri": b.google_meet_uri,
            "status": b.status,
            "lead_id": b.lead_id,
            "meeting_id": b.meeting_id,
            "created_at": b.created_at.isoformat(),
        }
        for b in bookings
    ]


@router.get("/bookings/{booking_id}")
def get_booking_details(booking_id: str, session: Session = Depends(get_db)):
    """Get single booking details with audit logs."""
    booking = BookingService.get_by_id(session, booking_id)
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )
    return {
        "id": booking.id,
        "profile_id": booking.booking_profile_id,
        "profile_slug": booking.profile.public_slug if booking.profile else None,
        "customer_name": booking.customer_name,
        "customer_email": booking.customer_email,
        "customer_company": booking.customer_company,
        "customer_phone": booking.customer_phone,
        "meeting_purpose": booking.meeting_purpose,
        "start_time": booking.start_time.isoformat(),
        "end_time": booking.end_time.isoformat(),
        "timezone": booking.timezone,
        "google_calendar_event_id": booking.google_calendar_event_id,
        "google_meet_uri": booking.google_meet_uri,
        "status": booking.status,
        "lead_id": booking.lead_id,
        "meeting_id": booking.meeting_id,
        "created_at": booking.created_at.isoformat(),
        "logs": [
            {
                "id": log.id,
                "event_type": log.event_type,
                "provider": log.provider,
                "status": log.status,
                "details": log.details,
                "created_at": log.created_at.isoformat(),
            }
            for log in booking.logs
        ],
    }
