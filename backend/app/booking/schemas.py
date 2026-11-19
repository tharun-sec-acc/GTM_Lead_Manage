from datetime import datetime
from typing import Any
from pydantic import BaseModel, EmailStr, Field, field_validator


class WeekdayAvailabilitySchema(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0=Monday ... 6=Sunday")
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$", default="09:00")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$", default="17:00")
    is_enabled: bool = True


class BookingProfileCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=255)
    public_slug: str | None = Field(default=None, max_length=100)
    description: str | None = None
    company_name: str = Field(default="DENSO", max_length=255)
    meeting_title: str = Field(default="DENSO Solutions Discovery Call", max_length=255)
    meeting_description: str | None = None
    duration_minutes: int = Field(default=30, ge=10, le=240)
    buffer_before_minutes: int = Field(default=10, ge=0, le=60)
    buffer_after_minutes: int = Field(default=10, ge=0, le=60)
    minimum_notice_minutes: int = Field(default=120, ge=0, le=1440)
    booking_horizon_days: int = Field(default=30, ge=1, le=90)
    max_meetings_per_day: int = Field(default=8, ge=1, le=50)
    timezone: str = Field(default="Asia/Kolkata", max_length=64)
    availabilities: list[WeekdayAvailabilitySchema] | None = None


class BookingProfileUpdate(BaseModel):
    display_name: str | None = None
    public_slug: str | None = None
    description: str | None = None
    company_name: str | None = None
    meeting_title: str | None = None
    meeting_description: str | None = None
    duration_minutes: int | None = None
    buffer_before_minutes: int | None = None
    buffer_after_minutes: int | None = None
    minimum_notice_minutes: int | None = None
    booking_horizon_days: int | None = None
    max_meetings_per_day: int | None = None
    timezone: str | None = None
    is_active: bool | None = None
    availabilities: list[WeekdayAvailabilitySchema] | None = None


class BookingProfileResponse(BaseModel):
    id: str
    owner_user_id: str | None
    public_slug: str
    public_url: str
    display_name: str
    description: str | None
    company_name: str
    meeting_title: str
    meeting_description: str | None
    default_provider: str
    duration_minutes: int
    buffer_before_minutes: int
    buffer_after_minutes: int
    minimum_notice_minutes: int
    booking_horizon_days: int
    max_meetings_per_day: int
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    availabilities: list[WeekdayAvailabilitySchema]


class PublicBookingProfileResponse(BaseModel):
    public_slug: str
    display_name: str
    description: str | None
    company_name: str
    meeting_title: str
    meeting_description: str | None
    duration_minutes: int
    timezone: str
    booking_horizon_days: int
    minimum_notice_minutes: int


class SlotItem(BaseModel):
    start: str  # ISO string in customer requested timezone
    end: str    # ISO string in customer requested timezone
    utc_start: str
    utc_end: str


class AvailabilityResponse(BaseModel):
    profile_slug: str
    timezone: str
    duration_minutes: int
    slots: list[SlotItem]


class ReservationRequest(BaseModel):
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"


class ReservationResponse(BaseModel):
    reservation_token: str
    expires_at: datetime
    start_time: datetime
    end_time: datetime


class BookingConfirmRequest(BaseModel):
    reservation_token: str
    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: EmailStr
    customer_company: str | None = None
    customer_phone: str | None = None
    meeting_purpose: str | None = None
    timezone: str = "UTC"
    idempotency_key: str | None = None


class BookingPublicDetails(BaseModel):
    id: str
    customer_name: str
    customer_email: str
    customer_company: str | None
    meeting_title: str
    meeting_description: str | None
    start_time: str
    end_time: str
    timezone: str
    google_meet_uri: str | None
    status: str
    created_at: str
    management_token: str | None = None
    reschedule_url: str | None = None
    cancellation_url: str | None = None


class RescheduleRequest(BaseModel):
    new_start_time: datetime
    new_end_time: datetime
    timezone: str = "UTC"
    reason: str | None = None


class CancellationRequest(BaseModel):
    reason: str | None = None


class CalendarConnectionStatus(BaseModel):
    google_calendar: dict[str, Any]
    microsoft_outlook: dict[str, Any]
    google_meet_ready: bool
    can_accept_bookings: bool
    message: str
