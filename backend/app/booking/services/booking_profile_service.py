import re
import secrets
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.booking.models import BookingAvailability, BookingProfile
from app.booking.schemas import (
    BookingProfileCreate,
    BookingProfileUpdate,
    WeekdayAvailabilitySchema,
)


def slugify(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or secrets.token_hex(4)


def ensure_unique_slug(session: Session, base_slug: str, exclude_id: str | None = None) -> str:
    slug = base_slug
    counter = 1
    while True:
        query = select(BookingProfile).where(BookingProfile.public_slug == slug)
        if exclude_id:
            query = query.where(BookingProfile.id != exclude_id)
        existing = session.scalar(query)
        if not existing:
            return slug
        counter += 1
        slug = f"{base_slug}-{counter}"


class BookingProfileService:
    @staticmethod
    def get_by_id(session: Session, profile_id: str) -> BookingProfile | None:
        return session.get(BookingProfile, profile_id)

    @staticmethod
    def get_by_slug(session: Session, slug: str) -> BookingProfile | None:
        return session.scalar(select(BookingProfile).where(BookingProfile.public_slug == slug))

    @staticmethod
    def list_all(session: Session) -> list[BookingProfile]:
        return list(
            session.scalars(
                select(BookingProfile).order_by(BookingProfile.created_at.desc())
            ).all()
        )

    @staticmethod
    def create_profile(
        session: Session,
        data: BookingProfileCreate,
        owner_user_id: str | None = None,
    ) -> BookingProfile:
        raw_slug = data.public_slug or slugify(data.display_name)
        slug = ensure_unique_slug(session, raw_slug)

        profile = BookingProfile(
            owner_user_id=owner_user_id,
            public_slug=slug,
            display_name=data.display_name,
            description=data.description,
            company_name=data.company_name or "DENSO",
            meeting_title=data.meeting_title or "DENSO Solutions Discovery Call",
            meeting_description=data.meeting_description,
            duration_minutes=data.duration_minutes,
            buffer_before_minutes=data.buffer_before_minutes,
            buffer_after_minutes=data.buffer_after_minutes,
            minimum_notice_minutes=data.minimum_notice_minutes,
            booking_horizon_days=data.booking_horizon_days,
            max_meetings_per_day=data.max_meetings_per_day,
            timezone=data.timezone or "Asia/Kolkata",
            is_active=True,
        )
        session.add(profile)
        session.flush()

        # Add availabilities (default Monday-Friday 09:00 - 17:00 if omitted)
        availabilities = data.availabilities
        if availabilities is None or len(availabilities) == 0:
            availabilities = [
                WeekdayAvailabilitySchema(
                    weekday=day,
                    start_time="09:00",
                    end_time="17:00",
                    is_enabled=True,
                )
                for day in range(5)  # 0 to 4 (Mon to Fri)
            ]

        for item in availabilities:
            avail = BookingAvailability(
                booking_profile_id=profile.id,
                weekday=item.weekday,
                start_time=item.start_time,
                end_time=item.end_time,
                is_enabled=item.is_enabled,
            )
            session.add(avail)

        session.commit()
        session.refresh(profile)
        return profile

    @staticmethod
    def update_profile(
        session: Session,
        profile_id: str,
        data: BookingProfileUpdate,
    ) -> BookingProfile:
        profile = session.get(BookingProfile, profile_id)
        if not profile:
            raise ValueError(f"Booking profile {profile_id} not found.")

        if data.public_slug and data.public_slug != profile.public_slug:
            profile.public_slug = ensure_unique_slug(session, slugify(data.public_slug), exclude_id=profile.id)

        if data.display_name is not None:
            profile.display_name = data.display_name
        if data.description is not None:
            profile.description = data.description
        if data.company_name is not None:
            profile.company_name = data.company_name
        if data.meeting_title is not None:
            profile.meeting_title = data.meeting_title
        if data.meeting_description is not None:
            profile.meeting_description = data.meeting_description
        if data.duration_minutes is not None:
            profile.duration_minutes = data.duration_minutes
        if data.buffer_before_minutes is not None:
            profile.buffer_before_minutes = data.buffer_before_minutes
        if data.buffer_after_minutes is not None:
            profile.buffer_after_minutes = data.buffer_after_minutes
        if data.minimum_notice_minutes is not None:
            profile.minimum_notice_minutes = data.minimum_notice_minutes
        if data.booking_horizon_days is not None:
            profile.booking_horizon_days = data.booking_horizon_days
        if data.max_meetings_per_day is not None:
            profile.max_meetings_per_day = data.max_meetings_per_day
        if data.timezone is not None:
            profile.timezone = data.timezone
        if data.is_active is not None:
            profile.is_active = data.is_active

        if data.availabilities is not None:
            # Delete old availabilities
            for old_av in list(profile.availabilities):
                session.delete(old_av)
            session.flush()

            for item in data.availabilities:
                avail = BookingAvailability(
                    booking_profile_id=profile.id,
                    weekday=item.weekday,
                    start_time=item.start_time,
                    end_time=item.end_time,
                    is_enabled=item.is_enabled,
                )
                session.add(avail)

        session.commit()
        session.refresh(profile)
        return profile

    @staticmethod
    def set_active(session: Session, profile_id: str, is_active: bool) -> BookingProfile:
        profile = session.get(BookingProfile, profile_id)
        if not profile:
            raise ValueError(f"Booking profile {profile_id} not found.")
        profile.is_active = is_active
        session.commit()
        session.refresh(profile)
        return profile

    @staticmethod
    def get_or_create_default(session: Session) -> BookingProfile:
        default_slug = "denso-discovery"
        existing = session.scalar(
            select(BookingProfile).where(BookingProfile.public_slug == default_slug)
        )
        if existing:
            return existing

        # If any profile exists, return the first one
        any_profile = session.scalar(select(BookingProfile).order_by(BookingProfile.created_at.asc()))
        if any_profile:
            return any_profile

        return BookingProfileService.create_profile(
            session,
            BookingProfileCreate(
                display_name="DENSO Solutions Team",
                public_slug=default_slug,
                description="Schedule a 30-minute discovery call to discuss DENSO Industrial Solutions (IM, MCE, VDI, TWMS).",
                company_name="DENSO",
                meeting_title="DENSO Solutions Discovery Call",
                duration_minutes=30,
                buffer_before_minutes=10,
                buffer_after_minutes=10,
                minimum_notice_minutes=120,
                booking_horizon_days=30,
                max_meetings_per_day=8,
                timezone="Asia/Kolkata",
            ),
        )
