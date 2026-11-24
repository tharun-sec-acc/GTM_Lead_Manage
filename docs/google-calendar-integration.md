# Calendar availability (local pilot)

The local meetings screen connects the configured organizer and queries Google Calendar FreeBusy. `POST /google/availability` accepts timezone-aware ISO 8601 `start` and `end`, both in the future and within `MEETING_BOOKING_WINDOW_DAYS`. It returns organizer-timezone slots; a Calendar error or incomplete response fails closed rather than offering availability.

Configure `MEETING_TIMEZONE` as an IANA timezone, `MEETING_DURATION_MINUTES` (default 30), `MEETING_WORKDAY_START_HOUR`, `MEETING_WORKDAY_END_HOUR`, and `MEETING_BOOKING_WINDOW_DAYS`. Slots are on weekdays within the configured hours, aligned to the duration. They are informational only and can become stale. This legacy route remains availability-only; calendar events, invitations, booking tokens and double-booking protection belong to the implemented [meetings and booking](meetings-and-booking.md) flow.

`GET /google/oauth/start` begins the browser-bound OAuth flow, `GET /google/oauth/callback` completes it, `GET /google/oauth/status` returns local connection status, and `POST /google/oauth/disconnect` revokes the token. Apply migrations at startup with `alembic upgrade head`. Automated tests mock Google; they do not prove a real account or permissions work.

External prospects cannot reach a localhost page. Real booking requires a separately approved HTTPS deployment and an appropriate security design; this pilot must not use a public tunnel or proxy.
