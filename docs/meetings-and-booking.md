# Unified meetings, artifacts and public booking

Two related subsystems are implemented: **meetings** (`backend/app/meetings`, migration `0015_unified_meetings`)
and **public booking** (`backend/app/booking`, migration `0017_public_booking_system`). Both are driven from the
`/meetings` screen; booking additionally has public prospect pages.

## 1. Provider model

`backend/app/meetings/base.py` defines `MeetingProvider` with an explicit capability set
(`instant_meeting`, `scheduled_meeting`, `calendar_invitations`, `recording_retrieval`,
`transcript_retrieval`, `availability_lookup`). `capabilities.py` declares full capabilities for both
`teams` and `google_meet`, and `providers/__init__.py` resolves a provider by name.

| Provider | Implementation |
| --- | --- |
| `teams` | Microsoft Graph: `/me/onlineMeetings` for instant meetings, `/me/events` with `isOnlineMeeting` for scheduled ones, Graph join URL (`joinWebUrl`), participants, recordings and call transcripts, invite/reschedule/cancel through the organizer's Outlook calendar |
| `google_meet` | Google Meet space creation and Calendar events with a Meet conference link, participants, Drive recordings/transcripts when the account recorded and the scopes allow it |

`GET /meetings/providers/status` returns each provider's connection state, organizer email, scopes and
capabilities. A provider that is not connected fails its calls; it does not silently fall back to the other.

## 2. Meeting records and endpoints

`meetings` rows hold provider, external meeting id, organizer email, lead/contact/product links, title,
description, type (`instant`/`scheduled`), join URL, schedule, timezone, status and raw provider metadata.
Child tables store participants, recordings, transcripts and transcript entries, Bedrock analysis, and action
items.

| Method and path | Purpose |
| --- | --- |
| `GET /meetings/providers/status` | Provider connection and capability status |
| `GET /meetings` | List meetings (filterable) |
| `POST /meetings` | Create an instant or scheduled meeting and invite participants |
| `GET /meetings/{id}` | Meeting detail with participants, artifacts, analysis and action items |
| `POST /meetings/{id}/sync-artifacts` | Discover recordings/transcripts/participants from the provider |
| `POST /meetings/{id}/transcript` | Paste a manual transcript or call notes |
| `POST /meetings/{id}/analyze` | Run Bedrock meeting intelligence over the transcript |
| `POST /meetings/{id}/action-items`, `PATCH /meetings/action-items/{id}` | Create or update action items |
| `POST /meetings/{id}/send-invites` | Resend calendar invitations with the join link |
| `POST /meetings/{id}/reschedule`, `POST /meetings/{id}/cancel` | Move or cancel the event and notify attendees |
| `POST /meetings/{id}/send-followup` | Send the reviewed follow-up draft through the mailer |

Creating a meeting also links the lead (and sets its `extra["stage"]` to `Meeting Scheduled` when the
attribute exists) and triggers an initial analysis attempt; failures there are logged and deferred rather
than failing the meeting creation.

## 3. Artifacts and analysis

- `meetings/artifacts/storage_service.py` writes artifacts to the local archive root
  (`/app/attachments/meetings`, backed by the `attachments_data` volume) and, when
  `AWS_S3_UPLOAD_ENABLED=true` plus a bucket/region are configured, uploads the same bytes to S3.
- `meetings/artifacts/normalization.py` normalizes entries and parses WebVTT transcripts.
- `meetings/intelligence/meeting_analyzer.py` runs Bedrock analysis to produce a summary, minutes-of-meeting
  style sections and suggested action items from the transcript text.
- Celery schedules `poll_meeting_artifacts` every 5 minutes to pick up newly available recordings/transcripts.

Recording/transcript availability depends on tenant policy and the organizer actually recording the call;
Teams does not expose artifacts for every meeting, and Google Meet requires the recording to have been created
in Drive. Disabled tenant recording features will return empty discovery results, not invented data.

## 4. Public booking

`booking_profiles` define a public, unguessable `public_slug` with display name, description, meeting title and
description, provider, duration, buffers, minimum notice, booking horizon, maximum meetings per day, timezone
and an active flag. `booking_availabilities` hold a weekly window per weekday (start/end `HH:MM`, enabled).
`bookings` store the customer details, start/end, timezone, status, Google Calendar event id, Meet URI, hashed
cancellation and reschedule tokens, and an optional idempotency key. `booking_reservations` hold short-lived
slot holds; `booking_event_logs` record provider interactions.

Flow:

1. `GET /public/book/{slug}` returns the public profile; an inactive or unknown slug is a 404.
2. `GET /public/book/{slug}/availability?start=&end=&timezone=&duration_minutes=` aggregates busy intervals from
   the connected Google calendar **and** the connected Outlook organizer (`MicrosoftCalendarProvider` only
   supplies busy intervals), applies buffers, notice, horizon, per-day maximum and working windows, and returns
   free slots in the requested timezone.
3. `POST /public/book/{slug}/reserve` places a 10-minute hold (`booking_reservations`, hashed reservation token)
   and rejects double holds with 409.
4. `POST /public/book/{slug}/confirm` validates the hold, creates a **Google Calendar event with a Google Meet
   link** (`sendUpdates=all`), matches or creates the CRM contact and lead, creates the core `Meeting` record and
   the `Booking`, and returns the management token. A repeated `idempotency_key` returns the existing booking.
5. `GET /public/bookings/{token}`, `POST /public/bookings/{token}/reschedule` and
   `/cancel` back the self-service `/book/manage/[token]` page.
6. Celery `cleanup_expired_booking_reservations_task` runs every minute to release expired holds.

Authenticated organization endpoints (`/api/bookings/...`) list profiles, create/update/activate/deactivate
them, show calendar connection state and list bookings; the `booking-management` component in `/meetings`
drives them.

## 5. Frontend routes

| Route | Screen |
| --- | --- |
| `/meetings` | Unified calendar: availability, meeting creation, transcripts, MoM analysis, action items, reschedule/cancel/follow-up, booking profile management |
| `/book/[slug]` | Public prospect booking page: profile, availability, slot reservation, confirmation form |
| `/book/manage/[token]` | Public self-service page to view, reschedule or cancel a confirmed booking |

Public routes are rendered outside the authenticated shell (`app-shell.tsx` treats `/book/` as public).

## 6. Configuration

| Variable | Purpose |
| --- | --- |
| `MICROSOFT_*` | Entra app registration, organizer, Graph base URL and token-cache Fernet key (see [Microsoft 365 setup](microsoft-365-setup.md)) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `GOOGLE_WORKSPACE_ORGANIZER_EMAIL`, `GOOGLE_TOKEN_ENCRYPTION_KEY` | Google Workspace connection; required for booking confirmation because the calendar event is created with Google |
| `GOOGLE_CALENDAR_ENABLED`, `GOOGLE_MEET_ENABLED`, `GOOGLE_DRIVE_ENABLED`, `GOOGLE_WORKSPACE_EVENTS_ENABLED` | Feature switches for the Google provider |
| `AWS_S3_BUCKET`, `AWS_S3_UPLOAD_ENABLED`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Artifact archive; without S3 the local volume is used |
| `MEETING_TIMEZONE`, `MEETING_DURATION_MINUTES`, `MEETING_WORKDAY_START_HOUR`, `MEETING_WORKDAY_END_HOUR`, `MEETING_BOOKING_WINDOW_DAYS` | Legacy single-organizer availability defaults |

## 7. Limitations

- Booking confirmation always creates a **Google** Calendar event and Meet link. Outlook/Teams booking is not
  wired into the booking service; Outlook is used for busy-interval checks and Teams meetings are created from
  the authenticated meetings screen instead.
- Microsoft Teams recording/transcript retrieval depends on tenant policy, organizer licensing and Graph
  permissions (`OnlineMeetings.ReadWrite`, `Calendars.ReadWrite` as configured); this has been exercised with
  mocked tests only, not a live tenant.
- The public booking pages are local-only by design. Real prospects need an approved HTTPS deployment, and the
  pages have no captcha or per-IP rate limiting.
- Management tokens are stored as hashes, are not single-use, and are shown only in the confirmation response;
  losing the link means an administrator must handle the change.
- Automated coverage: `backend/tests/test_meetings.py` and `backend/tests/test_booking.py`. No live Google or
  Microsoft call is made by the tests.
