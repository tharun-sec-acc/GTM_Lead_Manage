# GTM Prospecting session context and handoff

Updated: 17 November 2026, following the multi-product repository audit and baseline attempt.

This is the canonical project handoff. It records actual implementation and verification, not completion of the full long-term product roadmap. Never copy credentials, tokens, private environment values or customer message content into this file.

## Latest update: product workspaces implemented (17 November 2026)

- Product workspaces are live in the existing application. Migration head is `0012_product_attribution`;
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
- UI/API ports remain loopback-only. Database/Redis ports are unpublished. There is no application login or role isolation. Do not expose this pilot publicly.
- Database revision: `0010_company_intelligence`. A verified PostgreSQL custom-format backup was retained in the current Copilot session's files before migration: `gtm-before-intelligence-20261116.dump`. It contains application data; do not publish it.
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
- No app authentication or production/public deployment.
- Gmail network access and separately approved live vendor testing remain operational prerequisites.

Do not treat these gaps as implemented because research is now enabled. Preserve existing message approvals, suppression/inbox controls, local-only ports and user records.

## 9. Related documentation

See [README](../README.md), [architecture](company-intelligence-architecture.md), [implementation status](company-intelligence-implementation.md), [roles](company-intelligence-agents.md), [sources](company-intelligence-sources.md), [API](company-intelligence-api.md), [database](company-intelligence-database.md), [setup](company-intelligence-setup.md), [testing](company-intelligence-testing.md), [Lead 360](lead-360-profile.md), [outreach](multi-recipient-outreach.md), [Apollo](apollo-contact-management.md) and [Microsoft setup](microsoft-365-setup.md).
