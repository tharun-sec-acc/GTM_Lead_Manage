# Multi-sheet Excel import

## Status and scope

The local import workflow reads all worksheets in `.xlsx` workbooks and lets sales choose which worksheets to import. Each selected worksheet has its own mapping and preview. It keeps existing batch and lead IDs intact and records worksheet name and original Excel row number in the import report.

This milestone detects duplicate company names and email addresses and reports them as `duplicate`; it does not merge companies, attach duplicate rows as contacts, or offer merge/skip/retain decisions after import. A person/contact worksheet mapped to the company field is still treated as company rows; contact management is a separate pending milestone. Do not treat this as a completed contact importer.

## User workflow

1. Upload or drag-and-drop an `.xlsx` workbook.
2. The upload preview lists worksheet names, non-empty row counts, column counts, headers and the first five non-empty rows.
3. Select one or more non-empty worksheets or select all non-empty sheets. Different column layouts may be mapped independently.
4. Map a company-name column for every selected worksheet. Other fields are optional; unmapped columns remain in the lead's `extra` object.
5. Start the import. The existing Celery worker processes the batch in one database transaction. Invalid rows are reported without blocking valid rows. Duplicate detection sees previously stored leads and leads already inserted earlier in the current workbook.
6. Review the consolidated row counts and row-level invalid/duplicate records. Each row includes worksheet name, original row number, status, message and original column values.

Supported mapped fields:

| Mapping | Storage |
| --- | --- |
| Company name | `leads.company_name` (required) |
| Company domain | `leads.domain` (validated hostname; do not include scheme or path) |
| Email | `leads.email` (validated; optional) |
| Revenue, contact number, remarks, key-person information | Existing lead fields |
| Designation, industry, location | Additional nullable lead columns |
| Any other source columns | `leads.extra`, keyed by original worksheet header |

Duplicate rows are never automatically merged. Detection normalizes company names and compares normalized emails. It does not prove that two different names or email addresses belong to distinct companies, and domain is not currently a duplicate key.

## API and implementation

- `POST /batches`: stores the workbook and returns per-sheet metadata and previews.
- `GET /batches/{batch_id}/preview`: returns the same worksheet-level preview for a draft.
- `POST /batches/{batch_id}/start`: accepts `{"mapping":{"Sheet name":{"company_name":"Company", ...}}}` for selected sheets.
- `GET /batches/{batch_id}`: returns sheet metadata, consolidated status counts and row-level report entries including `sheet_name`.
- `POST /batches/{batch_id}/retry`: retries a failed batch using its saved selection/mappings.

`backend/app/imports.py` uses openpyxl read-only mode. `workbook_rows()` remains as a compatibility adapter for the previous active-sheet parsing contract. A flat legacy field mapping on a previously created draft batch is applied to its original active worksheet; the new UI posts a per-sheet mapping object.

Migration `0006_multisheet_import` adds worksheet headers to batches, industry/designation/location to leads, and a worksheet name to import rows. It replaces the prior `(batch_id, row_number)` uniqueness rule with `(batch_id, sheet_name, row_number)`, preserving existing records under the empty worksheet-name default. It does not delete or rewrite historical lead IDs, campaigns or messages.

## Limits and failure behavior

- `.xlsx` only; `.xls` and CSV are not accepted by this endpoint.
- 10 MB compressed upload, 100 MB total uncompressed archive, at most 50 worksheets, 100 columns per worksheet and 5,000 non-empty data rows across the workbook.
- A sheet with no header/data is shown as empty and cannot be selected. A workbook with no worksheet containing a header is rejected.
- A worksheet with a header but no data can be selected and yields no row records.
- Corrupt workbooks and configured-size violations are rejected before creating a batch. Mapping errors leave the batch in draft.
- Valid and invalid rows are reported independently; a worker/database failure rolls back the import transaction and marks the batch failed through the existing task handler.
- Formula values use cached results, which may be blank. Excel numeric phone values may lose leading zeroes; store phone numbers as text.
- The 5,000-row cap is workbook-wide to bound import work. If the business needs higher volumes, raise it only with load testing and queue/resource review.

## Testing

`backend/tests/test_imports.py` covers per-sheet preview and mapping, different headers, empty sheets, duplicate records across worksheets, invalid rows, worksheet/row provenance, preservation of unmapped columns, selected sheets and existing single-sheet behavior. Tests use temporary SQLite and synthetic workbook data; they do not call Apollo or external services.

For local checks, run the backend test suite from `backend` and apply/check migrations against a disposable database before deploying. Do not use a production database for migration tests. Keep the application loopback-only and use synthetic or explicitly approved local test data.
