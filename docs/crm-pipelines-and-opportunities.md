# Sales CRM: pipelines, opportunities, tasks and scoring

Status: core implemented on 24 November 2026 (backend, migration, API, board UI, tests written).
Backend tests and the frontend build were **not executed** in this environment (the local shell cannot
fork child processes), so treat the verification section as pending until you run them.

## Why this exists

The repository had a prospecting product with leads, contacts, campaigns and emails, but no sales
pipeline: no opportunity object, no stages, no ownership, no activity timeline and no way to answer
"what is open and what is it worth". Everything already attached to a company (research, outreach,
meetings, booking) needed one place to convert into revenue.

This module adds that layer on top of the shared `Lead`/`Contact` records instead of introducing a
second customer model.

## Data model

All tables are organization-scoped (`organization_id` FK to `organizations`, `ON DELETE CASCADE`).

| Table | Purpose |
| --- | --- |
| `crm_pipelines` | Named pipeline per organization, unique per organization, one `is_default` |
| `crm_pipeline_stages` | Ordered stages with `probability` (0-100) and terminal `is_won` / `is_lost` flags |
| `crm_opportunities` | `lead_id`, optional `contact_id`, amount in minor units, currency, expected close date, status `open/won/lost`, owner, source, `custom_fields`, lost reason/timestamps |
| `crm_opportunity_stage_events` | Append-only stage history (from → to stage and status, note, actor) |
| `crm_activities` | Shared timeline: note, call, email, meeting, task, system; linked to lead/contact/opportunity |
| `crm_tasks` | General sales tasks with owner, priority, due date and completion timestamp (separate from the reply-linked `SalesTask`) |
| `crm_custom_fields` | Organization-defined field definitions (`text/number/date/boolean/select`) for leads or opportunities |
| `crm_saved_views` | Stored filters per user or shared, for leads/opportunities/tasks |

`leads` gained additive columns: `owner_id`, `lifecycle_stage` (`lead/qualified/opportunity/customer/merged`),
`qualification_status` (`unqualified/qualified/disqualified`), `score`, `source`, `source_detail`,
`custom_fields`, `merged_into_id`.

Migration: `0021_crm_pipeline_and_opportunities` (revises `0020_billing_foundation`), additive only;
existing leads default to `lifecycle_stage='lead'` and `score=0`.

## Default pipeline

`ensure_default_pipeline` creates one pipeline with seven stages on first CRM access:

| Stage | Probability | Terminal |
| --- | --- | --- |
| New | 10% | |
| Qualified | 25% | |
| Meeting | 45% | |
| Proposal | 65% | |
| Negotiation | 80% | |
| Won | 100% | won |
| Lost | 0% | lost |

Pipelines and stages are editable per organization; no stage name is hardcoded in business logic.

## API

Mounted at `/crm` and `/api/crm`. Reads require a valid tenant context; writes require `rep` or above;
structural changes (pipelines, stages, custom fields, merge, ownership reassignment) require `manager`
or above. A `read_only` member receives `403`.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/crm/pipelines` | Pipelines with ordered stages; creates the default on first call |
| POST | `/crm/pipelines` | `manager`; unique name per organization; seeds default stages |
| PATCH | `/crm/pipelines/{id}` | `manager`; rename, describe, archive |
| POST | `/crm/pipelines/{id}/stages` | `manager`; unique name, probability 0-100 |
| PATCH | `/crm/stages/{id}` | `manager`; won and lost are mutually exclusive |
| DELETE | `/crm/stages/{id}` | `manager`; `409` while opportunities reference it or fewer than two stages remain |
| GET | `/crm/opportunities` | Filters: `pipeline_id`, `stage_id`, `status`, `owner_id`, `lead_id`, `q` |
| POST | `/crm/opportunities` | `rep`; requires a lead in this organization and a valid pipeline/stage/owner/contact |
| GET | `/crm/opportunities/{id}` | Detail plus stage history |
| PATCH | `/crm/opportunities/{id}` | `rep`; name, amount, close date, owner, contact, source, custom fields |
| POST | `/crm/opportunities/{id}/stage` | `rep`; writes a stage event and a timeline activity |
| POST | `/crm/opportunities/{id}/close` | `rep`; `won` or `lost` (lost requires a reason); `409` if already closed |
| GET | `/crm/summary` | Executive summary: leads, pipeline metrics, tasks, activity count, needs attention |
| GET | `/crm/pipeline-summary` | Metrics for one pipeline (defaults to the default pipeline) |
| GET/POST | `/crm/tasks` | Open/overdue filters; `rep` to create |
| PATCH | `/crm/tasks/{id}` | Status, priority, due date, owner |
| POST | `/crm/tasks/{id}/complete` | Marks done and appends a timeline activity |
| GET/POST | `/crm/activities` | Timeline entries; must link to lead, contact or opportunity |
| GET | `/crm/leads` | CRM lead list with search, qualification, lifecycle, owner |
| PATCH | `/crm/leads/{id}` | Lifecycle, qualification, source, custom fields, score refresh; ownership needs `manager` |
| POST | `/crm/leads/{id}/score` | Recompute the deterministic score, returns factors |
| GET | `/crm/leads/{id}/duplicates` | Same-organization candidates by domain, company name or email |
| POST | `/crm/leads/{id}/merge` | `manager`; moves contacts, opportunities, tasks and activities, marks the source `merged` |
| GET | `/crm/leads/{id}/timeline` | Lead + activities + opportunities + tasks |
| GET | `/crm/owners` | Active members for owner pickers |
| GET/POST | `/crm/custom-fields` | Definitions per entity; `manager` to create |
| PATCH/DELETE | `/crm/custom-fields/{id}` | `manager` |
| GET/POST | `/crm/views` | Saved filters; `rep` to create |
| DELETE | `/crm/views/{id}` | Owner or `manager` |

## Lead scoring

Deterministic and explainable — every factor is returned to the caller:

| Signal | Points |
| --- | --- |
| Company domain confirmed | +10 |
| Company email on record | +10 |
| Industry / location / revenue band / phone | +5 each |
| Saved active contacts | +5 each, capped at +20 |
| Any contact email captured | +10 |
| Key decision maker identified | +10 |

Capped at 100. No AI is used, and nothing is inferred that is not stored on the record.

## Duplicate detection and merge

Candidates are other non-merged leads in the same organization sharing a normalized domain, company key
or email, with the matched reasons returned. Merge moves:

- contacts (a contact that clashes on email/Apollo ID is deactivated instead of duplicated),
- opportunities, tasks and activities (re-pointed at the target),
- missing company fields (domain, email, industry, location, revenue, phone, key person) from the donor.

The source lead is kept with `merged_into_id` set and `lifecycle_stage='merged'`, and a `system` activity
records the merge. The API writes an audit row (`leads_merged`).

## Reporting

`pipeline_metrics` returns per-stage counts and values, open count/value, probability-weighted forecast,
won/lost counts and values, win rate and average days-to-won. `executive_summary` adds lead totals by
qualification/lifecycle, task counts, activities in the last 30 days and a "needs attention" list
(overdue tasks and qualified leads with no open opportunity).

Attribution caveat: these are CRM-reported values keyed to the opportunity and its source field. They do
not yet join advertising spend, so cost-per-lead or campaign-sourced revenue is not claimed.

## UI

`/crm` (sidebar: **Sales pipeline**):

- six metric tiles (open pipeline, weighted forecast, won, leads, cycle time, tasks),
- a stage-by-stage board with per-deal stage selector and Won/Lost actions,
- an opportunity form with a company picker from CRM leads,
- open tasks with quick completion and inline task creation,
- a "needs attention" panel.

Role awareness: read-only members see the board without write controls.

## Tests written (not executed)

`backend/tests/test_crm_pipeline.py` covers default pipeline creation, the full opportunity lifecycle with
stage history and summary metrics, lost-reason validation, cross-tenant `404`/empty-list isolation, stage
deletion guards, role gates, lead scoring, duplicate detection + merge (contacts/activities move, source
marked merged), and tasks/custom fields/saved views.

Run: `cd backend && PYTHONPATH=. python -m pytest tests/test_crm_pipeline.py -q`
and `alembic upgrade head` before exercising the UI.

## Known limitations

- No territories, quota assignment, forecast scenarios, account hierarchy or bulk operations.
- Merge, custom-field and saved-view management exist as endpoints only; the board does not edit them.
- Custom field values are stored in JSON but there is no per-field validation against the definition.
- Email/WhatsApp/call activity is not yet copied into `crm_activities`; only CRM-created events appear there.
- Legacy leads imported before multi-tenancy (NULL `organization_id`) stay invisible to authenticated
  tenants until a write claims them (creating an opportunity or task claims the record).
- No pagination beyond `limit`; no CSV export of opportunities.
