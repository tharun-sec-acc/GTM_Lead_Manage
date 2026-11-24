# Microsoft 365 calendar availability (local pilot)

This milestone replaces the meetings screen's active Google Calendar availability flow with Microsoft Entra sign-in and Microsoft Graph availability lookup. It does **not** create Outlook events or Teams meetings, send email, retrieve recordings or transcripts, or access OneDrive/SharePoint. The application now requires sign-in (see [authentication and organizations](authentication-and-organizations.md)) and remains local-only; do not expose or forward its ports or use production customer data.

## Entra app registration and delegated permissions

1. In the DENSO-approved Microsoft Entra tenant, register a **single-tenant web application**. Add this exact redirect URI as a **Web** platform URI: `http://localhost:8000/microsoft/oauth/callback`. Create a client secret and store its value privately; do not put it in source control or chat.
2. Configure only these **delegated Microsoft Graph permissions** for this milestone:

   | Permission | Purpose | Endpoint | Personal Microsoft account | Admin consent |
   | --- | --- | --- | --- | --- |
   | `User.Read` (delegated) | Read the signed-in organizer's profile to confirm its configured email | `GET /v1.0/me` | Supported | Not required by the permission definition |
   | `Calendars.ReadBasic` (delegated) | Read the signed-in organizer's free/busy schedule | `POST /v1.0/me/calendar/getSchedule` | Not supported for `getSchedule` | Not required by the permission definition |

   The `getSchedule` API documents `Calendars.ReadBasic` as its least-privileged delegated work-or-school permission; `/me` documents `User.Read` as its least-privileged delegated profile permission. The app does not request application permissions or broader `Calendars.Read`/`Calendars.ReadWrite`. The permission reference does not mark these delegated permissions as requiring admin consent, but Entra tenant consent policy can still prevent user consent and require administrator approval. User sign-in by itself is not proof of Graph consent. No real tenant consent or API access has been tested here.
3. Use a single approved work-or-school account for the configured organizer. The OAuth callback validates the tenant ID, resolves the signed-in identity through Graph `/me`, requires its email or UPN to match the configured organizer, and requires the `Calendars.ReadBasic` scope before saving the connection.

## Local configuration

Copy `.env.example` to a private `.env`. Fill these values locally:

```text
MICROSOFT_TENANT_ID=<Entra directory (tenant) ID>
MICROSOFT_CLIENT_ID=<application (client) ID>
MICROSOFT_CLIENT_SECRET=<client secret value>
MICROSOFT_REDIRECT_URI=http://localhost:8000/microsoft/oauth/callback
MICROSOFT_ORGANIZER_EMAIL=<approved work-or-school organizer email>
MICROSOFT_TOKEN_ENCRYPTION_KEY=<Fernet key generated locally>
MICROSOFT_GRAPH_BASE_URL=https://graph.microsoft.com/v1.0
```

Generate `MICROSOFT_TOKEN_ENCRYPTION_KEY` locally, for example:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

This key is separate from the Entra client secret. It encrypts the temporary OAuth authorization-flow state and serialized MSAL token cache before database storage. Keep it private and stable: changing it makes existing encrypted values unreadable, and the organizer must reconnect. Never inspect, print, or share `.env` values.

Keep the existing local deployment safeguards: `MAIL_SEND_ENABLED=false`, `TRACKING_ENABLED=false`, and Compose's loopback-only API/UI bindings. Start Compose, open `http://localhost:3000/meetings`, and choose **Connect Microsoft organizer**. The browser returns to the local meetings screen after consent. Set `MEETING_TIMEZONE` to the organizer's IANA timezone; the API requests schedule times in UTC and displays generated slots in this configured timezone.

## Implemented behavior and limits

- OAuth authorization-code flow and token refresh use MSAL's confidential-client and serializable token-cache APIs. OAuth state is short-lived, single-use, browser-cookie-bound, and encrypted. The organizer token cache is Fernet-encrypted at rest.
- `POST /microsoft/availability` calls Graph v1.0 `POST /me/calendar/getSchedule` with one configured schedule, a UTC date-time range, and a 30-minute `availabilityViewInterval`. It considers non-free schedule items unavailable and never turns a Graph failure or incomplete schedule into free slots. It does not expose event subjects or locations.
- `GET /microsoft/oauth/status` reports the locally stored connection. `POST /microsoft/oauth/disconnect` removes the local encrypted MSAL cache only. It does not revoke tenant-side user consent; revoke consent through the tenant's approved Entra administration process if required.
- Availability is informational and may change before a future booking. The `/meetings` screen now creates Teams meetings and Outlook calendar events, returns `onlineMeeting.joinUrl`, invites participants, syncs artifacts and drafts follow-ups through the meetings module. The older `/microsoft/availability` endpoint remains availability-only and does not book, invite or send mail. Gmail SMTP/IMAP is a separate legacy mail integration and is not changed by this calendar milestone.
- Graph throttling, permission failures, expired authorization, malformed results, and organizer mismatch are surfaced as errors; the API does not offer slots when it cannot verify availability.
- Tests use mocked MSAL/Graph responses and temporary SQLite. No live Entra tenant, Graph endpoint, Microsoft 365 mailbox, real booking, or email send was used or validated.

## Microsoft migration status

| Area | Status |
| --- | --- |
| Entra OAuth and encrypted token cache | Implemented; mocked tests only |
| Outlook/Graph availability | Implemented; mocked tests only |
| Outlook event creation and Teams meeting link | Implemented in `backend/app/meetings/providers/teams_provider.py` (Graph `/me/events`, `/me/onlineMeetings`); mock-tested only |
| Outlook mail send and recent-message inbox sync | Implemented through OAuth mail accounts (`email_provider.MicrosoftGraphProvider`); delta/history sync and bounce processing remain unimplemented |
| Teams recordings and transcripts | Implemented as explicit sync/import in the meetings module; Graph change notifications are not implemented and tenant policy is unverified |
| Artifact archive | Local volume plus optional S3 upload (`meetings/artifacts/storage_service.py`); OneDrive/SharePoint archive is not implemented |
| Bedrock meeting analysis | Implemented (`meetings/intelligence/meeting_analyzer.py`) for summary, minutes of meeting and action items; Jira and CRM task automation is not implemented |
| Power Platform connection | Future possibility only; not imminent or implemented |

Each later milestone must verify the operation's HTTP method, request/response fields, delegated versus application permissions, tenant admin-consent requirements, and documented limitations before implementation.

## Official references

- [Microsoft identity platform](https://learn.microsoft.com/en-us/entra/identity-platform/)
- [MSAL for Python](https://learn.microsoft.com/en-us/entra/msal/python/)
- [OAuth 2.0 authorization-code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow)
- [Microsoft Graph `calendar: getSchedule` v1.0](https://learn.microsoft.com/en-us/graph/api/calendar-getschedule?view=graph-rest-1.0)
- [Microsoft Graph `user: get` v1.0](https://learn.microsoft.com/en-us/graph/api/user-get?view=graph-rest-1.0)
- [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference)
- [Microsoft Graph permissions overview](https://learn.microsoft.com/en-us/graph/permissions-overview)

Future work must also consult the relevant official references before implementing the associated functionality:

- [Create Outlook event](https://learn.microsoft.com/en-us/graph/api/user-post-events?view=graph-rest-1.0) and [Outlook calendar online meetings](https://learn.microsoft.com/en-us/graph/outlook-calendar-online-meetings)
- [Online meeting resource](https://learn.microsoft.com/en-us/graph/api/resources/onlinemeeting?view=graph-rest-1.0), [list recordings](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-recordings?view=graph-rest-1.0), [list transcripts](https://learn.microsoft.com/en-us/graph/api/onlinemeeting-list-transcripts?view=graph-rest-1.0), and [recording/transcript change notifications](https://learn.microsoft.com/en-us/graph/teams-changenotifications-callrecording-and-calltranscript)
- [Send Outlook mail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0), [list messages](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0), and [message delta query](https://learn.microsoft.com/en-us/graph/delta-query-messages)
- [Drive resource](https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0) and [download drive item content](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0)
- [Amazon S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html) and [Amazon Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
