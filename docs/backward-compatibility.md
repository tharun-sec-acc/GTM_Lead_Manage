# Backward compatibility and migrations

## Compatibility principles

- Existing lead IDs, campaign IDs, enrollment/message IDs and relationships are retained.
- Schema changes are additive or nullable where prior records lack the new value.
- Do not delete/recreate application data to upgrade the schema.
- Existing campaign and mail APIs remain available.
- The previous flat, active-sheet import mapping is accepted for legacy draft batches.
- Historical import rows receive an empty `sheet_name` when upgraded; new reports display this as a legacy worksheet.

## Migrations

Apply migrations from `backend` using `alembic upgrade head`; Compose does this before starting the API. Current additions:

- `0005_google_booking_scope`: records whether an OAuth state request explicitly asks for Calendar event access.
- `0006_multisheet_import`: adds worksheet metadata, import provenance, the composite `(batch_id, sheet_name, row_number)` uniqueness rule, and nullable company industry/designation/location fields.
- `0007_apollo_contact_management`: allows a nullable Apollo ID for manual contacts, adds contact profile/soft-removal fields, and adds normalized Apollo search snapshots.
- `0008_enrollment_contact_link`: adds a nullable contact foreign key to campaign enrollments; existing recipient histories remain unassociated.

Before upgrading an existing deployment, take an approved database backup and test the upgrade on a copy. The migrations do not intentionally drop business records. Do not point migration tests at a production database.

## Compatibility validation performed

Automated tests run on temporary SQLite databases. The multi-sheet migration was also applied after seeding a pre-migration lead, batch and import row; the original row data remained and `sheet_name` received its compatibility default. Apollo/contact migration validation seeded a contact using the old columns and verified its ID/data were retained and new fields received safe defaults. A fresh-database Alembic `check` should report no model drift.

Migration `0008_enrollment_contact_link` was applied to a fresh temporary SQLite database, followed by Alembic's schema-drift check. SQLite tests are useful for migration logic but do not replace a PostgreSQL backup/restore rehearsal and schema upgrade test before deployment.
