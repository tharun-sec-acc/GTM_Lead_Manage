from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def available_slots(start: datetime, end: datetime, busy: list[tuple[datetime, datetime]],
                    duration_minutes: int, timezone_name: str,
                    workday_start_hour: int, workday_end_hour: int):
    zone = ZoneInfo(timezone_name)
    current_slot = start.replace(second=0, microsecond=0)
    if current_slot < start:
        current_slot += timedelta(minutes=1)
    slots = []
    while current_slot + timedelta(minutes=duration_minutes) <= end:
        slot_end = current_slot + timedelta(minutes=duration_minutes)
        local = current_slot.astimezone(zone)
        local_end = slot_end.astimezone(zone)
        minute = local.hour * 60 + local.minute
        eligible = (local.weekday() < 5 and local.date() == local_end.date()
                    and local.utcoffset() == local_end.utcoffset()
                    and workday_start_hour * 60 <= minute
                    and local_end.hour * 60 + local_end.minute <= workday_end_hour * 60
                    and (minute - workday_start_hour * 60) % duration_minutes == 0)
        if eligible and not any(current_slot < busy_end and slot_end > busy_start
                                for busy_start, busy_end in busy):
            slots.append({"start": local.isoformat(), "end": local_end.isoformat()})
        current_slot += timedelta(minutes=1)
    return slots
