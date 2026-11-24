# Billing, plans and usage entitlement

Status: foundation implemented on 24 November 2026 (backend, API, settings screen, tests written).
No payment provider is connected yet: plan changes record entitlements only and take no money.

## Why this exists

The SaaS foundation already had organizations, roles, invitations and an audit log, but the
`organizations.plan` column was a free-text label with no catalogue, no subscription record and no
usage metering. Plan limits could not be configured, reported or enforced.

This module adds the missing half of the foundation:

- a **plan catalogue stored as data** (pricing and limits are rows, not constants),
- one **subscription per organization** with trial/period state,
- **usage meters per organization, metric and month**,
- **entitlement checks** that other modules can depend on,
- an **API and settings screen** for the organization to read and change its plan.

## Data model

| Table | Purpose |
| --- | --- |
| `billing_plans` | Catalogue row: `code`, `name`, `price_cents` (`NULL` = custom pricing), `currency`, `billing_interval`, `trial_days`, `is_public`, `is_active`, `sort_order`, `limits` (JSON), `features` (JSON) |
| `billing_subscriptions` | One row per organization (`uq_subscription_org`): `plan_id`, `status`, `seats`, `trial_ends_at`, `current_period_start`, `current_period_end`, `cancel_at_period_end`, `canceled_at`, plus optional provider columns |
| `billing_usage_records` | `organization_id` + `metric` + `period_start` (unique): `quantity` for the current month |

`limits` maps a metric name to an integer allowance. An explicit `null` means unlimited; a metric
that is absent from `limits` is treated as unlimited and is not reported.

`features` is a list of capability keys used by `require_feature(...)`, e.g. `crm`,
`company_intelligence`, `market_intelligence`, `zoho_sync`, `api_access`.

Migration: `0020_billing_foundation` (revises `0019_saas_multi_tenant_auth`) creates the three tables.
The catalogue itself is **seeded on first use** by `app.billing.service.seed_default_plans`, so pricing
stays editable data rather than a migration constant.

## Default catalogue

| Code | Price | Seats | Leads | Emails / month | Research runs / month |
| --- | --- | --- | --- | --- | --- |
| `free` | ₹0 | 3 | 250 | 250 | 10 |
| `starter` | ₹2,999 / month | 5 | 5,000 | 5,000 | 100 |
| `growth` | ₹7,999 / month | 15 | 25,000 | 20,000 | 500 |
| `business` | ₹19,999 / month | 40 | 100,000 | 75,000 | 2,000 |
| `enterprise` | custom | unlimited | unlimited | unlimited | unlimited |

Paid plans carry a 14-day trial (`enterprise` 30). These are example prices for an India-first launch;
change the rows or `DEFAULT_PLANS` to re-price.

### Legacy plan labels

Organizations created before this module stored `organizations.plan` as `pro`, `free` or `enterprise`.
`LEGACY_PLAN_ALIASES` maps `pro` → `growth`, `premium` → `business`, `trial` → `growth`. When a
subscription is first created:

- a **newly created** organization on a plan with `trial_days` starts in `trialing` with
  `trial_ends_at = created_at + trial_days`;
- an **older** organization resolves to `active`, so no retroactive trial is granted;
- `organizations.plan` is kept in sync whenever the plan is changed.

## API

Mounted at `/billing` and `/api/billing`.

| Method and path | Role | Behaviour |
| --- | --- | --- |
| `GET /billing/plans` | any member | Public, active catalogue rows in display order |
| `GET /billing/subscription` | any member | Subscription state, active plan, features, limits, usage, remaining |
| `GET /billing/usage` | any member | Plan code with limits, usage and remaining for the current period |
| `POST /billing/subscription/change` | `admin` or `owner` | Switch to another active plan; writes a `billing_plan_changed` audit row |
| `POST /billing/subscription/cancel` | `owner` | Cancels at period end; access continues until `current_period_end` |
| `POST /billing/subscription/resume` | `owner` | Clears the pending cancellation (or reactivates a canceled subscription) |

There is no checkout or webhook endpoint yet. Switching plans records the entitlement change without
taking payment, and the UI says so. Attach a payment provider by filling the `provider`,
`provider_customer_id` and `provider_subscription_id` columns from its webhook.

## Enforcement

`app.billing.service` provides the primitives:

- `get_or_create_subscription`, `refresh_subscription` (expired trial → `active`, period roll-over,
  deferred cancellation),
- `effective_plan`, `usage_snapshot`, `current_usage`, `get_limit`,
- `check_limit(...)` raising `LimitExceeded`, `record_usage(...)`,
- `change_plan`, `cancel_subscription`, `resume_subscription`.

Wired into existing behaviour:

| Metric | Where it is checked or metered |
| --- | --- |
| `seats` | `POST /organizations/members/invite` → `402 Payment Required` when active members plus pending invitations reach the plan seat count |
| `email_sends_monthly` | `app/email_sender.py` records one unit after a provider-accepted send (never blocks an email that already left) |

FastAPI dependency factories are available for new endpoints:

```python
from app.billing.dependencies import require_feature, require_within_limit

@router.post("/campaigns", dependencies=[Depends(require_feature("email_outreach"))])
def create_campaign(...): ...

@router.post("/enrich", dependencies=[Depends(require_within_limit("enrichment_credits_monthly"))])
def enrich(...): ...
```

`require_feature` returns `403` naming the required capability; `require_within_limit` returns `402`
with the used and allowed amount.

## Kill switch

`BILLING_ENFORCE_LIMITS=false` makes `check_limit` a no-op while usage keeps being recorded and
reported. `BILLING_DEFAULT_PLAN_CODE` (default `growth`) is the fallback when an organization's stored
label cannot be resolved. `BILLING_CURRENCY` documents the expected catalogue currency (default `INR`).

## Settings screen

`/settings/billing` shows the active plan and status, trial and period dates, a usage grid with
progress bars, and the catalogue. Plan switching, cancellation and resuming require `admin`/`owner`;
other roles see read-only state. The page is linked from the sidebar as **Billing & Plan**.

## Known limitations

- No payment provider, invoices, tax handling, dunning or proration. `change_plan` is immediate with no
  credit or charge calculation.
- No usage reset task: a meter is scoped to a calendar month key, so a new month starts at zero without
  a scheduled job.
- Only `seats` and `email_sends_monthly` are enforced or recorded today. Lead, research, campaign,
  account and integration meters exist in the catalogue and are reported, but their write paths are not
  yet gated.
- Plan capping of existing over-limit organizations is not retroactive: lowering a plan does not delete
  data, it only blocks new actions that are actually checked.
