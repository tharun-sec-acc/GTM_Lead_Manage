# SaaS platform audit, feature inventory and roadmap

Audited: 24 November 2026, on the existing repository, before this milestone's changes except where
marked. This document is the audit deliverable requested for the all-in-one platform programme: what
exists, what is partial, what is missing, what changed, and what comes next.

## 1. Method and its limits

The audit read the repository directly: routers, models, migrations, Celery tasks, configuration,
frontend routes and tests. Classification is by **behaviour visible in code**, not by the presence of a
route, model or screen alone.

Verification limits for this milestone:

- The local shell cannot fork child processes (`fork: Resource temporarily unavailable`,
  `Win32 error 299`), so `pytest`, `npm run typecheck`, `next build` and the dev server could not run.
  Every test count quoted below is **historical**, not a result produced today.
- `frontend/node_modules` is absent, so the frontend has not been type-checked or rendered.
- Live provider behaviour (Meta, Google Ads, WhatsApp, SMS, mailbox OAuth, Zoho) was not exercised.

## 2. Architecture assessment

Modular monolith, unchanged and appropriate for the current stage:

```text
Next.js 15 / React 19 (app router, 34 pages)
        | REST + JWT (Bearer header or HttpOnly cookie)
FastAPI (modular routers) --- PostgreSQL (Alembic, additive migrations)
        |---- AWS Bedrock, Apollo, Google, Microsoft Graph, Zoho CRM
        +---- Redis broker -> Celery worker + Beat (scheduled crawls, sync, cleanup)
```

Strengths to preserve:

- One `Lead`/`Contact`/`Batch` core reused by research, outreach, meetings, booking and products, so the
  "one company record" idea is already partly real.
- Every long-running provider operation is a Celery job with status, retry and logs.
- Provider credentials are encrypted at rest (`OAuthConnection`, `ZohoConnection`) and integration
  routers already expose connect/disconnect/status.
- Organizations, roles, invitations, revoked tokens, password reset and audit rows exist, so the
  tenancy skeleton precedes the new modules.

Structural weaknesses found:

1. **Billing was a label, not a system.** `organizations.plan` was free text with no catalogue,
   subscription, usage meter or entitlement check. Fixed in this milestone.
2. **Tenant enforcement was uneven.** `get_tenant_context` was used in only 10 files. Lead- and
   batch-scoped endpoints in `main.py` resolved records by primary key alone, so a member of one
   organization could read or change another organization's lead, contacts and import batch if they
   knew the ID. Fixed in this milestone for those endpoints.
3. **Legacy NULL-organization rows** were visible to every authenticated tenant through
   `organization_id IS NULL` clauses. Now those rows resolve to the anonymous legacy/default context
   only (see [billing and subscriptions](billing-and-subscriptions.md) and `tenant_scope_clause`).
4. **Audit logging is sparse.** Only registration, login, sent email, reply sync and (now) billing
   changes write `AuditLog` rows. CRUD on leads, campaigns, integrations and permissions is not audited.
5. **No rate limiting, no MFA/SSO, no email-verification delivery.** `JWT_SECRET_KEY` still ships with a
   development default.
6. **Unsafe defaults** recorded in earlier docs remain: `AUTH_ALLOW_ANONYMOUS_FALLBACK=true`, the
   unauthenticated inbound market-intelligence webhook, and an SSR-ish webhook target check that does
   not validate SSRF for outbound subscriptions.

## 3. Implementation inventory

Classification: **Working** = complete path in code; **Partial** = some of the path exists;
**Credential-gated** = code exists but needs provider approval/keys; **Mocked** = tests stub the provider;
**Missing** = no implementation.

| Area | Classification | Evidence and gaps |
| --- | --- | --- |
| Email/password auth, JWT access + refresh, revocation, password reset | Working | `app/auth/routes.py`, `security.py`; lockout after failed attempts; no MFA, no verification email delivery |
| Organizations, membership, role hierarchy, invitations, org switching | Working | `app/auth/*`, roles `owner/admin/manager/rep/read_only` (the brief's 9 roles are not all modelled) |
| Tenant isolation | Partial → improved | Context dependency exists; by-ID holes in `main.py` closed today; other routers resolve children through a tenant-checked parent |
| Audit logs | Partial | Model plus four call sites before this milestone (registration, login, sent email, reply sync) and two added for billing; no audit UI, no export |
| Billing, plans, entitlements, usage | **Working (new)** | `app/billing/*`, migration `0020`, `/settings/billing`; no payment provider |
| Excel import, mapping, duplicate review | Working | `app/imports.py`, Celery import task |
| Lead/company profile, contacts, Apollo discovery | Credential-gated | Apollo key required; enrichment is manual by design |
| Company intelligence research | Credential-gated | Bedrock + bounded crawling; Playwright fallback opt-in |
| Automotive market intelligence | Working (synthetic-tested) | 62 seeded sources, scoring, alerts, outbound HMAC webhooks; inbound webhook is unauthenticated |
| Campaigns, drafts, approvals, SMTP/IMAP | Working with gates | `MAIL_SEND_ENABLED=false` by default |
| Email accounts (Gmail/Microsoft OAuth), conversations inbox | Credential-gated | Provider consent required; sync is a recent-message pull |
| Meetings (Teams/Meet), minutes, action items | Credential-gated, mocked tests | Artifacts local volume or S3 |
| Public booking | Working, Google-only event creation | No captcha/IP throttle; Outlook used for busy times only |
| Zoho CRM sync | Credential-gated, polling only | No webhooks, deletes not propagated |
| Products and product-scoped workflows | Working | Isolation is workflow-level inside one organization |
| CRM pipelines, opportunities, stages, forecasts | **Working (new)** | `app/crm/*`, migration `0021`, `/crm`; weighted forecast and stage history; territories and quotas still missing |
| Duplicate detection and merge, custom fields, saved views | **Working (new, partial UI)** | Duplicate detection + merge, custom-field definitions and saved views are implemented with endpoints; only the board UI is built, merge/field/view management is API-only |
| Meta Ads, Google Ads, LinkedIn Ads connectors | **Missing** | No code, no OAuth, no sync |
| Meta Lead Ads / Google lead-form ingestion | **Missing** | No webhook, no provider IDs |
| WhatsApp Business, SMS | **Missing** | No provider client or consent store |
| Shared omnichannel inbox beyond email | Partial | Email conversations exist; other channels absent |
| Landing pages, form builder, website widgets, UTM capture | **Missing** | No public capture endpoint |
| SEO audit, keyword data, backlinks, GA4, Search Console | **Missing** | Only company-website crawling for research exists |
| Marketing automation engine (triggers/actions/branches) | **Missing** | Only fixed Celery schedules |
| Quotes, proposals, contracts, e-signature, payments | **Missing** | No commercial models |
| Customer success: onboarding, health, renewals, NPS, support | **Missing** | No models |
| AI workspace, assistants, buying signals beyond market events | Partial | Bedrock drafting/classification/research exist; no unified workspace, no per-tenant AI usage ledger |
| Unified analytics for marketing/revenue | Partial | Per-area views exist; no cross-module revenue attribution |
| Integration framework (connect → sync → webhook → revoke) | Partial | Repeated per-provider code; no shared registry, retry policy or connection-state machine |
| Usage limits, subscriptions | **Working (new)** | See billing doc; only seats and email sends are enforced so far |
| SSO, advanced enterprise controls, integration marketplace | **Missing** | — |

## 4. Changes made in this milestone

Highest-priority foundation work, because the rest of the roadmap depends on it.

### 4.1 Billing and entitlements foundation

New `backend/app/billing/` package: plan catalogue as data, subscription lifecycle with trial and
period roll-over, monthly usage meters, limit checks, feature gates, audit rows on plan changes, and
`/billing/*` endpoints (also under `/api/billing`). Migration `0020_billing_foundation` adds
`billing_plans`, `billing_subscriptions`, `billing_usage_records`. Migration `0020_billing_foundation`
(itself superseded as head by `0021_crm_pipeline_and_opportunities`).

Enforcement wired into existing behaviour: seat limits on member invitations (`402`), email-send
metering after a provider-accepted send. Feature and limit dependency factories are ready for the next
modules.

### 4.2 Tenant isolation hardening

`backend/app/main.py` now resolves leads and import batches through `require_lead` / `require_batch`
with the tenant context, and list endpoints use `tenant_scope_clause`:

- `GET /leads/{id}/profile`, `PUT /leads/{id}/domain`, Apollo search/results/enrich,
  `GET/POST /leads/{id}/contacts`, `PUT/DELETE /leads/{id}/contacts/{contact_id}`
- `GET /batches/{id}`, `/batches/{id}/preview`, `POST /batches/{id}/start`, `/batches/{id}/retry`

A record owned by another organization now returns `404` instead of leaking data. Legacy rows with a
NULL organization stay reachable only through the anonymous fallback used by the single-tenant pilot.

### 4.3 Frontend

`/settings/billing` (client page) shows plan, status, trial/period dates, usage with progress bars, the
catalogue and role-gated plan actions. Added to the sidebar as **Billing & Plan**.

### 4.4 Files touched

| Path | Change |
| --- | --- |
| `backend/app/billing/{__init__,models,plans,service,schemas,dependencies,routes}.py` | New billing module |
| `backend/migrations/versions/0020_billing_foundation.py` | New migration |
| `backend/app/models.py` | Registers billing models for metadata/create-all |
| `backend/app/main.py` | Billing router mount; tenant-aware lead/batch helpers and endpoints |
| `backend/app/auth/organizations.py` | Seat-limit check on invitations |
| `backend/app/email_sender.py` | Email-send usage metering |
| `backend/app/config.py` | `BILLING_*` settings |
| `backend/tests/test_billing_foundation.py` | New tests (not executed in this environment) |
| `frontend/app/settings/billing/page.tsx`, `frontend/components/app-shell.tsx` | Billing screen and nav |
| `docs/billing-and-subscriptions.md`, `docs/saas-platform-audit.md`, `README.md`, `docs/session-context.md` | Documentation |

### 4.5 New endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/billing/plans`, `/api/billing/plans` | Plan catalogue |
| GET | `/billing/subscription` | Subscription + entitlements + usage |
| GET | `/billing/usage` | Limits, usage, remaining |
| POST | `/billing/subscription/change` | admin/owner, audited |
| POST | `/billing/subscription/cancel` | owner, cancels at period end |
| POST | `/billing/subscription/resume` | owner |

### 4.6 Tests written (not run)

`backend/tests/test_billing_foundation.py` covers catalogue and default subscription state, role-gated
and audited plan change, seat-limit `402`, usage metering plus snapshot, cancel/resume, and cross-tenant
`404` for lead profile, domain update, contacts and batch reads. These are unverified until the shell can
run `cd backend && PYTHONPATH=. python -m pytest -q`.

### 4.7 CRM core (milestone 2)

New `backend/app/crm/` package with organization-scoped pipelines, ordered stages (probability plus
won/lost flags), opportunities tied to the existing shared `Lead` and `Contact`, append-only stage history,
a shared activity timeline, CRM tasks, custom-field definitions and saved views. Leads gained additive
lifecycle columns (owner, lifecycle stage, qualification, score, source, custom fields, merge target) and a
deterministic, explainable score. Duplicate detection and merge move contacts, opportunities, tasks and
activities to the surviving company and keep the source as `merged`.

API: `/crm/*` (also `/api/crm`), mounted in `main.py`. Reporting: `/crm/summary` and
`/crm/pipeline-summary` provide pipeline value, probability-weighted forecast, won/lost, win rate, cycle
time, task counts and a needs-attention list. Migration `0021_crm_pipeline_and_opportunities` is the new
head. UI: `/crm` board with pipeline selector, metric tiles, stage moves, Won/Lost actions, tasks and the
attention panel; sidebar entry **Sales pipeline**.

Tests written: `backend/tests/test_crm_pipeline.py` (not executed in this environment).

## 5. Prioritised roadmap

Ordered so that each release is sellable and each depends only on what precedes it.

**Release 1 — foundation (in progress).** Done: auth, organizations, roles, invitations, audit rows,
encrypted provider credentials, plan catalogue, subscriptions, usage meters, tenant isolation for leads
and batches. Remaining before customers: payment-provider integration with webhooks, API rate limiting,
audit coverage for destructive actions, remove the anonymous fallback in production, rotate
`JWT_SECRET_KEY`, email-verification delivery, and a backup/restore runbook.

**Release 2 — complete CRM (core delivered).** Shipped: pipelines and stages per organization, opportunities
with value/close date/owner/source, activity timeline, tasks, lead lifecycle/ownership/qualification, lead
scoring, duplicate detection with merge, custom-field definitions, saved views, stage history, weighted
forecast and executive summary. Remaining: territories, quotas, merge/custom-field/saved-view UI, account
hierarchy and bulk operations.

**Release 3 — lead acquisition (core delivered).** Shipped: shared connector framework for Meta Ads and
Google Ads (read-only), organization-scoped encrypted credentials with a has-credentials flag instead of
token exposure, campaign mirroring with per-day metrics, Meta Lead Ads delivery verified by
`X-Hub-Signature-256` plus verify-token handshake, Google lead-form delivery verified by a shared key,
idempotent submissions and webhook receipts, website capture forms with consent and honeypot, UTM and
landing-page attribution, and campaign → qualified lead → opportunity → won-revenue reporting with an
explicit correlation caveat. Remaining: provider OAuth app flows, ad set/ad/keyword reporting, campaign
mutation behind approval and spend safeguards, LinkedIn/Microsoft/TikTok/Amazon connectors, provider-side
token revocation, CAPTCHA/IP rate limiting, and the landing-page builder (Release 6).

**Release 4 — communication.** WhatsApp Business (approved templates, consent, conversation windows), an
SMS provider abstraction, shared inbox with assignment, response-time metrics, suppression and templates.

**Release 5 — marketing automation.** Trigger/condition/delay/branch engine with approvals, communication
limits, execution history and versioning, replacing ad-hoc Celery jobs.

**Release 6 — website and SEO.** Landing pages from templates, forms and widgets with consent and spam
controls, website audit, GA4 and Search Console.

**Release 7 — commercial management.** Product catalogue, quotes/proposals with versions and PDF,
approval rules, contracts with expiry reminders, e-signature and payment links through providers.

**Release 8 — customer success.** Onboarding plans, support tickets, renewals, health indicators from
available data only, NPS, expansion opportunities.

**Release 9 — advanced intelligence.** AI workspace with per-tenant usage and citations, buying signals,
competitor monitoring, revenue intelligence and attribution with explicit attribution windows.

**Release 10 — enterprise.** SSO, granular permissions, retention/export controls, integration
marketplace, advanced audit.

## 6. Requirements needing external input

| Need | Why it is blocked |
| --- | --- |
| Meta app review + Business verification | Ads and Lead Ads APIs, webhook subscriptions |
| Google Ads developer token + OAuth verification | Reporting API |
| WhatsApp Business Account + template approval | Messaging policy compliance |
| SMS provider account and sender identity | Delivery and consent rules |
| Payment provider account (India + international) | Subscriptions, invoices, webhooks |
| AWS Bedrock model access | Research, drafting, classification |
| Apollo API plan | Contact discovery and enrichment |
| Google/Microsoft tenant consent | Mailbox, calendar, Meet/Teams |

## 7. Known limitations after this milestone

- No payment provider: plan changes are entitlement-only, no invoices, proration or dunning.
- Only seat and email-send meters are enforced/recorded; other catalogue meters are reported as zero.
- Audit coverage remains sparse outside auth, email and billing.
- Legacy NULL-organization rows stay visible to the anonymous fallback context; a production deployment
  must set `AUTH_ALLOW_ANONYMOUS_FALLBACK=false` and backfill `organization_id`.
- Roles are the five existing ones, not the nine role names in the platform brief, and permissions are
  role-level rather than per-object.
- Not verified in this environment: backend tests, frontend typecheck/build, any rendered screen, and any
  live provider call.

## 8. Next recommended milestone

Release 4 (omnichannel communication): a shared conversation model with assignment and a unified inbox,
per-user mailbox OAuth for Gmail/Microsoft (the existing Microsoft integration only covers calendar
availability), WhatsApp Business templates and consent records, a configurable SMS provider, and reply
routing — reusing the advertising module's consent, suppression and webhook-idempotency patterns. In
parallel, keep closing the Release 1 commercial gaps (payment provider with signed webhooks, API rate
limiting, remove the anonymous fallback in production) and the CRM/advertising UI gaps listed above.
