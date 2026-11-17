# Product migrations, deployment and rollback

## Migrations

Two additive revisions follow the research head `0010_company_intelligence`:

| Revision | Down revision | Contents |
| --- | --- | --- |
| `0011_products` | `0010_company_intelligence` | Creates `products`, `product_leads` (unique `product_id` + `lead_id`), `product_opportunities`, `email_templates`, `email_template_versions`, `email_attachments`, `research_fact_overrides`; adds nullable `product_id` to `campaigns` and `batches` |
| `0012_product_attribution` | `0011_products` | Seeds four products with fixed IDs and backfills existing records |

Nothing is dropped, recreated or reset. Existing IDs, contacts, Apollo results, campaign/enrollment/
message/reply/tracking history, research graphs, OAuth rows, suppressions and approvals are untouched.

### Deterministic seed and backfill

`0012_product_attribution` inserts:

- `General / Unassigned` — `00000000-0000-0000-0000-000000000001`
- `Vehicle Digital Inspection` — `...0002`
- `Loss Tracker` — `...0003`
- `Aftermarket Super App` — `...0004`

Every existing `leads` row gets a `product_leads` association to General / Unassigned, and every
`campaigns`/`batches` row with a null `product_id` is attributed to the same product. Product
ownership is never inferred from company name, industry or campaign content.

The `downgrade()` removes the seeded associations and columns. Do not run it against a database that
has real product assignments.

## Before applying to the local database

1. Confirm Docker Desktop and the Compose services are running (`docker compose ps`).
2. Read the current revision:
   `docker compose exec api alembic current`
3. Create a timestamped PostgreSQL backup and verify it is readable:
   `docker compose exec -T db pg_dump -U <user> -Fc <database> > gtm-before-products-YYYYMMDD.dump`
   `pg_restore --list gtm-before-products-YYYYMMDD.dump`
4. Review both migrations. They are additive and must not drop business records.
5. Capture before counts for leads, contacts, campaigns, enrollments, messages, replies, research
   jobs and OAuth rows.
6. Testing on a disposable database first is recommended:
   `..\\.venv\\Scripts\\python.exe -m pytest -q` (temporary SQLite databases).

## Applying

The API container runs `alembic upgrade head` on start, so a normal rebuild applies the migrations:

```powershell
docker compose up --build -d
docker compose exec api alembic current
```

Verify after the upgrade:

- `alembic current` reports `0012_product_attribution`.
- `GET /health` returns 200.
- `GET /products` returns the four seeded products.
- Lead/contact/campaign/message/reply/research counts match the pre-upgrade capture.
- A synthetic product import associates an existing company instead of duplicating it.
- `GET /overview` returns non-null totals without double-counting companies.

For drift checking against a disposable database, run `alembic check` there — not against the
operator's live database during normal operation.

## Rollback

Application rollback is preferred; keep the additive schema.

1. Stop the affected containers.
2. Redeploy the previous application image. The new tables and nullable columns remain in place and
   are ignored by older code.
3. Do not run `alembic downgrade` on the operator's database: it deletes product assignments,
   templates and override history.
4. A backup restore is a separate, approved maintenance action. Never delete Docker volumes or run
   destructive reset commands.

## Environment and safety

- No new environment variables are required for products, imports, campaigns, templates or metrics.
- Research remains opt-in (`COMPANY_INTELLIGENCE_ENABLED`) and keeps its existing budgets.
- Sending remains governed by `MAIL_SEND_ENABLED`, approval, suppression, inbox and budget gates.
  Product scoping does not change any sending rule.
- Attachment storage uses the private local volume adapter (`/app/attachments`); no S3 backend and
  no public URL is exposed.
- The application stays unauthenticated and loopback-only. Do not publish the ports.
