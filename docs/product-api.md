# Product API reference

All routes are served by the existing FastAPI application (`http://localhost:8000`). The interactive
schema is at `/docs`. The API is unauthenticated and loopback-only; product scoping is workflow
isolation, not authorization.

## Products

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/products?status=active` | List products, ordered by name |
| POST | `/products` | Create; `slug` is unique, lowercase, immutable afterwards |
| GET | `/products/{product_id}` | Read one |
| PUT | `/products/{product_id}` | Update name, description, context, value proposition, industries |
| PATCH | `/products/{product_id}/status` | `active` or `archived` |
| DELETE | `/products/{product_id}` | Always 405: archive instead |

`product_context`, `value_proposition` and `target_industries` are the inputs used by product
opportunity analysis and product templates.

## Product companies

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/products/{product_id}/leads` | Association plus embedded master-company fields and active contact count; filters `stage`, `priority`, `status` |
| POST | `/products/{product_id}/leads` | Associate an existing master company; 409 if already associated, 422 if the product is archived |
| PUT | `/products/{product_id}/leads/{lead_id}` | Update stage, priority, status, sales notes |
| DELETE | `/products/{product_id}/leads/{lead_id}` | Remove the association only; the master company and history remain |
| GET | `/products/{product_id}/contacts` | Active contacts of the product's companies, with company name |

Stages: `prospect`, `engaged`, `qualified`, `proposal`, `negotiation`, `won`, `lost`, `on_hold`.
Priorities: `high`, `medium`, `low`.

## Product import

| Method | Path | Notes |
| --- | --- | --- |
| POST | `/batches` | `.xlsx` upload; optional `product_id` form field. 404 unknown product, 422 archived product |
| GET | `/batches?product_id=...` | Filtered import history |
| GET | `/products/{product_id}/batches` | Product import history |
| POST | `/batches/{batch_id}/start` | Map selected worksheets and queue the import |
| POST | `/batches/{batch_id}/retry` | Retry only a failed batch |
| GET | `/batches/{batch_id}` | Status, counts and row report |

Existing companies are associated with the importing product instead of being duplicated. A company
already associated with that product is reported as a duplicate row.

## Product campaigns

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/products/{product_id}/campaigns` | Campaigns owned by the product |
| POST | `/products/{product_id}/campaigns` | Create a draft campaign |
| GET | `/campaigns?product_id=...` | Global listing filtered by product |
| POST | `/campaigns` | `product_id` optional but validated when supplied |
| POST | `/campaigns/{id}/enrollments` | Rejects companies not associated with the campaign's product (409) |
| POST | `/campaigns/{id}/enrollments/bulk` | Same rule, atomic: one invalid recipient rejects the batch |

Drafts, approval, suppression, inbox checks, reply stops, send budget and activation behaviour are
unchanged by product scoping.

## Product metrics

`GET /products/{product_id}/overview?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` returns:

- `associated_companies`, `active_contacts`, `campaigns_count`
- `messages_by_status`, `replies_count`, `meeting_tasks_open`
- `contacted_companies`, `contacted_company_percent` (null when there are no companies)
- `research_jobs`, `research_jobs_completed`, `research_jobs_active`, `research_jobs_failed`
- `pipeline` (current companies per stage)
- `date_range`, `metrics_note`

`GET /overview?start_date=...&end_date=...` returns consolidated totals:

- `unique_companies` (master companies), `product_associations`,
  `product_associated_companies`
- `unique_contacts`, `product_associated_contacts`
- `total_campaigns`, `total_messages`, `total_replies`, `products_count`
- `per_product[]` with `associated_companies`, `active_contacts`, `campaigns_count`

Dates filter campaigns, messages and replies. Company, contact and pipeline counts are current state.
Invalid dates return 422.

## Product research and meetings

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/products/{product_id}/research` | Research jobs for the product's companies |
| GET | `/products/{product_id}/sales-tasks` | Meeting-request tasks attributed through the campaign |
| POST | `/products/{product_id}/leads/{lead_id}/opportunity` | Bedrock opportunity analysis; always `draft` |
| GET | `/products/{product_id}/leads/{lead_id}/opportunity` | Latest opportunity |
| PATCH | `/products/{product_id}/leads/{lead_id}/opportunity/{opp_id}/status` | `draft`, `reviewed`, `approved` |
| GET | `/research/jobs/{job_id}/diff` | Added/changed/conflicting facts against the previous completed job |
| POST | `/research/facts/{fact_id}/override` | Append-only manual override with reason |
| GET | `/research/facts/{fact_id}/overrides` | Override history; original fact unchanged |

Existing research endpoints (`/intelligence/...`) remain company-scoped and are reused across
products.

## Templates

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/templates?product_id=global` | Global templates (`product_id IS NULL`) |
| GET | `/templates?product_id={product_id}` | Product templates |
| POST | `/templates` | Create; optional `product_id`, `parent_template_id` for an override |
| PUT | `/templates/{id}` | Content updates create a new version |
| PATCH | `/templates/{id}/status?is_active=` | Activate/deactivate |
| GET | `/templates/{id}/versions` | Immutable version history |
| POST | `/templates/{id}/preview` | Render with sample values |

Unknown `{{variables}}` are rejected with 422 and the offending names. A product override is a new
template owned by the product; it never mutates the global original.
