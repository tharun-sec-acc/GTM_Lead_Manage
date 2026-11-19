from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.booking.models import BookingProfile
from app.booking.schemas import SlotItem


def normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_time_str(time_str: str) -> time:
    parts = time_str.split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))


def generate_available_slots(
    profile: BookingProfile,
    target_timezone_str: str,
    range_start: datetime,
    range_end: datetime,
    busy_intervals: list[tuple[datetime, datetime]],
    daily_meeting_counts: dict[date, int] | None = None,
    now_utc: datetime | None = None,
) -> list[SlotItem]:
    """
    Generate valid, non-overlapping booking slots for a profile within range_start to range_end.
    - Aggregates profile working hours in profile.timezone.
    - Applies buffer_before_minutes and buffer_after_minutes.
    - Respects minimum_notice_minutes and booking_horizon_days.
    - Respects max_meetings_per_day.
    - Filters out conflicts with busy_intervals in UTC.
    - Formats slots in customer's requested target_timezone_str.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    else:
        now_utc = normalize_utc(now_utc)

    try:
        profile_tz = ZoneInfo(profile.timezone or "Asia/Kolkata")
    except (ZoneInfoNotFoundError, ValueError):
        profile_tz = ZoneInfo("Asia/Kolkata")

    try:
        target_tz = ZoneInfo(target_timezone_str)
    except (ZoneInfoNotFoundError, ValueError):
        target_tz = profile_tz

    daily_counts = daily_meeting_counts or {}

    # Map weekday (0=Monday..6=Sunday) to profile availability config
    avail_map = {
        av.weekday: av
        for av in (profile.availabilities or [])
        if av.is_enabled
    }

    horizon_cutoff_utc = now_utc + timedelta(days=profile.booking_horizon_days)
    notice_cutoff_utc = now_utc + timedelta(minutes=profile.minimum_notice_minutes)

    # Convert range to profile timezone dates
    start_local = range_start.astimezone(profile_tz)
    end_local = range_end.astimezone(profile_tz)

    current_date = start_local.date()
    end_date = end_local.date()

    duration = timedelta(minutes=max(10, profile.duration_minutes))
    buffer_before = timedelta(minutes=max(0, profile.buffer_before_minutes))
    buffer_after = timedelta(minutes=max(0, profile.buffer_after_minutes))
    step = duration  # standard step matches meeting duration

    slots: list[SlotItem] = []

    while current_date <= end_date:
        weekday = current_date.weekday()
        avail = avail_map.get(weekday)

        if not avail:
            current_date += timedelta(days=1)
            continue

        # Check daily meeting limits
        if daily_counts.get(current_date, 0) >= profile.max_meetings_per_day:
            current_date += timedelta(days=1)
            continue

        work_start_time = parse_time_str(avail.start_time)
        work_end_time = parse_time_str(avail.end_time)

        # Datetimes in profile timezone
        day_work_start = datetime.combine(current_date, work_start_time, tzinfo=profile_tz)
        day_work_end = datetime.combine(current_date, work_end_time, tzinfo=profile_tz)

        slot_start_local = day_work_start

        while slot_start_local + duration <= day_work_end:
            slot_end_local = slot_start_local + duration

            slot_start_utc = slot_start_local.astimezone(timezone.utc)
            slot_end_utc = slot_end_local.astimezone(timezone.utc)

            # Check minimum notice and horizon constraints
            if slot_start_utc < notice_cutoff_utc or slot_start_utc > horizon_cutoff_utc:
                slot_start_local += step
                continue

            # Check if within range_start and range_end
            if slot_start_utc < range_start.astimezone(timezone.utc) or slot_end_utc > range_end.astimezone(timezone.utc):
                slot_start_local += step
                continue

            # Effective organizer occupied window including buffers
            blocked_start = slot_start_utc - buffer_before
            blocked_end = slot_end_utc + buffer_after

            # Check for conflict with any busy interval
            has_conflict = False
            for b_start, b_end in busy_intervals:
                # normalize
                b_start_utc = normalize_utc(b_start)
                b_end_utc = normalize_utc(b_end)
                if max(blocked_start, b_start_utc) < min(blocked_end, b_end_utc):
                    has_conflict = True
                    break

            if not has_conflict:
                slot_start_target = slot_start_utc.astimezone(target_tz)
                slot_end_target = slot_end_utc.astimezone(target_tz)

                slots.append(
                    SlotItem(
                        start=slot_start_target.isoformat(),
                        end=slot_end_target.isoformat(),
                        utc_start=slot_start_utc.isoformat(),
                        utc_end=slot_end_utc.isoformat(),
                    )
                )

            slot_start_local += step

        current_date += timedelta(days=1)

    return slots
