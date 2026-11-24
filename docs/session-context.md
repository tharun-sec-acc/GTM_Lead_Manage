# GTM Prospecting session context and handoff

Updated: 24 November 2026, following the documentation refresh described below. The previous revision was the
17 November 2026 multi-product repository audit.

This is the canonical project handoff. It records actual implementation and verification, not completion of the full long-term product roadmap. Never copy credentials, tokens, private environment values or customer message content into this file.

## Latest update: advertising and lead capture — Release 3 (24 November 2026)

- Milestone 3. New `backend/app/advertising/` package: Meta Ads and Google Ads connectors (read-only),
  campaign mirroring with daily metrics, Meta Lead Ads and Google lead-form webhooks, website capture forms,
  attribution touchpoints and campaign → won-revenue reporting. New `docs/advertising-and-lead-capture.md`.
- Six new organization-scoped tables (`ads_connections`, `ads_campaigns`, `ads_metrics`, `lead_capture_forms`,
  `lead_capture_submissions`, `attribution_touchpoints`, `webhook_receipts`). Migration
  `0022_advertising_lead_capture` is the new head and is additive only.
- Captured leads are ordinary tenant `Lead` rows (`source` = `website_form` / `meta_lead_ads` /
  `google_lead_form`) plus a touchpoint carrying UTM, landing page, referrer and campaign id, so CRM scoring,
  duplicate detection and pipeline reporting apply unchanged.
- Endpoints under `/advertising` and `/api/advertising`; public capture at `POST /public/forms/{slug}/submit`,
  Meta delivery at `/public/webhooks/meta` (HMAC `X-Hub-Signature-256`, verify-token handshake) and Google at
  `/public/webhooks/google` (shared key, constant-time compare). No provider call can change spend.
- Frontend: `/advertising` workspace (connections, sync, campaign funnel table with CPL/cost-per-qualified,
  forms with an embeddable snippet, visible attribution caveat) and an **Advertising** sidebar entry.
- Tests executed: `backend/tests/test_advertising_lead_capture.py` — 12 passed; full backend suite —
  **294 passed, 0 failed** (8m43s); `tsc --noEmit` — clean. The earlier bash `fork` failure was worked around
  by `exec`-ing the native PowerShell binary directly, which also runs the migration-to-head test that now
  covers `0022`.

## Previous update: CRM core — pipelines, opportunities and tasks (24 November 2026)

- Milestone 2 of the roadmap. New `backend/app/crm/` package: organization-scoped pipelines with ordered
  configurable stages, opportunities tied to the existing `Lead`/`Contact` (amount, expected close date,
  owner, source, custom fields), append-only stage history, a shared activity timeline, CRM tasks,
  custom-field definitions and saved views. New `docs/crm-pipelines-and-opportunities.md`.
- `leads` gained additive columns: `owner_id`, `lifecycle_stage`, `qualification_status`, `score`, `source`,
  `source_detail`, `custom_fields`, `merged_into_id`. Migration
  `0021_crm_pipeline_and_opportunities` is the new head and is additive only.
- Deterministic, explainable lead scoring; duplicate detection by domain/company name/email and a merge that
  re-points contacts, opportunities, tasks and activities, deactivates conflicting contacts, marks the source
  `merged` and writes an audit row. Reporting via `GET /crm/summary` and `/crm/pipeline-summary`
  (open value, weighted forecast, won/lost, win rate, cycle time, tasks, needs attention).
- Every `/crm` endpoint resolves the tenant context; by-ID access returns `404` for another organization.
  Writes require `rep`; pipelines, stages, custom fields, merge and ownership reassignment require `manager`.
  All mutating endpoints are also mounted under `/api/crm`.
- Frontend: `/crm` board page (pipeline selector, metric tiles, stage moves, Won/Lost, tasks, attention
  panel) and a **Sales pipeline** sidebar entry. Read-only members see it without write controls.
- Tests written but **not executed**: `backend/tests/test_crm_pipeline.py` (default pipeline, opportunity
  lifecycle plus history and summary, lost-reason validation, cross-tenant isolation, stage deletion guards,
  role gates, scoring, duplicate merge, tasks/custom fields/saved views). The shell still cannot fork child
  processes (`fork: Resource temporarily unavailable`, exit 254), so pytest, `tsc` and `next build` could not
  run and no screen was rendered.

## Previous update: SaaS foundation — billing entitlements and tenant isolation (24 November 2026)

- Audited the repository against the all-in-one platform brief. The audit, feature inventory, gap list and
  phased roadmap are in [the platform audit](saas-platform-audit.md). Auth, organizations, roles, invitations,
  encrypted provider credentials and audit rows already existed; the two real foundation gaps were the missing
  billing/entitlement system and uneven tenant enforcement in `backend/app/main.py`.
- Added `backend/app/billing/` (plan catalogue stored as data, one subscription per organization with trial and
  period state, monthly usage meters, limit checks, feature gates) with `/billing/*` endpoints in
  `backend/app/billing/routes.py`, mounted at `/billing` and `/api/billing`. Migration
  `0020_billing_foundation` is the new head and adds `billing_plans`, `billing_subscriptions`,
  `billing_usage_records`; the catalogue is seeded on first use, so pricing stays editable data.
- Enforcement added to existing behaviour: member invitations return `402` when the seat allowance is reached,
  and provider-accepted emails increment `email_sends_monthly`. `BILLING_ENFORCE_LIMITS=false` is the kill switch.
- Closed cross-tenant by-ID access in `main.py`: lead profile, domain update, Apollo search/results/enrich,
  lead contacts create/update/delete and all batch by-ID endpoints now resolve through the tenant context and
  return `404` for another organization's record. Legacy rows with a NULL `organization_id` remain visible only
  to the anonymous fallback context.
- Frontend: new `/settings/billing` page and a **Billing & Plan** sidebar entry.
- Tests written but **not executed**: `backend/tests/test_billing_foundation.py` (catalogue and default
  subscription, role-gated and audited plan change, seat-limit `402`, usage metering, cancel/resume, and
  cross-tenant `404` for leads, contacts and batches). The shell still cannot fork child processes
  (`fork: Resource temporarily unavailable`, exit 254), so pytest, `tsc` and `next build` could not run and no
  screen was rendered. See [billing and subscriptions](billing-and-subscriptions.md).

## Previous update: documentation refresh (24 November 2026)

- The README and handoff had drifted substantially behind the implementation. The code contains ten further
  feature domains beyond the product-workspace milestone: SaaS authentication and organizations
  (`0019_saas_multi_tenant_auth`), unified meetings (`0015_unified_meetings`), the advanced research engine
  (`0016_advanced_research_engine`), public booking (`0017_public_booking_system`), Zoho CRM
  (`0018_zoho_crm_integration`), market intelligence (`90a32bdfdc2e`, `a23dfc0ad970`) and OAuth email accounts.
- Documentation was completed against the source. New pages: [authentication and organizations](authentication-and-organizations.md),
  [email accounts and sending](email-accounts-and-sending.md), [meetings and booking](meetings-and-booking.md),
  [Zoho CRM integration](zoho-crm-integration.md) and [market intelligence](market-intelligence.md). The README
  status tables, environment reference, route list, API map and troubleshooting were rewritten; the Microsoft
  and Google setup pages no longer describe meetings, booking, artifacts and S3 archival as unimplemented.
- `.env.example` was extended with the settings read by `backend/app/config.py` but missing from the example
  (S3 archive, browser wait, keyless discovery switches and the optional cookie domain), and the session-cookie
  guidance was clarified. The environment keeps a `[TEMPLATE]` marker line at the top of the file; that line was
  not editable with the available file tools.
- No application code, migration, credential or private environment value was changed. Sending, research and
  provider flags remain as the operator left them.
- Verification was limited by the local shell: every command that spawns a child process failed with
  `fork: Resource temporarily unavailable` (exit 254), so the backend suite, `tsc` and `next build` could not be
  run for this revision. Historic pass counts below remain historical. Re-run `pytest` from `backend` with
  `PYTHONPATH=.` and `npm run typecheck && npm run build` from `frontend` before relying on them.

## Previous update: product workspaces implemented (17 November 2026)

- Product workspaces are live in the existing application. Migration head at that milestone was `0012_product_attribution`;
  `0011_products` creates the product, association, opportunity, template, version, attachment and research
  override tables, and `0012_product_attribution` seeds four products and attributes existing leads,
  campaigns and batches to `General / Unassigned`.
- Imports, campaign creation and recipient enrollment now validate product ownership on the server. Importing
  an existing master company associates it with the product instead of duplicating it. Campaign enrollment
  rejects a company that is not associated with the campaign's product (atomic for bulk additions).
- `/overview` is the consolidated dashboard; `/products/{slug}` provides overview, companies, import,
  research, contacts, campaigns, templates, meetings and analytics workspaces.
- Verification: full backend suite **180 passed** (`..\.venv\Scripts\python.exe -m pytest -q`, 104s). The
  earlier `TestClient` stall did not reproduce. Frontend type-check/build and Playwright were not run because
  Node.js/npm were unavailable on `PATH` in this session, so the new UI is not yet verified in a browser.
- No live Apollo, Bedrock, Gmail, Microsoft Graph or research calls; no credential or `.env` changes; no
  migration applied to the operator's PostgreSQL database.
- Documentation: [multi-product architecture](multi-product-architecture.md), [product API](product-api.md),
  [migration and deployment](product-migration-and-deployment.md).

## Historical request: incremental multi-product platform

The operator supplied a 906-line master implementation specification. It requires a repository/baseline audit before code changes, shared master companies with product associations, hybrid versioned templates, shared company research with separate product opportunities, scoped workflows, rich editing/private attachments and milestone-gated regression/deployment.

- Read the [audit and implementation map](multi-product-implementation-plan.md) before starting implementation. It records inspected models/routes/import/sending/research/UI/deployment, proposed table/API/file changes and milestone A-K gates.
- Current product status: **not implemented; milestone A baseline gate blocked**. No product models, migration, API or UI code was changed.
- New baseline: frontend type-check and production build passed; six existing mocked browser tests passed in 53.3 seconds.
- Full backend suite stalled after 12 completion dots, with no final result. A bounded diagnostic of the first research test timed out entering `TestClient`: AnyIO/Windows asyncio setup was blocked in `socket.accept` for its self-pipe, before the test body. Cause remains unconfirmed; do not report an assertion failure or passing full baseline.
- Subsequent baseline-only diagnostics: Python 3.14.10 with Windows Proactor policy uses TCP fallback for `socketpair`; standalone pairing timed out, and a normal `127.0.0.1` self-connection returned **10013 / WSAEACCES**. Stop denied socket attempts until sandbox policy allows the Python process's ephemeral loopback connections; do not patch application/event-loop code to bypass the restriction.
- Docker environment overrides are absent; the default config path resolves to `C:\Users\SI1107\.docker\config.json` (not reopened after the earlier config-access warning). Its original warning text was not retained. Docker engine/containers/database remain unverified, not failed with an invented endpoint error. Manual policy access to Docker config/active engine and a running Docker Desktop are needed before retry.
- Docker availability probe reported configuration access denied under current sandbox constraints. No denied-path retries, permission changes, Docker service changes, database revision/count inspection, new backup or migration were attempted.
- Only the audit document, README link/status and this handoff were updated. Private environment/credentials and live provider operations were untouched. Test-owned helper processes were stopped by their runners; the stalled pytest process was explicitly stopped.
- Resolve baseline/runtime-access gates before milestone B. Do not apply a migration or start Compose's automatic `alembic upgrade head` without a new verified backup.

## Latest follow-up (supersedes earlier activation-only observations)

- The operator reported `ResourceNotFoundException` and approved discovered profile `us.anthropic.claude-sonnet-5-5` as the private local default in `us-east-1`, with US cross-region routing approved. No credential/mail settings changed.
- A live synthetic invocation exposed unsupported `temperature`; the shared Converse helper now omits it. A subsequent server-default request returned `{"ok": true}` (47 input / 9 output tokens).
- Real ORIX jobs exposed its four-character static JavaScript shell. The operator explicitly approved a bounded Playwright fallback and paid research retest. `RESEARCH_BROWSER_ENABLED=true` locally, false by default.
- Added `backend/app/company_intelligence/sources/browser.py`, Playwright requirements and Chromium/system dependency installation in the backend Dockerfile. API/worker/scheduler were rebuilt/recreated successfully. Browser requests use the same public-IP-pinned broker, robots/byte/time limits and same-site GET policy; direct networking, external assets/APIs, images/media/WebSockets/service workers remain blocked. Rendering is explicitly text-only; stylesheet loads resolve without fetching visual dependencies so external font failures cannot block SPA preload gates.
- Real offline Chromium smoke passed; 48 targeted backend tests passed. Earlier full-suite/frontend/migration results below are historical, not repeated for this follow-up.
- Latest live collector-only ORIX check: one `playwright` homepage source, 763 extracted characters, 1,383,815 fetched bytes, no notes. This demonstrates live text retrieval, not comprehensive site coverage.
- Earlier persisted live jobs remain partial with zero facts: `e26f9785-0216-4f3a-9c4e-0aafb8fb3deb` (static shell/schema error) and `f91523fa-7ea9-4990-9fd0-28012b347367` (browser stylesheet dependency; all roles completed). Prompts now include the actual evidence schema/minimum quote bound.
- **Final end-to-end report retest is pending:** execution environment initialization twice failed before issuing the final POST. Do not claim a new job/report, supported ORIX facts or completed full-flow success after the final rendering fix. Do not bypass environment restrictions.
- Next: in the ORIX job UI choose **Review & refresh research**, use the configured server model, approve processing and select **Refresh with new source collection**. Ordinary Start can reuse a previous partial job; failed-role retry is not equivalent to fresh collection. Review actual source-backed findings and unavailable financial/news categories.
- No mail/draft generation, approval, activation or sending was performed. See [detailed verification](company-intelligence-testing.md#live-model-and-browser-follow-up).

## 1. Current application and deployment

- Workspace: `C:\Users\SI1107\Denso\GTM_prospect_mvp`; Windows; not a Git repository at the last check.
- Modular monolith: Next.js/React/TypeScript frontend; FastAPI/SQLAlchemy backend; PostgreSQL; Celery worker/beat with Redis.
- Local Docker Compose services: `frontend`, `api`, `worker`, `scheduler`, `db`, `redis`.
- Frontend: `http://localhost:3000`; API: `http://localhost:8000`; OpenAPI: `http://localhost:8000/docs`.
- UI/API ports remain loopback-only. Database/Redis ports are unpublished. Authentication and organization tenancy are implemented; a configurable anonymous fallback (`AUTH_ALLOW_ANONYMOUS_FALLBACK`) can still map unauthenticated calls to the default organization. Do not expose this pilot publicly.
- Database revision at the last recorded live check: `0010_company_intelligence`; the current migration head in the repository is `0020_billing_foundation` (see [authentication and organizations](authentication-and-organizations.md)). A verified PostgreSQL custom-format backup was retained in the current Copilot session's files before migration: `gtm-before-intelligence-20261116.dump`. It contains application data; do not publish it.
- Last read-only state: 55 leads, 1 paused campaign, 1 enrollment, 4 draft messages, 0 SMTP-accepted events, 0 research jobs. These are timestamped observations, not constants.

## 2. Implemented milestones

### Imports, leads and contacts

- Multi-sheet Excel upload, sheet previews/mapping, background imports, per-row validation/provenance and duplicate reporting.
- Domain/URL validation and normalization; manually saving a domain is independent of Apollo.
- Persisted Apollo people-search snapshots; salesperson-selected enrichment with current-employer confirmation and conservative company-domain checks.
- Inline employer-confirmation checkbox replaces the blocking browser confirmation popup.
- Manual contact create/edit/soft-remove; existing lead/contact IDs and campaign histories retained.

### Outreach and mail safeguards

- Shared outreach editor in the campaign screen and Lead 360.
- Atomic enrollment of 1-100 recipients from selected saved contacts or pasted addresses; each gets an independent thread, never shared CC/BCC.
- Exact-content message approvals; edits/regeneration invalidate approval; per-recipient suppression/reply-stop controls.
- Gmail SMTP sending and IMAP reply polling; application send budget; optional unsubscribe headers/footer and optional tracking.
- Explicit Bedrock inference-profile discovery/pagination/selection; actionable AWS errors; no automatic cross-region profile choice.
- Existing operator-approved non-secret mail settings remain sending enabled, unsubscribe footer disabled, tracking requested and daily send limit 500. No public HTTPS tracking base was configured at the previous check, so public open/click tracking is unavailable.
- Gmail IMAP 993 and SMTP 587 previously timed out from Windows and Docker while Google HTTPS worked. Credentials could not be verified. Do not bypass inbox monitoring or TLS; approved network access is required. This network check was not repeated for research activation.

### Microsoft calendar

- Single Entra delegated organizer connection with encrypted MSAL cache and Graph v1.0 availability.
- Availability only: no booking, Outlook event, Teams invitation/join link, recording/transcript or meeting follow-up pipeline.
- Legacy Google calendar records/routes remain for compatibility; the active calendar UI uses Microsoft.

### Combined dashboard and research

- `/` and `/dashboard` share the same implementation rather than separate competing overview/import pages.
- DENSO light/red sidebar shell, mobile navigation, real loaded-record metrics, Excel import, local company/domain search and guided workflow.
- Selected-company workbench provides research, domain/people review, Lead 360 and compose links. Previous-company people are cleared; late responses cannot overwrite another company's selected contacts.
- Lead 360 embeds research and the shared outreach editor.
- Standalone research at `/intelligence`; job workspace at `/intelligence/jobs/{id}`.
- Source/citation/financial/status/category/date filters, provenance, partial-result visibility and JSON export of loaded records.

## 3. Company Intelligence backend

The research domain is under `backend/app/company_intelligence`.

1. Validate company/domain and optional existing lead association.
2. Reuse an active/fresh matching job or persist a new queued job.
3. Run bounded official-site static HTTP/HTTPS collection and optional text-PDF extraction in Celery.
4. Run seven separate objective-specific Bedrock extraction roles: company, news, financial, funding, leadership, competitors and signals.
5. Run deterministic verification: source/quote/value support, financial qualifiers and scoped conflict checks.
6. Run deterministic synthesis using supported persisted findings, not new generated factual claims.
7. Persist progress, source snapshots, facts/citations, role errors/retries, usage and versioned reports.

Important behavior:

- Connections pin a validated public IP with original TLS SNI/Host. Private/reserved/mixed DNS, unsupported schemes/ports/credentials and off-domain redirects are rejected.
- Robots policy and redirect targets are checked. Crawl-delay/rate, attempted requests, pages/depth, bytes, source duration and PDF page limits bound collection.
- Failed downloads conservatively consume their byte allowance; daily job/model-call/source-byte budgets are atomic.
- Values and quotes must be extractive evidence substrings. Numerical financials also require supported entity, currency, unit, period and standalone/consolidated scope.
- Verification is lexical/structural, not an independent factual, accounting, legal or current-employment audit.
- Job-to-source associations preserve historical snapshots. Facts/sources default to the latest job; a requested historical job must belong to that company.
- Failed-role retry retains successful facts and produces a new report version. Cancellation is cooperative; in-flight work may finish its bounded operation.
- Duplicate worker execution cannot claim an already-running/completed job. Automatic recovery after a worker dies mid-job is not implemented.
- Selected `research_fact_ids` (maximum 20) are resolved server-side for the enrollment's lead. Unsupported/conflicting/hypothetical/cross-company findings are rejected. Research selection/generation never approves mail.

## 4. Current research environment

The latest operator request explicitly authorized adding research settings to the private `.env` and enabling the feature for UI testing. No credentials were changed or copied into documentation.

| Setting | Active local value |
| --- | --- |
| Feature | Enabled |
| Parallel extraction roles | 3 |
| Comprehensive crawl | Up to 12 pages, depth 5 |
| Quick crawl | Up to 5 pages, depth 1 |
| HTTP request / source duration | 12 / 120 seconds |
| Cache / failed-role retries | 24 hours / 2 |
| Response / cumulative source bytes | 2,000,000 / 8,000,000 |
| UTC-day jobs / model calls / source bytes | 100 / 500 / 50,000,000 |
| External search provider/key | Empty; no adapter implemented |
| Latest approved AWS default | `us.anthropic.claude-sonnet-5-5`, `us-east-1`; credentials preserved |
| Browser fallback | Enabled locally; disabled by default |

The complete non-secret environment block and step-by-step UI test are in [research setup](company-intelligence-setup.md). `.env.example` intentionally keeps the feature disabled for fresh installations. Its depth 5 setting was retained; the Python code's fallback depth remains 2.

API, worker and scheduler were recreated with existing images to apply these settings. Read-only checks confirmed feature/settings agreement in API and worker, worker research-task registration, model configuration present, search unavailable, HTTP readiness and unchanged data counts. No research was started.

The shared browser was opened at `/intelligence`: the research form is visible, the API reports enabled, and Start research remains disabled without the required input/consent. No profile discovery, paid research or email action was triggered.

## 5. How the user should test next

1. Refresh the dashboard and select an imported company using name/domain search.
2. Confirm/save its official domain, then open Research; alternatively use standalone intelligence.
3. Start with Quick, or choose Comprehensive for all categories.
4. Load AWS profiles and explicitly choose an approved profile, reviewing routing regions. A previous diagnostic found the then-configured base model needed an inference profile. A configured model or listed profile is not proof of invocation access.
5. Review processing/cost consent and explicitly submit Start research. This is the point at which website requests and chargeable AWS calls may occur.
6. Inspect actual job/role progress, source passages, dates, limitations and financial scope. Retry only eligible failures; refresh may incur new calls.
7. To test draft generation, open Lead 360, select reviewed facts and approved product context, then generate and review. Do not approve/activate campaigns just to test research.

Live model invocation and real browser source collection have now been verified separately; the final useful cited-report retest remains pending. Do not describe activation, mocked tests or empty earlier reports as full-flow success.

## 6. API and file map

Research routes:

- `GET /intelligence/status`
- `POST/GET /intelligence/research`
- `GET /intelligence/research/{id}` and `/progress`
- `POST /intelligence/research/{id}/retry` and `/cancel`
- `GET /intelligence/companies/{id}`, `/facts`, `/sources` and category aliases
- `GET /intelligence/reports/{id}`
- Existing draft-generation API accepts optional `research_fact_ids` and explicit inference-profile override.

Key implementation files:

- [Dashboard/import/workbench](../frontend/app/page.tsx), [dashboard route](../frontend/app/dashboard/page.tsx), [overview metrics](../frontend/components/workspace-overview.tsx), [shell](../frontend/components/app-shell.tsx), [styles](../frontend/app/style.css).
- [Research workspace](../frontend/components/intelligence-workspace.tsx), [report](../frontend/components/intelligence-report.tsx), [fact picker](../frontend/components/research-fact-picker.tsx), [API types](../frontend/lib/intelligence.ts).
- [Lead 360](../frontend/app/leads/[id]/page.tsx), [outreach editor](../frontend/components/outreach-workspace.tsx).
- [Research API](../backend/app/company_intelligence/api.py), [orchestrator](../backend/app/company_intelligence/orchestrator.py), [models](../backend/app/company_intelligence/models.py), [source adapter](../backend/app/company_intelligence/sources/website.py), [extraction](../backend/app/company_intelligence/agents/runner.py), [budgets](../backend/app/company_intelligence/services/budget.py).
- [Settings](../backend/app/config.py), [shared Bedrock integration](../backend/app/bedrock.py), [Celery tasks](../backend/app/tasks.py), [outreach validation](../backend/app/followup_api.py).
- [Migration 0010](../backend/migrations/versions/0010_company_intelligence.py) adds ten research-owned tables, including job/source associations, without resetting existing data.
- [Research tests](../backend/tests/test_company_intelligence.py), [browser tests](../frontend/tests/intelligence.spec.ts), [Playwright configuration](../frontend/playwright.config.ts).

## 7. Verification evidence and local commands

Last code-validation milestone:

- 104 backend tests passed, including 28 research cases.
- 6 mocked Chromium browser workflows passed, including Excel mapping -> domain search -> same-company research.
- Frontend TypeScript check and production build passed.
- Fresh disposable SQLite migration to 0010 and Alembic no-drift check passed.
- A separate automated 0009 -> 0010 upgrade preserved an existing seeded lead.
- Docker builds/deployment passed; actual local PostgreSQL revision, research tables, Celery task registration, readiness and existing record counts were verified.
- Desktop/mobile layout checks passed; no horizontal overflow at 390px. Temporary test server on port 3101 was stopped.

These tests mocked external research/AWS/mail boundaries. They do not prove live website coverage, AWS invocation, Gmail delivery, external Graph access or complete PostgreSQL/Celery recovery under failures.

The latest environment-only activation used read-only readiness/settings checks, not another full suite run or paid research.

From `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

From `frontend`, with Node.js available:

```powershell
npm ci
npx playwright install chromium
npm run typecheck
npm run build
npm test
```

The local Python interpreter is the workspace `.venv\Scripts\python.exe`. Node 22.23.5 is available in the current Copilot session files under `node-v22.23.5-win-x64`; it may need to be added to PATH. Do not reuse a session-specific absolute path on another computer.

## 8. Remaining gaps and boundaries

- No external search/news/RSS/registry adapter, OCR, authenticated crawling or automatic official-domain discovery. Research uses the supplied official host (and `www`) only; opt-in text-only Playwright does not support every JavaScript dependency.
- No complete coverage guarantee, financial normalization, valuation/market-share estimation, independently verified factual accuracy or product-catalogue matching.
- No report PDF/Excel export; JSON export covers loaded records.
- No separate research queue, hard total-job deadline, dollar budget or automatic stuck-worker recovery.
- No duplicate-merge workflow, full sales ownership/stage history or complete CRM pipeline.
- No Calendly, Dataverse, Power Automate or external CRM integration.
- No actual Microsoft booking/Teams lifecycle, recording/transcripts/S3/MoM/Jira automation.
- No production/public deployment, monitoring or backup policy; authentication and tenancy are implemented but unverified against a live external identity setup.
- Gmail network access and separately approved live vendor testing remain operational prerequisites.

Do not treat these gaps as implemented because research is now enabled. Preserve existing message approvals, suppression/inbox controls, local-only ports and user records.

## 9. Related documentation

See [README](../README.md), [architecture](company-intelligence-architecture.md), [implementation status](company-intelligence-implementation.md), [roles](company-intelligence-agents.md), [sources](company-intelligence-sources.md), [API](company-intelligence-api.md), [database](company-intelligence-database.md), [setup](company-intelligence-setup.md), [testing](company-intelligence-testing.md), [Lead 360](lead-360-profile.md), [outreach](multi-recipient-outreach.md), [Apollo](apollo-contact-management.md) and [Microsoft setup](microsoft-365-setup.md).
