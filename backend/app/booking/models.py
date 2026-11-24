from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class BookingProfile(Base):
    __tablename__ = "booking_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    public_slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_name: Mapped[str] = mapped_column(String(255), default="DENSO")
    meeting_title: Mapped[str] = mapped_column(String(255), default="DENSO Solutions Discovery Call")
    meeting_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_provider: Mapped[str] = mapped_column(String(32), default="google_meet")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    buffer_before_minutes: Mapped[int] = mapped_column(Integer, default=10)
    buffer_after_minutes: Mapped[int] = mapped_column(Integer, default=10)
    minimum_notice_minutes: Mapped[int] = mapped_column(Integer, default=120)
    booking_horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    max_meetings_per_day: Mapped[int] = mapped_column(Integer, default=8)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    # Relationships
    availabilities: Mapped[list["BookingAvailability"]] = relationship(
        "BookingAvailability",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="BookingAvailability.weekday",
    )
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking",
        back_populates="profile",
        cascade="all, delete-orphan",
        order_by="Booking.start_time.desc()",
    )
    reservations: Mapped[list["BookingReservation"]] = relationship(
        "BookingReservation",
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class BookingAvailability(Base):
    __tablename__ = "booking_availabilities"
    __table_args__ = (
        UniqueConstraint("booking_profile_id", "weekday", name="uq_profile_weekday"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_profile_id: Mapped[str] = mapped_column(
        ForeignKey("booking_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday .. 6=Sunday
    start_time: Mapped[str] = mapped_column(String(8), nullable=False, default="09:00")
    end_time: Mapped[str] = mapped_column(String(8), nullable=False, default="17:00")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    profile: Mapped["BookingProfile"] = relationship("BookingProfile", back_populates="availabilities")


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_profile_id: Mapped[str] = mapped_column(
        ForeignKey("booking_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meeting_id: Mapped[str | None] = mapped_column(
        ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    lead_id: Mapped[str | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[str | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="google_meet")

    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    customer_company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meeting_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    google_calendar_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    google_meet_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="confirmed", index=True)  # confirmed, cancelled, rescheduled

    cancellation_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    reschedule_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    profile: Mapped["BookingProfile"] = relationship("BookingProfile", back_populates="bookings")
    logs: Mapped[list["BookingEventLog"]] = relationship(
        "BookingEventLog", back_populates="booking", cascade="all, delete-orphan", order_by="BookingEventLog.created_at"
    )


class BookingReservation(Base):
    __tablename__ = "booking_reservations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_profile_id: Mapped[str] = mapped_column(
        ForeignKey("booking_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reservation_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)  # pending, confirmed, expired, released
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    profile: Mapped["BookingProfile"] = relationship("BookingProfile", back_populates="reservations")


class BookingEventLog(Base):
    __tablename__ = "booking_event_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    booking_id: Mapped[str | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="google_meet")
    provider_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="success")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    booking: Mapped["Booking | None"] = relationship("Booking", back_populates="logs")
