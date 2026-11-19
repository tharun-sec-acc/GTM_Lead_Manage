import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingProfile, BookingReservation
from app.booking.services.availability_service import (
    AvailabilityService,
    AvailabilityServiceError,
)
from app.booking.services.slot_generator import normalize_utc


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class ReservationConflictError(Exception):
    def __init__(self, message: str = "The selected time slot is no longer available."):
        super().__init__(message)
        self.message = message


class ReservationExpiredError(Exception):
    def __init__(self, message: str = "Reservation hold has expired. Please select a slot again."):
        super().__init__(message)
        self.message = message


class ReservationService:
    @staticmethod
    def create_reservation(
        session: Session,
        profile: BookingProfile,
        start_time: datetime,
        end_time: datetime,
        timezone_str: str = "UTC",
        require_both_calendars: bool = True,
    ) -> tuple[str, datetime]:
        start_utc = normalize_utc(start_time)
        end_utc = normalize_utc(end_time)
        now_utc = datetime.now(timezone.utc)

        if end_utc <= start_utc:
            raise ValueError("End time must be after start time.")

        # Check minimum notice and horizon
        notice_cutoff = now_utc + timedelta(minutes=profile.minimum_notice_minutes)
        horizon_cutoff = now_utc + timedelta(days=profile.booking_horizon_days)

        if start_utc < notice_cutoff:
            raise ReservationConflictError("Selected slot does not satisfy the minimum notice requirement.")
        if start_utc > horizon_cutoff:
            raise ReservationConflictError("Selected slot exceeds the booking horizon.")

        # Check buffers against existing busy intervals
        buffer_before = timedelta(minutes=profile.buffer_before_minutes)
        buffer_after = timedelta(minutes=profile.buffer_after_minutes)

        blocked_start = start_utc - buffer_before
        blocked_end = end_utc + buffer_after

        # Fetch busy intervals
        busy_intervals = AvailabilityService.get_busy_intervals(
            session=session,
            profile=profile,
            start_time=blocked_start,
            end_time=blocked_end,
            require_both_calendars=require_both_calendars,
        )

        for b_start, b_end in busy_intervals:
            b_start_utc = normalize_utc(b_start)
            b_end_utc = normalize_utc(b_end)
            if max(blocked_start, b_start_utc) < min(blocked_end, b_end_utc):
                raise ReservationConflictError("The selected time slot is already booked or conflicts with existing events.")

        # Generate cryptographic token
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        expires_at = now_utc + timedelta(minutes=10)

        reservation = BookingReservation(
            booking_profile_id=profile.id,
            start_time=start_utc,
            end_time=end_utc,
            reservation_token_hash=token_hash,
            status="pending",
            expires_at=expires_at,
        )
        session.add(reservation)
        session.commit()

        return raw_token, expires_at

    @staticmethod
    def get_valid_reservation(
        session: Session,
        profile_id: str,
        raw_token: str,
    ) -> BookingReservation:
        token_hash = hash_token(raw_token)
        now_utc = datetime.now(timezone.utc)

        reservation = session.scalar(
            select(BookingReservation).where(
                and_(
                    BookingReservation.booking_profile_id == profile_id,
                    BookingReservation.reservation_token_hash == token_hash,
                )
            )
        )

        if not reservation:
            raise ReservationExpiredError("Reservation not found.")

        if reservation.status != "pending":
            raise ReservationExpiredError(f"Reservation is already {reservation.status}.")

        if normalize_utc(reservation.expires_at) <= now_utc:
            reservation.status = "expired"
            session.commit()
            raise ReservationExpiredError("Reservation hold has expired.")

        return reservation

    @staticmethod
    def release_reservation(session: Session, reservation: BookingReservation) -> None:
        reservation.status = "released"
        session.commit()

    @staticmethod
    def cleanup_expired(session: Session) -> int:
        now_utc = datetime.now(timezone.utc)
        result = session.execute(
            update(BookingReservation)
            .where(
                and_(
                    BookingReservation.status == "pending",
                    BookingReservation.expires_at <= now_utc,
                )
            )
            .values(status="expired")
        )
        session.commit()
        return result.rowcount
