import pytest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient

from app.booking.models import (
    Booking,
    BookingAvailability,
    BookingProfile,
    BookingReservation,
)
from app.booking.providers.google_calendar_provider import GoogleCalendarProvider
from app.booking.providers.microsoft_calendar_provider import MicrosoftCalendarProvider
from app.booking.schemas import WeekdayAvailabilitySchema
from app.booking.services.availability_service import (
    AvailabilityService,
    AvailabilityServiceError,
    merge_intervals,
)
from app.booking.services.booking_profile_service import BookingProfileService
from app.booking.services.booking_service import BookingService
from app.booking.services.cancellation_service import CancellationService
from app.booking.services.reschedule_service import RescheduleService
from app.booking.services.reservation_service import (
    ReservationConflictError,
    ReservationExpiredError,
    ReservationService,
    hash_token,
)
from app.booking.services.slot_generator import generate_available_slots, normalize_utc
from app.database import Base, get_db
from app.main import app
from app.models import Contact, GoogleOAuthCredential, Lead, MicrosoftOAuthCredential


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    db_path = tmp_path / "booking_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override

    with TestClient(app, base_url="http://localhost:8000") as test_client:
        yield test_client, factory

    app.dependency_overrides.clear()
    engine.dispose()


def test_merge_intervals():
    t0 = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 11, 20, 11, 30, tzinfo=timezone.utc)

    # Overlapping
    intervals = [(t0, t2), (t1, t3)]
    merged = merge_intervals(intervals)
    assert len(merged) == 1
    assert merged[0] == (t0, t3)

    # Disjoint
    t4 = datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc)
    t5 = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
    merged2 = merge_intervals([(t0, t1), (t4, t5)])
    assert len(merged2) == 2
    assert merged2[0] == (t0, t1)
    assert merged2[1] == (t4, t5)


def test_booking_profile_service(workspace):
    _, factory = workspace
    with factory() as session:
        # 1. Seeds default profile if empty
        profiles = BookingProfileService.list_all(session)
        assert len(profiles) == 0

        default_prof = BookingProfileService.get_or_create_default(session)
        assert default_prof.public_slug == "denso-discovery"
        assert default_prof.is_active is True
        assert len(default_prof.availabilities) == 5  # Mon-Fri

        # 2. Lookup by slug
        found = BookingProfileService.get_by_slug(session, "denso-discovery")
        assert found is not None
        assert found.id == default_prof.id

        # 3. Slug collision handling
        p2 = BookingProfileService.create_profile(
            session,
            data=type("BookingProfileCreate", (), {
                "display_name": "DENSO Solutions Team",
                "public_slug": "denso-discovery",
                "description": "Another profile",
                "company_name": "DENSO",
                "meeting_title": "Discovery 2",
                "meeting_description": None,
                "duration_minutes": 45,
                "buffer_before_minutes": 15,
                "buffer_after_minutes": 15,
                "minimum_notice_minutes": 60,
                "booking_horizon_days": 14,
                "max_meetings_per_day": 5,
                "timezone": "UTC",
                "availabilities": None,
            })(),
        )
        assert p2.public_slug == "denso-discovery-2"
        assert p2.duration_minutes == 45


def test_slot_generator():
    profile = BookingProfile(
        id="prof-1",
        public_slug="test-slug",
        display_name="Test Profile",
        duration_minutes=30,
        buffer_before_minutes=10,
        buffer_after_minutes=10,
        minimum_notice_minutes=0,
        booking_horizon_days=30,
        max_meetings_per_day=5,
        timezone="UTC",
        is_active=True,
    )
    # Weekday 4 is Friday
    profile.availabilities = [
        BookingAvailability(
            booking_profile_id="prof-1",
            weekday=4,
            start_time="09:00",
            end_time="12:00",
            is_enabled=True,
        )
    ]

    # Friday Nov 20, 2026
    range_start = datetime(2026, 11, 20, 0, 0, tzinfo=timezone.utc)
    range_end = datetime(2026, 11, 20, 23, 59, tzinfo=timezone.utc)
    now_utc = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)

    # Slot from 10:00 to 10:30 is busy
    busy_intervals = [
        (
            datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
            datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc),
        )
    ]

    slots = generate_available_slots(
        profile=profile,
        target_timezone_str="UTC",
        range_start=range_start,
        range_end=range_end,
        busy_intervals=busy_intervals,
        now_utc=now_utc,
    )

    utc_starts = [s.utc_start for s in slots]
    # 09:00 - 09:30 has buffer_after=10min (ends at 09:40) -> does not touch 10:00 -> available!
    # 09:30 - 10:00 has buffer_after=10min (ends at 10:10) -> overlaps 10:00-10:30 -> excluded!
    # 10:00 - 10:30 is directly busy -> excluded!
    # 10:30 - 11:00 has buffer_before=10min (starts at 10:20) -> overlaps 10:00-10:30 -> excluded!
    # 11:00 - 11:30 has buffer_before=10min (starts at 10:50) -> does not touch 10:30 -> available!
    # 11:30 - 12:00 -> available!

    assert "2026-11-20T09:00:00+00:00" in utc_starts
    assert "2026-11-20T09:30:00+00:00" not in utc_starts  # blocked by buffer after
    assert "2026-11-20T10:00:00+00:00" not in utc_starts  # busy
    assert "2026-11-20T10:30:00+00:00" not in utc_starts  # blocked by buffer before
    assert "2026-11-20T11:00:00+00:00" in utc_starts
    assert "2026-11-20T11:30:00+00:00" in utc_starts


def test_public_booking_flow(workspace, monkeypatch):
    client, factory = workspace

    # Mock Google & Outlook providers
    monkeypatch.setattr(
        GoogleCalendarProvider, "is_connected", lambda session: True
    )
    monkeypatch.setattr(
        MicrosoftCalendarProvider, "is_connected", lambda session: True
    )

    # Google FreeBusy returns busy 10:00-10:30
    monkeypatch.setattr(
        GoogleCalendarProvider,
        "get_busy_intervals",
        lambda session, s, e: [
            (
                datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
                datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc),
            )
        ],
    )
    # Microsoft Outlook returns busy 14:00-14:30
    monkeypatch.setattr(
        MicrosoftCalendarProvider,
        "get_busy_intervals",
        lambda session, s, e: [
            (
                datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc),
                datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc),
            )
        ],
    )

    # Calendar event creation mock
    monkeypatch.setattr(
        GoogleCalendarProvider,
        "create_calendar_event",
        lambda *args, **kwargs: (
            "google-cal-event-999",
            "https://meet.google.com/abc-defg-hij",
            {"status": "confirmed", "hangoutLink": "https://meet.google.com/abc-defg-hij"},
        ),
    )

    # Seed profile
    with factory() as session:
        prof = BookingProfile(
            id="prof-auto",
            public_slug="denso-sales",
            display_name="DENSO Industrial Automation",
            meeting_title="DENSO Solutions Discovery Call",
            meeting_description="Discuss TWMS and Inspection Management.",
            duration_minutes=30,
            buffer_before_minutes=0,
            buffer_after_minutes=0,
            minimum_notice_minutes=0,
            booking_horizon_days=30,
            max_meetings_per_day=8,
            timezone="UTC",
            is_active=True,
        )
        session.add(prof)
        session.flush()

        # Add Friday weekday availability
        session.add(
            BookingAvailability(
                booking_profile_id=prof.id,
                weekday=4,
                start_time="09:00",
                end_time="17:00",
                is_enabled=True,
            )
        )
        session.commit()

    # 1. GET Public Profile
    res = client.get("/api/public/book/denso-sales")
    assert res.status_code == 200
    pdata = res.json()
    assert pdata["public_slug"] == "denso-sales"
    assert pdata["display_name"] == "DENSO Industrial Automation"

    # 2. GET Availability
    res = client.get(
        "/api/public/book/denso-sales/availability",
        params={
            "start": "2026-11-20T00:00:00Z",
            "end": "2026-11-20T23:59:59Z",
            "timezone": "UTC",
        },
    )
    assert res.status_code == 200
    avail_data = res.json()
    slots = avail_data["slots"]
    utc_starts = [s["utc_start"] for s in slots]
    # Google busy at 10:00 must NOT be available
    assert "2026-11-20T10:00:00+00:00" not in utc_starts
    # Outlook busy at 14:00 must NOT be available
    assert "2026-11-20T14:00:00+00:00" not in utc_starts
    # 11:00 is free on both!
    assert "2026-11-20T11:00:00+00:00" in utc_starts

    # 3. POST Reserve Slot
    reserve_res = client.post(
        "/api/public/book/denso-sales/reserve",
        json={
            "start_time": "2026-11-20T11:00:00Z",
            "end_time": "2026-11-20T11:30:00Z",
            "timezone": "UTC",
        },
    )
    assert reserve_res.status_code == 200
    reservation = reserve_res.json()
    token = reservation["reservation_token"]
    assert token

    # 4. Attempt to reserve same slot concurrently -> Conflict 409
    dup_reserve = client.post(
        "/api/public/book/denso-sales/reserve",
        json={
            "start_time": "2026-11-20T11:00:00Z",
            "end_time": "2026-11-20T11:30:00Z",
            "timezone": "UTC",
        },
    )
    assert dup_reserve.status_code == 409

    # 5. Confirm Booking
    confirm_res = client.post(
        "/api/public/book/denso-sales/confirm",
        json={
            "reservation_token": token,
            "customer_name": "Arun Kumar",
            "customer_email": "arun.kumar@vrlgroup.in",
            "customer_company": "VRL Logistics",
            "customer_phone": "+91 9876543210",
            "meeting_purpose": "Fleet optimization and TWMS integration.",
            "timezone": "Asia/Kolkata",
            "idempotency_key": "booking-key-001",
        },
    )
    assert confirm_res.status_code == 200
    booking_data = confirm_res.json()
    assert booking_data["status"] == "confirmed"
    assert booking_data["google_meet_uri"] == "https://meet.google.com/abc-defg-hij"
    mgmt_token = booking_data["management_token"]
    assert mgmt_token

    # 6. Verify CRM integration (Lead & Contact & Meeting)
    with factory() as session:
        lead = session.scalar(select(Lead).where(Lead.company_name == "VRL Logistics"))
        assert lead is not None
        assert lead.extra.get("source") == "public_booking"

        contact = session.scalar(select(Contact).where(Contact.email == "arun.kumar@vrlgroup.in"))
        assert contact is not None
        assert contact.lead_id == lead.id
        assert contact.source == "public_booking"

        booking_rec = session.scalar(select(Booking).where(Booking.customer_email == "arun.kumar@vrlgroup.in"))
        assert booking_rec is not None
        assert booking_rec.lead_id == lead.id
        assert booking_rec.contact_id == contact.id
        assert booking_rec.meeting_id is not None
        assert booking_rec.google_calendar_event_id == "google-cal-event-999"

    # 7. Check Lead 360 profile timeline
    with factory() as session:
        lead_id = session.scalar(select(Lead.id).where(Lead.company_name == "VRL Logistics"))
    lead_prof_res = client.get(f"/leads/{lead_id}/profile")
    assert lead_prof_res.status_code == 200
    prof_json = lead_prof_res.json()
    timeline = prof_json.get("timeline", [])
    # Timeline should include public_booking event
    booking_events = [ev for ev in timeline if ev["type"] == "public_booking"]
    assert len(booking_events) >= 1
    assert "Arun Kumar" in booking_events[0]["summary"]

    # 8. Self-Service: Retrieve booking with management token
    get_book_res = client.get(f"/api/public/bookings/{mgmt_token}")
    assert get_book_res.status_code == 200
    assert get_book_res.json()["customer_email"] == "arun.kumar@vrlgroup.in"

    # 9. Self-Service: Reschedule booking
    monkeypatch.setattr(
        GoogleCalendarProvider,
        "update_calendar_event",
        lambda *args, **kwargs: {"updated": True},
    )
    resched_res = client.post(
        f"/api/public/bookings/{mgmt_token}/reschedule",
        json={
            "new_start_time": "2026-11-20T15:00:00Z",
            "new_end_time": "2026-11-20T15:30:00Z",
            "timezone": "Asia/Kolkata",
            "reason": "Schedule conflict with internal review.",
        },
    )
    assert resched_res.status_code == 200
    resched_data = resched_res.json()
    assert "2026-11-20T15:00:00" in resched_data["start_time"]

    # 10. Self-Service: Cancel booking
    monkeypatch.setattr(
        GoogleCalendarProvider,
        "delete_calendar_event",
        lambda *args, **kwargs: True,
    )
    cancel_res = client.post(
        f"/api/public/bookings/{mgmt_token}/cancel",
        json={"reason": "Completed discovery via email."},
    )
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["status"] == "cancelled"

    with factory() as session:
        cancelled_b = session.get(Booking, booking_data["id"])
        assert cancelled_b.status == "cancelled"


def test_calendar_failure_handling(workspace, monkeypatch):
    client, factory = workspace

    # When Google or Outlook fails, availability must reject with 502
    monkeypatch.setattr(GoogleCalendarProvider, "is_connected", lambda s: False)
    monkeypatch.setattr(MicrosoftCalendarProvider, "is_connected", lambda s: True)

    with factory() as session:
        prof = BookingProfile(
            id="prof-fail",
            public_slug="fail-slug",
            display_name="Fail Test",
            timezone="UTC",
            is_active=True,
        )
        session.add(prof)
        session.commit()

    res = client.get(
        "/api/public/book/fail-slug/availability",
        params={
            "start": "2026-11-20T00:00:00Z",
            "end": "2026-11-20T23:59:59Z",
        },
    )
    assert res.status_code == 502
    assert "Google Calendar" in res.json()["detail"]


def test_cleanup_expired_reservations(workspace):
    _, factory = workspace
    with factory() as session:
        prof = BookingProfile(
            id="prof-exp",
            public_slug="exp-slug",
            display_name="Expiration Test",
            timezone="UTC",
            is_active=True,
        )
        session.add(prof)
        session.flush()

        # Expired reservation
        res1 = BookingReservation(
            booking_profile_id=prof.id,
            start_time=datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 20, 10, 30, tzinfo=timezone.utc),
            reservation_token_hash="hash-1",
            status="pending",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        # Active reservation
        res2 = BookingReservation(
            booking_profile_id=prof.id,
            start_time=datetime(2026, 11, 20, 11, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 11, 20, 11, 30, tzinfo=timezone.utc),
            reservation_token_hash="hash-2",
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        session.add_all([res1, res2])
        session.commit()

        count = ReservationService.cleanup_expired(session)
        assert count == 1

        session.refresh(res1)
        session.refresh(res2)
        assert res1.status == "expired"
        assert res2.status == "pending"


def test_admin_booking_endpoints(workspace, monkeypatch):
    client, factory = workspace

    monkeypatch.setattr(GoogleCalendarProvider, "is_connected", lambda s: True)
    monkeypatch.setattr(MicrosoftCalendarProvider, "is_connected", lambda s: True)

    # 1. Check calendar connections
    status_res = client.get("/api/bookings/calendar-connections")
    assert status_res.status_code == 200
    st = status_res.json()
    assert st["google_connected"] is True
    assert st["microsoft_connected"] is True
    assert st["both_connected"] is True
    assert st["default_provider"] == "google_meet"

    # 2. List profiles (seeds default)
    prof_list_res = client.get("/api/bookings/profiles")
    assert prof_list_res.status_code == 200
    profiles = prof_list_res.json()
    assert len(profiles) >= 1
    default_p = profiles[0]

    # 3. Create new profile
    create_res = client.post(
        "/api/bookings/profiles",
        json={
            "display_name": "Executive Demo Team",
            "company_name": "DENSO",
            "meeting_title": "Executive Product Demo",
            "duration_minutes": 45,
            "buffer_before_minutes": 15,
            "buffer_after_minutes": 15,
            "minimum_notice_minutes": 180,
            "booking_horizon_days": 14,
            "max_meetings_per_day": 4,
            "timezone": "Asia/Kolkata",
            "availabilities": [
                {"weekday": 0, "start_time": "10:00", "end_time": "16:00", "is_enabled": True},
                {"weekday": 1, "start_time": "10:00", "end_time": "16:00", "is_enabled": True},
            ],
        },
    )
    assert create_res.status_code == 201
    created_prof = create_res.json()
    assert created_prof["display_name"] == "Executive Demo Team"
    assert created_prof["duration_minutes"] == 45
    prof_id = created_prof["id"]

    # 4. Patch profile
    patch_res = client.patch(
        f"/api/bookings/profiles/{prof_id}",
        json={
            "meeting_title": "Updated Executive Demo",
            "duration_minutes": 60,
        },
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["meeting_title"] == "Updated Executive Demo"
    assert patch_res.json()["duration_minutes"] == 60

    # 5. Deactivate profile
    deact_res = client.post(f"/api/bookings/profiles/{prof_id}/deactivate")
    assert deact_res.status_code == 200
    assert deact_res.json()["is_active"] is False

    # 6. Public page for deactivated profile returns 404
    public_res = client.get(f"/api/public/book/{created_prof['public_slug']}")
    assert public_res.status_code == 404

    # 7. Reactivate
    act_res = client.post(f"/api/bookings/profiles/{prof_id}/activate")
    assert act_res.status_code == 200
    assert act_res.json()["is_active"] is True

