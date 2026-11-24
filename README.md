# Solwer GTM Lead Management & Sales Intelligence Platform

This repository is a local-first GTM workspace: Excel import, company and contact discovery, evidence-backed
company research, automotive market intelligence, multi-product campaign outreach, a reply/conversation inbox,
Microsoft Teams and Google Meet meeting management with AI minutes-of-meeting, a public prospect booking page,
Zoho CRM synchronization, and organization-level authentication.

> **Safety and status:** This is a pilot, not a production service. Authentication and organization tenancy are
> implemented, but an anonymous default-organization fallback is available through configuration, sending
> defaults to disabled, and there is no production deployment, monitoring, backup or support policy. Do not
> expose the API, dashboard, PostgreSQL or Redis publicly. When sending is explicitly enabled, approved due
> emails in active campaigns reach real recipients. External provider behavior (Gmail, Microsoft Graph, AWS
> Bedrock, Apollo, Zoho) has been exercised with mocked tests; live credentials and tenant consent must be
> verified separately.

## Contents

- [What exists today](#what-exists-today)
- [Not implemented](#not-implemented)
- [Architecture and data flow](#architecture-and-data-flow)
- [Local setup](#local-setup)
- [Configuration reference](#configuration-reference)
- [End-to-end flows](#end-to-end-flows)
- [Tracking and privacy](#tracking-and-privacy)
- [API and implementation map](#api-and-implementation-map)
- [Testing and verification](#testing-and-verification)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)

## What exists today

| Area | Implemented | Important limitation |
| --- | --- | --- |
| Accounts and tenancy | Email/password registration and login, JWT access and refresh sessions in HttpOnly cookies, token revocation, password reset, organizations with `owner`/`admin`/`manager`/`rep`/`read_only` roles, invitations, organization switching, audit log rows | No SSO, MFA, email-verification delivery or IP rate limiting; a configurable anonymous fallback maps unauthenticated calls to the default organization |
| Plans and entitlements | Data-driven plan catalogue (free/starter/growth/business/enterprise), one subscription per organization with trial and period state, monthly usage meters, seat and email-send enforcement, tenant-scoped by-ID access for leads and import batches, `/settings/billing` screen | No payment provider, invoices, proration or dunning; only seat and email-send meters are enforced; legacy NULL-organization rows stay visible to the anonymous fallback |
| Combined dashboard | `/` and `/dashboard` share one workspace: real counts, Excel upload/mapping, company/domain search, selected-company research and contact workbench, research history and outreach links | Counts cover loaded records; research and Apollo calls always require explicit actions |
| Global overview | `/overview` consolidated counts across products | Aggregates loaded records, not a warehouse |
| Product workspaces | Data-driven product selector and `Add product`; `/products/{slug}` overview, companies, import, research, contacts, campaigns, templates, meetings and analytics | Products share master companies and company research; product scoping is workflow isolation inside one organization |
| Spreadsheet import | Multi-sheet `.xlsx` drag-and-drop, per-sheet preview/mapping, background import, row-level report with worksheet provenance | Company name is required per selected sheet; duplicate candidates are reported, not merged |
| Lead and contact discovery | Review imported leads, manually confirm a domain, retain Apollo search candidates, enrich selected people, create/edit/soft-remove manual contacts | No automatic company/domain discovery, automatic enrichment or independent contact verification |
| Sales CRM | Configurable pipelines and stages per organization, opportunities with value, close date, owner and source, stage history, won/lost with lost reasons, tasks, activity timeline, lead ownership/lifecycle/qualification, deterministic lead scoring, duplicate detection and merge, custom-field definitions, saved views, weighted forecast and executive summary on `/crm` | Merge, custom-field and saved-view management are API-only in the UI; no territories, quotas, per-user activity sync or forecast scenarios yet |
| Lead 360 profile | Company overview, embedded research, contact creation, embedded outreach editor, campaign messages, replies, market intelligence and a synthesized activity timeline | Owner, lifecycle stage/history and proposal/contract modules remain unimplemented |
| Company Intelligence | Opt-in Celery research jobs, autonomous keyless discovery (sitemaps, RSS/Atom, outbound references, GLEIF, Wikipedia/Wikidata, SEC EDGAR), bounded HTML/PDF retrieval, opt-in text-only Playwright fallback, seven extraction roles plus verification/synthesis, citations, coverage metrics, financial qualifiers, versioned reports, retry/cancel and reviewed-fact selection | No external search API; restrictive robots/browser policy limits coverage; live end-to-end report retest is still pending |
| Automotive market intelligence | 62 seeded Indian automotive sources, scheduled SSRF-safe crawl, article dedup, Bedrock/heuristic event classification, company resolution, six-product matching, explainable dual scoring, alerts, watchlists, inbound signal webhook, outbound HMAC-signed Slack/Teams webhooks, drill-down UI | The inbound webhook is unauthenticated; scores and extracted problems are heuristic; sources must be curated |
| Campaigns and follow-ups | Multiple saved-contact selection or pasted addresses, atomic additions of up to 100 recipients, independent threads, draft editing, approval, configurable follow-up delays, pause/stop/resume | Additions require a draft campaign; sending is disabled by default; drafts and generated claims need human review |
| Email accounts | OAuth Gmail and Microsoft 365 mailbox connections, default sender, account sync, direct send, bulk outreach, per-message attachments, conversation inbox | Provider quota is not queried; sync is a recent-message pull, not full delta history |
| AI assistance | Bedrock email sequences, research extraction, reply classification, response suggestions, meeting minutes and market-event classification; explicit inference-profile discovery/selection and actionable AWS errors | Approved AWS access is required; profile selection does not prove invocation access; no product-catalogue grounding |
| Email and replies | Campaign sending over Gmail SMTP, IMAP polling for the legacy path, OAuth API sending/sync for connected mailboxes, threaded replies, unsubscribe and suppression controls | SMTP/API acceptance is not delivery; mailbox matching and bounce detection are best effort |
| Tracking | SMTP-accepted events; optional open pixel and approved-link click redirect | Disabled by default, approximate, and needs a separately approved public HTTPS service |
| Meetings | Unified Teams and Google Meet provider model, instant and scheduled meetings, participants, invitations/reschedule/cancel, recording and transcript retrieval, local/S3 artifact archive, Bedrock minutes-of-meeting, action items, follow-up drafts | Requires tenant recording policy and provider consent; provider paths are mock-tested only |
| Public booking | Booking profiles with weekly availability, buffers, notice, horizon and daily caps, public availability aggregated from Google and Outlook calendars, 10-minute reservation holds, confirmation with Google Calendar + Meet event, CRM lead/contact creation, self-service reschedule/cancel links | Confirmation always creates a Google event; no reCAPTCHA or IP throttling; needs an approved HTTPS deployment for real prospects |
| Zoho CRM | OAuth connection with encrypted tokens, module/field discovery, editable field mappings with conflict policies, outbound/inbound sync jobs, logs, conflict resolution, per-lead sync, GTM-to-Deal stage mapping | Polling only (no Zoho webhooks), deletes are not propagated, mock-tested only |
| Microsoft 365 calendar | Entra delegated organizer connection, Graph availability lookup for the calendar screen and booking availability | Availability and meeting creation depend on tenant consent and licensing |
| Operations | FastAPI, PostgreSQL, Redis, Celery worker/beat, Docker Compose, Alembic migrations, rolling 24-hour send-budget status and automated tests | No monitoring/backup policy, provider-aware throttling or complete live integration validation |

Migration head is `0021_crm_pipeline_and_opportunities` (the market-intelligence and earlier revisions use hash-style
names, e.g. `90a32bdfdc2e` and `a23dfc0ad970`). Migrations are additive and preserve existing records. See
[migration and deployment notes](docs/product-migration-and-deployment.md) and
[authentication and organizations](docs/authentication-and-organizations.md) and
[billing and subscriptions](docs/billing-and-subscriptions.md).

The SaaS programme audit, feature inventory and phased roadmap live in
[the platform audit](docs/saas-platform-audit.md). The sales pipeline is documented in
[CRM pipelines and opportunities](docs/crm-pipelines-and-opportunities.md) and paid acquisition
in [advertising and lead capture](docs/advertising-and-lead-capture.md).

## Not implemented

- Side-by-side duplicate merge UI, custom-field value editor and saved-view sharing UI (the CRM endpoints exist);
  importing people rows as contacts; Apollo organization firmographics; sales territories, quotas and
  forecast scenarios beyond the probability-weighted pipeline.
- Advertising: provider OAuth *app* flows (accounts are connected with a provider-approved token),
  ad set/ad/creative and keyword reports, campaign mutation (create/pause/budget), LinkedIn/Microsoft/TikTok/Amazon
  connectors, provider-side token revocation, and CAPTCHA or IP rate limiting on public capture forms.
- Recipient file import; per-provider send pacing; analytics date filters and CSV/Excel export.
- Email verification delivery and verification endpoint; SSO/SAML; MFA; provider-side token revocation.
- Payment-provider checkout, invoices, tax handling, proration and dunning for subscriptions; enforcement of
  the lead, research, campaign, mailbox and integration meters (they are catalogued and reported but not yet
  gated on their write paths).
- Jira tasks, task owners and turnaround tracking; Calendly, Dataverse, Power Automate and other external CRM
  integrations (Zoho CRM is the implemented CRM sync).
- Teams/Dataverse booking: the public booking flow always creates a Google Calendar event with a Google Meet
  link. Teams meetings are created from the authenticated meetings screen.
- Provider webhooks for mail or Zoho; mailbox delta/history sync beyond a recent-message pull.
- Authenticated playback of meeting recordings; artifacts are stored locally and optionally uploaded to S3.

Do not assume a planned feature exists, and do not treat a meeting-request classification as a scheduled
meeting.

## Architecture and data flow

```text
Browser: Next.js 15 / React 19 / TypeScript (localhost:3000)
    | REST + JWT (HttpOnly cookies or Bearer)
    v
FastAPI (localhost:8000) --- PostgreSQL: users, organizations, leads, uploads,
    |                         campaigns, messages, replies, events, research,
    |                         products, meetings, bookings, Zoho, market data,
    |                         billing plans, subscriptions and usage
    |---- Apollo API: selected contact discovery/enrichment
    |---- AWS Bedrock: drafting, classification, research, minutes, market events
    |---- Google: OAuth mail/calendar/Meet, booking events
    |---- Microsoft Entra + Graph: organizer connection, Teams, availability
    |---- Zoho CRM: inbound/outbound record sync
    |
    +---- Redis broker <---- Celery worker + Celery Beat
                              | Excel imports
                              | bounded research collection and Bedrock extraction
                              | Gmail IMAP polling / OAuth mailbox sync / reply classification
                              | due-mail dispatch (sending disabled by default)
                              | meeting artifact polling
                              | booking reservation cleanup
                              | Zoho sync and token refresh
                              + market-source crawl
```

Compose runs `frontend`, `api`, `worker`, `scheduler`, `db` and `redis`. The API applies migrations on startup.
Excel uploads are stored in the database; message attachments and meeting artifacts use the
`attachments_data` volume (with optional S3 upload for meeting artifacts). Celery Beat intervals are defined in `backend/app/tasks.py`
(imports 10 s, inbox 30 s, due mail 30 s, reply classification 60 s, mailbox sync 60 s, booking cleanup 60 s,
Zoho outbound 120 s, meeting artifacts 300 s, Zoho inbound 300 s, market crawl 300 s, Zoho token refresh
900 s).

This is a modular monolith, not microservices. Redis is the Celery broker; Kafka and per-workload queues are not
implemented.

## Local setup

### Prerequisites

- Docker Desktop with Docker Compose and sufficient local resources.
- A private copy of `.env.example` as `.env`. Integration credentials are optional until that integration is
  used. Do not paste credentials into chat or commit `.env`.
- Use only synthetic or otherwise approved test data and approved service accounts.

From the project directory in PowerShell:

```powershell
Copy-Item .env.example .env
# Edit .env privately. Keep MAIL_SEND_ENABLED=false and replace JWT_SECRET_KEY.
docker compose up --build
```

Open `http://localhost:3000`. On first run, register at `/register` to create your organization and sign in.
The API health check is `http://localhost:8000/health`; interactive API documentation is at
`http://localhost:8000/docs`.

| Route | Screen |
| --- | --- |
| `/` , `/dashboard` | Combined dashboard: import, company search, workbench |
| `/overview` | Consolidated cross-product overview |
| `/products/{slug}` and its sub-pages | Product overview, companies, import, research, contacts, campaigns, templates, meetings, analytics |
| `/leads`, `/leads/{id}` | Company list and Lead 360 profile |
| `/intelligence`, `/intelligence/jobs/{id}` | Standalone company research and report |
| `/market-intelligence` | Automotive market radar, opportunities, sources, watchlists, webhooks |
| `/followups`, `/campaigns` | Campaign and conversation workspaces |
| `/meetings` | Unified Teams/Google Meet calendar, MoM, booking profiles |
| `/zoho` | Zoho CRM connection, mappings, sync and conflicts |
| `/book/{slug}`, `/book/manage/{token}` | Public booking page and self-service management |
| `/settings/profile`, `/settings/organization`, `/settings/team`, `/settings/integrations`, `/settings/email-accounts` | Account, tenant, roles, integrations and mailboxes |
| `/login`, `/register`, `/forgot-password`, `/reset-password`, `/invite/{token}` | Authentication |

The containers share the `.env` values. The example PostgreSQL username and password are for local development
only. Do not publish the database or Redis. To stop the services without removing persisted volumes:

```powershell
docker compose down
```

`docker compose down -v` deletes the named data volumes. Establish an approved backup, retention and deletion
process before using sensitive data.

## Configuration reference

Set values in `.env`; no secrets belong in source code or the browser.

### Core and mail

| Variable | Purpose and default |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection; Compose example points to `db` |
| `REDIS_URL` | Celery broker connection; Compose example points to `redis` |
| `APOLLO_API_KEY` | Required for Apollo search/enrichment; subject to account access and credits |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Legacy account and app password for campaign SMTP/IMAP |
| `MAIL_SEND_ENABLED` | `false` by default. Explicit `true` enables approved due emails in active campaigns, subject to all remaining gates |
| `MAIL_UNSUBSCRIBE_ENABLED` | `true` by default. Explicit `false` omits unsubscribe footer/headers and removes that HTTPS prerequisite; inbox checks, reply stops and suppressions remain enforced |
| `TRACKING_ENABLED` | `false` by default. Requests open pixels and approved-link redirects; they can only be included when an HTTPS base URL is configured |
| `PUBLIC_BASE_URL` | Empty by default. An approved HTTPS base URL is needed for invitation links, unsubscribe links and public tracking; this setting does not deploy or verify an endpoint |
| `DAILY_SEND_LIMIT` | Rolling 24-hour application attempt budget; default 50. This is separate from provider quotas |
| `AWS_REGION`, `BEDROCK_MODEL_ID` | Region and Converse-compatible model or inference-profile ID/ARN. The UI can explicitly override the model for individual generation/research requests |
| `AWS_S3_BUCKET`, `AWS_S3_UPLOAD_ENABLED`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | Optional archive for meeting recordings/transcripts; without it, artifacts stay on the local volume |

### Company intelligence

| Variable | Purpose and default |
| --- | --- |
| `COMPANY_INTELLIGENCE_ENABLED` | `false` by default. Enables research submission/retries; saved reports remain readable while disabled |
| `RESEARCH_BROWSER_ENABLED`, `RESEARCH_BROWSER_WAIT_MS` | Opt-in text-only Playwright fallback and render wait (default 10,000 ms) |
| `RESEARCH_MAX_CONCURRENT_AGENTS` | Concurrent category extraction calls per job; default 3, bounded 1-5 |
| `RESEARCH_MAX_PAGES_PER_COMPANY`, `RESEARCH_MAX_CRAWL_DEPTH` | Code defaults 25 pages / depth 3; `.env.example` sets 12 / 5. Quick research caps at 5 pages / depth 1 |
| `RESEARCH_REQUEST_TIMEOUT`, `RESEARCH_MAX_DURATION_SECONDS` | Code defaults 20 s per request and 180 s for source collection, not the whole Bedrock job |
| `RESEARCH_MAX_CONTENT_SIZE`, `RESEARCH_MAX_TOTAL_CONTENT_SIZE` | Code defaults 3,000,000 bytes per response and 15,000,000 per crawl |
| `RESEARCH_CACHE_TTL_HOURS`, `RESEARCH_MAX_RETRIES` | Defaults 24-hour freshness / 2 manual retries per failed role |
| `RESEARCH_DAILY_BUDGET`, `RESEARCH_DAILY_BEDROCK_CALLS`, `RESEARCH_DAILY_SOURCE_BYTES` | UTC-day limits: 100 jobs, 500 model calls, 50,000,000 source bytes |
| `RESEARCH_DISCOVERY_ENABLED`, `RESEARCH_DISCOVERY_MAX_CANDIDATES`, `RESEARCH_DISCOVERY_MAX_DOMAINS`, `RESEARCH_DISCOVERY_MAX_CANDIDATES_PER_DOMAIN`, `RESEARCH_DISCOVERY_MIN_SCORE`, `RESEARCH_DISCOVERY_MAX_BYTES`, `RESEARCH_DISCOVERY_DEADLINE_SECONDS` | Keyless discovery switches and bounds |
| `RESEARCH_DISCOVERY_WIKIPEDIA_ENABLED`, `RESEARCH_DISCOVERY_SEC_ENABLED`, `RESEARCH_DISCOVERY_GLEIF_ENABLED` | Individual discovery adapters |
| `RESEARCH_SEARCH_PROVIDER`, `RESEARCH_SEARCH_API_KEY` | Reserved; no external search adapter is implemented |

See [discovery](docs/company-intelligence-discovery.md), [sources](docs/company-intelligence-sources.md) and
[setup](docs/company-intelligence-setup.md).

### Microsoft 365, Google and meetings

| Variable | Purpose |
| --- | --- |
| `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | Single-tenant Entra web-app identifiers and secret |
| `MICROSOFT_REDIRECT_URI` | Must be `http://localhost:8000/microsoft/oauth/callback` |
| `MICROSOFT_ORGANIZER_EMAIL` | The approved work-or-school organizer accepted by the callback |
| `MICROSOFT_TOKEN_ENCRYPTION_KEY` | Fernet key for OAuth state and the serialized MSAL cache |
| `MICROSOFT_GRAPH_BASE_URL` | Must be `https://graph.microsoft.com/v1.0` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` | Google OAuth web app for Gmail sending, Calendar, Meet and booking events |
| `GOOGLE_WORKSPACE_ORGANIZER_EMAIL`, `GOOGLE_TOKEN_ENCRYPTION_KEY` | Legacy organizer identity and token key |
| `GOOGLE_CALENDAR_ENABLED`, `GOOGLE_MEET_ENABLED`, `GOOGLE_DRIVE_ENABLED`, `GOOGLE_WORKSPACE_EVENTS_ENABLED` | Google feature switches |
| `MEETING_TIMEZONE`, `MEETING_DURATION_MINUTES`, `MEETING_WORKDAY_START_HOUR`, `MEETING_WORKDAY_END_HOUR`, `MEETING_BOOKING_WINDOW_DAYS` | Defaults for the single-organizer availability view |

See [Microsoft 365 setup](docs/microsoft-365-setup.md), [meetings and booking](docs/meetings-and-booking.md) and
[Google Workspace setup](docs/google-workspace-setup.md).

### Zoho CRM

| Variable | Purpose |
| --- | --- |
| `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REDIRECT_URI` | Zoho API-console app; redirect default `http://localhost:8000/zoho/oauth/callback` |
| `ZOHO_ACCOUNTS_DOMAIN`, `ZOHO_API_DOMAIN`, `ZOHO_CRM_API_VERSION` | Regional endpoints and API version (default India / `v8`) |
| `ZOHO_TOKEN_ENCRYPTION_KEY` | Fernet key for stored Zoho tokens |
| `ZOHO_SYNC_ENABLED` | Master switch for scheduled Zoho sync tasks |

See [Zoho CRM integration](docs/zoho-crm-integration.md).

### Authentication and organizations

| Variable | Purpose and default |
| --- | --- |
| `JWT_SECRET_KEY`, `JWT_ALGORITHM` | Token signing; **replace the development default** with a private 32+ character value |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Session lifetimes (120 / 14 days) |
| `CORS_ALLOWED_ORIGINS` | Explicit credentialed browser origins |
| `COOKIE_SECURE`, `COOKIE_SAMESITE`, `COOKIE_DOMAIN` | Cookie attributes; set `COOKIE_SECURE=true` for HTTPS |
| `AUTH_ENABLED`, `AUTH_ALLOW_ANONYMOUS_FALLBACK` | Require sign-in / allow the default-organization fallback |
| `DEFAULT_ORG_NAME`, `DEFAULT_ORG_SLUG` | Organization created for the fallback and first run |
| `BILLING_DEFAULT_PLAN_CODE`, `BILLING_CURRENCY` | Fallback plan code (`growth`) and catalogue currency (`INR`) |
| `BILLING_ENFORCE_LIMITS` | `true` enforces metered plan limits; `false` reports usage without blocking |

See [authentication and organizations](docs/authentication-and-organizations.md).

For Bedrock, use an approved AWS credential provider available **inside** the API and worker containers; host
credentials are not automatically passed through by this Compose file. Never share encryption keys, client
secrets or app passwords.

### Bedrock model and inference-profile setup

A live request once returned an AWS `ValidationException` because the configured model required an inference
profile rather than on-demand throughput with its base model identifier. That is a configuration blocker, not
proof that every permission is invalid.

1. In a selected campaign's **AI draft generation** panel, select **Load AWS inference profiles**.
2. Select an approved profile and review its routing regions. No profile is selected automatically.
3. Enter approved factual context, expand a recipient, and select **Generate this recipient's drafts**. Review,
   edit, save and approve the resulting emails.

Discovery needs `bedrock:ListInferenceProfiles`; Converse needs `bedrock:InvokeModel` on the chosen profile and
backing models. A listed profile is not proof of access. The draft dropdown applies only to that workspace; the
research form persists its own selected ARN on the job, and reply classification uses environment settings.

## End-to-end flows

Exercise each flow with synthetic data first. External steps need correctly configured accounts and network
access.

### 1. Import companies

1. On the dashboard, drag an `.xlsx` file onto the upload area or choose a file.
2. Review worksheet previews, select one or more sheets, and map each sheet's columns independently. `Company
   name` is required on each selected sheet. Domain, email, revenue, contact number, remarks, key-person
   information, designation, industry and location are optional; unmapped columns are retained as lead fields.
3. Start the import. The API stores the file and marks the batch pending; Celery imports it. The UI refreshes
   automatically.
4. Open the report to see `imported`, `invalid` and `duplicate` rows with worksheet and source row. Duplicates
   are skipped for review, not merged. Failed batches can be retried.

Limits: 10 MB compressed, 100 MB uncompressed, 50 worksheets, 100 columns per sheet and 5,000 non-empty rows
across the workbook. Formula cells use cached values; numeric phone numbers may lose leading zeroes. See
[multi-sheet Excel import](docs/multi-sheet-excel-import.md).

### 2. Find, research and select contacts

1. Search the company list by name or domain (local records, up to 1,000 loaded leads — not external discovery).
2. Select **Review**, enter the verified official domain and use **Save domain** to store it without calling
   Apollo or starting research.
3. Select **Company research**, review the prefilled company/site, depth, AWS profile and processing consent,
   then submit. Quick research extracts company/news/leadership/signals; comprehensive adds
   financial/funding/competitors.
4. Inspect persisted progress, quotes, source URLs, dates, financial qualifiers and limitations. Retry failed
   roles or cancel bounded work.
5. Continue with **Domain & people** for Apollo or **Compose outreach** for Lead 360.

Apollo: search returns up to 25 seniority-filtered candidates for the confirmed domain; verify identity and
employer, confirm the employer inline when Apollo has not matched it, then **Select & enrich** each person.
Enrichment may consume credits and may still return no email. See
[Apollo contact management](docs/apollo-contact-management.md).

### 3. Create and review a campaign

1. In Lead 360 use **Add people** to save names, designations and optional business emails, then **Compose and
   approve emails**, or use **Outreach** for all companies. Create or choose a campaign and select manual or
   automatic follow-ups with 0-5 delays of 1-365 days (default 3, 4, 5).
2. While the campaign is a draft, add 1-100 recipients from selected saved contacts, the imported company email,
   and/or pasted addresses. Each addition is all-or-nothing and each person gets a separate thread.
3. Expand a recipient and save drafts, or generate a sequence with an approved inference profile and up to 20
   reviewed, cited research facts for that company. Review all claims; empty drafts remain editable without AWS.
4. Approve the exact saved initial email and each follow-up (manual mode) or the saved follow-up sequence
   (automatic mode). Editing invalidates approval.
5. Activate the campaign. Activation schedules eligible messages; it does not override `MAIL_SEND_ENABLED=false`.

### 4. Sending, replies and safety gates

Sending requires an active campaign and recipient, exact approval, working Gmail SMTP credentials, a complete
inbox sync, no suppression, no unresolved delivery report and budget remaining. Automatic follow-ups also need
current sequence approval.

`MAIL_UNSUBSCRIBE_ENABLED=true` additionally requires an approved HTTPS base and appends unsubscribe links and
headers. SMTP acceptance creates a `sent`/`smtp_accepted` record and is **not** delivery; reconcile `sending` or
`unknown` attempts manually instead of retrying blindly. The worker polls the INBOX over IMAP, stops follow-ups
on replies, records unsubscribe/hard-bounce suppressions, and requires manual review of unmatched delivery
reports. See [email capacity and rate limits](docs/email-capacity-and-rate-limits.md) and
[multi-recipient outreach](docs/multi-recipient-outreach.md).

OAuth mailbox connections (`/settings/email-accounts`) provide a second sending and syncing path for Gmail and
Microsoft 365 accounts, plus direct and bulk outreach from the dashboard. See
[email accounts, sending and conversations](docs/email-accounts-and-sending.md).

### 5. Meetings, minutes and booking

1. On `/meetings`, connect Microsoft 365 (Teams) and/or Google (Meet), choose a provider and create an instant or
   scheduled meeting with participants.
2. After the call, sync artifacts to pull recordings/transcripts, or paste a transcript, then run analysis for
   minutes-of-meeting content and suggested action items. Review and assign action items, send invitations,
   reschedule or cancel, and send a reviewed follow-up draft.
3. Booking profiles define public availability. The prospect books at `/book/{slug}`, which places a short hold
   and then creates a Google Calendar event with a Meet link, the CRM lead/contact and the meeting record.
   Prospects manage changes at `/book/manage/{token}`.

See [meetings and booking](docs/meetings-and-booking.md) and
[Microsoft 365 setup](docs/microsoft-365-setup.md).

### 6. Market intelligence and CRM sync

Market sources are crawled on a schedule; new announcements are classified, matched to the six Solwer products,
scored and surfaced as alerts/opportunities on `/market-intelligence`. Watchlists, source management and
outbound webhook subscriptions are on the same screen. Zoho CRM is connected on `/zoho`, where mappings, sync
triggers, job logs and conflicts are managed. See [market intelligence](docs/market-intelligence.md) and
[Zoho CRM integration](docs/zoho-crm-integration.md).

## Tracking and privacy

When tracking is enabled and an HTTPS base is configured, opens are recorded via a pixel and clicks only via
explicitly added approved HTTPS links. If tracking is enabled without an HTTPS base and unsubscribe links are
disabled, mail sends without pixels/redirects and the UI reports tracking as unavailable. Original destination
links are preserved and SMTP acceptance/replies remain recorded.

Images can be blocked, cached or loaded by proxies; scanners can follow links. Neither event proves a person
read or clicked. The application stores reply content, tracking events, addresses, uploads, encrypted OAuth
tokens and meeting artifacts.

The local Compose configuration does **not** expose tracking or unsubscribe URLs externally. A real deployment
needs an approved security and privacy design plus separately accessible HTTPS endpoints; never expose the
unauthenticated fallback, dashboard, PostgreSQL or Redis. Follow applicable consent, disclosure and retention
requirements.

## API and implementation map

Interactive documentation lists complete request schemas. Major groups:

| Area | Key endpoints |
| --- | --- |
| Authentication | `POST /auth/register`, `/login`, `/refresh`, `/logout`; `GET /auth/me`; `PUT /auth/profile`; `POST /auth/change-password`, `/switch-org/{id}`, `/forgot-password`, `/reset-password` (also under `/api/auth`) |
| Organizations | `GET/PUT /organizations/current`; `GET /organizations/members`; `POST /organizations/members/invite`; `PUT/DELETE /organizations/members/{id}`; invitations list/revoke |
| Billing and plans | `GET /billing/plans`; `GET /billing/subscription`; `GET /billing/usage`; `POST /billing/subscription/change`; `/cancel`; `/resume` (also under `/api/billing`) |
| Sales CRM | `GET/POST /crm/pipelines`, `PATCH /crm/pipelines/{id}`, stage create/patch/delete; `GET/POST /crm/opportunities`, detail/patch, `/stage`, `/close`; `GET /crm/summary`, `/crm/pipeline-summary`; tasks, activities, CRM leads (score, duplicates, merge, timeline), owners, custom fields, saved views (also under `/api/crm`) |
| Integrations and mail | `GET /api/integrations/status`; `POST /api/integrations/{provider}/disconnect`; `GET /api/email-accounts`; account default/disconnect/sync; `POST /api/email-accounts/send` |
| Health and import | `GET /health`, `POST /batches`, `GET /batches`, `/batches/{id}`, `/batches/{id}/preview`, `POST /batches/{id}/start`, `/batches/{id}/retry` |
| Company Intelligence | `GET /intelligence/status`; `POST/GET /intelligence/research`; job detail/progress/retry/cancel; company facts/sources/category views; `GET /intelligence/reports/{id}` |
| Leads and Apollo | `GET /leads`, `GET /leads/{id}/profile`, `PUT /leads/{id}/domain`, `POST /leads/{id}/apollo/search`, `/apollo/enrich`, `GET/POST /leads/{id}/contacts`, `GET /contacts` |
| Products | `GET/POST /products`, `GET/PUT /products/{id}`, `PATCH /products/{id}/status`; product leads/contacts/campaigns/batches/research; templates and attachments |
| Campaigns and analytics | `GET/POST /campaigns`, `GET /campaigns/{id}`, `/analytics`, `POST /campaigns/{id}/enrollments`, `/enrollments/bulk`, `/activate`, `/pause`, `/approve-sequence` |
| Outreach and conversations | `GET /outreach/recipients`, `POST /outreach/bulk-send`, `POST /leads/{id}/direct-outreach`, `GET /conversations`, `POST /conversations/{id}/reply`, `/generate-draft`, `/followup-status` |
| Bedrock | `GET /integrations/bedrock/status`, `GET /integrations/bedrock/profiles?next_token=...`; `POST /enrollments/{id}/generate` accepts `context`, optional `inference_profile_id` and up to 20 `research_fact_ids` |
| Drafts and replies | `PUT /messages/{id}`, `POST /messages/{id}/approve`, `/reject`, `/resolve-send`, `/tracking-links`; `/enrollments/{id}/generate`, `/stop`, `/resume`; reply classification and response drafting |
| Mailbox and tasks | `GET /mailbox/status`, `/mailbox/capacity`, `GET /replies/unmatched`, `POST /replies/{id}/resolve`, `POST /suppressions`, `GET /sales-tasks`, `POST /sales-tasks/{id}/complete` |
| Meetings | `GET /meetings/providers/status`; `GET/POST /meetings`; detail; `/sync-artifacts`, `/transcript`, `/analyze`, `/action-items`, `/send-invites`, `/reschedule`, `/cancel`, `/send-followup` |
| Booking | `GET /public/book/{slug}`, `/availability`, `POST /reserve`, `/confirm`; `GET /public/bookings/{token}`, `POST /reschedule`, `/cancel`; `/api/bookings/profiles`, `/api/bookings`, `/api/bookings/calendar-connections` |
| Zoho CRM | `GET /zoho/oauth/authorize`, `/callback`, `/connection`, `POST /zoho/verify`, `/disconnect`, `/sync`, `/sync/leads/{id}`, `GET /zoho/modules`, `/mappings`, `/sync/jobs`, `/sync/logs`, `/conflicts`, `POST /zoho/conflicts/{id}/resolve` (also under `/api/zoho`) |
| Market intelligence | `GET /api/market-intelligence/overview`, `/feed`, `/opportunities`, `/companies`, `/sources`, `/alerts`, `/watchlists`, `/webhooks`; `POST /webhook`, `/webhooks/test`, source `crawl`/`test` |
| Microsoft and Google | `GET /microsoft/oauth/start`, `/callback`, `/status`; `POST /microsoft/oauth/disconnect`, `/microsoft/availability`; equivalent `/google/...` routes |
| Public email links | `/public/unsubscribe/{token}`; opt-in `/public/open/{token}` and `/public/r/{token}`. Local-only in the current deployment |

Important code locations: `frontend/app` contains the screens; `backend/app/main.py` registers routers;
`backend/app/auth` implements accounts and tenancy; `imports.py`, `apollo.py`, `followup_api.py`, `mailer.py`,
`mailbox.py`, `bedrock.py`, `email_provider.py`, `email_accounts_api.py`, `microsoft_graph.py`,
`google_workspace.py` and `tasks.py` implement their workflows; `company_intelligence/`, `products.py`,
`product_research.py`, `email_templates.py`, `attachments.py`, `meetings/`, `booking/`, `zoho/` and
`market_intelligence/` are the feature domains; `models.py` defines shared records and `backend/migrations/versions`
holds Alembic revisions. Avoid sharing API tokens, unsubscribe tokens or OAuth codes in logs or support requests.

## Testing and verification

Backend tests use temporary SQLite databases and mock external integrations. From PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
Set-Location backend
$env:PYTHONPATH = "."
..\.venv\Scripts\python -m pytest
Set-Location ..
```

Suites present: imports, follow-ups, generation, bedrock, attachments, templates, products, product isolation,
product research, research discovery, company intelligence, conversations intelligence, Denso/Solwer TWMS copy,
email accounts and sending, Google Workspace, Microsoft Graph, native meetings, booking, Zoho CRM,
market intelligence and SaaS multi-tenant auth.

Frontend checks, with Node.js 22 and dependencies installed:

```powershell
Set-Location frontend
npm ci
npx playwright install chromium
npm run typecheck
npm run build
npm test
Set-Location ..
```

**Verification (24 November 2026, after the advertising and lead-capture milestone):**

- Full backend suite: **294 passed, 0 failed** (8m43s) against a local `.venv` (`backend/requirements-dev.txt`).
  The suite includes the migration-to-head check, which now covers `0022_advertising_lead_capture`.
- Frontend type-check (`tsc --noEmit`): clean. `next build` was **not** run for this milestone.
- Earlier milestones reported 282, 205, 180, 104, 76 and 46 passing backend tests as features landed.
- An environment note: on this Windows machine the shell that wraps commands cannot create child processes
  (`fork: Resource temporarily unavailable`). Running the provider commands through the native PowerShell
  binary (for example `exec .../powershell.exe -NoProfile -Command '...'` from Git Bash) works; plain
  `bash -c` pipelines do not.
- Live AWS/Bedrock, text-only Chromium, Meta, Google Ads and webhook deliveries are mocked in the automated
  suite. No live tenant, mailbox, ad account or paid provider run is implied by passing tests; the manual
  procedures in each integration document must be executed against real credentials before launch.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Redirected to `/login` unexpectedly | Cookies blocked, `JWT_SECRET_KEY` changed after issuing tokens, token expired/revoked, or the user lost membership in the active organization |
| `401` on API calls while the UI loads | `AUTH_ALLOW_ANONYMOUS_FALLBACK` and cookie domain/secure settings; check the `X-Organization-Id` header and memberships |
| Invitation link does not arrive | Invitations are not emailed; copy the `invite_url` returned to the administrator |
| Import stays pending | Check `worker`, `scheduler`, Redis and PostgreSQL; inspect worker/scheduler logs; failed batches can be retried |
| Research unavailable or job queued | Check `COMPANY_INTELLIGENCE_ENABLED`, migration state and `/intelligence/status`; rebuild API/worker with matching code |
| Research missing facts | Read source/role errors; check robots policy, official-site evidence, AWS access and budgets; external search is not implemented |
| Apollo search fails or returns no email | Confirm domain, API key, permissions and credits; search is limited to 25 candidates |
| Bedrock action fails | Read the displayed error; select an approved inference profile, check discovery/invocation permissions and container credentials |
| Mail does not send | Check send status, exact approval, campaign/recipient activity, SMTP credentials and inbox sync, suppressions, unresolved attempts and daily limit |
| Gmail connection times out | Have the network administrator allow outbound TCP to `imap.gmail.com:993` and `smtp.gmail.com:587`; an OAuth mailbox connection over 443 is an alternative |
| Mail status is `sending` or `unknown` | Inspect the mailbox and reconcile manually |
| Meeting artifacts never appear | Confirm the organizer is connected, the meeting was recorded, tenant policy allows recording/transcripts, and Graph/Drive scopes are granted; `poll_meeting_artifacts` runs every 5 minutes |
| Booking availability is empty or errors | Check connected Google and Microsoft organizers, profile hours/buffers/notice/horizon, future range and timezone; an error is not "no conflicts" |
| Zoho sync does nothing | Check `/zoho/connection`, `ZOHO_SYNC_ENABLED`, token refresh task, mapping directions and sync logs |
| Market radar is empty | Check enabled sources, source crawl results, worker logs and Bedrock availability; the inbound webhook can inject a test signal |
| Tracking is on but no opens/clicks appear | Requires an approved publicly reachable HTTPS base URL; even working tracking is approximate |

For logs use `docker compose logs api`, `docker compose logs worker` or `docker compose logs scheduler`. Treat logs
as potentially sensitive.

## Roadmap

Intended but unimplemented stages: duplicate resolution UI, normalized lifecycle/ownership history, Jira task
sync with owners and turnaround tracking, Teams-based public booking, provider webhooks for mail and CRM, delta
mailbox sync, authenticated recording playback, and analytics export. Each needs implementation, official
endpoint verification, tests, tenant consent and its own review. A real external deployment also needs an
approved HTTPS design; no tunnel or proxy is authorized for this pilot.
