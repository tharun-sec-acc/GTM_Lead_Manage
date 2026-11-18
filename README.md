# DENSO GTM Prospecting - local pilot

This repository contains a standalone sales prospecting pilot: upload Excel, search companies by name or domain, collect cited company research, find and select Apollo contacts, prepare and approve outreach, review replies and meeting-request tasks, and check a Microsoft 365 organizer's calendar availability.

> **Safety and status:** This is an unauthenticated, local-only pilot, not a production system. Anyone with local access can view or change data and use configured integrations. Do not expose or forward its ports or treat it as production-ready. Sending defaults to disabled; explicitly enabling it allows approved due emails in active campaigns to reach real recipients. The UI and API are bound to loopback in Compose; PostgreSQL and Redis have no published ports. Microsoft meeting booking and the post-demo workflow are **not implemented**.

## Multi-product platform

Product workspaces are implemented incrementally on the existing application: shared master companies with
product associations, product-scoped imports and campaigns, product overview and consolidated global
overview, hybrid versioned email templates, attachments, and product opportunity analysis over shared
company research. Migration head is `0013_research_discovery`; migrations are additive and preserve
existing records. See [multi-product architecture](docs/multi-product-architecture.md), [product API](docs/product-api.md)
and [migration, deployment and rollback](docs/product-migration-and-deployment.md).

The [repository audit and milestone map](docs/multi-product-implementation-plan.md) remains as background on
existing relationships and preservation risks; its status section is historical and was superseded by the
implemented routes, migrations and workspaces named above.

**Verification (17 November 2026):** the full backend suite ran to completion with **205 tests passing**
(`backend: PYTHONPATH=. ../.venv_new/bin/pytest tests/ -q`), including LeadRoad <> DENSO Solwer TWMS copy
automation, immediate draft pre-population, mailbox synchronization, received mail analytics, attachments, product CRUD,
product-scoped import, cross-product campaign/enrollment rejection, templates and existing research/outreach coverage.
Frontend type-check (`npm run typecheck`) and Next.js 15 production build (`npm run build`) completed with 0 errors across all 9 routes.

## What exists today

| Area | Implemented | Important limitation |
| --- | --- | --- |
| Combined dashboard | `/` and `/dashboard` share one workspace: real counts, Excel upload/mapping, company/domain search, selected-company research and contact workbench, research history and outreach links | Counts cover loaded records; research and Apollo calls always require explicit actions |
| Product workspaces | Data-driven product selector and `Add product`; `/overview` consolidated dashboard; `/products/{slug}` overview, companies, import, research, contacts, campaigns, templates, meetings and analytics | Products share master companies and company research; product scoping is workflow isolation, not authentication or tenant separation |
| Spreadsheet import | Multi-sheet `.xlsx` drag-and-drop, per-sheet preview/mapping, background import, row-level report | Company name is required per selected sheet; duplicate candidates are reported, not merged |
| Lead and contact discovery | Review imported leads, manually confirm a domain, retain Apollo search candidates, enrich selected people, and create/edit/soft-remove manual contacts | No automatic company/domain discovery, automatic enrichment, independent contact verification or automatic outreach |
| Lead 360 profile | Company overview, embedded research, contact creation, embedded outreach editor, campaign messages, replies and synthesized activity timeline | Meetings, commercial lifecycle and owner/stage history are not implemented; data is bounded and local-only |
| Company Intelligence | Opt-in Celery research jobs, autonomous keyless discovery (sitemaps, RSS/Atom, outbound references, GLEIF registry, Wikipedia/Wikidata, SEC EDGAR), bounded cross-domain HTML/PDF retrieval, opt-in text-only Playwright fallback, seven extraction roles plus verification/synthesis, citations, coverage metrics, financial qualifiers, versioned reports, retry/cancel and reviewed-fact selection | No external search API; discovered URLs need retrieval and are leads, not facts; restrictive browser mode and robots policy limit coverage; final rendered-source report retest is pending |
| Campaigns and follow-ups | Multiple saved-contact selection or pasted addresses, atomic additions of up to 100 recipients, independent threads, draft editing, approval, configurable follow-up delays, pause/stop/resume | Additions require a draft campaign; sending is disabled by default; drafts and generated claims need human review |
| AI assistance | Bedrock email sequences, research extraction, reply classification and response suggestions; explicit inference-profile discovery/selection and actionable AWS errors | Approved AWS access is required; profile selection does not prove invocation access; no product catalogue grounding or independently verified factual accuracy |
| Email and replies | Gmail SMTP sending code, IMAP inbox polling, threaded replies, unsubscribe and suppression controls | SMTP acceptance is not delivery; mailbox matching and bounce detection are best effort |
| Tracking | SMTP-accepted events; optional open pixel and approved-link click redirect | Tracking is disabled by default, approximate and requires a separately approved public HTTPS service for real recipients |
| Meeting requests | A `meeting_requested` reply classification creates an in-app sales task | It does not create a meeting request, scheduling link, invitation or Meet conference |
| Microsoft 365 calendar | One Entra delegated organizer connection and Graph availability lookup on a local screen | Slots are informational, can become stale, and cannot be booked; only mocked Microsoft tests have run |
| Operations | FastAPI, PostgreSQL, Redis, Celery worker/beat, Docker Compose, Alembic migrations, rolling 24-hour send-budget status and automated tests | No app login, roles, production deployment, monitoring/backup policy, provider-aware throttling or complete external integration validation |

### Requested features still outstanding

- Merge/skip/retain duplicate-resolution UI; importing people rows as contacts; Apollo organization firmographics; normalized sales lifecycle, ownership and stage history.
- Recipient file import; rate pacing and analytics date filters/export. Checkbox selection and pasted multiple addresses are implemented.
- Booking tokens and scheduling-email drafts, a prospect booking page, conflict-safe booking, Outlook event creation and Teams meeting links/invitations.
- Teams recording/transcription configuration, recording or transcript retrieval, S3 archival and authenticated playback. A shared local playback password was selected for future implementation; it is **not implemented**.
- Transcript-based Bedrock analysis, reviewed minutes of meeting (MoM), lead-stage history, approved Jira tasks, task owners and turnaround tracking.
- Paid external search/registry providers, product matching, Tracxn, Calendly, Dataverse, Power Automate and external CRM integration. Current research runs its own keyless discovery across sitemaps, feeds, references, Wikipedia/Wikidata and SEC EDGAR, then retrieves a bounded, scored cross-domain source set with HTTP/PDF and an opt-in text-only Playwright fallback. See [discovery](docs/company-intelligence-discovery.md). Tracxn is explicitly out of scope for now.

Do not assume the planned features exist or treat a meeting-request task as a scheduled meeting.

### Combined dashboard and Company Intelligence milestone

The old import screen and separate overview are now **one shared dashboard**, available at `/` and `/dashboard`. The sidebar's company shortcut jumps to its company table. The dashboard shows actual loaded companies, saved domains, recent imports and active campaigns; unavailable data stays unavailable rather than showing fabricated counts.

**Guided flow:** upload Excel -> map sheets -> review the import -> search by company name/domain -> select **Research** or **Review** -> save/confirm the domain -> run approved research or search Apollo -> open Lead 360 -> select reviewed cited facts -> generate/edit -> approve -> activate outreach.

- **Save domain** validates and stores the company domain without calling Apollo, consuming enrichment credits or starting research.
- **Research** opens the selected company's research form in the same dashboard. The company ID/name/domain carry through; another lead is not created. Research runs only after explicit processing consent and submission.
- **Domain & people** retains saved Apollo candidates, inline employer confirmation, selective enrichment and manual contacts. Switching companies clears the previous company's people.
- **Compose outreach** opens that company's embedded editor. Up to 20 reviewed cited facts can be selected; the API rejects unavailable, conflicting, hypothetical, unsupported or cross-company facts. Generation still creates unapproved drafts.
- Research reports provide category/source/status filters, financial periods, source-reported news dates, quotes/PDF page references, provenance and JSON export. Search, filters and export cover loaded records; load remaining pages for a complete export.

Migration `0010_company_intelligence` adds research-owned tables and job/source snapshots; existing lead/contact/campaign records remain intact. Historical job views use job-scoped facts and sources instead of mixing newer research into old reports. Research is **off by default** and does not run automatically after imports. Enabling it requires approved AWS access and may incur costs.

Detailed documentation: [architecture](docs/company-intelligence-architecture.md), [implementation and gaps](docs/company-intelligence-implementation.md), [research roles](docs/company-intelligence-agents.md), [sources and limits](docs/company-intelligence-sources.md), [API](docs/company-intelligence-api.md), [database](docs/company-intelligence-database.md), [setup](docs/company-intelligence-setup.md), and [testing](docs/company-intelligence-testing.md).

**Current local UI-test configuration:** Research is now explicitly enabled in the private `.env` at the operator's request. API, worker and scheduler were recreated and verified; `/intelligence/status` returns `enabled: true`, `model_configured: true`, `search_configured: false`. Local limits include 12 pages and crawl depth 5 (quick mode still caps these at 5 pages/depth 1). Existing credentials, AWS model settings, mail settings and daily send limit were not changed. No research was submitted to verify this switch. See the [complete session context](docs/session-context.md) and [UI test instructions](docs/company-intelligence-setup.md#test-from-the-ui).

**Subsequent live model fix:** The operator approved `BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-5-5` in `us-east-1` (US cross-region routing) and `RESEARCH_BROWSER_ENABLED=true`. The shared Bedrock request now omits the unsupported `temperature` parameter. A live server-default JSON invocation succeeded. The deployed text-only browser collector retrieved 763 characters of real ORIX homepage text, versus four characters from static HTML; external network restrictions remain in place. **48 targeted backend tests passed**, and an offline real-Chromium smoke passed. Earlier live jobs are retained but contain no supported facts; the final paid research retest after the text-rendering fix could not start because the execution environment stopped initializing. In the UI choose **Review & refresh research**, review the server default/consent, then **Refresh with new source collection** to avoid the old cached shell. Credentials and mail settings were not changed, and no mail was generated or sent. See [verification details](docs/company-intelligence-testing.md#live-model-and-browser-follow-up).

### Current Microsoft 365 migration status

The active meetings screen now uses Microsoft Entra OAuth and Microsoft Graph v1.0 calendar availability. Migration `0009_microsoft_oauth` adds isolated tables for expiring OAuth state and the encrypted MSAL token cache; the existing Google tables and migration history are retained. The OAuth flow binds short-lived state to the browser, verifies the configured tenant and organizer via Graph `/me`, requires delegated `Calendars.ReadBasic`, encrypts the serialized cache, and supports local disconnect. Availability calls `POST /me/calendar/getSchedule` and fails closed on Graph errors or incomplete data.

**This is availability only, not booking.** Outlook event creation, Teams meetings/join links, Outlook mail, replies, recording/transcript retrieval, OneDrive/SharePoint, S3 archival and Bedrock meeting intelligence are not implemented. The Google calendar API remains mounted as a legacy compatibility path, but the active meetings UI no longer uses it. Existing Google records are not deleted or migrated. The Microsoft implementation has mocked tests only; no real Entra tenant or Graph call has been tested. See [Microsoft 365 setup and implementation status](docs/microsoft-365-setup.md).

### Current platform-enhancement milestone status

**Milestone 1 (multi-sheet Excel import), Apollo contact management, the initial Lead 360 profile, and separate per-recipient outreach are implemented.** Workbooks show sheet names, non-empty row/column counts and previews; selected worksheets can be mapped independently; row reports include worksheet and source row. Duplicate candidates are detected across existing and earlier-in-the-same-import leads but are not merged. Importing contact rows as contacts and duplicate resolution actions remain unimplemented.

Migration `0006_multisheet_import` adds worksheet provenance and nullable industry, designation and location fields. Migration `0007_apollo_contact_management` adds normalized Apollo search snapshots and manually maintained contacts with soft removal. Migration `0008_enrollment_contact_link` optionally associates each campaign enrollment with one saved contact while preserving independent recipient threads. Existing records remain in place; old flat active-sheet mappings are supported by a compatibility path. Limits remain 10 MB compressed, 100 MB uncompressed, 50 worksheets, 100 columns per sheet and 5,000 non-empty rows across the workbook. Initial campaign analytics and rolling application send-budget status are also implemented; Gmail delivery/quota status is not queried. See [multi-sheet Excel import](docs/multi-sheet-excel-import.md), [Apollo contact management](docs/apollo-contact-management.md), [Lead 360 profile](docs/lead-360-profile.md), [multi-recipient outreach](docs/multi-recipient-outreach.md), [follow-up analytics](docs/followup-analytics.md), [email capacity and rate limits](docs/email-capacity-and-rate-limits.md) and [lead data relationships](docs/lead-data-relationships.md).

**File-level implementation map for the remaining requested milestones:**

| Milestone | Main files expected to change | Main compatibility/safety concerns |
| --- | --- | --- |
| Apollo contact management | Implemented: `backend/app/apollo.py`, `backend/app/models.py`, `backend/app/main.py`, `backend/migrations/versions/0007_apollo_contact_management.py`, `frontend/app/page.tsx`, `docs/apollo-contact-management.md` | Domain matching is a conservative association check, not deliverability verification |
| Initial Lead 360° profile | Implemented: `backend/app/main.py`, `backend/app/models.py`, `frontend/app/leads/[id]/page.tsx`, `docs/lead-360-profile.md`, `docs/lead-data-relationships.md`, `docs/backward-compatibility.md` | Preserve existing lead IDs and campaign histories; unbuilt modules remain explicit |
| Separate per-recipient outreach | Implemented: `backend/app/models.py`, `backend/app/followup_api.py`, `frontend/components/outreach-workspace.tsx`, `frontend/components/recipient-picker.tsx`, `frontend/app/followups/page.tsx`, `backend/migrations/versions/0008_enrollment_contact_link.py`, `docs/multi-recipient-outreach.md` | Atomic bulk selection/paste is supported; recipient file import remains unimplemented |
| Meeting participant experience | `backend/app/microsoft_graph.py`, meeting models/API, `frontend/app/meetings/page.tsx`, `backend/migrations/versions/0009_microsoft_oauth.py`, `docs/microsoft-365-setup.md` | Current Graph integration is availability-only; local-only and no real invitations |
| Email capacity and rate limits | Basic rolling application budget implemented: `backend/app/config.py`, `backend/app/mailer.py`, `backend/app/followup_api.py`, `frontend/components/outreach-workspace.tsx`, `.env.example`, `docs/email-capacity-and-rate-limits.md` | Gmail quotas are not queried; no pacing; use approved limits and enable sending only deliberately |
| Follow-up analytics | Initial campaign counts implemented: `backend/app/followup_api.py`, `frontend/app/followups/page.tsx`, `docs/followup-analytics.md` | Unique recipient denominators; no date filters/export; distinguish SMTP acceptance from delivery and approximate tracking |

## Architecture and data flow

```text
Browser: Next.js / React / TypeScript (localhost:3000)
    | REST
    v
FastAPI (localhost:8000) ---- PostgreSQL: leads, uploads, campaigns,
    |                         messages, replies, events, OAuth state
    |---- Apollo API: selected contact discovery/enrichment
    |---- AWS Bedrock: optional text generation/classification
    |---- Company Intelligence: jobs, source snapshots, facts, reports
    |---- Microsoft Entra OAuth + Graph: organizer availability
    |
    +---- Redis broker <---- Celery worker + Celery Beat
                              | import Excel
                              | bounded website/PDF research and Bedrock extraction
                              | Gmail IMAP polling / reply classification
                              + Gmail SMTP sending (disabled by default)
```

Compose runs `frontend`, `api`, `worker`, `scheduler`, `db` and `redis`. The API applies migrations on startup. PostgreSQL and Redis data use named Docker volumes. Excel uploads are currently stored in the database; no S3 upload storage is implemented. Celery Beat dispatches pending imports every 10 seconds, polls the inbox and dispatches due mail every 60 seconds, and dispatches reply classification every 120 seconds. Jobs execute asynchronously, but optional Bedrock actions requested in the UI and Microsoft availability requests run through the API.

This is a modular monolith, not microservices. Redis is the Celery broker; Kafka and separate per-workload queues are not implemented. Gmail OAuth is not implemented: the existing SMTP/IMAP integration uses a Gmail app password, independently of Google Calendar OAuth.

## Local setup

### Prerequisites

- Docker Desktop with Docker Compose and sufficient local resources.
- A private copy of `.env.example` as `.env`. Integration credentials are optional until that integration is used. Do not paste credentials into chat or commit `.env`.
- Use only synthetic or otherwise approved test data and approved service accounts.

From the project directory in PowerShell:

```powershell
Copy-Item .env.example .env
# Edit .env privately. Keep MAIL_SEND_ENABLED=false.
docker compose up --build
```

Open `http://localhost:3000` (or `/dashboard`) for the combined dashboard/import/company workspace, `/intelligence` for standalone research, `/followups` for campaigns, and `/meetings` for Outlook calendar availability. The API health check is `http://localhost:8000/health`; FastAPI's interactive API documentation is at `http://localhost:8000/docs`.

The containers share the `.env` values. The example PostgreSQL username and password are only for local development. Do not publish the database or Redis. To stop the services without removing persisted volumes:

```powershell
docker compose down
```

Stopping services does not delete the database, Redis data, uploads or credentials stored in volumes. Establish an approved backup, retention and deletion process before using sensitive data.

## Configuration reference

Set values in `.env`; no secrets belong in source code or the browser.

| Variable | Purpose and default |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection; Compose example points to `db` |
| `REDIS_URL` | Celery broker connection; Compose example points to `redis` |
| `APOLLO_API_KEY` | Required for Apollo search/enrichment; subject to account access and credits |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Account and app password for SMTP and IMAP; account must permit app passwords and IMAP |
| `MAIL_SEND_ENABLED` | `false` by default. Explicit `true` enables approved due emails in active campaigns, subject to all remaining gates |
| `MAIL_UNSUBSCRIBE_ENABLED` | `true` by default. Explicit `false` omits unsubscribe footer/headers and removes that HTTPS prerequisite; inbox checks, reply stops and suppressions remain enforced |
| `TRACKING_ENABLED` | `false` by default. Requests open pixels and approved-link redirects; they can only be included when an HTTPS base URL is configured |
| `PUBLIC_BASE_URL` | Empty by default. An approved HTTPS base URL is required when unsubscribe links are enabled and for public open/click tracking; this setting does not deploy or verify an endpoint |
| `DAILY_SEND_LIMIT` | Rolling 24-hour application attempt budget; default and example are 50. This is separate from Gmail quotas and does not guarantee sending capacity; use an approved account-specific limit |
| `AWS_REGION`, `BEDROCK_MODEL_ID` | Optional Bedrock features require a region and Converse-compatible model or approved inference-profile ID/ARN. The UI can explicitly override the model for individual draft-generation or research requests |
| `COMPANY_INTELLIGENCE_ENABLED` | `false` by default. Explicit opt-in enables research submission/retries; saved reports remain readable while disabled |
| `RESEARCH_MAX_CONCURRENT_AGENTS` | Concurrent category extraction calls per job; default 3, bounded to 1-5 |
| `RESEARCH_MAX_PAGES_PER_COMPANY`, `RESEARCH_MAX_CRAWL_DEPTH` | Code defaults 12 pages / depth 2; example and current local UI-test environment use depth 5. Quick research uses at most 5 pages / depth 1. Attempted page requests are also bounded |
| `RESEARCH_REQUEST_TIMEOUT`, `RESEARCH_MAX_DURATION_SECONDS` | Defaults 12 seconds per HTTP request and 120 seconds for source collection, not the entire Bedrock job. DNS/PDF parsing and in-flight AWS calls can extend cancellation latency |
| `RESEARCH_MAX_CONTENT_SIZE`, `RESEARCH_MAX_TOTAL_CONTENT_SIZE` | Defaults 2,000,000 bytes per response and 8,000,000 per crawl; failed downloads conservatively consume their reserved byte allowance |
| `RESEARCH_CACHE_TTL_HOURS`, `RESEARCH_MAX_RETRIES` | Defaults 24-hour freshness / 2 manual retries per failed role; completed role results are retained |
| `RESEARCH_DAILY_BUDGET`, `RESEARCH_DAILY_BEDROCK_CALLS`, `RESEARCH_DAILY_SOURCE_BYTES` | UTC-day application limits: 100 jobs, 500 model calls, 50,000,000 source bytes. Token usage is recorded when returned, not a dollar-cost guarantee |
| `RESEARCH_SEARCH_PROVIDER`, `RESEARCH_SEARCH_API_KEY` | Reserved only; no external search adapter is implemented. Setting these does not enable search |
| `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` | Single-tenant Entra web-app identifiers and secret for the delegated organizer connection |
| `MICROSOFT_REDIRECT_URI` | Must be `http://localhost:8000/microsoft/oauth/callback` |
| `MICROSOFT_ORGANIZER_EMAIL` | The one approved work-or-school organizer accepted by the callback and queried for availability |
| `MICROSOFT_TOKEN_ENCRYPTION_KEY` | Fernet key for encrypted OAuth flow state and serialized MSAL token cache; retain privately |
| `MICROSOFT_GRAPH_BASE_URL` | Must be `https://graph.microsoft.com/v1.0` |
| `MEETING_TIMEZONE` | IANA organizer timezone used to display slots; default `UTC` |
| `MEETING_DURATION_MINUTES` | Slot duration; default `30`, allowed 1-240 |
| `MEETING_WORKDAY_START_HOUR`, `MEETING_WORKDAY_END_HOUR` | Weekday working hours; defaults `9` and `17`, with start before end and end at most 24 |
| `MEETING_BOOKING_WINDOW_DAYS` | Maximum future availability range; default `30`, allowed 1-90. This does not enable booking |

For Microsoft calendar registration, delegated permissions, local key generation, and current migration limits, see [Microsoft 365 setup](docs/microsoft-365-setup.md). The app requests `User.Read` and `Calendars.ReadBasic` as delegated permissions only; application permissions are not configured. Tenant sign-in does not itself guarantee Graph consent, and tenant policy may require administrator approval. See [Google Workspace setup](docs/google-workspace-setup.md) only for the legacy Google calendar integration. For Bedrock, use an approved AWS credential provider available **inside** the API and worker containers; host credentials are not automatically passed through by this Compose file. Never share the Microsoft encryption key, client secret, or Gmail app password.

### Bedrock model and inference-profile setup

A live request with synthetic input returned an AWS `ValidationException`: the configured model cannot use on-demand throughput with its base model identifier and requires an inference profile. This is the observed drafting blocker, not evidence that every AWS permission or credential is invalid.

1. In a selected campaign's **AI draft generation** panel, select **Load AWS inference profiles**.
2. Select an approved profile and review its displayed routing regions. No profile is selected automatically; cross-region processing needs your organization's approval.
3. Enter approved factual context, expand a recipient, and select **Generate this recipient's drafts**. Review, edit, save and approve the resulting emails.

Discovery requires `bedrock:ListInferenceProfiles`. Converse generation requires `bedrock:InvokeModel` with access to the chosen profile and backing models, including any destination-region policy requirements. A listed profile is not proof of access or model compatibility. Discovery is paginated; **Load more profiles** retrieves the next page.

The draft dropdown applies only to explicit generation in that workspace and resets on page reload. The research form has its own explicit selector; its selected ARN is persisted on that research job and used by its worker. Neither selector updates environment settings or unrelated reply classification/response suggestions. For an approved persistent default, configure `BEDROCK_MODEL_ID` privately with the approved profile ID/ARN and recreate affected API/worker containers. Profile discovery alone does not require a migration; the research domain does.

Credential, permission, model/profile, throttling and malformed-response errors are surfaced without exposing raw AWS response text. Failed generation leaves saved drafts and approvals intact; successful regeneration asks for confirmation before replacing drafts and invalidating approval. Profile-based live generation remains unverified until an approved profile is selected and invoked.

Official references: [ListInferenceProfiles](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_ListInferenceProfiles.html), [inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles.html), and [Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html).

## End-to-end flow currently implemented

The following describes the available path and where it stops. Exercise it with synthetic data first; external service functions require correctly configured accounts and network access. Real sending requires explicit operator approval and remains subject to mailbox and message checks.

### 1. Import companies

1. On the combined dashboard, drag an `.xlsx` file onto the upload area or choose a file.
2. Review all worksheet previews, select one or more sheets, and map each sheet's columns independently. `Company name` is required on each selected sheet. Domain, email, revenue, contact number, remarks, key-person information, designation, industry and location are optional. Unmapped columns are retained as additional lead fields.
3. Start the import. The API stores the file and marks the batch pending; the scheduler dispatches it to the worker. Refresh is automatic in the UI.
4. Open the import report to see `imported`, `invalid`, and `duplicate` rows. Invalid rows include missing company names or malformed emails. Duplicate checks match normalized company names or emails against existing leads; candidates are skipped and shown for review, not merged. Failed batches can be retried.

The import reads all workbook worksheets; only sheets selected and mapped by sales are processed. Limits are 10 MB per file, 100 MB uncompressed, 50 worksheets, 100 columns per sheet and 5,000 non-empty data rows across the workbook. Formula cells use cached values, which may be empty; phone numbers stored as numbers may lose leading zeroes. Imports are transactional; repeated delivery does not intentionally create the batch twice. The UI shows up to 100 recent imports and 1,000 leads, so its counts are displayed-item counts, not necessarily database totals. See [multi-sheet Excel import](docs/multi-sheet-excel-import.md).

### 2. Find a company, research it and select contacts

1. Search the dashboard's company list by name or domain. This searches up to 1,000 loaded leads; it is not external domain discovery.
2. Select **Review**, enter the verified official website/domain and use **Save domain** if you only want to save it. This action does not call Apollo.
3. Select **Company research** (or the table's **Research** action), review the prefilled company/site, depth, AWS profile and processing consent, then explicitly submit. Quick research extracts company/news/leadership/signals; comprehensive adds financial/funding/competitors.
4. Follow persisted worker and role progress. Open quotes and source URLs; inspect dates, financial entity/currency/unit/period/scope and limitations. Missing facts remain unavailable. Retry failed roles or cancel bounded work; an in-flight operation may finish before cancellation takes effect.
5. Continue with **Domain & people** for Apollo or **Compose outreach** for Lead 360. Standalone research is also available under Company Intelligence without creating a lead.

**Apollo contact selection:**

1. Select **Review** on an imported company and enter its manually verified company domain, such as `example.com`, or website URL, such as `https://www.example.com/`. The API validates the URL and stores the normalized domain.
2. Select **Search Apollo**. The first page contains up to 25 candidates filtered for owner, founder, C-suite, VP, head and director seniority; there is no UI pagination.
3. Verify each candidate's identity and current company. Search results may include previous employers and do not provide the email directly. If Apollo has not matched the employer domain, explicitly check the inline employer-confirmation box to enable enrichment; there is no blocking confirmation popup.
4. Select **Select & enrich** for each desired person. The selected Apollo record is enriched and stored with its source and retrieval timestamp. A selected person may still have no email; enrichment may consume credits. Phone numbers and personal emails are not requested.

Missing emails do **not** automatically trigger Apollo. The lead's original email is not automatically replaced by an enriched contact email. For campaign enrollment, select saved people with emails or explicitly enter additional addresses.

### 3. Create and review a campaign

1. Open a company's **Lead 360** profile and use **Add people** to save names, designations and optional business emails. Use **Compose and approve emails** to work within the profile, or open **Follow-up management** for all companies. Create or choose a campaign. Choose manual approval for each message or automatic follow-ups with a separately approved saved sequence. Supply zero to five delays of 1-365 days; the default UI values are 3, 4 and 5 days after the previous accepted message.
2. While the campaign is a draft, choose a company (already fixed in Lead 360), check multiple saved people, optionally select the imported company email, and/or paste additional plain email addresses separated by commas, semicolons or whitespace. Select **Add N recipients**. Each addition accepts 1-100 recipients and is all-or-nothing: invalid, suppressed, mismatched-contact or duplicate addresses reject the entire addition. Each person gets a separate thread, never shared CC/BCC. Use a new draft campaign to add people after activation.
3. Expand a recipient, enter and save each initial/follow-up draft. Alternatively, load and select an approved Bedrock inference profile if needed, paste approved company/product context, optionally select up to 20 reviewed cited research facts for that company, and generate that recipient's sequence. A URL in the draft context alone is not browsed; research must be run separately first. There is no product catalogue. Review factual claims and edit as needed. Empty drafts remain editable without AWS.
4. Approve the exact saved initial email. In manual mode approve each follow-up individually. In automatic mode review and approve all saved follow-up drafts as a sequence. Editing drafts can invalidate approval and requires review again. No AI text is exempt from approval.
5. Activate the campaign. Activation schedules eligible initial messages; it does not override `MAIL_SEND_ENABLED=false`. The worker dispatches approved due messages only if sending is enabled and all checks pass. Pause the campaign or stop individual recipients as needed.

Lead 360 shows only the current company's recipient threads, but activation and pause still affect the entire selected campaign. A warning identifies hidden recipients from other companies; whole-sequence approval is not offered there while recipients are hidden. Review all recipients on the full follow-up page. The profile's historical overview/timeline is a snapshot; reload the page to update it after outreach changes.

### 4. Sending, follow-ups and safety gates

Sending is disabled by default. When explicitly enabled, the sender requires an active campaign and recipient, exact message approval, Gmail credentials, a successful and complete inbox sync, no suppression, no unresolved unmatched delivery report, and the configured sending limit. Automatic follow-ups also require current sequence approval. It checks the mailbox immediately before sending.

`MAIL_UNSUBSCRIBE_ENABLED=true` additionally requires an approved HTTPS base and appends the unsubscribe link and headers. Explicitly setting it to `false` omits both and removes only that prerequisite; it does not disable processing unsubscribe replies or checking suppressions. The operator must determine whether outreach without unsubscribe links is appropriate under applicable organizational/provider rules and consent requirements.

The sender uses Gmail SMTP on port 587 with STARTTLS. A successful SMTP response creates a `sent`/`smtp_accepted` record and schedules the next follow-up relative to that acceptance time, not relative to campaign creation. Enabling sending does not approve drafts or activate campaigns automatically.

**SMTP acceptance is not delivery.** A crash or disconnection may leave a message `sending` or `unknown`. Do not retry blindly: check Gmail, then use **Confirmed sent** or **Confirmed not sent**. A message confirmed not sent becomes a draft and requires new approval. SMTP cannot guarantee exactly-once delivery.

Real outreach requires appropriate organizational approval, recipient consent and operational testing. Enabling outbound SMTP does not authorize exposing the unauthenticated application.

### 5. Replies, bounces and meeting tasks

The worker polls the configured Gmail **INBOX** through IMAP over TLS. Matched replies stop automated follow-ups until sales reviews the reply and explicitly resumes the recipient. Unsubscribe requests and detected hard bounces add suppressions; resuming cannot override a suppression. Unmatched delivery reports require manual review before future sending proceeds.

Reply matching uses message headers and, in some cases, sender address. DSN and bounce matching are best effort; some replies or bounces may not be detected, and messages can arrive between the final inbox check and SMTP submission. Inbox failure or incomplete catch-up blocks sending. Review mailbox status and unmatched items.

Bedrock classification is advisory and may run in the background when configured or on request. It can classify an interested reply, a meeting request, an information request and other outcomes. A `meeting_requested` classification creates an in-app task for sales to arrange a meeting; sales can mark the task complete. Suggested replies are editable drafts and still require approval. **The automated meeting workflow stops here.**

### 6. Check organizer availability independently

1. Configure the Entra single-tenant web app, organizer account, and delegated permissions as described in [Microsoft 365 setup](docs/microsoft-365-setup.md).
2. On **Outlook calendar availability**, connect the configured work-or-school organizer and grant the requested permissions. The callback validates the tenant ID and confirms the organizer via Graph `/me`.
3. Enter a future range using the computer's timezone. The API queries the configured organizer with Graph v1.0 `POST /me/calendar/getSchedule`, then displays weekday slots in the configured organizer timezone and duration.
4. A Graph error, permission failure, or incomplete response returns an error rather than showing the calendar as free. Disconnect removes the local encrypted MSAL cache; it does not revoke tenant-side consent.

The connection uses delegated `User.Read` for profile verification and `Calendars.ReadBasic` for availability. Personal Microsoft accounts are not supported for `getSchedule`. Connection status reports locally stored credentials and scopes, not a live check that a token or permission will work. Availability can change immediately after it is queried. There is no slot selection, reservation, availability recheck for booking, Outlook event, Teams link or invitation. The older Google Calendar route and records remain as a legacy compatibility path and are not used by the meetings screen.

## Tracking and privacy

When optional tracking is enabled and an HTTPS base is configured, opens are recorded via a pixel and clicks only via explicitly added approved HTTPS links. If tracking is enabled without an HTTPS base and unsubscribe links are disabled, mail can send without pixels/redirects: the sender logs a warning and the UI explicitly reports tracking as unavailable. Original destination links are preserved; SMTP acceptance and matched replies remain recorded. Setting the tracking flag alone does not make an endpoint public.

Images can be blocked, cached or loaded by proxies; security scanners can follow links. Neither event proves a person read or clicked the email. Delivery confirmation is not provided by Gmail SMTP. The application stores reply content, tracking events, email addresses, uploads, the encrypted Microsoft token cache, and retained legacy Google credentials in its database.

The local Compose configuration does **not** expose tracking or unsubscribe URLs externally. A future real-outreach deployment needs an approved security and privacy design and separately accessible HTTPS public endpoints; never expose the unauthenticated API, dashboard, PostgreSQL or Redis. For the current pilot, do not add a tunnel, proxy, webhook or port forwarding. Follow applicable consent, disclosure and retention requirements before any use beyond synthetic local testing.

## Pros, cons and trade-offs

| Decision | Benefits | Limitations and risks |
| --- | --- | --- |
| Local unauthenticated pilot | Fast setup and simple sales workflow | No user isolation, roles or audit identity; unsafe for production or public access |
| FastAPI modular monolith | One backend and reusable business logic; simpler than microservices | Shared deployment and scaling; heavy integrations may affect API responsiveness |
| Redis/Celery background work | Imports and scheduled mail do not depend on an open browser | Requires worker, scheduler and Redis operation; queues are not separated by workload |
| PostgreSQL records and migrations | Persistent workflow state and schema versioning | Local volumes need backup and access control; uploads and sensitive content are stored in the database |
| Apollo sales-selected contacts | Human checks candidates before enrichment and credit usage | Requires a confirmed domain, eligible account and credits; results and emails may be absent or outdated |
| Bedrock-assisted text | Speeds drafting and classification; structured responses are checked | Outputs may be wrong, omit context or be influenced by untrusted text; requires review and approved AWS data handling |
| Combined import/research dashboard | One path from spreadsheet to company/domain review and outreach; same underlying leads and contacts | Company search is local and bounded, not automatic domain discovery; large workspaces need server-side search/pagination |
| Evidence-first company research | Verbatim values/quotes, persisted provenance, original financial qualifiers, partial success and historical job snapshots | Official sites can be incomplete, biased or stale; lexical checks do not establish factual truth, current employment or legal/accounting accuracy |
| Static HTTP/PDF rather than browser scraping | No browser execution or third-party subrequests; pinned connections and bounded crawl | Cannot research JavaScript-only pages, scanned PDFs, authenticated sources or external news; source failures can exhaust conservative budgets |
| Bounded parallel research | Category calls run outside the API with daily job/call/byte limits and manual retries | Shares the existing Celery queue; no durable recovery of a worker killed mid-job, dollar-cost ceiling, or total-job deadline; do not blindly retry stuck jobs |
| Gmail SMTP and IMAP | Uses an existing mailbox; replies and unsubscribe handling are integrated | Sending limits, app-password availability, best-effort mailbox matching and no reliable delivery/open confirmation |
| Human approval and suppressions | Reduces unintended outreach and preserves control | Adds manual work; race conditions and external mailbox behavior still need operational monitoring |
| Microsoft Graph availability | Shows organizer availability without manually opening Outlook | One configured work-or-school organizer; not a booking system, availability becomes stale, and delegated Graph consent is required |
| Optional open/click tracking | Provides indicative engagement signals | Proxy/scanner noise, blocking, privacy obligations and public-endpoint requirements |

## API and implementation map

The interactive API documentation lists complete request schemas. Major groups:

| Area | Key endpoints |
| --- | --- |
| Health and import | `GET /health`, `POST /batches`, `GET /batches`, `GET /batches/{id}`, `GET /batches/{id}/preview`, `POST /batches/{id}/start`, `POST /batches/{id}/retry` |
| Company Intelligence | `GET /intelligence/status`; `POST/GET /intelligence/research`; job detail/progress/retry/cancel; company facts/sources/category views; `GET /intelligence/reports/{id}`. Facts/sources accept `job_id`, `limit`, `offset` |
| Leads and Apollo | `GET /leads`, `GET /leads/{id}/profile`, `PUT /leads/{id}/domain`, `POST /leads/{id}/apollo/search`, `POST /leads/{id}/apollo/enrich`, `GET/POST /leads/{id}/contacts` |
| Campaigns and analytics | `GET/POST /campaigns`, `GET /campaigns/{id}`, `GET /campaigns/{id}/analytics`, `POST /campaigns/{id}/enrollments`, `POST /campaigns/{id}/enrollments/bulk`, `/activate`, `/pause`, `/approve-sequence` |
| Bedrock | `GET /integrations/bedrock/status` (configuration only, not an access test), `GET /integrations/bedrock/profiles?next_token=...`; `POST /enrollments/{id}/generate` accepts `context`, optional `inference_profile_id` and up to 20 `research_fact_ids` |
| Drafts and replies | `PUT /messages/{id}`, `POST /messages/{id}/approve`, `/reject`, `/resolve-send`, `/tracking-links`; `POST /campaigns/{id}/enrollments` (optional `contact_id`), `/enrollments/{id}/generate`, `/stop`, `/resume`; reply classification, response drafting and review endpoints |
| Mailbox and tasks | `GET /mailbox/status`, `GET /mailbox/capacity`, `GET /replies/unmatched`, `POST /replies/{id}/resolve`, `POST /suppressions`, `GET /sales-tasks`, `POST /sales-tasks/{id}/complete` |
| Microsoft calendar | `GET /microsoft/oauth/start`, `/callback`, `/status`; `POST /microsoft/oauth/disconnect`, `/microsoft/availability` |
| Legacy Google calendar | `GET /google/oauth/start`, `/callback`, `/status`; `POST /google/oauth/disconnect`, `/google/availability` (not used by the active meetings UI) |
| Public email links | `/public/unsubscribe/{token}`; opt-in `/public/open/{token}` and `/public/r/{token}`. These are local-only in the current deployment |

Important code locations: `frontend/app` contains the screens; `backend/app/main.py` registers API routes; `imports.py`, `apollo.py`, `followup_api.py`, `mailer.py`, `mailbox.py`, `bedrock.py`, `microsoft_graph.py`, `google_workspace.py` and `tasks.py` implement the respective workflows. `models.py` defines records; `backend/migrations/versions` contains Alembic migrations. Avoid sharing API tokens, unsubscribe tokens or OAuth codes in logs or support requests.

## Testing and verification

Backend tests use temporary SQLite databases and mock external integrations. From PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
Set-Location backend
..\.venv\Scripts\python -m pytest
Set-Location ..
```

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

The combined-dashboard/intelligence milestone passed **104 backend tests**, frontend type-check/production build and **6 Playwright browser tests**. Tests cover the research lifecycle, duplicate execution/submission, scoped historical facts/sources, partial retry and versioned reports, cancellation, rejected fabricated evidence, financial qualifiers, private/mixed-DNS/redirect rules, request/byte budgets and selected-fact outreach restrictions. Browser tests cover Excel upload/mapping -> company/domain search -> prefilled research, separate domain saving, mobile navigation, citations/financial/news filters, retry/cancel, Apollo confirmation and reviewed-fact generation without mail approval.

Fresh disposable SQLite upgrade to `0010_company_intelligence` and `alembic check` passed with no drift. A separate automated `0009` -> `0010` test preserved a seeded existing lead. All research, AWS, SMTP and browser API boundaries in automated tests are synthetic/mocked; the browser Excel fixture verifies UI/mapping, while backend import tests exercise real workbook parsing. These are not live vendor tests.

The preceding optional-unsubscribe milestone passed 76 backend tests. Its mail safeguards remain in the full regression, including inbox/suppression/reply-stop checks and clear network-timeout messages.

The earlier Microsoft milestone passed 46 backend tests. Microsoft OAuth/Graph, AWS generation and SMTP calls in automated tests are mocked; no real Entra tenant or Graph endpoint was used. A separate live synthetic Bedrock diagnostic established the inference-profile requirement, but successful approved-profile generation/research has **not** been verified. No real meetings or emails were created by these checks. Tests do not establish live Gmail delivery, Apollo enrichment, public tracking or production behavior. Live integrations require separately approved accounts, permissions, synthetic data and end-to-end testing.

Source changes are not automatically deployed into existing Docker containers. Rebuild the API, worker, scheduler and frontend after configuration/code changes. At the operator's explicit request, the local non-secret settings are now `MAIL_SEND_ENABLED=true`, `MAIL_UNSUBSCRIBE_ENABLED=false`, and `TRACKING_ENABLED=true`; credentials and the existing daily limit were not changed. No public tracking endpoint is configured, so public open/click signals are unavailable. A credential-like Apollo value was previously removed from the example environment file; rotate that value with Apollo if it was real.

**Live sending check:** The updated services were rebuilt, and API/frontend returned HTTP 200. Network-only checks from both Windows and the API container resolved Gmail DNS but timed out connecting to `imap.gmail.com:993` and `smtp.gmail.com:587`; Google HTTPS on port 443 connected. Credentials have therefore not been verified. Approved network/firewall access to both Gmail ports is required; do not disable TLS or inbox monitoring to bypass this blocker. At the check there was one draft campaign, four draft messages, no approved due messages and no new SMTP-accepted event. Sending being enabled does not mean any email was sent.

**Company Intelligence local rollout (16 November 2026):** A PostgreSQL custom-format backup was verified before the additive migration. API, worker, scheduler and frontend were rebuilt/recreated; database revision is `0010_company_intelligence` and the research task is registered on the worker. Read-only checks preserved **55 leads, 1 paused campaign and 4 draft messages**, with **0 SMTP-accepted events**. The combined dashboard is live at `/` and `/dashboard`. Research was disabled at the original rollout. In the subsequent operator-requested UI-test configuration update, research was enabled and bounded settings were added to the private `.env`; API/worker settings and readiness were verified after recreation. There were still **0 research jobs**. No paid research, test emails, meeting invitations, approvals, campaign activation or credential changes were performed. The Gmail network blocker above was not re-tested or bypassed.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Import stays pending | Check that `worker`, `scheduler`, Redis and PostgreSQL are running; inspect worker/scheduler logs. A failed batch has a retry action |
| Research unavailable or job remains queued | Check `COMPANY_INTELLIGENCE_ENABLED`, apply migration `0010` during approved deployment, and rebuild API/worker with matching code. Review `/intelligence/status`; imports do not start research automatically |
| Research has missing/partial findings | Read source and role errors. Check robots policy, official-site evidence, AWS/profile access and configured budgets. External search/JavaScript/OCR are not supported. Retry only failed roles; review costs before forced refresh |
| Apollo search fails or no email appears | Confirm the domain, API key, account permissions and credits. Search is limited to the first 25 candidates; enrichment can return no email |
| Bedrock action fails | Read the displayed error. The observed base-model failure requires an approved inference profile: load/select one in the campaign panel and review routing regions. Check discovery/invocation permissions, Converse support and credentials inside the relevant API/worker container; the UI override does not change background defaults |
| Mail does not send | Check the live sending status, exact draft approval, active campaign/recipient, Gmail app-password authentication and complete inbox sync, suppressions, unresolved attempts and daily limit. HTTPS unsubscribe is required only while `MAIL_UNSUBSCRIBE_ENABLED=true`; saving credentials alone does not enable sending |
| Gmail connection times out | Have the network administrator allow outbound TCP to `imap.gmail.com:993` and `smtp.gmail.com:587` from Windows/Docker. A timeout does not establish whether Gmail credentials are valid |
| Tracking is on but no opens/clicks appear | Check the UI tracking note and an approved publicly reachable HTTPS base URL. Without one no pixels/redirects are added. SMTP acceptance/replies remain recorded; even working public tracking is approximate |
| Mail status is `sending` or `unknown` | Inspect Gmail and reconcile manually; do not retry an uncertain attempt blindly |
| Microsoft connect fails | Check the exact localhost callback, tenant and client IDs, secret, configured organizer, Fernet key, delegated permissions and tenant consent policy; see [setup](docs/microsoft-365-setup.md) |
| No slots or availability error | Confirm future range, booking-window setting, weekday hours, timezone, Microsoft organizer connection and Graph permission. Errors do not mean the calendar is free |

For local service logs, use `docker compose logs api`, `docker compose logs worker`, or `docker compose logs scheduler`. Treat logs as potentially sensitive.

## Future end-to-end meeting flow

The intended next stages are: prospect expresses interest -> sales-approved scheduling invitation -> local-test booking page and token -> Graph availability recheck -> idempotent Outlook event and returned Teams join URL -> tenant-enabled recording/transcript handling -> private OneDrive/SharePoint and/or S3 archive -> reviewed Bedrock insights and MoM -> approved Jira tasks, owners, lead-stage history and turnaround tracking. These are roadmap items, not implemented functionality. Each stage requires implementation, official endpoint/permission verification, tests, appropriate tenant consent and its own review. The current localhost-only app cannot be opened by an external prospect; real bookings would require a separately approved HTTPS deployment and security design. No public tunnel or proxy is authorized for this pilot.
